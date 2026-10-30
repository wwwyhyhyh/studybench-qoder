"""相关块推荐：源块词项 → 其他块的词项重合度（qoder/CONTRACTS.md 补充口径）。

1. 从 ``chunk_terms`` 取源块的词项，按 ``tf`` 降序取前 30 个（tf 相同按词项升序，稳定）。
2. 到其他块里按词项交集打分：``score(c) = Σ_{t ∈ terms(源) ∩ terms(c)} idf(t)``，
   ``idf`` 与 :mod:`studybench.search` 的 ``_idf`` 完全一致（``df`` 取全库、``N`` 为块总数）。
3. 排除源块自身与同文档的其他块（即「同文档同块」）。
4. 排序：score 降序 → chunk_id 升序（多趟稳定排序，结果可复现）。

只读路径：仅 ``require_schema``，不做 DDL，也不写 ``query_log``（这不是一次查询）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .search import _idf
from .store import Store, escape_sql

#: 源块参与比对的词项上限（按 tf 降序）。
SOURCE_TERM_LIMIT = 30

#: CLI 默认显示的条数。
DEFAULT_TOP = 5


@dataclass
class RelatedHit:
    """一条相关块命中（对外只输出契约点名的五个字段）。"""

    chunk_id: str
    score: float
    path: str
    heading: str
    line_start: int
    # 内部字段：人读输出的公共词项分解，不进入 as_dict。
    matched_terms: list[str]
    score_parts: list[tuple[str, float]]

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "score": round(self.score, 6),
            "path": self.path,
            "heading": self.heading,
            "line_start": self.line_start,
        }


@dataclass
class RelatedOutcome:
    """一次相关块推荐的结果（含空结果）。"""

    chunk: str
    terms: list[str]
    hits: list[RelatedHit]
    n_chunks: int
    elapsed_ms: int

    @property
    def n_hits(self) -> int:
        return len(self.hits)

    def as_dict(self, top: int | None = None) -> dict:
        shown = self.hits if top is None else self.hits[: max(0, top)]
        return {
            "chunk": self.chunk,
            "terms": list(self.terms),
            "n_hits": self.n_hits,
            "n_chunks": self.n_chunks,
            "elapsed_ms": self.elapsed_ms,
            "results": [hit.as_dict() for hit in shown],
        }


def related(db_path: str, chunk_id: str) -> RelatedOutcome:
    """返回与 ``chunk_id`` 词项重合度最高的全部块（排序后，展示条数由调用方截断）。

    源块不存在时抛 :class:`LookupError`（CLI 映射为退出码 2）；无命中时
    ``n_hits == 0``（CLI 映射为退出码 4）。
    """

    started = time.perf_counter()
    store = Store(db_path)
    try:
        store.require_schema()
        source_rows = store.fetch_chunk_rows([chunk_id])
        if not source_rows:
            raise LookupError(f"块不存在：{chunk_id}")
        source = source_rows[0]

        term_rows = store.execute(
            "SELECT term, tf FROM chunk_terms WHERE chunk_id = "
            + escape_sql(chunk_id)
            + f" ORDER BY tf DESC, term ASC LIMIT {SOURCE_TERM_LIMIT}"
        )
        terms = [str(row[0]) for row in term_rows]

        n_chunks = int(store.one("SELECT COUNT(*) FROM chunks")[0])
        hits: list[RelatedHit] = []
        if terms and n_chunks:
            # 全库取源词项的 (term, chunk_id, tf)：df 与 search 同口径（含源块自身）。
            df: dict[str, int] = {}
            terms_by_chunk: dict[str, set[str]] = {}
            for term, cid, _tf in store.fetch_term_rows(terms):
                df[term] = df.get(term, 0) + 1  # (chunk_id, term) 主键保证唯一
                terms_by_chunk.setdefault(cid, set()).add(term)
            idf_by_term = {term: _idf(df[term], n_chunks) for term in df}

            candidate_ids = [cid for cid in terms_by_chunk if cid != chunk_id]
            for row in store.fetch_chunk_rows(candidate_ids):
                # 排除同文档的其他块（「同文档同块」）。
                if row["doc_id"] == source["doc_id"]:
                    continue
                shared = terms_by_chunk.get(row["chunk_id"], set())
                common = [term for term in terms if term in shared]
                if not common:
                    continue
                score_parts = [(term, idf_by_term[term]) for term in common]
                score = 0.0
                for _term, value in score_parts:
                    score += value
                hits.append(
                    RelatedHit(
                        chunk_id=row["chunk_id"],
                        score=score,
                        path=row["path"],
                        heading=row["heading"],
                        line_start=row["line_start"],
                        matched_terms=common,
                        score_parts=score_parts,
                    )
                )
            # 多趟稳定排序（等价于 score↓, chunk_id↑）。
            hits.sort(key=lambda hit: hit.chunk_id)
            hits.sort(key=lambda hit: hit.score, reverse=True)

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return RelatedOutcome(
            chunk=chunk_id,
            terms=terms,
            hits=hits,
            n_chunks=n_chunks,
            elapsed_ms=elapsed_ms,
        )
    finally:
        store.close()


__all__ = [
    "DEFAULT_TOP",
    "SOURCE_TERM_LIMIT",
    "RelatedHit",
    "RelatedOutcome",
    "related",
]
