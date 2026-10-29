/*!
 * 学研台 StudyBench · 浏览器端检索（qoder/CONTRACTS.md §4 逐条复刻）
 *
 * 核心层（tokenize / tfMap / makeExcerpt / runSearch）与 Python 侧
 * studybench/terms.py、studybench/search.py 逐条一致，是 site/test/parity.mjs
 * 的对拍对象：
 *   1. NFKC 归一化 → CJK 游程取相邻 2-gram（游程长度 1 取单字），
 *      ASCII 词小写且长度 >= 2，其余字符一律为分隔；
 *   2. 停用词只过滤整词项（2-gram 含停用字仍保留）；
 *   3. BM25：idf = ln(1 + (N - df + 0.5) / (df + 0.5))，
 *      score = Σ idf * tf_eff * (k1 + 1) / (tf_eff + k1 * (1 - b + b * n_chars / avg))，
 *      k1 = 1.2，b = 0.75；tf_eff = tf_text + 2 * tf_heading（导出的 postings 已并入）；
 *   4. 求和顺序 = 查询词项首次出现顺序（浮点确定性）；
 *   5. 排序：score 降序 → heading_hit 降序 → mtime 降序 → chunk_id 升序；
 *   6. 摘录 ≤160 字、命中词前后 40 字，按 Unicode 码点计数（与 Python len 一致）。
 *
 * 本文件同时是浏览器经典脚本与 Node CommonJS 模块（parity.mjs require 加载）；
 * 无任何外部请求，索引来自 data/index_export.json（相对本页）。
 */
(function (global) {
  "use strict";

  var K1 = 1.2;
  var B = 0.75;
  var EXCERPT_WIDTH = 160;
  var EXCERPT_CONTEXT = 40;

  /* 契约 §4.4 停用词：与 terms.py STOPWORDS 同表（首现顺序去重，61 项）。 */
  var STOPWORD_LIST = [
    "的", "了", "是", "在", "和", "与", "对", "用", "为", "及", "或", "等", "就",
    "都", "也", "要", "会", "能", "把", "被", "从", "而", "其", "之", "个", "中",
    "上", "下", "不", "有", "我", "你", "他", "这", "那", "所", "以",
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "was", "were", "be", "been", "it", "this", "that", "with", "as", "at", "by",
    "from"
  ];
  var STOPWORDS = new Set(STOPWORD_LIST);

  /* 演示查询：来自 qoder/corpus_demo/_queries.json（真实演示语料查询）。 */
  var DEMO_QUERIES = [
    "满二叉树和完全二叉树区别",
    "归并排序为什么稳定",
    "kruskal为什么要按边权排序",
    "分光计调到什么程度算调好",
    "转动惯量平行轴定理怎么验证",
    "联合密度怎么求待定常数",
    "样本方差为什么除以n减一",
    "实验数据应该怎么记录",
    "第三范式到底消除什么依赖",
    "索引建多了会有什么坏处"
  ];

  /* ---------------------------------------------------------------- *
   * 分词（terms.py 逐条复刻；按 Unicode 码点处理，与 Python len 一致）
   * ---------------------------------------------------------------- */

  function isCJK(ch) {
    var c = ch.codePointAt(0);
    return (c >= 0x3400 && c <= 0x4dbf) || (c >= 0x4e00 && c <= 0x9fff);
  }

  function isAsciiAlnum(ch) {
    var c = ch.codePointAt(0);
    return (c >= 97 && c <= 122) || (c >= 65 && c <= 90) || (c >= 48 && c <= 57);
  }

  function rawTerms(text) {
    var normalized = String(text).normalize("NFKC");
    var cps = Array.from(normalized);
    var terms = [];
    var i = 0;
    while (i < cps.length) {
      if (isCJK(cps[i])) {
        var start = i;
        i += 1;
        while (i < cps.length && isCJK(cps[i])) i += 1;
        if (i - start === 1) {
          terms.push(cps[start]);
        } else {
          for (var k = start; k < i - 1; k++) terms.push(cps[k] + cps[k + 1]);
        }
      } else if (isAsciiAlnum(cps[i])) {
        var from = i;
        i += 1;
        while (i < cps.length && isAsciiAlnum(cps[i])) i += 1;
        var word = cps.slice(from, i).join("").toLowerCase();
        if (word.length >= 2) terms.push(word);
      } else {
        i += 1;
      }
    }
    return terms;
  }

  function filteredTerms(text) {
    var raw = rawTerms(text);
    var out = [];
    for (var i = 0; i < raw.length; i++) {
      if (!STOPWORDS.has(raw[i])) out.push(raw[i]);
    }
    return out;
  }

  /* tokenize：按首次出现顺序去重（顺序影响 score_parts 展示，Python 同序）。 */
  function tokenize(text) {
    var seen = new Set();
    var unique = [];
    var list = filteredTerms(text);
    for (var i = 0; i < list.length; i++) {
      if (!seen.has(list[i])) {
        seen.add(list[i]);
        unique.push(list[i]);
      }
    }
    return unique;
  }

  /* tf_map：同一套分词的词频统计。 */
  function tfMap(text) {
    var counts = new Map();
    var list = filteredTerms(text);
    for (var i = 0; i < list.length; i++) {
      counts.set(list[i], (counts.get(list[i]) || 0) + 1);
    }
    return counts;
  }

  /* ---------------------------------------------------------------- *
   * 摘录（search.py make_excerpt 逐字复刻，码点级）
   * ---------------------------------------------------------------- */

  function cpIndexOf(cps, needle) {
    if (!needle.length || needle.length > cps.length) return -1;
    var last = cps.length - needle.length;
    for (var i = 0; i <= last; i++) {
      var ok = true;
      for (var j = 0; j < needle.length; j++) {
        if (cps[i + j] !== needle[j]) { ok = false; break; }
      }
      if (ok) return i;
    }
    return -1;
  }

  function makeExcerpt(text, matchedTerms) {
    var cps = Array.from(String(text));
    if (cps.length <= EXCERPT_WIDTH) return String(text);
    var pos = -1;
    for (var i = 0; i < matchedTerms.length; i++) {
      var found = cpIndexOf(cps, Array.from(matchedTerms[i]));
      if (found >= 0 && (pos < 0 || found < pos)) pos = found;
    }
    if (pos < 0) pos = 0;
    var start = Math.max(0, pos - EXCERPT_CONTEXT);
    var end = start + EXCERPT_WIDTH - 2;
    if (end >= cps.length) end = cps.length;
    start = Math.max(0, end - (EXCERPT_WIDTH - 2));
    var prefix = start > 0 ? "…" : "";
    var suffix = end < cps.length ? "…" : "";
    return prefix + cps.slice(start, end).join("") + suffix;
  }

  /* ---------------------------------------------------------------- *
   * BM25 打分与排序（search.py 逐条复刻）
   * ---------------------------------------------------------------- */

  function round6(x) {
    return Number(Number(x).toFixed(6));
  }

  var preparedCache = typeof WeakMap === "function" ? new WeakMap() : null;

  /* postings/df/docs 转 Map，避免原型链键与逐词对象查找。 */
  function prepareIndex(index) {
    if (preparedCache) {
      var hit = preparedCache.get(index);
      if (hit) return hit;
    }
    var postings = new Map();
    var rawPostings = index.postings || {};
    Object.keys(rawPostings).forEach(function (term) {
      var byChunk = rawPostings[term];
      var inner = new Map();
      Object.keys(byChunk).forEach(function (cid) {
        inner.set(cid, byChunk[cid]);
      });
      postings.set(term, inner);
    });
    var df = new Map();
    var rawDf = index.df || {};
    Object.keys(rawDf).forEach(function (term) {
      df.set(term, rawDf[term]);
    });
    var docs = new Map();
    (index.docs || []).forEach(function (doc) {
      docs.set(doc.doc_id, doc);
    });
    var prepared = {
      postings: postings,
      df: df,
      docs: docs,
      chunks: index.chunks || [],
      meta: index.meta || {}
    };
    if (preparedCache) preparedCache.set(index, prepared);
    return prepared;
  }

  /* 排序：score 降序 → heading_hit 降序 → mtime 降序 → chunk_id 升序
   *（等价于 search.py 的四趟稳定排序；chunk_id 唯一，全序确定）。 */
  function cmpHit(a, b) {
    if (b.score !== a.score) return b.score - a.score;
    if (b.heading_hit !== a.heading_hit) return b.heading_hit - a.heading_hit;
    if (a.mtime !== b.mtime) return a.mtime < b.mtime ? 1 : -1;
    if (a.chunk_id !== b.chunk_id) return a.chunk_id < b.chunk_id ? -1 : 1;
    return 0;
  }

  function asResult(h) {
    return {
      chunk_id: h.chunk_id,
      score: round6(h.score),
      path: h.path,
      heading: h.heading,
      line_start: h.line_start,
      line_end: h.line_end,
      excerpt: h.excerpt,
      matched_terms: h.matched_terms.slice(),
      score_parts: h.score_parts.map(function (p) { return [p[0], p[1]]; }),
      heading_hit: h.heading_hit
    };
  }

  /**
   * 与 Python search() 同构的一次检索。
   * index: index_export.json 解析后的对象；query: 原始查询串；top: 截取条数。
   */
  function runSearch(index, query, top) {
    var started = nowMs();
    var p = prepareIndex(index);
    var chunks = p.chunks;
    var n = chunks.length;

    var totalChars = 0;
    for (var ci = 0; ci < chunks.length; ci++) totalChars += chunks[ci].n_chars;
    var avgLen = n ? totalChars / n : 0.0;
    var avgNorm = avgLen > 0 ? avgLen : 1.0;

    var termsList = tokenize(query);
    var hits = [];

    if (termsList.length && n) {
      /* df 覆盖全库（对应 search.py 的 fetch_term_rows；导出文件的 df 即全库 df）。 */
      var idfByTerm = new Map();
      for (var ti = 0; ti < termsList.length; ti++) {
        var d = p.df.get(termsList[ti]);
        if (d) idfByTerm.set(termsList[ti], Math.log(1 + (n - d + 0.5) / (d + 0.5)));
      }

      /* 候选召回：含任一查询词项的块（对应 FULLTEXT 召回 + 覆盖退路的并集）。 */
      var candidates = new Set();
      for (var cj = 0; cj < termsList.length; cj++) {
        var byChunk = p.postings.get(termsList[cj]);
        if (byChunk) byChunk.forEach(function (tf, cid) { candidates.add(cid); });
      }

      var headingCache = new Map();
      for (var ck = 0; ck < chunks.length; ck++) {
        var chunk = chunks[ck];
        if (!candidates.has(chunk.chunk_id)) continue;

        /* matched 保持查询词项首现顺序；求和顺序与之相同（浮点确定性）。 */
        var matched = [];
        for (var tm = 0; tm < termsList.length; tm++) {
          var m = p.postings.get(termsList[tm]);
          if (m && m.has(chunk.chunk_id)) matched.push(termsList[tm]);
        }
        if (!matched.length) continue;

        var score = 0.0;
        var parts = [];
        for (var tc = 0; tc < matched.length; tc++) {
          var term = matched[tc];
          var tfEff = p.postings.get(term).get(chunk.chunk_id);
          var contribution = idfByTerm.get(term) * tfEff * (K1 + 1) /
            (tfEff + K1 * (1 - B + B * chunk.n_chars / avgNorm));
          score += contribution;
          parts.push([term, round6(contribution)]);
        }

        var hTokens = headingCache.get(chunk.heading);
        if (!hTokens) {
          hTokens = new Set(tokenize(chunk.heading));
          headingCache.set(chunk.heading, hTokens);
        }
        var headingHit = 0;
        for (var th = 0; th < matched.length; th++) {
          if (hTokens.has(matched[th])) headingHit += 1;
        }

        var doc = p.docs.get(chunk.doc_id) || {};
        hits.push({
          chunk_id: chunk.chunk_id,
          score: score,
          path: doc.path || "",
          heading: chunk.heading,
          line_start: chunk.line_start,
          line_end: chunk.line_end,
          text: chunk.text,
          excerpt: makeExcerpt(chunk.text, matched),
          matched_terms: matched,
          score_parts: parts,
          heading_hit: headingHit,
          mtime: doc.mtime || ""
        });
      }
      hits.sort(cmpHit);
    }

    var elapsed = Math.trunc(nowMs() - started);
    var shown = typeof top === "number" ? hits.slice(0, Math.max(0, top)) : hits;
    return {
      query: query,
      terms: termsList,
      n_hits: hits.length,
      n_chunks: n,
      avg_len: avgLen,
      elapsed_ms: elapsed,
      results: shown.map(asResult)
    };
  }

  function nowMs() {
    return typeof performance !== "undefined" && performance.now
      ? performance.now()
      : Date.now();
  }

  /* ---------------------------------------------------------------- *
   * 浏览器 UI（Node 侧 require 加载时不执行）
   * ---------------------------------------------------------------- */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  /* 摘录高亮：对摘录码点做命中掩码，再按游程包 <mark>；textContent 防注入。 */
  function highlightFragment(excerpt, matchedTerms) {
    var cps = Array.from(excerpt);
    var lower = cps.map(function (c) { return c.toLowerCase(); });
    var marks = new Array(cps.length);
    (matchedTerms || []).forEach(function (term) {
      var t = Array.from(String(term).toLowerCase());
      if (!t.length) return;
      for (var i = 0; i + t.length <= lower.length; i++) {
        var ok = true;
        for (var j = 0; j < t.length; j++) {
          if (lower[i + j] !== t[j]) { ok = false; break; }
        }
        if (ok) {
          for (var k = i; k < i + t.length; k++) marks[k] = true;
          i += t.length - 1;
        }
      }
    });
    var frag = document.createDocumentFragment();
    var buf = "";
    var cur = false;
    function flush() {
      if (!buf) return;
      if (cur) {
        var mark = el("mark", null, buf);
        frag.appendChild(mark);
      } else {
        frag.appendChild(document.createTextNode(buf));
      }
      buf = "";
    }
    for (var i = 0; i < cps.length; i++) {
      var m = !!marks[i];
      if (m !== cur) {
        flush();
        cur = m;
      }
      buf += cps[i];
    }
    flush();
    return frag;
  }

  function fillMeta(meta, nTerms) {
    var values = {
      n_docs: meta.n_docs !== undefined ? String(meta.n_docs) : "—",
      n_chunks: meta.n_chunks !== undefined ? String(meta.n_chunks) : "—",
      n_terms: nTerms !== undefined ? String(nTerms) : "—",
      avg_len: meta.avg_len !== undefined ? Number(meta.avg_len).toFixed(1) : "—",
      generated_at: meta.generated_at || "—"
    };
    Object.keys(values).forEach(function (key) {
      var nodes = document.querySelectorAll('[data-meta="' + key + '"]');
      for (var i = 0; i < nodes.length; i++) nodes[i].textContent = values[key];
    });
  }

  function renderStatus(statusNode, out) {
    statusNode.textContent = "";
    if (!out.terms.length) {
      statusNode.appendChild(el("p", "trial-status trial-warn",
        "查询无可检索词项（单字、停用词或过短），换个说法试试。"));
      return;
    }
    var head = "词项 [" + out.terms.join("、") + "] · 命中 " + out.n_hits +
      " / " + out.n_chunks + " 块 · 耗时 " + out.elapsed_ms + " ms";
    statusNode.appendChild(el("p", "trial-status", head));
    if (!out.n_hits) {
      statusNode.appendChild(el("p", "trial-status trial-warn",
        "没有命中的知识块。索引只含演示语料，试试下方演示查询。"));
    }
  }

  function renderHit(hit) {
    var card = el("article", "hit");
    var top = el("div", "hit-top");
    top.appendChild(el("code", "hit-ref",
      hit.path + ":" + hit.line_start + "-" + hit.line_end));
    top.appendChild(el("span", "hit-score", "得分 " + hit.score.toFixed(6)));
    card.appendChild(top);
    card.appendChild(el("h4", "hit-heading", hit.heading));

    var quote = el("blockquote", "hit-excerpt");
    quote.appendChild(highlightFragment(hit.excerpt, hit.matched_terms));
    card.appendChild(quote);

    var meta = el("p", "hit-parts");
    meta.appendChild(el("span", "part-label", "得分分解"));
    hit.score_parts.forEach(function (part) {
      meta.appendChild(el("span", "part", part[0] + " = " + part[1].toFixed(6)));
    });
    if (hit.heading_hit > 0) {
      meta.appendChild(el("span", "part part-head",
        "标题命中 " + hit.heading_hit + " 词项"));
    }
    card.appendChild(meta);
    return card;
  }

  function renderResults(container, out) {
    container.textContent = "";
    out.results.forEach(function (hit) {
      container.appendChild(renderHit(hit));
    });
  }

  function loadIndex() {
    return fetch("data/index_export.json").then(function (resp) {
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      return resp.json();
    }).catch(function () {
      /* file:// 等环境 fetch 受限，退回 XHR（部分浏览器允许同目录读取）。 */
      return new Promise(function (resolve, reject) {
        try {
          var xhr = new XMLHttpRequest();
          xhr.open("GET", "data/index_export.json", true);
          xhr.onload = function () {
            if (xhr.status === 0 || (xhr.status >= 200 && xhr.status < 300)) {
              try {
                resolve(JSON.parse(xhr.responseText));
              } catch (err) {
                reject(err);
              }
            } else {
              reject(new Error("HTTP " + xhr.status));
            }
          };
          xhr.onerror = function () { reject(new Error("XHR 失败")); };
          xhr.send();
        } catch (err) {
          reject(err);
        }
      });
    });
  }

  function bootUI() {
    if (typeof document === "undefined") return;
    var form = document.getElementById("demo-form");
    var input = document.getElementById("demo-input");
    var chips = document.getElementById("demo-chips");
    var status = document.getElementById("demo-status");
    var results = document.getElementById("demo-results");
    var note = document.getElementById("demo-note");
    if (!form || !input || !chips || !status || !results) return;

    var index = null;

    function showLoadError(message) {
      if (!note) return;
      note.hidden = false;
      note.textContent = "索引加载失败（" + message +
        "）。请通过静态服务器打开，例如：python -m http.server，再访问本页。";
    }

    loadIndex().then(function (data) {
      index = data;
      var nTerms = index.df ? Object.keys(index.df).length : 0;
      fillMeta(index.meta || {}, nTerms);
      if (note) {
        note.hidden = false;
        note.textContent = "索引就绪：" + (index.meta ? index.meta.n_chunks : "—") +
          " 块 / " + nTerms + " 词项，检索在你的浏览器本地完成，不经过任何服务器。";
      }
    }).catch(function (err) {
      showLoadError(err && err.message ? err.message : "未知错误");
    });

    DEMO_QUERIES.forEach(function (q) {
      var chip = el("button", "chip", q);
      chip.type = "button";
      chip.addEventListener("click", function () {
        input.value = q;
        doSearch();
      });
      chips.appendChild(chip);
    });

    function doSearch() {
      if (!index) {
        status.textContent = "";
        status.appendChild(el("p", "trial-status trial-warn",
          "索引尚未加载完成，请稍候重试。"));
        return;
      }
      var query = input.value;
      if (!query.trim()) {
        status.textContent = "";
        status.appendChild(el("p", "trial-status trial-warn", "请输入查询词。"));
        results.textContent = "";
        return;
      }
      var out = runSearch(index, query);
      renderStatus(status, out);
      renderResults(results, out);
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      doSearch();
    });
  }

  var StudyBench = {
    version: "1.0.0",
    K1: K1,
    B: B,
    STOPWORDS: STOPWORD_LIST,
    DEMO_QUERIES: DEMO_QUERIES,
    tokenize: tokenize,
    tfMap: tfMap,
    makeExcerpt: makeExcerpt,
    prepareIndex: prepareIndex,
    runSearch: runSearch
  };

  global.StudyBench = StudyBench;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = StudyBench;
  } else {
    bootUI();
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
