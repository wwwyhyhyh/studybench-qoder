"""ingest.py 单测：切块 / 行号 / 幂等重导 / 元数据 / --reset（契约 §3）。"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from studybench import ingest
from studybench.store import Store, escape_sql

MINI = Path(__file__).parent / "fixtures" / "mini"


def _write_md(root: Path, rel: str, content: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_parse_markdown_sections_and_line_numbers() -> None:
    md = (
        "# 标题\n"
        "\n"
        "引言一段。\n"
        "\n"
        "## 甲\n"
        "\n"
        "甲正文。\n"
        "第二行。\n"
        "\n"
        "## 乙\n"
        "乙正文。\n"
    )
    title, sections = ingest.parse_markdown(md, "fallback")
    assert title == "标题"
    assert [section["heading"] for section in sections] == ["标题", "甲", "乙"]
    preamble, first, second = sections
    assert preamble["text"] == "引言一段。"
    assert (preamble["line_start"], preamble["line_end"]) == (1, 3)
    assert first["text"] == "甲正文。\n第二行。"
    assert (first["line_start"], first["line_end"]) == (5, 8)
    assert second["text"] == "乙正文。"
    assert (second["line_start"], second["line_end"]) == (10, 11)


def test_parse_markdown_h3_stays_in_section() -> None:
    md = "# T\n\n## 甲\n\n正文。\n### 深层\n更深。\n"
    _, sections = ingest.parse_markdown(md, "f")
    assert len(sections) == 1
    assert sections[0]["text"] == "正文。\n### 深层\n更深。"


def test_ingest_mini_corpus_counts(tmp_path: Path) -> None:
    db = str(tmp_path / "sb.db")
    first = ingest.ingest_directory(str(MINI), db)
    # 三篇小文，每篇 1 引言 + 2 小节 = 3 块。
    assert first["docs"] == 3
    assert first["chunks"] == 9
    second = ingest.ingest_directory(str(MINI), db)
    assert second["docs"] == 3 and second["chunks"] == 9  # 幂等重导

    with Store(db) as store:
        docs = store.iter_docs()
        chunks = store.iter_chunks()
        assert len(docs) == 3 and len(chunks) == 9
        ids = [chunk["chunk_id"] for chunk in chunks]
        assert len(set(ids)) == 9  # chunk_id 稳定不重复
        for chunk in chunks:
            assert chunk["n_chars"] == len(chunk["text"])
            assert chunk["chunk_id"] == f"{chunk['doc_id']}#c{chunk['seq']:02d}"


def test_searchable_text_is_natural_text(tmp_path: Path) -> None:
    """裁决·锚点1：searchable_text 存自然文本 heading + 换行 + text，供 NGRAM 索引。"""

    db = str(tmp_path / "sb.db")
    ingest.ingest_directory(str(MINI), db)
    with Store(db) as store:
        for chunk in store.iter_chunks():
            found = store.execute(
                "SELECT searchable_text FROM chunks WHERE chunk_id = "
                + escape_sql(chunk["chunk_id"])
            )
            assert str(found[0][0]) == chunk["heading"] + "\n" + _text_of(store, chunk["chunk_id"])


def _text_of(store: Store, chunk_id: str) -> str:
    row = store.execute(
        "SELECT text FROM chunks WHERE chunk_id = " + escape_sql(chunk_id)
    )
    return str(row[0][0])


def test_doc_metadata_derivation(tmp_path: Path) -> None:
    db = str(tmp_path / "sb.db")
    ingest.ingest_directory(str(MINI), db)
    with Store(db) as store:
        by_path = {doc["path"]: doc for doc in store.iter_docs()}
    rel = "数据结构/树与二叉树.md"
    assert rel in by_path
    doc = by_path[rel]
    expected_id = "d" + hashlib.sha1(rel.encode("utf-8")).hexdigest()[:8]
    assert doc["doc_id"] == expected_id  # 契约 §3：d<sha1(path)[:8]>
    assert doc["title"] == "树与二叉树"
    assert doc["course"] == "数据结构"  # 首层目录名
    assert doc["kind"] == ""
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", doc["mtime"])
    assert re.fullmatch(r"[0-9a-f]{64}", doc["sha256"])


def test_reingest_replaces_old_terms(tmp_path: Path) -> None:
    src = tmp_path / "src"
    db = str(tmp_path / "sb.db")
    _write_md(src, "a.md", "# A\n\n## 甲\n\n甲乙 丙丁\n")
    ingest.ingest_directory(str(src), db)
    with Store(db) as store:
        before = {row[1] for row in store.iter_term_rows()}
    assert {"甲乙", "丙丁", "甲"} <= before

    _write_md(src, "a.md", "# A\n\n## 乙\n\n戊己 庚辛\n")
    ingest.ingest_directory(str(src), db)
    with Store(db) as store:
        after = {row[1] for row in store.iter_term_rows()}
        assert before & after == set()  # 旧词项已按 path 删除（幂等）
        assert store.stats()["docs"] == 1


def test_flags_override_front_matter_and_path(tmp_path: Path) -> None:
    src = tmp_path / "src"
    db = str(tmp_path / "sb.db")
    _write_md(src, "x/y.md", "---\ncourse: 概率论\nkind: 讲义\n---\n# 标题\n\n## 一\n\n甲乙\n")
    _write_md(src, "z/w.md", "# 另一\n\n## 一\n\n丙丁\n")
    ingest.ingest_directory(str(src), db)
    with Store(db) as store:
        docs = {doc["path"]: doc for doc in store.iter_docs()}
    assert docs["x/y.md"]["course"] == "概率论" and docs["x/y.md"]["kind"] == "讲义"
    assert docs["z/w.md"]["course"] == "z" and docs["z/w.md"]["kind"] == ""

    ingest.ingest_directory(str(src), db, course="统一课程", kind="统一类型")
    with Store(db) as store:
        for doc in store.iter_docs():
            assert doc["course"] == "统一课程" and doc["kind"] == "统一类型"


def test_reset_clears_everything_and_skips_empty(tmp_path: Path) -> None:
    src = tmp_path / "src"
    db = str(tmp_path / "sb.db")
    _write_md(src, "a.md", "# A\n\n## 甲\n\n甲乙\n")
    _write_md(src, "empty.md", "\n\n")
    summary = ingest.ingest_directory(str(src), db)
    assert summary["docs"] == 1 and summary["skipped"] == ["empty.md"]
    with Store(db) as store:
        store.log_query("2026-10-30T00:00:00+08:00", "q", None, 0, 1)
        assert store.stats()["docs"] == 1

    again = ingest.ingest_directory(str(src), db, reset=True)
    assert again["reset"] is True
    with Store(db) as store:
        stats = store.stats()
        assert stats["docs"] == 1 and stats["chunks"] == 1  # reset 后重导回
        assert store.one("SELECT COUNT(*) FROM query_log") == (0,)  # query_log 也清空


def test_non_utf8_input_is_usage_error(tmp_path: Path) -> None:
    src = tmp_path / "src"
    path = src / "bad.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"# \xff\xfe\n")
    with pytest.raises(ValueError, match="UTF-8"):
        ingest.ingest_directory(str(src), str(tmp_path / "sb.db"))


def test_ingest_missing_src_is_usage_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="不是目录"):
        ingest.ingest_directory(str(tmp_path / "nope"), str(tmp_path / "sb.db"))


def test_src_qoder_prefix_is_stripped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """裁决·锚点2：CWD 是 qoder/ 根时，--src qoder/corpus_demo 解析到 corpus_demo。"""

    src = tmp_path / "corpus_demo"
    _write_md(src, "a.md", "# A\n\n## 甲\n\n甲乙\n")
    db = str(tmp_path / "sb.db")
    monkeypatch.chdir(tmp_path)  # 模拟 WSL 内 CWD = qoder/ 根

    summary = ingest.ingest_directory("qoder/corpus_demo", db)
    assert summary["docs"] == 1
    assert summary["src"] == "corpus_demo"  # 剥前缀后的相对路径（相对 CWD = qoder/ 根）

    # 真实存在的路径不受剥前缀逻辑影响；不可剥的缺失路径仍报错。
    assert ingest.ingest_directory("corpus_demo", db)["docs"] == 1
    with pytest.raises(ValueError, match="不是目录"):
        ingest.ingest_directory("qoder/不存在目录", db)
