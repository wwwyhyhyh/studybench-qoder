"""tasks.py 单测：严格校验与明确报错（契约 §7）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from studybench.tasks import TaskSchemaError, load_tasks

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_valid_fixture() -> None:
    records = load_tasks(FIXTURES / "tasks_valid.json")
    assert [record["task_id"] for record in records] == [
        "t-done-a",
        "t-doing-ds",
        "t-blocked-cmp",
        "t-next-week-phy",
        "t-idle",
    ]
    first = records[0]
    assert first["title"] == "物理实验：扭摆法数据处理"
    assert first["status"] == "done"
    assert first["done"] == ["拟合 Ix-x^2 图", "不确定度计算"]
    assert first["blockers"] == []
    for record in records:
        for field in ("task_id", "title", "course", "due", "priority", "status"):
            assert isinstance(record[field], str) and record[field]
        for field in ("done", "doing", "next", "blockers"):
            assert isinstance(record[field], list)


def test_single_string_accepted_for_list_fields(tmp_path: Path) -> None:
    path = tmp_path / "one.json"
    path.write_text(
        '{"tasks": [{"task_id": "t1", "title": "T", "course": "C", "due": "2026-11-01",'
        ' "priority": "high", "status": "doing", "done": "单条", "blockers": "卡住"}]}',
        encoding="utf-8",
    )
    record = load_tasks(path)[0]
    assert record["done"] == ["单条"]
    assert record["blockers"] == ["卡住"]


def test_missing_required_field_reports_field_and_index() -> None:
    with pytest.raises(TaskSchemaError) as info:
        load_tasks(FIXTURES / "tasks_missing_field.json")
    message = str(info.value)
    assert "title" in message
    assert "tasks[0]" in message


def test_bad_due_date_reports_field() -> None:
    with pytest.raises(TaskSchemaError) as info:
        load_tasks(FIXTURES / "tasks_bad_due.json")
    message = str(info.value)
    assert "due" in message
    assert "2026/11/01" in message


def test_duplicate_task_id_rejected() -> None:
    with pytest.raises(TaskSchemaError) as info:
        load_tasks(FIXTURES / "tasks_duplicate_id.json")
    assert "t-dup" in str(info.value)


def test_tasks_must_be_a_list() -> None:
    with pytest.raises(TaskSchemaError) as info:
        load_tasks(FIXTURES / "tasks_not_list.json")
    assert "数组" in str(info.value)


def test_top_level_tasks_key_required(tmp_path: Path) -> None:
    path = tmp_path / "no_tasks_key.json"
    path.write_text('{"items": []}', encoding="utf-8")
    with pytest.raises(TaskSchemaError) as info:
        load_tasks(path)
    assert "'tasks'" in str(info.value)


def test_top_level_must_be_object(tmp_path: Path) -> None:
    path = tmp_path / "top_list.json"
    path.write_text('[{"task_id": "t1"}]', encoding="utf-8")
    with pytest.raises(TaskSchemaError) as info:
        load_tasks(path)
    assert "顶层必须是对象" in str(info.value)


def test_missing_file_reports_path(tmp_path: Path) -> None:
    with pytest.raises(TaskSchemaError) as info:
        load_tasks(tmp_path / "nope.json")
    assert "nope.json" in str(info.value)


def test_invalid_json_reports_line(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"tasks": [}', encoding="utf-8")
    with pytest.raises(TaskSchemaError) as info:
        load_tasks(path)
    assert "JSON" in str(info.value)


def test_list_field_wrong_type_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad_list.json"
    path.write_text(
        '{"tasks": [{"task_id": "t1", "title": "T", "course": "C", "due": "2026-11-01",'
        ' "priority": "high", "status": "doing", "done": [1, 2]}]}',
        encoding="utf-8",
    )
    with pytest.raises(TaskSchemaError) as info:
        load_tasks(path)
    assert "'done'" in str(info.value)
