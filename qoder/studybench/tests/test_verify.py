"""verify.py 单测：产物同构 / --check 全等 / --check 差异 / 基准缺失（契约 §10、§11）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from studybench import cli, ingest, search, verify

MINI = Path(__file__).parent / "fixtures" / "mini"

QUERIES = {
    "queries": [
        {
            "query": "完全二叉树 叶子结点",
            "expect_heading": "二叉树的性质",
            "why": "fixture：验证同构与全等路径",
        },
        {
            "query": "哈夫曼编码",
            "expect_heading": "哈夫曼树与编码",
            "why": "fixture：验证同构与全等路径",
        },
    ]
}


@pytest.fixture()
def env(tmp_path: Path) -> tuple[str, Path, Path]:
    db = str(tmp_path / "sb.db")
    ingest.ingest_directory(str(MINI), db)
    queries = tmp_path / "_queries.json"
    queries.write_text(json.dumps(QUERIES, ensure_ascii=False), encoding="utf-8")
    return db, queries, tmp_path / "expected_results.json"


def _run_check(monkeypatch: pytest.MonkeyPatch, db: str, out: Path, queries: Path) -> int:
    """把 CLI 默认的基准文件/查询清单指到 fixture 后跑 verify --check。"""

    monkeypatch.setattr(verify, "DEFAULT_OUT", out)
    monkeypatch.setattr(verify, "DEFAULT_QUERIES", queries)
    return cli.main(["verify", "--check", "--db", db])


def test_build_shape_matches_frozen_schema(env: tuple[str, Path, Path]) -> None:
    """产物字段与 expected_results.json 完全同构，top5 即 search(top=5) 的投影。"""

    db, queries, _ = env
    payload = verify.build(db, queries)

    assert set(payload) == {"generated_at", "db", "results"}
    assert payload["generated_at"].endswith("+08:00")
    assert payload["db"] == db
    assert [item["query"] for item in payload["results"]] == [
        item["query"] for item in QUERIES["queries"]
    ]

    for item in payload["results"]:
        assert set(item) == {"query", "expect_heading", "top5"}
        assert len(item["top5"]) <= verify.TOP_N
        for hit in item["top5"]:
            assert tuple(hit) == verify.TOP_FIELDS  # 字段与顺序冻结
            assert isinstance(hit["score"], float)
            assert hit["score"] == round(hit["score"], 6)
            assert hit["line_start"] >= 1

    # 与直接检索逐字段一致（top-5 截断 + 得分 6 位小数）。
    outcome = search.search(db, QUERIES["queries"][1]["query"], top=verify.TOP_N)
    assert payload["results"][1]["top5"] == [
        {
            "chunk_id": hit.chunk_id,
            "score": round(hit.score, 6),
            "path": hit.path,
            "heading": hit.heading,
            "line_start": hit.line_start,
        }
        for hit in outcome.hits[: verify.TOP_N]
    ]


def test_check_all_equal_exit_zero(
    env: tuple[str, Path, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """先按同一 fixture 生成基准，再 --check：全部一致退出 0。"""

    db, queries, out = env
    verify.write(db, out, queries)
    assert out.exists()

    assert _run_check(monkeypatch, db, out, queries) == 0
    assert "全部一致" in capsys.readouterr().out


def test_check_difference_exit_four(
    env: tuple[str, Path, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """篡改基准的 chunk_id 与得分后 --check：打印差异表退出 4。"""

    db, queries, out = env
    verify.write(db, out, queries)
    payload = json.loads(out.read_text(encoding="utf-8"))
    hit = payload["results"][0]["top5"][0]
    hit["chunk_id"] = "d00000000#c99"
    hit["score"] = 1.0
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    assert _run_check(monkeypatch, db, out, queries) == 4
    printed = capsys.readouterr().out
    assert "| 查询 | 位次 |" in printed
    assert "d00000000#c99" in printed and "1.000000" in printed


def test_check_missing_baseline_exit_three(
    env: tuple[str, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """基准文件缺失：退出 3，不尝试检索。"""

    db, queries, out = env
    assert not out.exists()
    assert _run_check(monkeypatch, db, out, queries) == 3
