"""search.py 单测：BM25 / 排序 / 过滤 / 引用 / query_log（契约 §4.2、§4.3、§6）。"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pytest

from studybench import ingest, search
from studybench.search import B, K1, SearchOutcome, make_excerpt
from studybench.store import Store

MINI = Path(__file__).parent / "fixtures" / "mini"


@pytest.fixture()
def mini_db(tmp_path: Path) -> str:
    db = str(tmp_path / "sb.db")
    ingest.ingest_directory(str(MINI), db)
    return db


def _write_md(root: Path, rel: str, content: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_empty_terms_returns_empty_and_logs(mini_db: str) -> None:
    outcome = search.search(mini_db, "！！！？？")
    assert isinstance(outcome, SearchOutcome)
    assert outcome.terms == [] and outcome.n_hits == 0 and outcome.hits == []
    with Store(mini_db) as store:
        row = store.query_log_tail(1)[0]
        assert row["q"] == "！！！？？"
        assert row["n_hits"] == 0 and row["top_chunk"] is None


def test_search_hit_fields_and_reference(mini_db: str) -> None:
    """输出含 path:line 引用、得分分解、命中词与摘录（契约 §4.3）。"""

    outcome = search.search(mini_db, "完全二叉树 叶子结点", top=3)
    assert outcome.n_hits >= 1
    top = outcome.hits[0]
    assert top.path.endswith(".md")
    assert top.heading and top.line_start >= 1 and top.line_end >= top.line_start
    assert top.score > 0
    assert top.matched_terms and set(top.matched_terms) <= set(outcome.terms)
    assert 0 < len(top.excerpt) <= 160
    assert sum(value for _, value in top.score_parts) == pytest.approx(top.score, abs=1e-9)
    payload = top.as_dict()
    assert list(payload)[:3] == ["chunk_id", "score", "path"]
    assert payload["score"] == round(top.score, 6)
    # 排序：score 降序（契约 §4.2）。
    scores = [hit.score for hit in outcome.hits]
    assert scores == sorted(scores, reverse=True)


def test_query_log_written_for_real_search(mini_db: str) -> None:
    outcome = search.search(mini_db, "哈夫曼编码")
    with Store(mini_db) as store:
        row = store.query_log_tail(1)[0]
    assert row["n_hits"] == outcome.n_hits
    assert row["top_chunk"] == outcome.hits[0].chunk_id
    assert row["elapsed_ms"] == outcome.elapsed_ms


def test_no_results_still_logged(mini_db: str) -> None:
    outcome = search.search(mini_db, "魑魅魍魉")
    assert outcome.n_hits == 0
    with Store(mini_db) as store:
        row = store.query_log_tail(1)[0]
        assert row["n_hits"] == 0  # 空结果也必须写 query_log（契约 §6）


def test_fallback_recall_equals_fulltext_path(mini_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """FULLTEXT 召回为空时退回 chunk_terms 覆盖查询，结果一致（契约 §4.3）。"""

    direct = search.search(mini_db, "哈夫曼 前缀码")
    monkeypatch.setattr(
        "studybench.search.Store.fulltext_recall", lambda self, terms: []
    )
    fallback = search.search(mini_db, "哈夫曼 前缀码")
    assert fallback.n_hits > 0
    assert [hit.as_dict() for hit in fallback.hits] == [hit.as_dict() for hit in direct.hits]


def test_heading_boost_via_tf_eff(tmp_path: Path) -> None:
    """tf_eff = tf_text + 2*tf_heading：标题命中权重 ×2（契约 §4.2）。"""

    src = tmp_path / "src"
    # a：tf_text=2、标题无查询词 → tf_eff=2；b：tf_text=1、标题含查询词 → tf_eff=3。
    _write_md(src, "a.md", "# 甲文档\n\n## 一\n\nword again word\n")
    _write_md(src, "b.md", "# 乙文档\n\n## word\n\nword again\n")
    db = str(tmp_path / "sb.db")
    ingest.ingest_directory(str(src), db)

    with Store(db) as store:
        tf = {
            (row[0], row[1]): int(row[2])
            for row in store.execute("SELECT term, chunk_id, tf FROM chunk_terms WHERE term = 'word'")
        }
    id_a = "d" + hashlib.sha1(b"a.md").hexdigest()[:8]
    id_b = "d" + hashlib.sha1(b"b.md").hexdigest()[:8]
    assert tf[("word", f"{id_a}#c00")] == 2
    assert tf[("word", f"{id_b}#c00")] == 3  # 1 + 2*1：标题权重翻倍

    outcome = search.search(db, "word", top=2)
    assert outcome.n_hits == 2
    assert outcome.hits[0].heading == "word"  # 标题命中的块排前
    assert outcome.hits[0].heading_hit == 1 and outcome.hits[1].heading_hit == 0


def test_bm25_score_matches_formula(tmp_path: Path) -> None:
    """单块单查询词：手算 BM25 与实现一致（6 位小数）。"""

    src = tmp_path / "src"
    _write_md(src, "solo.md", "# 独库\n\n## 一\n\nword word again\n")
    db = str(tmp_path / "sb.db")
    ingest.ingest_directory(str(src), db)

    outcome = search.search(db, "word")
    assert outcome.n_chunks == 1
    assert outcome.avg_len == 15.0
    df, n, tf_eff, n_chars = 1, 1, 2, 15
    expected = (
        math.log(1 + (n - df + 0.5) / (df + 0.5))
        * tf_eff
        * (K1 + 1)
        / (tf_eff + K1 * (1 - B + B * n_chars / outcome.avg_len))
    )
    assert outcome.hits[0].score == pytest.approx(expected, abs=1e-12)
    assert round(outcome.hits[0].score, 6) == round(expected, 6)


def test_course_kind_since_filters(mini_db: str) -> None:
    """结构化过滤用 docs JOIN，不参与打分（契约 §4.3）。"""

    everything = search.search(mini_db, "示例数据")
    courses = {hit.course for hit in everything.hits}
    assert {"数据结构", "物理实验", "概率论"} <= courses  # 三门课都有「示例数据」

    ds_only = search.search(mini_db, "示例数据", course="数据结构")
    assert ds_only.hits and {hit.course for hit in ds_only.hits} == {"数据结构"}

    notes = search.search(mini_db, "示例数据", kind="不存在的类型")
    assert notes.n_hits == 0

    future = search.search(mini_db, "示例数据", since="2099-01-01")
    assert future.n_hits == 0
    past = search.search(mini_db, "示例数据", since="2000-01-01")
    assert past.n_hits == everything.n_hits


def test_same_word_different_courses_sorted_deterministically(mini_db: str) -> None:
    """跨课程区分（同词不同课）：顺序稳定可复现（契约 §9 演示价值）。"""

    first = search.search(mini_db, "概率论")
    second = search.search(mini_db, "概率论")
    assert first.n_hits > 0
    assert [hit.as_dict() for hit in first.hits] == [hit.as_dict() for hit in second.hits]
    assert first.hits[0].path.startswith("概率论/")


def test_excerpt_cut_around_hit() -> None:
    text = "前" * 200 + "关键词" + "后" * 200
    excerpt = make_excerpt(text, ["关键词"])
    assert len(excerpt) <= 160
    assert "关键词" in excerpt
    assert excerpt.startswith("…") and excerpt.endswith("…")
    assert make_excerpt("短文本", ["关键词"]) == "短文本"  # 命中不了就整段返回
    no_hit = make_excerpt("a" * 200, ["不存在的词"])
    assert len(no_hit) <= 160 and no_hit.endswith("…")
    assert len(make_excerpt("a" * 200, [])) <= 160
