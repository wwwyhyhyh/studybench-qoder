"""学研台 StudyBench：seekdb 混合检索（A）+ PowerContext 任务记忆（B）。

包内模块保持轻量导入：检索引擎（terms/store/ingest/search/export/evidence）
与命令接线（cli）由调用方按需 import；B 的 state/tasks/digest 依赖主仓
``powercontext``，一律由 cli 惰性导入。
"""

from __future__ import annotations

__version__ = "1.0.0"
