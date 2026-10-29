"""StudyBench 任务记忆层（qoder/CONTRACTS.md §7）——真用主仓 PowerContext 公共接口。

数据形状（契约 §7）：

- 一个任务 = 一个 ``powercontext.sources.Source``（source_type=``studybench.task``，
  ``name=task_id``，metadata 存 title/course/due/priority/status）。
- 一次进度更新 = 一个 ``powercontext.artifacts.Artifact``（family=``progress``，
  artifact_id=task_id）；每次 :func:`update_task` 追加一个不可变新 revision（版本化可追溯）。
- ``resume`` = 读该任务最近 3 个 progress revision。
- ``list_tasks`` = 每任务取最新 revision 渲染，按 ``due`` 升序、blockers 非空置顶。

主仓依赖与后端说明（如实声明，勿删）：

- 模型、组合根与**存储后端全部真用主仓 PowerContext**：已安装的
  ``powercontext[builtin]==1.4.1``（PyPI，含 aiosqlite 等 extras）。
  :data:`BACKEND` 恒为 ``"powercontext"``；包不可导入时在 import 期直接报错。
- 存储层 = 主仓官方关系型仓储 ``powercontext.builtin.persistence``：
  ``SQLiteProfile``（SQLite 文件，路径 ``--db``/``SB_PC_DB``）+ ``BUILTIN_TABLES``
  建库 + ``ScopeApplication.bootstrap_default()`` 提供 scope + ``SourceRepository``/
  ``ArtifactRepository`` 负责读写与 lineage 校验。异步仓储在同步对外签名内以
  ``asyncio.run()`` 包裹（契约四签名保持同步）。
  早期版本曾因 venv 缺 sqlalchemy/aiosqlite 而同形降级为自写 sqlite3 仓储；
  官方包安装后已切回官方实现，:data:`STORAGE_BACKEND` 如实标识当前引擎。

主仓源码定位：默认使用已安装的 ``powercontext`` 包；环境变量 ``SB_POWERCONTEXT_SRC``
或 ``POWERCONTEXT_SRC``（指向含 ``powercontext/__init__.py`` 的目录）可覆盖为
源码检出（例如主仓开发版）。
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel

#: Fixed +08:00 offset (契约 §7：ISO 周、本地时区 +08:00)。
CST = timezone(timedelta(hours=8))

#: Source type under which every task is recorded（契约 §7：kind="task"）。
TASK_SOURCE_TYPE = "studybench.task"

#: Artifact family that carries versioned progress snapshots.
PROGRESS_FAMILY = "progress"


def _bootstrap_powercontext_path() -> Path | None:
    """Optionally prefer a source checkout over the installed ``powercontext`` package.

    Only an explicit environment override is honored; no well-known directories
    are scanned, so the PyPI-installed package is the default provider.
    """

    for variable in ("SB_POWERCONTEXT_SRC", "POWERCONTEXT_SRC"):
        value = os.environ.get(variable)
        if not value:
            continue
        candidate = Path(value).expanduser()
        if (candidate / "powercontext" / "__init__.py").is_file():
            text = str(candidate)
            if text in sys.path:
                sys.path.remove(text)
            sys.path.insert(0, text)
            return candidate
    return None


_POWERCONTEXT_SRC = _bootstrap_powercontext_path()

try:  # 真用主仓公共接口与官方持久层：任何导入失败都应终止，而不是悄悄降级。
    import powercontext
    from powercontext.artifacts import Artifact, ArtifactDraft, ArtifactRef, ArtifactLineage
    from powercontext.builtin.persistence.artifacts import ArtifactRepository
    from powercontext.builtin.persistence.errors import (
        RepositoryNotFoundError,
        StoredPayloadConflictError,
    )
    from powercontext.builtin.persistence.sources import SourceRepository
    from powercontext.builtin.persistence.sqlite.profile import SQLiteConfig, SQLiteProfile
    from powercontext.builtin.persistence.tables import BUILTIN_TABLES
    from powercontext.builtin.scope.application import ScopeApplication
    from powercontext.context import Artifacts, Sources
    from powercontext.errors import (
        ArtifactNotFoundError,
        RevisionConflictError,
        SourceNotFoundError,
    )
    from powercontext.sources import (
        AdapterSourceDefinition,
        Source,
        SourceCatalog,
        SourceDefinitionRegistry,
        SourceMaterialization,
        SourceRef,
    )
except ImportError as error:  # pragma: no cover - environment guard
    raise ImportError(
        "studybench.state requires the main repository's powercontext package "
        "(powercontext[builtin]>=1.4.1, official persistence backend included). "
        "Alternatively set SB_POWERCONTEXT_SRC (or POWERCONTEXT_SRC) to a "
        "directory that contains powercontext/__init__.py."
    ) from error

if Sources.__module__ != "powercontext.context" or Source.__module__ != "powercontext.sources.models":
    raise ImportError("studybench.state imported a non-main-repository powercontext module")  # pragma: no cover

#: Identity of the active model layer: always the main repository's.
BACKEND = "powercontext"

#: Where the main repository's ``powercontext`` package was loaded from.
POWERCONTEXT_LOCATION = str(powercontext.__file__)

#: Official relational persistence engine behind the public store protocols.
STORAGE_BACKEND = "powercontext.builtin.persistence/sqlite"


class TaskSource(Source):
    """One task（契约 §7：kind="task"，metadata 存 title/course/due/priority/status）。"""

    kind: str = "task"
    metadata: dict[str, str] = {}


class DecisionRecord(BaseModel):
    """One recorded decision（契约 §7 body：``{"ts","text"}``）。"""

    ts: str
    text: str


class ProgressBody(BaseModel):
    """Body JSON of one progress artifact（契约 §7 形状，另存 status 便于看板渲染）。"""

    task_id: str
    done: list[str] = []
    doing: list[str] = []
    next: list[str] = []
    blockers: list[str] = []
    decisions: list[DecisionRecord] = []
    status: str = ""
    updated_at: str


class ProgressArtifact(Artifact[ProgressBody]):
    """One immutable progress snapshot revision."""

    family: ClassVar[str] = PROGRESS_FAMILY


class ProgressDraft(ArtifactDraft[ProgressBody]):
    """A proposed progress snapshot revision."""

    family: ClassVar[str] = PROGRESS_FAMILY


class _TaskAdapter:
    """Minimal adapter promoting :class:`TaskSource` into a source definition."""

    input_class = TaskSource
    name = TASK_SOURCE_TYPE
    source_class = TaskSource

    async def resolve(self, value: TaskSource, /) -> TaskSource:
        return value

    async def read(self, source: TaskSource, /) -> TaskSource:
        return source


def _definition_registry() -> SourceDefinitionRegistry:
    return SourceDefinitionRegistry([AdapterSourceDefinition(_TaskAdapter())])


def _progress_ref(task_id: str) -> ArtifactRef:
    return ArtifactRef(family=PROGRESS_FAMILY, artifact_id=task_id, revision=1)


class _SessionSources:
    """``SourceStore`` + ``SourceCatalogBackend`` over the official ``SourceRepository``."""

    def __init__(self, session: "_Session") -> None:
        self._session = session

    def _ref(self, source_id: str) -> SourceRef:
        return SourceRef(source_type=TASK_SOURCE_TYPE, source_id=source_id)

    async def add(self, source: Source, /) -> Source:
        """Persist one source; an identical re-add is idempotent, a changed one errors."""

        if type(source) is not TaskSource:
            raise ValueError(f"unsupported source type: {type(source).__name__}")
        try:
            async with self._session.transaction() as connection:
                await self._session.source_repository.add(connection, self._session.scope_id, source)
        except StoredPayloadConflictError as error:
            raise ValueError(
                f"task {source.name!r} already exists with a different spec; "
                "use update_task to record progress"
            ) from error
        return source

    async def get(self, source: Source, /) -> Source:
        """Return the canonical stored source matching ``source``（主仓协议语义）。"""

        stored = await self.load_source(source.name)
        if type(stored) is not type(source) or stored != source:
            raise SourceNotFoundError(source)
        return stored

    async def load_source(self, source_id: str, /) -> Source:
        """Return one task source by ``task_id``（按 id 查找，无需先知全量）。"""

        try:
            async with self._session.transaction() as connection:
                stored = await self._session.source_repository.get(
                    connection, self._session.scope_id, self._ref(source_id)
                )
        except RepositoryNotFoundError as error:
            raise SourceNotFoundError(self._ref(source_id)) from error
        return stored.value

    async def list(self) -> tuple[Source, ...]:
        """Return every stored task source in journal order."""

        async with self._session.transaction() as connection:
            rows = await self._session.source_repository.list(
                connection, self._session.scope_id, source_type=TASK_SOURCE_TYPE
            )
        return tuple(row.value for row in rows)


class _SessionArtifacts:
    """``ArtifactStore`` + ``ArtifactCatalog`` over the official ``ArtifactRepository``."""

    def __init__(self, session: "_Session") -> None:
        self._session = session

    async def add(self, draft: ArtifactDraft[ProgressBody], /) -> ProgressArtifact:
        """Commit revision one of a task's progress history."""

        if draft.family != PROGRESS_FAMILY or type(draft.content) is not ProgressBody:
            raise ValueError("studybench state only accepts progress drafts")
        try:
            async with self._session.transaction() as connection:
                return await self._session.artifact_repository.create(
                    connection, self._session.scope_id, draft.content.task_id, draft
                )
        except RevisionConflictError:
            raise  # add_task 把「同 spec 重复 add」当作幂等处理
        except RepositoryNotFoundError as error:  # lineage 指向的 source 不存在
            raise ArtifactNotFoundError(draft) from error

    async def revise(
        self,
        artifact: Artifact[ProgressBody],
        draft: ArtifactDraft[ProgressBody],
        /,
    ) -> ProgressArtifact:
        """Commit the next revision only when ``artifact`` is still the head."""

        if artifact.family != PROGRESS_FAMILY or draft.family != PROGRESS_FAMILY:
            raise ValueError("studybench state only accepts progress drafts")
        try:
            async with self._session.transaction() as connection:
                return await self._session.artifact_repository.revise(
                    connection, self._session.scope_id, artifact, draft
                )
        except RepositoryNotFoundError as error:
            raise ArtifactNotFoundError(artifact) from error

    async def get(self, artifact: ArtifactRef, /) -> ProgressArtifact:
        """Return one exact revision."""

        ref = ArtifactRef(
            family=artifact.family, artifact_id=artifact.artifact_id, revision=int(artifact.revision)
        )
        try:
            async with self._session.transaction() as connection:
                return await self._session.artifact_repository.get(connection, self._session.scope_id, ref)
        except RepositoryNotFoundError as error:
            raise ArtifactNotFoundError(ref) from error

    async def latest(self, artifact: ArtifactRef, /) -> ProgressArtifact:
        """Return the newest visible revision."""

        try:
            async with self._session.transaction() as connection:
                return await self._session.artifact_repository.latest(
                    connection, self._session.scope_id, PROGRESS_FAMILY, artifact.artifact_id
                )
        except RepositoryNotFoundError as error:
            raise ArtifactNotFoundError(artifact) from error

    async def revisions(self, artifact: ArtifactRef, /) -> tuple[ProgressArtifact, ...]:
        """Return the full history in ascending revision order."""

        async with self._session.transaction() as connection:
            return await self._session.artifact_repository.revisions(
                connection, self._session.scope_id, PROGRESS_FAMILY, artifact.artifact_id
            )


class _Session:
    """One open official-repository session over the ``SB_PC_DB`` SQLite file."""

    def __init__(self, db_path: str) -> None:
        path = Path(db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = path
        self.registry = _definition_registry()
        self.source_repository = SourceRepository(self.registry)
        self.artifact_repository = ArtifactRepository(
            (ProgressArtifact,), sources=self.source_repository
        )
        self._profile_context = None
        self.profile = None
        self.scope_id = ""
        self.source_store = None
        self.artifact_store = None
        self.sources = None
        self.artifacts = None

    async def __aenter__(self) -> "_Session":
        url = f"sqlite+aiosqlite:///{self.db_path}"
        self._profile_context = SQLiteProfile.open(SQLiteConfig(url=url), tables=BUILTIN_TABLES)
        self.profile = await self._profile_context.__aenter__()
        self.scope_id = (await ScopeApplication(self.profile.database).bootstrap_default()).scope_id
        self.source_store = _SessionSources(self)
        self.artifact_store = _SessionArtifacts(self)
        catalog = SourceCatalog(backend=self.source_store, registry=self.registry)
        self.sources = Sources(catalog=catalog, store=self.source_store)
        self.artifacts = Artifacts(catalog=self.artifact_store, store=self.artifact_store)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        assert self._profile_context is not None
        await self._profile_context.__aexit__(*exc_info)

    def transaction(self):
        """Own one official transaction for a single repository operation."""

        assert self.profile is not None
        return self.profile.database.transaction()


def _now() -> str:
    """Current timestamp in the contract timezone（测试可 monkeypatch 以获得确定性）。"""

    return datetime.now(CST).isoformat(timespec="seconds")


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, list):
        return [str(entry) for entry in value]
    raise ValueError(f"expected a string or a list of strings, got {type(value).__name__}")


def _as_decisions(value: Any, now: str) -> list[DecisionRecord]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    decisions: list[DecisionRecord] = []
    for item in items:
        if isinstance(item, str):
            decisions.append(DecisionRecord(ts=now, text=item))
            continue
        if not isinstance(item, dict) or not str(item.get("text", "")).strip():
            raise ValueError("decision must be {'text': str, 'ts'?: str} or a plain string")
        decisions.append(DecisionRecord(ts=str(item.get("ts") or now), text=str(item["text"])))
    return decisions


def _validate_due(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    try:
        date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"due must be an ISO date (YYYY-MM-DD), got {text!r}") from error
    return text


def _metadata_of(source: TaskSource) -> dict[str, str]:
    return {
        "title": str(source.metadata.get("title", "")),
        "course": str(source.metadata.get("course", "")),
        "due": str(source.metadata.get("due", "")),
        "priority": str(source.metadata.get("priority", "")),
        "status": str(source.metadata.get("status", "")),
    }


def _render_task(source: TaskSource, artifact: ProgressArtifact | None) -> dict[str, Any]:
    body = artifact.content if artifact is not None else None
    status = (body.status if body is not None else "") or _metadata_of(source)["status"]
    return {
        "task_id": source.name,
        **_metadata_of(source),
        "status": status,
        "done": list(body.done) if body is not None else [],
        "doing": list(body.doing) if body is not None else [],
        "next": list(body.next) if body is not None else [],
        "blockers": list(body.blockers) if body is not None else [],
        "decisions": [item.model_dump() for item in body.decisions] if body is not None else [],
        "revision": 0 if artifact is None else int(artifact.revision),
        "updated_at": body.updated_at if body is not None else "",
    }


def add_task(db_path: str, spec: dict) -> dict:
    """Record one task（契约 §7 签名）。spec 必填 task_id/title，其余键可选。"""

    if not isinstance(spec, dict):
        raise ValueError("add_task: spec must be a dict")
    task_id = str(spec.get("task_id", "")).strip()
    title = str(spec.get("title", "")).strip()
    if not task_id:
        raise ValueError("add_task: spec.task_id is required")
    if not title:
        raise ValueError("add_task: spec.title is required")
    due = _validate_due(spec.get("due"))
    now = _now()
    metadata = {
        "title": title,
        "course": str(spec.get("course", "") or "").strip(),
        "due": due,
        "priority": str(spec.get("priority", "") or "medium").strip(),
        "status": str(spec.get("status", "") or "doing").strip(),
    }
    body = ProgressBody(
        task_id=task_id,
        done=_as_str_list(spec.get("done")),
        doing=_as_str_list(spec.get("doing")),
        next=_as_str_list(spec.get("next")),
        blockers=_as_str_list(spec.get("blockers")),
        decisions=_as_decisions(spec.get("decisions"), now),
        status=metadata["status"],
        updated_at=now,
    )

    async def run() -> dict:
        async with _Session(db_path) as session:
            source = TaskSource(
                name=task_id,
                materialization=SourceMaterialization.CAPTURED,
                description=title,
                kind="task",
                metadata=metadata,
            )
            await session.sources.add(source)
            reference = session.sources.catalog.as_ref(source)
            try:
                await session.artifacts.add(ProgressDraft(content=body, sources=(reference,)))
            except RevisionConflictError:
                pass  # 同一 spec 重复 add：保留既有版本历史（幂等）
            return _render_task(source, await session.artifacts.latest(_progress_ref(task_id)))

    return asyncio.run(run())


_PATCH_KEYS = {"done", "doing", "next", "blocker", "blockers", "decision", "status"}


def update_task(db_path: str, task_id: str, patch: dict) -> dict:
    """Append one progress artifact revision（契约 §7 签名，版本化可追溯）。"""

    if not isinstance(patch, dict):
        raise ValueError("update_task: patch must be a dict")
    unknown = sorted(set(patch) - _PATCH_KEYS)
    if unknown:
        raise ValueError(f"update_task: unsupported patch keys {unknown}; allowed: {sorted(_PATCH_KEYS)}")
    task_id = str(task_id).strip()
    if not task_id:
        raise ValueError("update_task: task_id is required")
    if not patch:
        raise ValueError("update_task: patch is empty")
    now = _now()

    async def run() -> dict:
        async with _Session(db_path) as session:
            source = await session.source_store.load_source(task_id)
            latest = await session.artifacts.latest(_progress_ref(task_id))
            current = latest.content
            body = ProgressBody(
                task_id=task_id,
                done=_as_str_list(patch["done"]) if "done" in patch else list(current.done),
                doing=_as_str_list(patch["doing"]) if "doing" in patch else list(current.doing),
                next=_as_str_list(patch["next"]) if "next" in patch else list(current.next),
                blockers=(
                    list(current.blockers)
                    + _as_str_list(patch["blocker"] if "blocker" in patch else patch["blockers"])
                    if "blocker" in patch or "blockers" in patch
                    else list(current.blockers)
                ),
                decisions=(
                    list(current.decisions) + _as_decisions(patch["decision"], now)
                    if "decision" in patch
                    else list(current.decisions)
                ),
                status=str(patch["status"]).strip() if "status" in patch else current.status,
                updated_at=now,
            )
            reference = session.sources.catalog.as_ref(source)
            revised = await session.artifacts.revise(
                latest, ProgressDraft(content=body, sources=(reference,))
            )
            return _render_task(source, revised)

    return asyncio.run(run())


def list_tasks(db_path: str) -> list[dict]:
    """任务看板（契约 §7 签名）：blockers 非空置顶，其余按 due 升序。"""

    async def run() -> list[dict]:
        async with _Session(db_path) as session:
            rendered: list[dict[str, Any]] = []
            for source in await session.sources.list():
                try:
                    latest = await session.artifacts.latest(_progress_ref(source.name))
                except ArtifactNotFoundError:
                    latest = None
                rendered.append(_render_task(source, latest))
            rendered.sort(
                key=lambda item: (
                    0 if item["blockers"] else 1,
                    item["due"] or "9999-12-31",
                    item["task_id"],
                )
            )
            return rendered

    return asyncio.run(run())


def resume_task(db_path: str, task_id: str) -> dict:
    """读该任务最近 3 个 progress revision，输出「上次做到哪 / 卡在哪 / 下一步」。"""

    task_id = str(task_id).strip()
    if not task_id:
        raise ValueError("resume_task: task_id is required")

    async def run() -> dict:
        async with _Session(db_path) as session:
            source = await session.source_store.load_source(task_id)
            history = await session.artifacts.revisions(_progress_ref(task_id))
            if not history:
                raise ArtifactNotFoundError(_progress_ref(task_id))
            recent = history[-3:]
            latest = recent[-1]
            return {
                "task_id": task_id,
                "task": _metadata_of(source),
                "last_updated": latest.content.updated_at,
                "done": list(latest.content.done),
                "doing": list(latest.content.doing),
                "next": list(latest.content.next),
                "blockers": list(latest.content.blockers),
                "decisions": [item.model_dump() for item in latest.content.decisions],
                "revisions": [
                    {"revision": int(item.revision), "updated_at": item.content.updated_at}
                    for item in recent
                ],
            }

    return asyncio.run(run())


def task_histories(db_path: str) -> list[dict]:
    """每任务的完整 revision 历史（周报 ``digest`` 与审计使用）。"""

    async def run() -> list[dict]:
        async with _Session(db_path) as session:
            histories: list[dict] = []
            for source in await session.sources.list():
                history = await session.artifacts.revisions(_progress_ref(source.name))
                histories.append(
                    {
                        "task": _render_task(source, history[-1] if history else None),
                        "revisions": [
                            {
                                "revision": int(item.revision),
                                "updated_at": item.content.updated_at,
                                "done": list(item.content.done),
                                "doing": list(item.content.doing),
                                "next": list(item.content.next),
                                "blockers": list(item.content.blockers),
                                "status": item.content.status,
                            }
                            for item in history
                        ],
                    }
                )
            return histories

    return asyncio.run(run())
