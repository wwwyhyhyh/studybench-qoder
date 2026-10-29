"""命令行接线（qoder/CONTRACTS.md §6）。

- A 的命令（ingest/search/index/export/log/evidence/selftest）直接实现；
- B 的命令（task/digest）**惰性 import** :mod:`studybench.state` 等，
  检索命令不承担 PowerContext 的导入成本。

退出码：0 成功；2 参数/输入错误；3 依赖或数据库错误；4 无结果（search 专用，
stdout 仍输出空结果结构）。``--json`` 输出单行 JSON。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DEPENDENCY = 3
EXIT_EMPTY = 4


def _default_db(env: str, fallback: str) -> str:
    return os.environ.get(env) or str(Path.home() / fallback)


def _default_seekdb() -> str:
    return _default_db("SB_DB", "sb-run/.runtime/sb.db")


def _default_powercontext() -> str:
    return _default_db("SB_PC_DB", "sb-run/.runtime/powercontext.db")


def _json_line(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


# ---------------------------------------------------------------- ingest


def cmd_ingest(args: argparse.Namespace) -> int:
    from . import ingest

    summary = ingest.ingest_directory(
        args.src,
        args.db,
        course=args.course,
        kind=args.kind,
        reset=args.reset,
    )
    if args.json:
        _json_line(summary)
    else:
        note = "（已清空全库重导）" if summary["reset"] else ""
        print(f"已索引 {summary['docs']} 篇文档、{summary['chunks']} 个块{note}")
        if summary["skipped"]:
            print(f"跳过空文件 {len(summary['skipped'])} 个：{'、'.join(summary['skipped'])}")
        print(f"库：{summary['db']}")
    return EXIT_OK


# ---------------------------------------------------------------- search


def cmd_search(args: argparse.Namespace) -> int:
    import datetime as _dt

    from . import search as search_mod

    if args.since:
        try:
            _dt.date.fromisoformat(args.since)
        except ValueError as error:
            raise ValueError(f"--since 需要 YYYY-MM-DD 日期，得到 {args.since!r}") from error
    if args.top < 1:
        raise ValueError(f"--top 需要 ≥ 1，得到 {args.top}")

    outcome = search_mod.search(
        args.db,
        args.query,
        course=args.course,
        kind=args.kind,
        since=args.since,
        top=args.top,
    )
    if args.json:
        _json_line(outcome.as_dict(top=args.top))
    else:
        if not outcome.terms:
            print("查询无可检索词项")
        elif outcome.n_hits == 0:
            print(f"无命中结果（{outcome.n_chunks} 个块，耗时 {outcome.elapsed_ms} ms）")
        else:
            print(
                f"共 {outcome.n_hits} 条命中，显示前 {min(args.top, outcome.n_hits)} 条"
                f"（耗时 {outcome.elapsed_ms} ms，库 {outcome.n_chunks} 块，"
                f"平均块长 {outcome.avg_len:.1f}）"
            )
            for rank, hit in enumerate(outcome.hits[: args.top], start=1):
                print()
                print(f"{rank}. [{hit.score:.6f}] {hit.path}:{hit.line_start}-{hit.line_end}")
                print(f"   小节：{hit.heading}")
                breakdown = " + ".join(
                    f"{term}({value:.6f})" for term, value in hit.score_parts
                )
                print(f"   得分分解：{breakdown}")
                print(f"   摘录：{hit.excerpt}")
    return EXIT_EMPTY if outcome.n_hits == 0 else EXIT_OK


# ---------------------------------------------------------------- index


def cmd_index(args: argparse.Namespace) -> int:
    from .store import Store

    store = Store(args.db)
    try:
        store.require_schema()
        stats = store.stats()
    finally:
        store.close()
    if args.json:
        _json_line(stats)
    else:
        print(
            f"文档 {stats['docs']} 篇｜块 {stats['chunks']} 个｜"
            f"词项 {stats['terms']} 个｜平均块长 {stats['avg_len']:.1f}"
        )
    return EXIT_OK


# ---------------------------------------------------------------- export


def cmd_export(args: argparse.Namespace) -> int:
    from . import export

    summary = export.export_index(args.db, args.out)
    print(
        f"已导出 {summary['n_docs']} 篇文档、{summary['n_chunks']} 个块、"
        f"{summary['terms']} 个词项 → {summary['out']}（{summary['bytes']} 字节）"
    )
    return EXIT_OK


# ---------------------------------------------------------------- log


def cmd_log(args: argparse.Namespace) -> int:
    from .store import Store

    store = Store(args.db)
    try:
        store.require_schema()
        rows = store.query_log_tail(args.tail)
    finally:
        store.close()
    if args.json:
        _json_line({"tail": args.tail, "rows": rows})
    else:
        if not rows:
            print("query_log 为空——先运行 studybench search。")
        for row in rows:
            top = row["top_chunk"] if row["top_chunk"] is not None else "-"
            print(
                f"{row['qid']:>5}  {row['ts']}  查询「{row['q']}」"
                f"  top={top}  命中 {row['n_hits']}  {row['elapsed_ms']} ms"
            )
    return EXIT_OK


# ---------------------------------------------------------------- task（B，惰性）


def _print_task_board(task: dict) -> None:
    print(f"- {task['task_id']} [{task['status'] or '-'}] {task['title']}")
    detail = (
        f"课程 {task['course'] or '-'}｜到期 {task['due'] or '-'}"
        f"｜优先级 {task['priority'] or '-'}｜revision {task['revision']}"
    )
    print(f"    {detail}")
    for key, label in (("done", "已完成"), ("doing", "进行中"), ("next", "下一步")):
        if task.get(key):
            print(f"    {label}：{'；'.join(task[key])}")
    if task.get("blockers"):
        print(f"    阻塞：{'；'.join(task['blockers'])}")
    for decision in task.get("decisions", []):
        print(f"    决策：{decision['text']}（{decision['ts']}）")


def cmd_task(args: argparse.Namespace) -> int:
    from . import state

    if args.task_cmd == "add":
        spec = {
            "task_id": args.task_id,
            "title": args.title,
        }
        for key, flag in (
            ("course", "course"),
            ("due", "due"),
            ("priority", "priority"),
            ("status", "status"),
        ):
            value = getattr(args, flag)
            if value:
                spec[key] = value
        task = state.add_task(args.pc_db, spec)
        if args.json:
            _json_line(task)
        else:
            _print_task_board(task)
        return EXIT_OK

    if args.task_cmd == "update":
        patch: dict = {}
        for key, flag in (
            ("done", "done"),
            ("doing", "doing"),
            ("next", "next"),
            ("blocker", "blocker"),
            ("decision", "decision"),
            ("status", "status"),
        ):
            value = getattr(args, flag)
            if value:
                patch[key] = value
        task = state.update_task(args.pc_db, args.task_id, patch)
        if args.json:
            _json_line(task)
        else:
            _print_task_board(task)
        return EXIT_OK

    if args.task_cmd == "status":
        tasks = state.list_tasks(args.pc_db)
        if args.json:
            _json_line({"tasks": tasks})
        else:
            if not tasks:
                print("当前没有任务——用 studybench task add 创建。")
            for task in tasks:
                _print_task_board(task)
        return EXIT_OK

    # resume
    task = state.resume_task(args.pc_db, args.task_id)
    if args.json:
        _json_line(task)
    else:
        print(f"# {task['task_id']}｜{task['task']['title']}")
        print(f"上次更新：{task['last_updated'] or '-'}")
        for key, label in (("done", "上次做到哪"), ("blockers", "现在卡在哪"), ("next", "下一步")):
            value = task.get(key, [])
            print(f"{label}：{'；'.join(value) if value else '无'}")
        history = " → ".join(
            f"r{item['revision']}@{item['updated_at']}" for item in task["revisions"]
        )
        print(f"最近版本：{history}")
    return EXIT_OK


# ---------------------------------------------------------------- digest（B，惰性）


def cmd_digest(args: argparse.Namespace) -> int:
    from . import digest as digest_mod
    from . import state, tasks as tasks_mod

    if args.tasks:
        for record in tasks_mod.load_tasks(args.tasks):
            state.add_task(args.pc_db, record)
    text = digest_mod.build_digest(args.pc_db, args.week)
    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"周报已写入 {out}")
    else:
        sys.stdout.write(text)
    return EXIT_OK


# ---------------------------------------------------------------- evidence


def cmd_evidence(args: argparse.Namespace) -> int:
    from . import evidence

    summary = evidence.write_evidence(args.db, args.pc_db, args.out_dir)
    for path in summary["files"]:
        print(f"已生成 {path}")
    print(f"query_log 行数：{summary['queries']}｜任务数：{summary['tasks']}")
    return EXIT_OK


# ---------------------------------------------------------------- selftest


def cmd_selftest(args: argparse.Namespace) -> int:
    tests_dir = Path(__file__).resolve().parent.parent / "tests"
    print(f"运行 pytest：{tests_dir}")
    try:
        import pytest
    except ImportError:
        print("pytest 不可用——请用 bash qoder/scripts/sb.sh selftest 运行。", file=sys.stderr)
        return EXIT_DEPENDENCY
    return int(pytest.main(["-q", str(tests_dir)]))


# ---------------------------------------------------------------- 解析器


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studybench",
        description="学研台 StudyBench：seekdb 检索 + PowerContext 任务记忆（契约 §6）",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    ingest = sub.add_parser("ingest", help="把 markdown 目录索引进 seekdb")
    ingest.add_argument("--src", required=True, help="markdown 根目录")
    ingest.add_argument("--db", default=_default_seekdb(), help="seekdb 库目录")
    ingest.add_argument("--course", default=None, help="覆盖全部文档的课程名")
    ingest.add_argument("--kind", default=None, help="覆盖全部文档的类型名")
    ingest.add_argument("--reset", action="store_true", help="清空全库后重导")
    ingest.add_argument("--json", action="store_true", help="输出单行 JSON")
    ingest.set_defaults(handler=cmd_ingest)

    search = sub.add_parser("search", help="检索（结果含 path:line 引用与得分分解）")
    search.add_argument("query", help="查询串（中文口语即可）")
    search.add_argument("--db", default=_default_seekdb(), help="seekdb 库目录")
    search.add_argument("--course", default=None, help="按课程过滤")
    search.add_argument("--kind", default=None, help="按类型过滤")
    search.add_argument("--since", default=None, help="按文档日期过滤（YYYY-MM-DD）")
    search.add_argument("--top", type=int, default=10, help="显示前 N 条（默认 10）")
    search.add_argument("--json", action="store_true", help="输出单行 JSON")
    search.set_defaults(handler=cmd_search)

    index = sub.add_parser("index", help="索引规模：文档数/块数/词项数/平均块长")
    index.add_argument("--db", default=_default_seekdb(), help="seekdb 库目录")
    index.add_argument("--json", action="store_true", help="输出单行 JSON")
    index.set_defaults(handler=cmd_index)

    export = sub.add_parser("export", help="导出 index_export.json（契约 §5）")
    export.add_argument("--out", required=True, help="输出文件路径")
    export.add_argument("--db", default=_default_seekdb(), help="seekdb 库目录")
    export.set_defaults(handler=cmd_export)

    log = sub.add_parser("log", help="query_log 尾部（使用数据）")
    log.add_argument("--db", default=_default_seekdb(), help="seekdb 库目录")
    log.add_argument("--tail", type=int, default=10, help="显示最近 N 条（默认 10）")
    log.add_argument("--json", action="store_true", help="输出单行 JSON")
    log.set_defaults(handler=cmd_log)

    task = sub.add_parser("task", help="任务记忆（PowerContext，契约 §7）")
    task.add_argument("--pc-db", default=_default_powercontext(), help="状态库路径")
    task_sub = task.add_subparsers(dest="task_cmd", required=True, metavar="action")

    task_add = task_sub.add_parser("add", help="登记一个任务")
    task_add.add_argument("--task-id", required=True)
    task_add.add_argument("--title", required=True)
    task_add.add_argument("--course", default=None)
    task_add.add_argument("--due", default=None, help="YYYY-MM-DD")
    task_add.add_argument("--priority", default=None)
    task_add.add_argument("--status", default=None)
    task_add.add_argument("--json", action="store_true")
    task_add.set_defaults(handler=cmd_task)

    task_update = task_sub.add_parser("update", help="追加一次进度（新 revision）")
    task_update.add_argument("task_id")
    task_update.add_argument("--done", action="append", default=None)
    task_update.add_argument("--doing", action="append", default=None)
    task_update.add_argument("--next", action="append", default=None)
    task_update.add_argument("--blocker", action="append", default=None)
    task_update.add_argument("--decision", action="append", default=None)
    task_update.add_argument("--status", default=None)
    task_update.add_argument("--json", action="store_true")
    task_update.set_defaults(handler=cmd_task)

    task_status = task_sub.add_parser("status", help="任务看板")
    task_status.add_argument("--json", action="store_true")
    task_status.set_defaults(handler=cmd_task)

    task_resume = task_sub.add_parser("resume", help="读最近 3 个 revision 续做")
    task_resume.add_argument("task_id")
    task_resume.add_argument("--json", action="store_true")
    task_resume.set_defaults(handler=cmd_task)

    digest = sub.add_parser("digest", help="周报（契约 §8）")
    digest.add_argument("--week", default=None, help="ISO 周，如 2026-W44（默认当前周）")
    digest.add_argument("--out", default=None, help="写入文件（缺省打印到 stdout）")
    digest.add_argument("--tasks", default=None, help="tasks.json 路径（先导入状态库）")
    digest.add_argument("--pc-db", default=_default_powercontext(), help="状态库路径")
    digest.set_defaults(handler=cmd_digest)

    evidence = sub.add_parser("evidence", help="生成 records 检索/状态记录")
    evidence.add_argument("--out-dir", default="records", help="输出目录（默认 records）")
    evidence.add_argument("--db", default=_default_seekdb(), help="seekdb 库目录")
    evidence.add_argument("--pc-db", default=_default_powercontext(), help="状态库路径")
    evidence.set_defaults(handler=cmd_evidence)

    selftest = sub.add_parser("selftest", help="运行 pytest（= bash qoder/scripts/sb.sh selftest）")
    selftest.set_defaults(handler=cmd_selftest)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except LookupError as error:  # 任务不存在等输入错误
        print(f"错误：{error}", file=sys.stderr)
        return EXIT_USAGE
    except ValueError as error:  # 参数/输入错误（含 tasks.json 校验）
        print(f"错误：{error}", file=sys.stderr)
        return EXIT_USAGE
    except Exception as error:  # 依赖或数据库错误
        print(f"错误：{type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_DEPENDENCY


if __name__ == "__main__":
    raise SystemExit(main())
