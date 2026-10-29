"""周报生成（qoder/CONTRACTS.md §8）：纯确定性模板，不调用任何 LLM。

固定四段，标题含 ISO 周号与日期区间（周一至周日，+08:00）：

1. 本周完成（status=done，或本周 revision 相对上一版新增了 done 项）
2. 进行中（status 非 done 且 doing/next 非空，每条带「下一步」）
3. 风险与阻塞（blockers 非空，或 due 落在下周且未完成）
4. 下周计划（未完成任务的 next 归并去重）

空段落写「本周无」，不省略。
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from . import state

#: 周界时区（契约 §7/§8：本地时区 +08:00）。
_TZ = state.CST

_WEEK_RE = re.compile(r"^(\d{4})-W(\d{1,2})$")

_EMPTY_SENTENCE = "本周无"

_HEADINGS = ("本周完成", "进行中", "风险与阻塞", "下周计划")


def resolve_week(week: str | None) -> tuple[date, date]:
    """Return the ``(monday, sunday)`` bounds of an ISO week（``YYYY-Www``，+08:00）。"""

    if week is None:
        today = datetime.now(_TZ).date()
        monday = today - timedelta(days=today.isoweekday() - 1)
    else:
        match = _WEEK_RE.fullmatch(str(week).strip())
        if match is None:
            raise ValueError(
                f"digest: invalid week {week!r}, expected ISO 'YYYY-Www' (e.g. '2026-W44')"
            )
        monday = date.fromisocalendar(int(match.group(1)), int(match.group(2)), 1)
    return monday, monday + timedelta(days=6)


def _done_added_within(revisions: list[dict], monday: date, sunday: date) -> bool:
    """Whether any in-week revision recorded done items absent from its predecessor."""

    previous: set[str] = set()
    for revision in revisions:
        day = str(revision.get("updated_at", ""))[:10]
        if monday.isoformat() <= day <= sunday.isoformat():
            if set(revision.get("done", [])) - previous:
                return True
        previous = set(revision.get("done", []))
    return False


def _in_range(text: str, start: date, end: date) -> bool:
    try:
        day = date.fromisoformat(text)
    except ValueError:
        return False
    return start <= day <= end


def _describe(task: dict) -> str:
    parts = [task["title"], "（", task["task_id"]]
    if task["course"]:
        parts.append(f" · {task['course']}")
    if task["due"]:
        parts.append(f" · due {task['due']}")
    parts.append("）")
    return "".join(parts)


def build_digest(db_path: str, week: str | None = None) -> str:
    """Render the four-section weekly digest for one ISO week（契约 §8 签名）。"""

    monday, sunday = resolve_week(week)
    year, week_number, _ = monday.isocalendar()
    next_monday, next_sunday = monday + timedelta(days=7), sunday + timedelta(days=7)

    completed: list[str] = []
    running: list[str] = []
    risks: list[str] = []
    plans: list[tuple[str, str]] = []
    planned: set[str] = set()

    for history in state.task_histories(db_path):
        task = history["task"]
        status = task["status"]
        headline = _describe(task)
        if status == "done" or _done_added_within(history["revisions"], monday, sunday):
            items = "；".join(task["done"]) if task["done"] else "（无明细）"
            completed.append(f"- {headline}：{items}")
        if status != "done" and (task["doing"] or task["next"]):
            step = task["next"][0] if task["next"] else task["doing"][0]
            running.append(f"- {headline}：下一步 {step}")
        if task["blockers"]:
            risks.append(f"- {headline}：阻塞 {'；'.join(task['blockers'])}")
        elif task["due"] and _in_range(task["due"], next_monday, next_sunday) and status != "done":
            risks.append(f"- {headline}：due 落在下周（{task['due']}）且未完成")
        if status != "done":
            for item in task["next"]:
                if item not in planned:
                    planned.add(item)
                    plans.append((item, task["title"]))

    lines = [f"# 学研台周报 {year}-W{week_number:02d}（{monday.isoformat()} ~ {sunday.isoformat()}）"]
    bodies = (
        completed,
        running,
        risks,
        [f"- {item}（{owner}）" for item, owner in plans],
    )
    for heading, body in zip(_HEADINGS, bodies):
        lines.append("")
        lines.append(f"## {heading}")
        lines.append("")
        if body:
            lines.extend(body)
        else:
            lines.append(_EMPTY_SENTENCE)
    return "\n".join(lines) + "\n"
