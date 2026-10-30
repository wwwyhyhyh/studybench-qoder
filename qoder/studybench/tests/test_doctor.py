"""doctor 单测：正常路径 / pylibseekdb 缺失 / 库未初始化（退出码 0 与 3）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from studybench import cli, doctor, ingest
from studybench.store import Store

MINI = Path(__file__).parent / "fixtures" / "mini"

#: 检查项顺序（①→⑥），报告与退出码都按它走。
NAMES = ["Python 版本", "pylibseekdb", "powercontext", "seekdb 库", "索引统计", "演示查询"]


@pytest.fixture()
def seeded_db(tmp_path: Path) -> str:
    """已 ingest 过 mini 语料的 seekdb 库（④⑤ 的正常数据）。"""

    db = str(tmp_path / "sb.db")
    assert ingest.ingest_directory(str(MINI), db)["chunks"] == 9
    return db


def test_doctor_all_ok_and_exit_zero(seeded_db: str, capsys: pytest.CaptureFixture[str]) -> None:
    checks = doctor.check_all(seeded_db)
    assert [check.name for check in checks] == NAMES
    assert all(check.ok for check in checks), [
        f"{check.name}：{check.detail}" for check in checks if not check.ok
    ]
    assert cli.main(["doctor", "--db", seeded_db]) == 0
    out = capsys.readouterr().out
    assert out.count("[OK]") == len(NAMES)
    assert "[FAIL]" not in out
    # ③ 要如实打印存储引擎标识（契约 §7：官方关系型仓储）。
    from studybench import state

    assert f"STORAGE_BACKEND={state.STORAGE_BACKEND}" in out


def test_doctor_reports_missing_pylibseekdb(
    seeded_db: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setitem(sys.modules, "pylibseekdb", None)  # 模拟依赖未安装

    check = doctor.check_seekdb()
    assert not check.ok
    assert "导入失败" in check.detail

    assert cli.main(["doctor", "--db", seeded_db]) == 3
    out = capsys.readouterr().out
    assert f"[FAIL] 2. {NAMES[1]}：" in out


def test_doctor_flags_uninitialized_db(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "empty.db"
    Store(str(db)).close()  # 建出库但不建表（只读路径不做 DDL）

    checks = doctor.check_all(str(db))
    failed = [check.name for check in checks if not check.ok]
    assert failed == [NAMES[3], NAMES[4]]
    assert "ingest" in checks[3].detail
    assert "ingest" in checks[4].detail

    assert cli.main(["doctor", "--db", str(db)]) == 3
    assert cli.main(["doctor", "--db", str(tmp_path / "nope.db")]) == 3
    assert "不存在" in doctor.check_library(str(tmp_path / "nope.db")).detail


def test_doctor_queries_needs_ten_items(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert doctor.check_queries().ok  # 契约 §9：演示语料自带 ≥ 10 条查询

    short = tmp_path / "_queries.json"
    short.write_text('{"queries": [{"query": "甲"}]}', encoding="utf-8")
    monkeypatch.setattr(doctor, "QUERIES_PATH", short)
    check = doctor.check_queries()
    assert not check.ok and "需要 ≥ 10" in check.detail

    monkeypatch.setattr(doctor, "QUERIES_PATH", tmp_path / "missing.json")
    assert not doctor.check_queries().ok
