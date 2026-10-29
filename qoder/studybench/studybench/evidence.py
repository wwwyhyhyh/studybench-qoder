"""由 query_log / 状态库生成 records 记录（qoder/CONTRACTS.md §6 evidence）。

产出两个文件（全部数值来自真实库，非手写；契约 §11.4）：

- ``seekdb-query-record.md``：seekdb 库规模 + query_log 真实行；
- ``powercontext-state-record.md``：任务看板 + 真实 Artifact 版本号。

PowerContext 状态层（B 模块）在此**惰性导入**。
"""

from __future__ import annotations

from pathlib import Path

from .store import Store, now_iso


def _seekdb_record(db_path: str) -> tuple[str, int]:
    store = Store(db_path)
    try:
        store.require_schema()
        stats = store.stats()
        rows = store.query_log_tail(100)
        lines = [
            "# 学研台 seekdb 检索记录",
            "",
            f"- 生成时间：{now_iso()}",
            f"- seekdb 库：{store.db_path}",
            f"- 规模：文档 {stats['docs']} 篇｜块 {stats['chunks']} 个｜"
            f"词项 {stats['terms']} 个｜平均块长 {stats['avg_len']:.1f}",
            "",
            f"## query_log（最近 {len(rows)} 条，按 qid 倒序）",
            "",
        ]
        if rows:
            lines.append("| qid | 时间 | 查询 | top_chunk | 命中数 | 耗时(ms) |")
            lines.append("| --- | --- | --- | --- | --- | --- |")
            for row in rows:
                top = row["top_chunk"] if row["top_chunk"] is not None else "-"
                lines.append(
                    f"| {row['qid']} | {row['ts']} | {row['q']} | {top} "
                    f"| {row['n_hits']} | {row['elapsed_ms']} |"
                )
        else:
            lines.append("query_log 为空——先运行 studybench search 生成真实检索记录。")
        return "\n".join(lines) + "\n", len(rows)
    finally:
        store.close()


def _powercontext_record(pc_db_path: str) -> tuple[str, int]:
    # 惰性导入：检索命令不承担 PowerContext 的导入成本。
    from . import state

    histories = state.task_histories(pc_db_path)
    lines = [
        "# 学研台 PowerContext 状态记录",
        "",
        f"- 生成时间：{now_iso()}",
        f"- 状态库：{pc_db_path}",
        f"- 模型层：{state.BACKEND}（主仓 powercontext）｜存储引擎：{state.STORAGE_BACKEND}",
        f"- 任务数：{len(histories)}",
        "",
    ]
    if not histories:
        lines.append("当前没有任务——先运行 studybench task add 生成真实状态记录。")
    for history in histories:
        task = history["task"]
        lines.append(f"## {task['task_id']}｜{task['title']}")
        lines.append("")
        lines.append(
            f"- 课程：{task['course'] or '-'}｜到期：{task['due'] or '-'}"
            f"｜优先级：{task['priority'] or '-'}｜状态：{task['status'] or '-'}"
        )
        lines.append(
            f"- 最新 revision：r{task['revision']}"
            + (f"（{task['updated_at']}）" if task["updated_at"] else "")
        )
        revisions = history["revisions"]
        if revisions:
            chain = " → ".join(
                f"r{item['revision']}@{item['updated_at']}" for item in revisions
            )
            lines.append(f"- 版本历史：{chain}")
        for key, label in (("done", "已完成"), ("doing", "进行中"), ("next", "下一步")):
            if task[key]:
                lines.append(f"- {label}：{'；'.join(task[key])}")
        if task["blockers"]:
            lines.append(f"- 阻塞：{'；'.join(task['blockers'])}")
        lines.append("")
    return "\n".join(lines) + "\n", len(histories)


def write_evidence(db_path: str, pc_db_path: str, out_dir: str) -> dict:
    """生成 records 两个文件；返回 ``{"files", "queries", "tasks"}``。"""

    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    seekdb_text, n_queries = _seekdb_record(db_path)
    seekdb_path = out / "seekdb-query-record.md"
    seekdb_path.write_text(seekdb_text, encoding="utf-8")

    pc_text, n_tasks = _powercontext_record(pc_db_path)
    pc_path = out / "powercontext-state-record.md"
    pc_path.write_text(pc_text, encoding="utf-8")

    return {
        "files": [str(seekdb_path), str(pc_path)],
        "queries": n_queries,
        "tasks": n_tasks,
    }
