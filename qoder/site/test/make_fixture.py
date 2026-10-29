# -*- coding: utf-8 -*-
"""site/test/fixture_index.json 生成器（仅站点测试资产，不参与运行时）。

期望值全部由**真实** studybench.terms（分词）+ search.py 公式（BM25 / 摘录 / 排序）
现算写入 fixture，因此 ``node parity.mjs`` 的 fixture 部分就是 JS 与 Python 的
直接对拍。运行：

    PYTHONPATH=qoder/studybench python qoder/site/test/make_fixture.py
"""

import json
import math
import sys

sys.path.insert(0, r"E:\CodeX\PowerContext-2026\qoder\studybench")
from studybench.terms import tokenize, tf_map, STOPWORDS  # noqa: E402

K1, B = 1.2, 0.75


def chunk_terms(heading, text):
    """ingest.py 逐字复刻：tf_eff = tf_text + 2 * tf_heading。"""

    counts = {}
    for term, count in tf_map(text).items():
        counts[term] = counts.get(term, 0) + count
    for term, count in tf_map(heading).items():
        counts[term] = counts.get(term, 0) + 2 * count
    return counts


def make_excerpt(text, matched_terms, width=160, ctx=40):
    """search.py 逐字复刻：≤160 字摘录，命中词前后截取。"""

    if len(text) <= width:
        return text
    positions = [p for p in (text.find(t) for t in matched_terms) if p >= 0]
    pos = min(positions) if positions else 0
    start = max(0, pos - ctx)
    end = start + width - 2
    if end >= len(text):
        end = len(text)
    start = max(0, end - (width - 2))
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end] + suffix


# ---- 手工设计的 4 docs / 8 chunks（每块只测一类行为） ----
DOC1 = {"doc_id": "d1a2b3c4", "path": "数据结构/树与二叉树.md", "title": "树与二叉树",
        "course": "数据结构", "kind": "笔记", "mtime": "2026-10-26"}
DOC2 = {"doc_id": "d5e6f7a8", "path": "数据库/索引与写放大.md", "title": "索引与写放大",
        "course": "数据库", "kind": "笔记", "mtime": "2026-10-28"}
DOC3 = {"doc_id": "d9b0c1d2", "path": "概率论/大数定律.md", "title": "大数定律与样本方差",
        "course": "概率论", "kind": "笔记", "mtime": "2026-10-26"}
DOC4 = {"doc_id": "de3f4a5b", "path": "竞赛/动态规划入门.md", "title": "动态规划入门",
        "course": "竞赛", "kind": "笔记", "mtime": "2026-10-30"}

LONG_C00 = ("编号是否连续，是判别两道高频选择题的入口；先记住入口，再看层数与性质。"
            "第 3 章的例题常用这一招设置陷阱。满二叉树每一层结点数都取到最大，深度为 k 时恰有 2^k 减一个结点；"
            "完全二叉树允许最后一层不满，但编号与同深度的满二叉树完全一致，缺口只能在最右侧。"
            "两者区别一句话：满二叉树是完全二叉树的特例，反之不成立。"
            "判别流程：先看编号，再数层数，最后用性质三交叉验证，考场上三十秒内可以做完。")
Q_TEXT = "查询计划参考列的统计信息，例如取值的方差与均值；方差越大，估算越保守。"
P_BASE = "随机变量的取值范围可以借助切比雪夫不等式估计，偏移越远概率越小。"
P_TEXT = P_BASE + " " * (len(Q_TEXT) - len(P_BASE))  # 纯空格补齐 n_chars，不新增词项

CHUNK_DEFS = [
    (DOC1, 0, "满二叉树与完全二叉树", LONG_C00, 3, 9),
    (DOC2, 0, "二级索引与写放大",
     "二级索引越多，写入时要同步维护的索引就越多，写放大随之出现；每次写入都要更新全部二级索引，"
     "这是索引过多的主要坏处。召回之后由ＢＭ２５完成重排，打分只看词频与块长。", 5, 12),
    (DOC2, 1, "统计信息与代价估算", Q_TEXT, 14, 17),
    (DOC3, 0, "贝塞尔校正与样本方差",
     "样本方差除以 n 减一而不是 n，是贝塞尔校正；除以 n 会系统性低估总体方差，自由度修正补足这一偏差。", 3, 8),
    (DOC3, 1, "方差的有界性", P_TEXT, 10, 13),
    (DOC3, 2, "补充", "状态转移方程的书写规范", 15, 15),
    (DOC4, 0, "引言", "状态转移方程的书写规范", 1, 1),
    (DOC4, 1, "小结", "状态转移方程的书写规范", 9, 9),
]

chunks = []
for doc, seq, heading, text, ls, le in CHUNK_DEFS:
    chunks.append({
        "chunk_id": "%s#c%02d" % (doc["doc_id"], seq), "doc_id": doc["doc_id"], "seq": seq,
        "heading": heading, "line_start": ls, "line_end": le, "text": text, "n_chars": len(text),
    })

postings = {}
for ch in chunks:
    for term, tf in chunk_terms(ch["heading"], ch["text"]).items():
        postings.setdefault(term, {})[ch["chunk_id"]] = tf
postings = {t: postings[t] for t in sorted(postings)}
df = {t: len(v) for t, v in postings.items()}
n = len(chunks)
avg = sum(c["n_chars"] for c in chunks) / n

DOCS = (DOC1, DOC2, DOC3, DOC4)


def search(query):
    """search.py 同构参考实现：求和顺序=查询词项首现顺序，4 趟稳定排序。"""

    terms_list = tokenize(query)
    out = {"query": query, "terms": terms_list, "n_hits": 0,
           "n_chunks": n, "avg_len": avg, "results": []}
    if not terms_list:
        return out
    idf_by = {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in terms_list if t in df}
    hits = []
    for ch in chunks:
        tfs = {t: postings[t][ch["chunk_id"]] for t in terms_list
               if t in postings and ch["chunk_id"] in postings[t]}
        matched = [t for t in terms_list if t in tfs]
        if not matched:
            continue
        score = 0.0
        parts = []
        for t in matched:
            tf_eff = tfs[t]
            c = idf_by[t] * tf_eff * (K1 + 1) / (tf_eff + K1 * (1 - B + B * ch["n_chars"] / avg))
            score += c
            parts.append([t, round(c, 6)])
        hh = len(set(matched) & set(tokenize(ch["heading"])))
        doc = next(d for d in DOCS if d["doc_id"] == ch["doc_id"])
        hits.append({
            "chunk_id": ch["chunk_id"], "score": round(score, 6), "path": doc["path"],
            "heading": ch["heading"], "line_start": ch["line_start"], "line_end": ch["line_end"],
            "excerpt": make_excerpt(ch["text"], matched), "matched_terms": matched,
            "score_parts": parts, "heading_hit": hh, "_mtime": doc["mtime"],
        })
    hits.sort(key=lambda h: h["chunk_id"])
    hits.sort(key=lambda h: h["_mtime"], reverse=True)
    hits.sort(key=lambda h: h["heading_hit"], reverse=True)
    hits.sort(key=lambda h: h["score"], reverse=True)
    out["n_hits"] = len(hits)
    out["results"] = [{k: v for k, v in h.items() if not k.startswith("_")} for h in hits]
    return out


# ---- 设计意图自检（fixture 本身必须先自洽） ----
assert len(P_TEXT) == len(Q_TEXT)
ids = search("状态")
assert [r["chunk_id"] for r in ids["results"]] == ["de3f4a5b#c00", "de3f4a5b#c01", "d9b0c1d2#c02"], ids
assert len({r["score"] for r in ids["results"]}) == 1, "状态 三块应同分"
fv = search("方差")
pair = [r for r in fv["results"] if r["chunk_id"] in ("d9b0c1d2#c01", "d5e6f7a8#c01")]
assert [p["chunk_id"] for p in pair] == ["d9b0c1d2#c01", "d5e6f7a8#c01"], fv
assert pair[0]["score"] == pair[1]["score"], pair
assert pair[0]["heading_hit"] == 1 and pair[1]["heading_hit"] == 0, pair
assert search("满二叉树和完全二叉树区别")["results"][0]["chunk_id"] == "d1a2b3c4#c00"
assert search("满二叉树和完全二叉树区别")["results"][0]["excerpt"].startswith("…"), "长文摘录应有前省略号"
assert [r["chunk_id"] for r in search("BM25 重排")["results"]] == ["d5e6f7a8#c00"]
assert search("的 了 是")["terms"] == [] and search("的 了 是")["n_hits"] == 0
assert search("混沌理论")["n_hits"] == 0
assert len(LONG_C00) > 160

fixture = {
    "version": 1,
    "_provenance": "站点回归夹具：期望值由 studybench.terms（真实分词）+ search.py 公式生成于 2026-10-30；"
                   "index 部分遵循 CONTRACTS.md §5 形状，tokenize_cases/cases 仅供 site/test/parity.mjs 使用。",
    "meta": {"project": "学研台 StudyBench", "corpus": "fixture", "generated_at": "2026-10-30T00:00:00+08:00",
             "n_docs": 4, "n_chunks": n, "avg_len": avg, "k1": K1, "b": B, "stopwords": list(STOPWORDS)},
    "docs": [DOC1, DOC2, DOC3, DOC4],
    "chunks": chunks,
    "postings": postings,
    "df": df,
    "tokenize_cases": [
        {"input": "ＢＭ２５ 第 3 章的习题", "expect": tokenize("ＢＭ２５ 第 3 章的习题")},
        {"input": "满二叉树和完全二叉树区别", "expect": tokenize("满二叉树和完全二叉树区别")},
        {"input": "的 了 是", "expect": []},
        {"input": "BM25 重排 n0", "expect": tokenize("BM25 重排 n0")},
        {"input": "a", "expect": []},
        {"input": "ＡＢｃ-ab", "expect": tokenize("ＡＢｃ-ab")},
        {"input": "状态——转移", "expect": tokenize("状态——转移")},
    ],
    "cases": [
        {"name": "多词命中 + 长文摘录", "query": "满二叉树和完全二叉树区别",
         "expect": search("满二叉树和完全二叉树区别")},
        {"name": "NFKC 全角 + ASCII 双词", "query": "BM25 重排", "expect": search("BM25 重排")},
        {"name": "纯 ASCII 单词（全角原文）", "query": "bm25", "expect": search("bm25")},
        {"name": "heading_hit 优先于 mtime（同分对）", "query": "方差", "expect": search("方差")},
        {"name": "score/mtime/chunk_id 三重 tie-break", "query": "状态", "expect": search("状态")},
        {"name": "多实词组合", "query": "样本方差", "expect": search("样本方差")},
        {"name": "停用词查询返回空", "query": "的 了 是", "expect": search("的 了 是")},
        {"name": "无命中查询", "query": "混沌理论", "expect": search("混沌理论")},
    ],
}

out_path = r"E:\CodeX\PowerContext-2026\qoder\site\test\fixture_index.json"
with open(out_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n")

print("fixture written:", out_path)
print("chunks:", n, "terms:", len(postings), "avg_len:", avg)
for c in fixture["cases"]:
    e = c["expect"]
    tops = " | ".join("%s s=%s hh=%d" % (r["chunk_id"], r["score"], r["heading_hit"])
                      for r in e["results"])
    print("CASE %-28s terms=%s hits=%d" % (c["name"], ",".join(e["terms"]) or "-", e["n_hits"]))
    print("     " + (tops or "(空)"))
