"""Temporary: per-query recall path + parity vs verification/expected_results.json.

Deleted before delivery.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/home/vertin/sb-run/qoder/studybench")

from studybench import search  # noqa: E402
from studybench.store import open_db  # noqa: E402
from studybench.terms import tokenize  # noqa: E402

DB = "/home/vertin/sb-run/.runtime/sb.db"
EXPECTED = "/mnt/e/CodeX/PowerContext-2026/qoder/verification/expected_results.json"

expected = json.load(open(EXPECTED, encoding="utf-8"))["results"]

store = open_db(DB)
print(f"{'query':<22} {'path':<10} {'ft':>4} {'cov':>4} {'hits':>5}  parity")
all_same = True
for item in expected:
    query = item["query"]
    terms = tokenize(query)
    ft = store.fulltext_recall(terms)
    cov = store.term_coverage(terms)
    outcome = search.search(DB, query, top=5)
    got_top5 = [
        {
            "chunk_id": hit.chunk_id,
            "score": round(hit.score, 6),
            "path": hit.path,
            "heading": hit.heading,
            "line_start": hit.line_start,
        }
        for hit in outcome.hits[:5]
    ]
    same = got_top5 == item["top5"]
    all_same &= same
    path = "FT" if len(ft) > 0 else "FALLBACK"
    print(f"{query:<22} {path:<10} {len(ft):>4} {len(cov):>4} {outcome.n_hits:>5}  {'SAME' if same else 'DIFF'}")
    if not same:
        for i in range(max(len(got_top5), len(item['top5']))):
            x = got_top5[i] if i < len(got_top5) else None
            y = item["top5"][i] if i < len(item["top5"]) else None
            fmt = lambda r: "none" if r is None else f"{r['chunk_id']}@{r['score']}"
            print(f"   #{i+1} new={fmt(x)}  expected={fmt(y)}")
store.close()
print("all top5 identical to expected_results.json:", all_same)
