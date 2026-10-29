"""tasks.json 读取与严格校验（qoder/CONTRACTS.md §7：D 产出，B 读取）。

契约形状::

    {"tasks": [{"task_id": "t-tou", "title": "物理实验：扭摆法数据处理",
                "course": "物理实验", "due": "2026-10-27", "priority": "high",
                "status": "done", "done": [...], "doing": [], "next": [...],
                "blockers": [...]}, ...]}

缺字段、类型不符、日期非法、task_id 重复都会抛出带明确位置信息的
:class:`TaskSchemaError`（``ValueError`` 子类）。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

#: 每个任务必须具备的字符串字段（契约 §7 样例）。
REQUIRED_FIELDS = ("task_id", "title", "course", "due", "priority", "status")

#: 可选的字符串数组字段（缺省为空列表）。
LIST_FIELDS = ("done", "doing", "next", "blockers")


class TaskSchemaError(ValueError):
    """tasks.json 不符合契约（缺字段 / 类型错 / 日期非法 / 重复 id）。"""


def load_tasks(path: str | Path) -> list[dict]:
    """Read and strictly validate a tasks.json file, returning normalized records."""

    file_path = Path(path)
    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError as error:
        raise TaskSchemaError(f"tasks.json 无法读取 {file_path}: {error}") from error
    try:
        document: Any = json.loads(raw)
    except json.JSONDecodeError as error:
        raise TaskSchemaError(
            f"tasks.json 不是合法 JSON（{file_path}）：第 {error.lineno} 行 {error.msg}"
        ) from error

    if not isinstance(document, dict):
        raise TaskSchemaError(
            f"tasks.json 顶层必须是对象（{file_path}），得到 {type(document).__name__}"
        )
    if "tasks" not in document:
        raise TaskSchemaError(f"tasks.json 缺少顶层字段 'tasks'（{file_path}）")
    items = document["tasks"]
    if not isinstance(items, list):
        raise TaskSchemaError(
            f"tasks.json 的 'tasks' 必须是数组（{file_path}），得到 {type(items).__name__}"
        )

    records: list[dict] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        where = f"{file_path} tasks[{index}]"
        if not isinstance(item, dict):
            raise TaskSchemaError(f"{where} 必须是对象，得到 {type(item).__name__}")
        for field in REQUIRED_FIELDS:
            if field not in item:
                raise TaskSchemaError(f"{where} 缺少必填字段 '{field}'")
            value = item[field]
            if not isinstance(value, str):
                raise TaskSchemaError(
                    f"{where} 字段 '{field}' 必须是字符串，得到 {type(value).__name__}"
                )
            if not value.strip():
                raise TaskSchemaError(f"{where} 字段 '{field}' 不能为空字符串")
        task_id = item["task_id"].strip()
        if task_id in seen:
            raise TaskSchemaError(f"{where} task_id 重复：{task_id!r}")
        seen.add(task_id)
        try:
            date.fromisoformat(item["due"].strip())
        except ValueError as error:
            raise TaskSchemaError(
                f"{where} 字段 'due' 不是合法日期（YYYY-MM-DD）：{item['due']!r}"
            ) from error

        record: dict[str, Any] = {field: item[field].strip() for field in REQUIRED_FIELDS}
        for field in LIST_FIELDS:
            value = item.get(field, [])
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list) or not all(isinstance(entry, str) for entry in value):
                raise TaskSchemaError(f"{where} 字段 '{field}' 必须是字符串数组")
            record[field] = list(value)
        records.append(record)
    return records
