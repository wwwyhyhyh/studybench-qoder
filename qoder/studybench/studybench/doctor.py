"""``studybench doctor``：环境与数据自检。

逐项打印 ``[OK]`` / ``[FAIL]`` 与细节，任何一项失败即给出可操作的下一步（装依赖、
跑 ingest、补语料）。检查顺序即依赖顺序——先确认解释器与依赖能导入，再谈库与数据。

只读原则：除 ②（临时目录里开一个探针库，用完删除）之外，不碰任何用户数据，
也不做 DDL（契约 §3：只读路径禁止建表）。
"""

from __future__ import annotations

import importlib
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

#: 契约 §2：运行环境要求 Python ≥ 3.12。
MIN_PYTHON = (3, 12)

#: 契约 §9：``corpus_demo/_queries.json`` 至少 10 条演示查询。
MIN_QUERY_ITEMS = 10

#: 演示查询文件按包内位置定位（``<qoder 根>/corpus_demo/_queries.json``），不受 CWD 影响。
QUERIES_PATH = Path(__file__).resolve().parents[2] / "corpus_demo" / "_queries.json"


@dataclass(frozen=True)
class Check:
    """一项检查的结果：项目名、是否通过、给人看的细节。"""

    name: str
    ok: bool
    detail: str


def _ok(name: str, detail: str) -> Check:
    return Check(name, True, detail)


def _bad(name: str, detail: str) -> Check:
    return Check(name, False, detail)


def _error_detail(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def _dist_version(name: str) -> str:
    """发行版版本号；取不到时返回 ``?``（不影响检查结论）。"""

    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return "?"


# ---------------------------------------------------------------- ① 解释器


def check_python() -> Check:
    current = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info < MIN_PYTHON:
        required = ".".join(str(part) for part in MIN_PYTHON)
        return _bad("Python 版本", f"需要 ≥ {required}，当前 {current}")
    return _ok("Python 版本", current)


# ---------------------------------------------------------------- ② 检索依赖


def check_seekdb() -> Check:
    """pylibseekdb 可 import，且能在临时目录真的开库建表（探针库用完删除）。"""

    try:
        importlib.import_module("pylibseekdb")
    except ImportError as error:
        return _bad("pylibseekdb", f"导入失败：{_error_detail(error)}；WSL 内 pip install pylibseekdb")
    probe_dir = Path(tempfile.mkdtemp(prefix="sb-doctor-"))
    try:
        from .store import Store

        with Store(str(probe_dir / "probe.db")) as store:
            store.ensure_schema()
            chunks = int(store.stats()["chunks"])
    except Exception as error:
        return _bad("pylibseekdb", f"临时目录开库失败：{_error_detail(error)}")
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)
    return _ok("pylibseekdb", f"{_dist_version('pylibseekdb')}｜探针库建表可读（块 {chunks}），临时目录已删除")


# ---------------------------------------------------------------- ③ 记忆层依赖


def check_powercontext() -> Check:
    try:
        importlib.import_module("powercontext")
    except ImportError as error:
        return _bad("powercontext", f"导入失败：{_error_detail(error)}；WSL 内 pip install 'powercontext[builtin]'")
    try:
        from . import state
    except Exception as error:
        return _bad("powercontext", f"studybench.state 导入失败：{_error_detail(error)}")
    return _ok("powercontext", f"{_dist_version('powercontext')}｜STORAGE_BACKEND={state.STORAGE_BACKEND}")


# ---------------------------------------------------------------- ④ seekdb 库


def check_library(db: str) -> Check:
    """库文件存在且 ``chunks`` 表可查（Store + require_schema，只读）。"""

    path = Path(db).expanduser()
    if not path.exists():
        return _bad("seekdb 库", f"不存在：{path}——先运行 studybench ingest --src qoder/corpus_demo")
    try:
        from .store import Store

        store = Store(str(path))
        try:
            store.require_schema()
            chunks = int(store.one("SELECT COUNT(*) FROM chunks")[0])
        finally:
            store.close()
    except Exception as error:
        return _bad("seekdb 库", f"{path}｜{_error_detail(error)}")
    return _ok("seekdb 库", f"{path}｜chunks 表可查（{chunks} 行）")


# ---------------------------------------------------------------- ⑤ 索引规模


def check_index_stats(db: str) -> Check:
    """``studybench index`` 的三项统计（文档 / 块 / 词项）。"""

    path = Path(db).expanduser()
    if not path.exists():
        return _bad("索引统计", f"库不存在：{path}——先运行 studybench ingest --src qoder/corpus_demo")
    try:
        from .store import Store

        store = Store(str(path))
        try:
            stats = store.stats()
        finally:
            store.close()
    except Exception as error:
        # 表不存在等原始错误对使用者没有行动指引，统一落到「先 ingest」
        return _bad(
            "索引统计",
            f"{_error_detail(error)}——库未初始化或已损坏，先运行 studybench ingest --src qoder/corpus_demo",
        )
    if stats["chunks"] == 0:
        return _bad("索引统计", "文档 0 篇｜块 0 个｜词项 0 个——先运行 studybench ingest --src qoder/corpus_demo")
    return _ok(
        "索引统计",
        f"文档 {stats['docs']} 篇｜块 {stats['chunks']} 个｜词项 {stats['terms']} 个"
        f"｜平均块长 {stats['avg_len']:.1f}",
    )


# ---------------------------------------------------------------- ⑥ 演示语料


def check_queries() -> Check:
    if not QUERIES_PATH.exists():
        return _bad("演示查询", f"缺失：{QUERIES_PATH}")
    try:
        payload = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return _bad("演示查询", f"{QUERIES_PATH}｜{_error_detail(error)}")
    items = payload.get("queries") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return _bad("演示查询", f"{QUERIES_PATH}｜缺少 queries 数组")
    if len(items) < MIN_QUERY_ITEMS:
        return _bad("演示查询", f"{QUERIES_PATH}｜只有 {len(items)} 条，需要 ≥ {MIN_QUERY_ITEMS}")
    return _ok("演示查询", f"{len(items)} 条｜{QUERIES_PATH}")


# ---------------------------------------------------------------- 汇总


def check_all(db: str) -> list[Check]:
    """跑完全部六项（单项失败不中断，问题一次看全）。"""

    return [
        check_python(),
        check_seekdb(),
        check_powercontext(),
        check_library(db),
        check_index_stats(db),
        check_queries(),
    ]


def report(checks: list[Check]) -> None:
    for index, check in enumerate(checks, start=1):
        tag = "OK" if check.ok else "FAIL"
        print(f"[{tag}] {index}. {check.name}：{check.detail}")
