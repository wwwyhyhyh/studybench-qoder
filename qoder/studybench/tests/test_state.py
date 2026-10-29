"""state.py 单测：主仓接口证明、版本化、重启可读、看板排序（契约 §7）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from studybench import state


def test_uses_main_repo_powercontext_interfaces() -> None:
    """证明用的是主仓公共接口，而不是私有格式或同形替身。"""

    import powercontext
    import powercontext.context

    assert state.BACKEND == "powercontext"
    assert state.Sources is powercontext.context.Sources
    assert state.Artifacts is powercontext.context.Artifacts
    assert state.Source is powercontext.sources.models.Source
    assert state.SourceRef is powercontext.sources.models.SourceRef
    assert state.ArtifactDraft is powercontext.artifacts.models.ArtifactDraft
    assert state.POWERCONTEXT_LOCATION.endswith("powercontext/__init__.py")
    assert Path(state.POWERCONTEXT_LOCATION).is_file()
    # 自定义 family 是主仓 Artifact/ArtifactDraft 的子类，而非独立实现。
    assert issubclass(state.ProgressArtifact, powercontext.artifacts.models.Artifact)
    assert issubclass(state.ProgressDraft, powercontext.artifacts.models.ArtifactDraft)
    assert state.ProgressArtifact.family == "progress"


def test_add_update_resume_versioned(tmp_path: Path) -> None:
    db = str(tmp_path / "pc.db")
    created = state.add_task(
        db,
        {
            "task_id": "t-ds",
            "title": "数据结构大作业",
            "course": "数据结构",
            "due": "2026-11-05",
            "priority": "high",
        },
    )
    assert created["task_id"] == "t-ds"
    assert created["revision"] == 1
    assert created["status"] == "doing"

    state.update_task(db, "t-ds", {"done": "完成哈夫曼树构建"})
    updated = state.update_task(db, "t-ds", {"doing": ["写实验报告"], "blocker": "等测试数据"})

    assert updated["revision"] == 3
    resume = state.resume_task(db, "t-ds")
    assert resume["task_id"] == "t-ds"
    assert resume["done"] == ["完成哈夫曼树构建"]
    assert resume["doing"] == ["写实验报告"]
    assert resume["blockers"] == ["等测试数据"]
    assert [item["revision"] for item in resume["revisions"]] == [1, 2, 3]
    assert resume["last_updated"] == resume["revisions"][-1]["updated_at"]
    # 每次 update 都留下一个可追溯的独立 revision（版本化）。
    board = state.list_tasks(db)
    assert board[0]["revision"] == 3
    assert board[0]["status"] == "doing"


def test_state_survives_process_restart(tmp_path: Path) -> None:
    """关闭后重开：每次调用都新开 SQLite 连接，重启后数据仍可读。"""

    db = str(tmp_path / "pc.db")
    spec = {
        "task_id": "t-phy",
        "title": "物理实验：扭摆法数据处理",
        "course": "物理实验",
        "due": "2026-10-27",
        "priority": "high",
    }
    state.add_task(db, spec)
    state.update_task(db, "t-phy", {"done": ["拟合 Ix-x^2 图"], "status": "done"})
    first = state.resume_task(db, "t-phy")
    assert Path(db).is_file()

    # 模拟重启：resume_task/list_tasks 各自重新打开数据库文件。
    again = state.resume_task(db, "t-phy")
    assert again == first
    board = state.list_tasks(db)
    assert board[0]["task_id"] == "t-phy"
    assert board[0]["status"] == "done"
    assert board[0]["done"] == ["拟合 Ix-x^2 图"]
    # 重启后仍可继续追加版本。
    state.update_task(db, "t-phy", {"decision": {"text": "报告定稿"}})
    resumed = state.resume_task(db, "t-phy")
    assert len(resumed["revisions"]) == 3
    assert resumed["decisions"][-1]["text"] == "报告定稿"


def test_list_tasks_blockers_first_then_due_ascending(tmp_path: Path) -> None:
    db = str(tmp_path / "pc.db")
    state.add_task(db, {"task_id": "t-late", "title": "晚到期", "due": "2026-11-20"})
    state.add_task(db, {"task_id": "t-early", "title": "早到期", "due": "2026-11-01"})
    state.add_task(db, {"task_id": "t-blocked", "title": "被阻塞", "due": "2026-11-10"})
    state.add_task(db, {"task_id": "t-blocked-early", "title": "被阻塞且早", "due": "2026-11-02"})
    state.update_task(db, "t-late", {"blocker": "缺依赖"})
    state.update_task(db, "t-blocked", {"blocker": "等审批"})
    state.update_task(db, "t-blocked-early", {"blocker": "等数据"})

    order = [task["task_id"] for task in state.list_tasks(db)]
    # blockers 非空置顶（三个被阻塞者内部按 due 升序），其余按 due 升序。
    assert order == ["t-blocked-early", "t-blocked", "t-late", "t-early"]


def test_update_status_patch_and_effective_status(tmp_path: Path) -> None:
    db = str(tmp_path / "pc.db")
    state.add_task(db, {"task_id": "t-a", "title": "任务 A", "due": "2026-11-01"})
    state.update_task(db, "t-a", {"status": "done", "done": "全部完成"})
    board = state.list_tasks(db)
    assert board[0]["status"] == "done"
    assert board[0]["done"] == ["全部完成"]
    resume = state.resume_task(db, "t-a")
    assert resume["task"]["status"] == "doing"  # Source metadata 保留初始值
    assert resume["done"] == ["全部完成"]


def test_add_task_idempotent_but_conflicting(tmp_path: Path) -> None:
    db = str(tmp_path / "pc.db")
    spec = {
        "task_id": "t-x",
        "title": "同一个任务",
        "course": "数据结构",
        "due": "2026-11-01",
        "priority": "medium",
    }
    state.add_task(db, spec)
    state.add_task(db, dict(spec))  # 完全相同 → 幂等
    assert len(state.list_tasks(db)) == 1
    with pytest.raises(ValueError, match="different spec"):
        state.add_task(db, {**spec, "title": "另一个题目"})


def test_patch_and_lookup_errors(tmp_path: Path) -> None:
    db = str(tmp_path / "pc.db")
    state.add_task(db, {"task_id": "t-a", "title": "任务 A", "due": "2026-11-01"})
    with pytest.raises(ValueError, match="unsupported patch keys"):
        state.update_task(db, "t-a", {"nonsense": 1})
    with pytest.raises(ValueError, match="due"):
        state.add_task(db, {"task_id": "t-b", "title": "任务 B", "due": "2026/11/02"})
    with pytest.raises(LookupError):
        state.resume_task(db, "t-missing")
    with pytest.raises(ValueError, match="empty"):
        state.update_task(db, "t-a", {})


def test_resume_reads_last_three_revisions(tmp_path: Path) -> None:
    db = str(tmp_path / "pc.db")
    state.add_task(db, {"task_id": "t-m", "title": "多版本任务", "due": "2026-11-01"})
    for index in range(5):
        state.update_task(db, "t-m", {"done": f"第 {index} 步"})
    resume = state.resume_task(db, "t-m")
    assert [item["revision"] for item in resume["revisions"]] == [4, 5, 6]
    assert resume["done"] == ["第 4 步"]
