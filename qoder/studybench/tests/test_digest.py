"""digest.py 单测：四段式、空段「本周无」、确定性、ISO 周（契约 §8）。"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from studybench import digest, state, tasks

FIXTURES = Path(__file__).parent / "fixtures"
WEEK = "2026-W44"  # 2026-10-26 ~ 2026-11-01（契约 §8 示例周）


def _prepare_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Import the fixture tasks with deterministic in-week timestamps."""

    db = str(tmp_path / "pc.db")
    monday, _ = digest.resolve_week(WEEK)
    monkeypatch.setattr(state, "_now", lambda: f"{monday.isoformat()}T10:00:00+08:00")
    for record in tasks.load_tasks(FIXTURES / "tasks_valid.json"):
        state.add_task(db, record)
    return db


def test_resolve_week_bounds() -> None:
    monday, sunday = digest.resolve_week(WEEK)
    assert monday.isoformat() == "2026-10-26"
    assert sunday.isoformat() == "2026-11-01"
    assert monday.isoweekday() == 1 and sunday.isoweekday() == 7
    with pytest.raises(ValueError, match="invalid week"):
        digest.resolve_week("2026/44")
    with pytest.raises(ValueError, match="invalid week"):
        digest.resolve_week("44-W2026")


def test_digest_four_fixed_sections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _prepare_database(tmp_path, monkeypatch)
    monday, sunday = digest.resolve_week(WEEK)
    text = digest.build_digest(db, WEEK)

    assert text.startswith("# 学研台周报 2026-W44（2026-10-26 ~ 2026-11-01）")
    assert f"（{monday.isoformat()} ~ {sunday.isoformat()}）" in text
    for heading in ("本周完成", "进行中", "风险与阻塞", "下周计划"):
        assert f"## {heading}" in text
    # 段落顺序固定。
    assert text.index("## 本周完成") < text.index("## 进行中")
    assert text.index("## 进行中") < text.index("## 风险与阻塞")
    assert text.index("## 风险与阻塞") < text.index("## 下周计划")


def test_digest_content_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _prepare_database(tmp_path, monkeypatch)
    text = digest.build_digest(db, WEEK)

    done_section = text.split("## 进行中")[0]
    # status=done 与「本周有 done 增量」（revision 1 在本周写入 done）都算完成。
    assert "物理实验：扭摆法数据处理" in done_section
    assert "数据结构大作业" in done_section
    # 进行中带下一步。
    running_section = text.split("## 进行中")[1].split("## 风险与阻塞")[0]
    assert "竞赛报名材料" in running_section
    assert "下一步 复习大数定律" in running_section
    assert "概率论习题课预习" in running_section
    assert "下一步 准备答辩" in running_section
    # 风险：blockers 非空 + due 落在下周未完成。
    risk_section = text.split("## 风险与阻塞")[1].split("## 下周计划")[0]
    assert "等老师签字" in risk_section
    assert "概率论习题课预习" in risk_section
    # 下周计划归并去重：跨任务重复的「复习大数定律」只出现一次。
    plan_section = text.split("## 下周计划")[1]
    assert plan_section.count("- 复习大数定律（") == 1
    assert "- 准备答辩（概率论习题课预习）" in plan_section
    # 无进展任务不出现。
    assert "整理实验数据归档" not in text


def test_digest_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _prepare_database(tmp_path, monkeypatch)
    first = digest.build_digest(db, WEEK)
    second = digest.build_digest(db, WEEK)
    assert first == second


def test_digest_empty_week_says_nothing_this_week(tmp_path: Path) -> None:
    db = str(tmp_path / "empty.db")
    text = digest.build_digest(db, WEEK)
    for heading in ("本周完成", "进行中", "风险与阻塞", "下周计划"):
        assert f"## {heading}" in text
    assert text.count("本周无") == 4


def test_digest_done_increment_from_update(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """本周通过 update 新增的 done 也计入「本周完成」，即使 status 仍非 done。"""

    db = str(tmp_path / "pc.db")
    monday, sunday = digest.resolve_week(WEEK)
    monkeypatch.setattr(state, "_now", lambda: f"{monday.isoformat()}T10:00:00+08:00")
    state.add_task(db, {"task_id": "t-inc", "title": "增量任务", "due": sunday.isoformat()})
    # 无 done、无 doing/next：四个段落都不会出现它。
    text = digest.build_digest(db, WEEK)
    assert "增量任务" not in text

    # 本周（周日）新增 done → 计入「本周完成」。
    monkeypatch.setattr(state, "_now", lambda: f"{sunday.isoformat()}T10:00:00+08:00")
    state.update_task(db, "t-inc", {"done": "本周才做完的一步"})
    text = digest.build_digest(db, WEEK)
    done_section = text.split("## 进行中")[0]
    assert "增量任务" in done_section

    # 下周的 update（新增 doing）不改变本周完成；任务仍在进行中则照常进入「进行中」。
    monkeypatch.setattr(
        state, "_now", lambda: f"{(sunday + timedelta(days=8)).isoformat()}T10:00:00+08:00"
    )
    state.update_task(db, "t-inc", {"doing": "推进第二步"})
    text = digest.build_digest(db, WEEK)
    done_section = text.split("## 进行中")[0]
    assert "增量任务" in done_section
    assert "推进第二步" not in done_section


def test_digest_default_week_is_current_iso_week(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = str(tmp_path / "empty.db")
    frozen = digest.resolve_week(WEEK)[0]
    monkeypatch.setattr(
        digest, "resolve_week", lambda week=None: (frozen, frozen + timedelta(days=6))
    )
    text = digest.build_digest(db)
    assert text.startswith("# 学研台周报 2026-W44（2026-10-26 ~ 2026-11-01）")
