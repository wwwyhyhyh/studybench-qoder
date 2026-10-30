"""verify 子命令：由演示查询复算 verification/expected_results.json（契约 §10、§11）。

产物与 ``verification/expected_results.json`` 完全同构::

    {"generated_at": "...", "db": "...", "results": [
        {"query": "...", "expect_heading": "...", "top5": [
            {"chunk_id": "...", "score": 28.069435, "path": "...",
             "heading": "...", "line_start": 7}]}]}

每条查询都走 :func:`studybench.search.search`（top=5），因此同样会写 query_log。
``--check`` 只比较 top-5 的 chunk_id 顺序与 6 位小数得分——这正是站点
parity 测试的判定口径（契约 §10）；generated_at / db 不参与比对。
"""

from __future__ import annotations

import json
from pathlib import Path

from . import search as search_mod
from .store import now_iso

#: qoder/ 根目录（本文件位于 qoder/studybench/studybench/verify.py）。
_PKG_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_QUERIES = _PKG_ROOT / "corpus_demo" / "_queries.json"
DEFAULT_OUT = _PKG_ROOT / "verification" / "expected_results.json"

#: 每条查询记录的命中条数（契约 §10：站点 parity 比较 top-5）。
TOP_N = 5

#: top5 条目的字段（顺序即输出顺序）。
TOP_FIELDS = ("chunk_id", "score", "path", "heading", "line_start")


def _read_queries(queries_path: str | Path | None = None) -> list[dict]:
    """读取 _queries.json 的 queries 数组（缺 query/expect_heading 视为输入错误）。"""

    path = Path(queries_path or DEFAULT_QUERIES).expanduser()
    payload = json.loads(path.read_text(encoding="utf-8"))
    queries = payload.get("queries")
    if not isinstance(queries, list):
        raise ValueError(f"查询清单缺少 queries 数组：{path}")
    for item in queries:
        if not isinstance(item, dict) or "query" not in item or "expect_heading" not in item:
            raise ValueError(f"查询条目缺少 query/expect_heading：{item!r}")
    return queries


def build(db_path: str, queries_path: str | Path | None = None) -> dict:
    """复算全部查询的 top-5，返回与 expected_results.json 同构的 dict。"""

    results = []
    for item in _read_queries(queries_path):
        outcome = search_mod.search(db_path, item["query"], top=TOP_N)
        top5 = [
            {
                "chunk_id": hit.chunk_id,
                "score": round(hit.score, 6),
                "path": hit.path,
                "heading": hit.heading,
                "line_start": hit.line_start,
            }
            for hit in outcome.hits[:TOP_N]
        ]
        results.append(
            {
                "query": item["query"],
                "expect_heading": item["expect_heading"],
                "top5": top5,
            }
        )
    return {"generated_at": now_iso(), "db": str(db_path), "results": results}


def write(
    db_path: str,
    out_path: str | Path | None = None,
    queries_path: str | Path | None = None,
) -> dict:
    """复算并写入 expected_results.json（indent=1，与既有产物排版一致）。"""

    payload = build(db_path, queries_path)
    out = Path(out_path or DEFAULT_OUT).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return payload


def load(path: str | Path | None = None) -> dict:
    """读取比对基准；文件缺失时抛 FileNotFoundError（CLI 映射为退出码 3）。"""

    return json.loads(Path(path or DEFAULT_OUT).expanduser().read_text(encoding="utf-8"))


def _same_hit(expected: dict, actual: dict) -> bool:
    return (
        expected.get("chunk_id") == actual.get("chunk_id")
        and round(float(expected.get("score", 0.0)), 6)
        == round(float(actual.get("score", 0.0)), 6)
    )


def diff(expected: dict, actual: dict) -> list[dict]:
    """逐条比对 top-5 chunk_id 顺序与 6 位小数得分，返回差异行（空 = 全等）。"""

    expected_by_query = {item["query"]: item for item in expected.get("results", [])}
    actual_by_query = {item["query"]: item for item in actual.get("results", [])}

    # 顺序：先按基准文件的查询顺序，再补上实际多出来的查询。
    order: list[str] = []
    for item in expected.get("results", []):
        if item["query"] not in order:
            order.append(item["query"])
    for item in actual.get("results", []):
        if item["query"] not in order:
            order.append(item["query"])

    rows: list[dict] = []
    for query in order:
        exp = expected_by_query.get(query)
        act = actual_by_query.get(query)
        if exp is None or act is None:
            rows.append(
                {
                    "query": query,
                    "rank": "-",
                    "expected_chunk": "—" if exp is None else "（基准有）",
                    "actual_chunk": "—" if act is None else "（基准缺）",
                    "expected_score": "—",
                    "actual_score": "—",
                }
            )
            continue
        exp_top = exp.get("top5", [])
        act_top = act.get("top5", [])
        for rank in range(max(len(exp_top), len(act_top))):
            exp_hit = exp_top[rank] if rank < len(exp_top) else None
            act_hit = act_top[rank] if rank < len(act_top) else None
            if exp_hit is not None and act_hit is not None and _same_hit(exp_hit, act_hit):
                continue
            rows.append(
                {
                    "query": query,
                    "rank": rank + 1,
                    "expected_chunk": exp_hit["chunk_id"] if exp_hit else "—",
                    "actual_chunk": act_hit["chunk_id"] if act_hit else "—",
                    "expected_score": (
                        f"{float(exp_hit['score']):.6f}" if exp_hit else "—"
                    ),
                    "actual_score": (
                        f"{float(act_hit['score']):.6f}" if act_hit else "—"
                    ),
                }
            )
    return rows


def format_diff(rows: list[dict]) -> str:
    """把差异行渲染成 markdown 表格（--check 有差异时打印）。"""

    columns = (
        ("query", "查询"),
        ("rank", "位次"),
        ("expected_chunk", "期望 chunk_id"),
        ("actual_chunk", "实际 chunk_id"),
        ("expected_score", "期望得分"),
        ("actual_score", "实际得分"),
    )
    lines = [
        "| " + " | ".join(label for _, label in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row[key]) for key, _ in columns) + " |")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_OUT",
    "DEFAULT_QUERIES",
    "TOP_FIELDS",
    "TOP_N",
    "build",
    "diff",
    "format_diff",
    "load",
    "write",
]
