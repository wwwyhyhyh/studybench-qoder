"""related.py 单测：命中字段 / 同文档排除 / 排序 / 退出码（2、4）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from studybench import ingest, related
from studybench.cli import main as cli_main

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


def _tree_chunk() -> str:
    """数据结构/树与二叉树.md 的「二叉树的性质」块。"""

    return ingest.doc_id_for("数据结构/树与二叉树.md") + "#c01"


def test_related_hit_fields_and_exclusions(mini_db: str) -> None:
    source = _tree_chunk()
    outcome = related.related(mini_db, source)

    assert outcome.chunk == source
    assert 0 < len(outcome.terms) <= related.SOURCE_TERM_LIMIT
    assert outcome.n_hits >= 1

    scores = [hit.score for hit in outcome.hits]
    assert scores == sorted(scores, reverse=True)
    for hit in outcome.hits:
        assert hit.chunk_id != source  # 排除自身
        assert not hit.path.startswith("数据结构/")  # 排除同文档的其他块
        assert hit.path.endswith(".md")
        assert hit.heading and hit.line_start >= 1
        assert hit.score > 0
        assert hit.matched_terms
        assert set(hit.matched_terms) <= set(outcome.terms)
        assert hit.score == pytest.approx(
            sum(value for _, value in hit.score_parts), abs=1e-9
        )


def test_related_cli_json_top_and_shape(mini_db: str, capsys: pytest.CaptureFixture) -> None:
    source = _tree_chunk()
    outcome = related.related(mini_db, source)

    code = cli_main(
        ["related", "--chunk", source, "--db", mini_db, "--json", "--top", "2"]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["chunk"] == source
    assert payload["n_hits"] == outcome.n_hits
    assert len(payload["results"]) == min(2, outcome.n_hits) == 2
    for item in payload["results"]:
        assert set(item) == {"chunk_id", "score", "path", "heading", "line_start"}
    assert payload["results"][0]["score"] == round(outcome.hits[0].score, 6)


def test_related_missing_chunk_exits_2(mini_db: str, capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(LookupError):
        related.related(mini_db, "d00000000#c99")

    code = cli_main(["related", "--chunk", "d00000000#c99", "--db", mini_db])
    assert code == 2
    assert "块不存在" in capsys.readouterr().err


def test_related_no_overlap_exits_4(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    src = tmp_path / "src"
    # 两篇文档词项完全不相交 → 源块没有任何可推荐的相关块。
    _write_md(src, "a.md", "# 甲\n\n## 一\n\n完全二叉树叶子结点\n")
    _write_md(src, "b.md", "# 乙\n\n## 二\n\n扭摆周期转动惯量\n")
    db = str(tmp_path / "sb.db")
    ingest.ingest_directory(str(src), db)

    source = ingest.doc_id_for("a.md") + "#c00"
    outcome = related.related(db, source)
    assert outcome.terms  # 源块本身有词项
    assert outcome.n_hits == 0

    assert cli_main(["related", "--chunk", source, "--db", db]) == 4
