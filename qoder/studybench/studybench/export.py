"""index_export.json 生成（qoder/CONTRACTS.md §5，字段与语义冻结）。

只含演示语料（当前库内容），绝不导出个人工作区。``postings`` 的值是
``tf_eff``（落库 tf，已含标题 ×2 权重）；``df`` 与 ``postings`` 键集一致；
``avg_len`` 用与检索侧完全相同的浮点值（站点 BM25 parity 依赖）。
"""

from __future__ import annotations

import json
from pathlib import Path

from .search import B, K1
from .store import Store, now_iso
from .terms import STOPWORDS

#: 导出文件大小上限（契约 §5：≤ 3 MB）。
MAX_EXPORT_BYTES = 3 * 1024 * 1024


def build_export(db_path: str) -> dict:
    """从 seekdb 库构造 ``index_export.json`` 的完整 dict。"""

    store = Store(db_path)
    try:
        store.require_schema()
        docs = sorted(store.iter_docs(), key=lambda doc: doc["doc_id"])
        chunks = sorted(
            store.iter_chunks(), key=lambda chunk: (chunk["doc_id"], chunk["seq"])
        )
        postings: dict[str, dict[str, int]] = {}
        for chunk_id, term, tf in store.iter_term_rows():
            postings.setdefault(term, {})[chunk_id] = tf
        postings = {term: postings[term] for term in sorted(postings)}
        df = {term: len(by_chunk) for term, by_chunk in postings.items()}
        total_chars = sum(chunk["n_chars"] for chunk in chunks)
        avg_len = total_chars / len(chunks) if chunks else 0.0

        return {
            "version": 1,
            "meta": {
                "project": "学研台 StudyBench",
                "corpus": "demo",
                "generated_at": now_iso(),
                "n_docs": len(docs),
                "n_chunks": len(chunks),
                "avg_len": avg_len,
                "k1": K1,
                "b": B,
                "stopwords": list(STOPWORDS),
            },
            "docs": [
                {
                    "doc_id": doc["doc_id"],
                    "path": doc["path"],
                    "title": doc["title"],
                    "course": doc["course"],
                    "kind": doc["kind"],
                    "mtime": doc["mtime"],
                }
                for doc in docs
            ],
            "chunks": [
                {
                    "chunk_id": chunk["chunk_id"],
                    "doc_id": chunk["doc_id"],
                    "seq": chunk["seq"],
                    "heading": chunk["heading"],
                    "line_start": chunk["line_start"],
                    "line_end": chunk["line_end"],
                    "text": chunk["text"],
                    "n_chars": chunk["n_chars"],
                }
                for chunk in chunks
            ],
            "postings": postings,
            "df": df,
        }
    finally:
        store.close()


def export_index(db_path: str, out_path: str) -> dict:
    """写出站点可用的自包含索引；返回摘要（契约 §6 export）。"""

    payload = build_export(db_path)
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_EXPORT_BYTES:
        raise ValueError(
            f"index_export.json 超过 3 MB 上限（当前 {len(encoded)} 字节）——"
            "导出只允许演示语料"
        )
    target = Path(out_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded)
    return {
        "out": str(target),
        "n_docs": payload["meta"]["n_docs"],
        "n_chunks": payload["meta"]["n_chunks"],
        "terms": len(payload["df"]),
        "bytes": len(encoded),
    }
