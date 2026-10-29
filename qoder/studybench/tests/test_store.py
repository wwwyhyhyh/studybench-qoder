"""store.py 单测：DDL 幂等 / 幂等写入 / 只读守卫 / query_log / 召回（契约 §3）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from studybench.store import Store, StoreError, escape_sql, open_db


def _doc(path: str, title: str = "标题") -> dict:
    return {
        "doc_id": "d00000001",
        "path": path,
        "title": title,
        "course": "课程",
        "kind": "类型",
        "mtime": "2026-10-26",
        "sha256": "a" * 64,
    }


def _chunk(doc_id: str, seq: int, heading: str, text: str, terms: dict[str, int]) -> dict:
    from studybench.ingest import chunk_terms, searchable_text

    return {
        "chunk_id": f"{doc_id}#c{seq:02d}",
        "doc_id": doc_id,
        "seq": seq,
        "heading": heading,
        "line_start": 1,
        "line_end": 3,
        "text": text,
        "n_chars": len(text),
        "searchable_text": searchable_text(heading, text),
        "terms": terms if terms is not None else chunk_terms(heading, text),
    }


def test_ensure_schema_idempotent(tmp_path: Path) -> None:
    with Store(str(tmp_path / "sb.db")) as store:
        store.ensure_schema()
        store.ensure_schema()  # 重复执行不报错（IF NOT EXISTS）
        assert store.stats()["docs"] == 0


def test_require_schema_guard_without_ddl(tmp_path: Path) -> None:
    db = str(tmp_path / "sb.db")
    store = open_db(db)
    try:
        with pytest.raises(StoreError, match="ingest"):
            store.require_schema()  # 只读路径不做 DDL，直接给可操作错误
    finally:
        store.close()
    with Store(db) as writer:
        writer.ensure_schema()
    with open_db(db) as reader:
        reader.require_schema()  # 建表后通过


def test_upsert_document_and_replace(tmp_path: Path) -> None:
    db = str(tmp_path / "sb.db")
    with Store(db) as store:
        store.ensure_schema()
        store.upsert_document(_doc("a.md"), [_chunk("d00000001", 0, "甲", "seekdb 引擎", {"甲": 1, "seekdb": 1})])
        assert store.stats()["docs"] == 1
        assert store.stats()["chunks"] == 1
        assert {row[1] for row in store.iter_term_rows()} == {"甲", "seekdb"}

        # 同 path 重写：title 更新、旧块与旧词项整体替换。
        store.upsert_document(_doc("a.md", title="新标题"), [_chunk("d00000001", 0, "乙", "全新内容", {"乙": 2, "全新": 1})])
        assert store.stats()["docs"] == 1
        assert store.stats()["chunks"] == 1
        docs = store.iter_docs()
        assert docs[0]["title"] == "新标题"
        assert {row[1] for row in store.iter_term_rows()} == {"乙", "全新"}


def test_fulltext_and_coverage_recall(tmp_path: Path) -> None:
    """裁决·锚点1 修订：NGRAM 全文索引 + 自然语言模式（OR 召回）承担主路径。"""

    db = str(tmp_path / "sb.db")
    with Store(db) as store:
        store.ensure_schema()
        store.upsert_document(
            _doc("a.md"),
            [_chunk("d00000001", 0, "检索引擎", "seekdb 存储与召回", {"检索": 1, "引擎": 1, "seekdb": 1})],
        )
        second = _doc("b.md")
        second["doc_id"] = "d00000002"
        store.upsert_document(
            second,
            [_chunk("d00000002", 0, "哈夫曼树", "哈夫曼编码是前缀码", {"哈夫": 1, "夫曼": 1, "曼编": 1, "编码": 1, "前缀": 1})],
        )
        third = _doc("c.md")
        third["doc_id"] = "d00000003"
        store.upsert_document(
            third,
            [_chunk("d00000003", 0, "孤词", "哈夫单独出现", {"哈夫": 1, "单独": 1})],
        )
        fourth = _doc("d.md")
        fourth["doc_id"] = "d00000004"
        store.upsert_document(
            fourth,
            [_chunk("d00000004", 0, "图算法", "kruskal 按边权排序求最小生成树", {"kruskal": 1, "边权": 1, "排序": 1})],
        )
        # 2 字符 CJK 词项走 NGRAM 自然模式召回。
        assert store.fulltext_recall(["检索"]) == ["d00000001#c00"]
        # 自然模式 OR：含任一查询词项的块都召回（只含「哈夫」的块也在内，不再排除）。
        assert set(store.fulltext_recall(["哈夫", "夫曼"])) == {"d00000002#c00", "d00000003#c00"}
        assert store.fulltext_recall(["不存在的词"]) == []
        assert store.fulltext_recall([]) == []
        # ≥3 字符 ASCII 查询同样走全文索引主路径（kruskal 实测可召回）。
        assert store.fulltext_recall(["kruskal"]) == ["d00000004#c00"]
        assert set(store.fulltext_recall(["kruskal", "检索"])) == {"d00000001#c00", "d00000004#c00"}
        # 覆盖召回：chunk_terms term IN (...)，仍是退路。
        assert set(store.term_coverage(["检索"])) == {"d00000001#c00"}
        assert set(store.term_coverage(["哈夫"])) == {"d00000002#c00", "d00000003#c00"}
        assert store.term_coverage(["没有"]) == []
        assert store.term_coverage([]) == []


def test_fulltext_index_recreated_as_ngram(tmp_path: Path) -> None:
    """旧库（SPACE 解析索引）经 ensure_schema 迁移为 NGRAM（裁决·锚点1）。"""

    db = str(tmp_path / "sb.db")
    with Store(db) as store:
        store.ensure_schema()
        store.upsert_document(
            _doc("a.md"),
            [_chunk("d00000001", 0, "检索引擎", "seekdb 存储与召回", {"检索": 1, "引擎": 1, "seekdb": 1})],
        )
        # 模拟旧索引：DROP 掉再按 SPACE 建（旧行为）。
        store.execute("DROP INDEX ft_chunks ON chunks")
        store.execute(
            "CREATE FULLTEXT INDEX ft_chunks ON chunks (searchable_text) WITH PARSER SPACE"
        )
        assert store.fulltext_recall(["检索"]) == []  # SPACE 下 2 字词项不可召回
    with Store(db) as store:
        store.ensure_schema()  # 迁移：DROP + NGRAM 重建
        assert store.fulltext_recall(["检索"]) == ["d00000001#c00"]


def test_fetch_chunk_rows_join(tmp_path: Path) -> None:
    db = str(tmp_path / "sb.db")
    with Store(db) as store:
        store.ensure_schema()
        store.upsert_document(_doc("a.md"), [_chunk("d00000001", 0, "甲", "正文", {"甲": 1})])
        rows = store.fetch_chunk_rows(["d00000001#c00", "missing#c00"])
        assert len(rows) == 1
        row = rows[0]
        assert row["path"] == "a.md"
        assert row["course"] == "课程"
        assert row["kind"] == "类型"
        assert row["mtime"] == "2026-10-26"
        assert row["heading"] == "甲"
        assert store.fetch_chunk_rows([]) == []


def test_fetch_term_rows_df_and_tf(tmp_path: Path) -> None:
    db = str(tmp_path / "sb.db")
    with Store(db) as store:
        store.ensure_schema()
        store.upsert_document(_doc("a.md"), [_chunk("d00000001", 0, "甲", "共享词 独有词", {"共享词": 1, "独有词": 1, "甲": 1})])
        second = _doc("b.md")
        second["doc_id"] = "d00000002"
        store.upsert_document(second, [_chunk("d00000002", 0, "乙", "共享词 另一词", {"共享词": 3, "乙": 1})])
        rows = store.fetch_term_rows(["共享词", "独有词"])
        df: dict[str, set[str]] = {}
        tf: dict[tuple[str, str], int] = {}
        for term, chunk_id, value in rows:
            df.setdefault(term, set()).add(chunk_id)
            tf[(term, chunk_id)] = value
        assert len(df["共享词"]) == 2  # df 是全库统计，不只候选
        assert len(df["独有词"]) == 1
        assert tf[("共享词", "d00000002#c00")] == 3


def test_query_log_and_tail(tmp_path: Path) -> None:
    db = str(tmp_path / "sb.db")
    with Store(db) as store:
        store.ensure_schema()
        store.log_query("2026-10-30T00:00:01+08:00", "第一查", "d1#c00", 2, 5)
        store.log_query("2026-10-30T00:00:02+08:00", "第二查", None, 0, 1)
        store.log_query("2026-10-30T00:00:03+08:00", "第三查", "d2#c01", 3, 7)
        rows = store.query_log_tail(2)
        assert [row["qid"] for row in rows] == [3, 2]  # 最近在前
        assert rows[0]["top_chunk"] == "d2#c01"
        assert rows[1]["top_chunk"] is None
        assert store.query_log_tail(10)[0]["q"] == "第三查"


def test_stats_and_reset(tmp_path: Path) -> None:
    db = str(tmp_path / "sb.db")
    with Store(db) as store:
        store.ensure_schema()
        store.upsert_document(_doc("a.md"), [_chunk("d00000001", 0, "甲", "12345", {"甲": 1})])
        stats = store.stats()
        assert stats["docs"] == 1 and stats["chunks"] == 1
        assert stats["terms"] == 1 and stats["avg_len"] == 5.0
        store.log_query("t", "q", None, 0, 0)
        store.reset()
        assert store.stats() == {"docs": 0, "chunks": 0, "terms": 0, "avg_len": 0.0}
        assert store.one("SELECT COUNT(*) FROM query_log") == (0,)


def test_escape_sql() -> None:
    assert escape_sql(None) == "NULL"
    assert escape_sql(7) == "7"
    assert escape_sql("it's") == "'it\\'s'"
    assert escape_sql("反\\斜") == "'反\\\\斜'"
