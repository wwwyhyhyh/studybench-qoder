"""候选召回 + BM25 重排 + 引用（qoder/CONTRACTS.md §4.2、§4.3）。

BM25（n_chars 长度归一，Python 与 JS 逐条一致）::

    idf(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
    score(c) = Σ_{t ∈ query_terms ∩ terms(c)}
               idf(t) * tf_eff * (k1 + 1) / (tf_eff + k1 * (1 - b + b * n_chars(c) / avg_len))
    tf_eff(t,c) = tf_text + 2 * tf_heading      # 已并入落库的 tf
    k1 = 1.2, b = 0.75

排序：score 降序 → heading_hit 降序 → mtime 降序 → chunk_id 升序。
求和顺序 = 查询词项的首次出现顺序（浮点确定性，parity 依赖）。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from .store import Store, StoreError, now_iso
from .terms import tokenize

#: BM25 参数（契约 §4.2，与导出 meta 一致）。
K1 = 1.2
B = 0.75

#: 摘录最大长度（契约 §4.3：≤160 字，命中词前后截取）。
EXCERPT_WIDTH = 160

_EXCERPT_CONTEXT = 40


@dataclass
class SearchHit:
    """一条检索命中（输出字段即契约 §4.3 规定的集合）。"""

    chunk_id: str
    score: float
    path: str
    heading: str
    line_start: int
    line_end: int
    excerpt: str
    matched_terms: list[str]
    score_parts: list[tuple[str, float]] = field(default_factory=list)
    # 内部字段：排序与过滤用，不进入 as_dict。
    heading_hit: int = 0
    mtime: str = ""
    course: str = ""
    kind: str = ""

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "score": round(self.score, 6),
            "path": self.path,
            "heading": self.heading,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "excerpt": self.excerpt,
            "matched_terms": list(self.matched_terms),
            "score_parts": [[term, round(value, 6)] for term, value in self.score_parts],
        }


@dataclass
class SearchOutcome:
    """一次检索的完整结果（含空结果）。"""

    query: str
    terms: list[str]
    hits: list[SearchHit]
    n_chunks: int
    avg_len: float
    elapsed_ms: int

    @property
    def n_hits(self) -> int:
        return len(self.hits)

    def as_dict(self, top: int | None = None) -> dict:
        shown = self.hits if top is None else self.hits[: max(0, top)]
        return {
            "query": self.query,
            "terms": list(self.terms),
            "n_hits": self.n_hits,
            "n_chunks": self.n_chunks,
            "avg_len": self.avg_len,
            "elapsed_ms": self.elapsed_ms,
            "results": [hit.as_dict() for hit in shown],
        }


def make_excerpt(text: str, matched_terms: list[str], width: int = EXCERPT_WIDTH) -> str:
    """命中词前后截取的 ≤160 字摘录；未命中正文时取开头。"""

    if len(text) <= width:
        return text
    positions = [pos for pos in (text.find(term) for term in matched_terms) if pos >= 0]
    pos = min(positions) if positions else 0
    start = max(0, pos - _EXCERPT_CONTEXT)
    end = start + width - 2  # 两侧省略号最多占 2 字
    if end >= len(text):
        end = len(text)
    start = max(0, end - (width - 2))
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end] + suffix


def _idf(df: int, n: int) -> float:
    return math.log(1 + (n - df + 0.5) / (df + 0.5))


def search(
    db_path: str,
    query: str,
    course: str | None = None,
    kind: str | None = None,
    since: str | None = None,
    top: int = 10,
) -> SearchOutcome:
    """执行一次检索并写 query_log（含空结果；契约 §4.3、§6）。"""

    started = time.perf_counter()
    terms_list = tokenize(query)
    store = Store(db_path)
    try:
        store.require_schema()
        n_chars_rows = [int(row[0]) for row in store.execute("SELECT n_chars FROM chunks")]
        n_chunks = len(n_chars_rows)
        avg_len = (sum(n_chars_rows) / n_chunks) if n_chunks else 0.0
        avg_norm = avg_len if avg_len > 0 else 1.0

        hits: list[SearchHit] = []
        if terms_list and n_chunks:
            # 召回：FULLTEXT 优先，空则退回 chunk_terms 覆盖查询（契约 §4.3）。
            candidates = store.fulltext_recall(terms_list)
            if not candidates:
                candidates = store.term_coverage(terms_list)
            rows = store.fetch_chunk_rows(candidates)
            # 结构化过滤不参与打分（契约 §4.3）。
            rows = [
                row
                for row in rows
                if (course is None or row["course"] == course)
                and (kind is None or row["kind"] == kind)
                and (since is None or (row["mtime"] and row["mtime"] >= since))
            ]
            term_rows = store.fetch_term_rows(terms_list)
            df: dict[str, int] = {}
            tf_by_chunk: dict[str, dict[str, int]] = {}
            for term, chunk_id, tf in term_rows:
                df[term] = df.get(term, 0) + 1  # (chunk_id, term) 主键保证唯一
                tf_by_chunk.setdefault(chunk_id, {})[term] = tf
            idf_by_term = {term: _idf(df[term], n_chunks) for term in df}

            heading_cache: dict[str, set[str]] = {}
            for row in rows:
                tfs = tf_by_chunk.get(row["chunk_id"], {})
                matched = [term for term in terms_list if term in tfs]
                if not matched:
                    continue  # 召回token不等于查询词项时防御性跳过
                score = 0.0
                score_parts: list[tuple[str, float]] = []
                for term in matched:
                    tf_eff = tfs[term]
                    contribution = (
                        idf_by_term[term]
                        * tf_eff
                        * (K1 + 1)
                        / (tf_eff + K1 * (1 - B + B * row["n_chars"] / avg_norm))
                    )
                    score += contribution
                    score_parts.append((term, contribution))
                if row["heading"] not in heading_cache:
                    heading_cache[row["heading"]] = set(tokenize(row["heading"]))
                heading_hit = len(set(matched) & heading_cache[row["heading"]])
                hits.append(
                    SearchHit(
                        chunk_id=row["chunk_id"],
                        score=score,
                        path=row["path"],
                        heading=row["heading"],
                        line_start=row["line_start"],
                        line_end=row["line_end"],
                        excerpt=make_excerpt(row["text"], matched),
                        matched_terms=matched,
                        score_parts=score_parts,
                        heading_hit=heading_hit,
                        mtime=row["mtime"],
                        course=row["course"],
                        kind=row["kind"],
                    )
                )
            # 多趟稳定排序（等价于 score↓, heading_hit↓, mtime↓, chunk_id↑）。
            hits.sort(key=lambda hit: hit.chunk_id)
            hits.sort(key=lambda hit: hit.mtime, reverse=True)
            hits.sort(key=lambda hit: hit.heading_hit, reverse=True)
            hits.sort(key=lambda hit: hit.score, reverse=True)

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        store.log_query(
            ts=now_iso(),
            q=query,
            top_chunk=hits[0].chunk_id if hits else None,
            n_hits=len(hits),
            elapsed_ms=elapsed_ms,
        )
        return SearchOutcome(
            query=query,
            terms=terms_list,
            hits=hits,
            n_chunks=n_chunks,
            avg_len=avg_len,
            elapsed_ms=elapsed_ms,
        )
    finally:
        store.close()


__all__ = ["B", "EXCERPT_WIDTH", "K1", "SearchHit", "SearchOutcome", "StoreError", "search"]
