#!/usr/bin/env node
/**
 * 学研台 StudyBench · 站点一致性校验（CONTRACTS.md §10、§11.3）
 *
 * 用法：node qoder/site/test/parity.mjs
 *
 * 第 1 部分 fixture 回归：加载 dist/app.js（发布物本体）与 test/fixture_index.json，
 *   后者的期望值由真实 Python 参考实现（studybench.terms + search.py 公式，见
 *   make_fixture.py）生成，逐字段对拍分词、得分（6 位小数）、排序、摘录。
 *
 * 第 2 部分 真实 parity：读 verification/expected_results.json（主控产出）。
 *   文件不存在 → 打印 SKIP 并按约定 exit 0；存在 → 对每条查询用 JS 排序器算
 *   top-5，与期望的 chunk_id 顺序、6 位小数 score 逐一比对，全等才 PASS。
 *
 * 退出码：0 = 全部 PASS 或 parity SKIP；1 = 任一 FAIL 或结构无法识别。
 */
import { createRequire } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const distDir = path.resolve(here, "..", "dist");
const requireCjs = createRequire(import.meta.url);

let StudyBench;
try {
  StudyBench = requireCjs(path.join(distDir, "app.js"));
} catch (error) {
  console.error("FATAL 无法加载 " + path.join(distDir, "app.js") + "：" + error.message);
  process.exit(1);
}

let nPass = 0;
let nFail = 0;

function report(ok, name, detail) {
  if (ok) {
    nPass += 1;
    console.log("PASS  " + name);
  } else {
    nFail += 1;
    console.log("FAIL  " + name + (detail ? "\n      " + detail : ""));
  }
}

function jsonEq(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function short(value) {
  let text;
  try {
    text = typeof value === "string" ? value : JSON.stringify(value);
  } catch {
    text = String(value);
  }
  return text.length > 160 ? text.slice(0, 160) + "…" : text;
}

/* ---------------- 第 1 部分：fixture 回归 ---------------- */

function runFixture() {
  const fixturePath = path.join(here, "fixture_index.json");
  let fixture;
  try {
    fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
  } catch (error) {
    report(false, "fixture 加载", String(error.message));
    return;
  }

  /* 夹具自身的形状自检（§5 语义）。 */
  report(
    fixture.meta.n_chunks === fixture.chunks.length,
    "fixture meta.n_chunks 与 chunks.length 一致",
    "meta=" + fixture.meta.n_chunks + " chunks=" + fixture.chunks.length
  );
  const postingsKeys = Object.keys(fixture.postings);
  const dfConsistent =
    postingsKeys.length === Object.keys(fixture.df).length &&
    postingsKeys.every((t) => fixture.df[t] === Object.keys(fixture.postings[t]).length);
  report(dfConsistent, "fixture df 与 postings 键集一致");

  /* 分词向量：期望值来自真实 studybench.terms.tokenize。 */
  for (const c of fixture.tokenize_cases || []) {
    const got = StudyBench.tokenize(c.input);
    report(
      jsonEq(got, c.expect),
      "tokenize " + short(c.input),
      "期望 " + short(c.expect) + "，得到 " + short(got)
    );
  }

  /* 检索用例：期望值由 Python 参考实现生成（BM25 / 摘录 / 四趟稳定排序）。 */
  for (const c of fixture.cases || []) {
    const expect = c.expect;
    const got = StudyBench.runSearch(fixture, c.query);
    const problems = [];
    if (got.query !== expect.query) problems.push("query");
    if (!jsonEq(got.terms, expect.terms)) {
      problems.push("terms 期望 " + short(expect.terms) + "，得到 " + short(got.terms));
    }
    if (got.n_hits !== expect.n_hits) {
      problems.push("n_hits 期望 " + expect.n_hits + "，得到 " + got.n_hits);
    }
    if (got.n_chunks !== expect.n_chunks) {
      problems.push("n_chunks 期望 " + expect.n_chunks + "，得到 " + got.n_chunks);
    }
    if (got.avg_len !== expect.avg_len) {
      problems.push("avg_len 期望 " + expect.avg_len + "，得到 " + got.avg_len);
    }
    const n = Math.max(expect.results.length, got.results.length);
    for (let i = 0; i < n; i++) {
      const e = expect.results[i];
      const g = got.results[i];
      if (!e || !g) {
        problems.push("results[" + i + "] 一侧缺失（期望 " + expect.results.length +
          " 条，得到 " + got.results.length + " 条）");
        continue;
      }
      const tag = "results[" + i + "] 期望 " + e.chunk_id + "：";
      if (g.chunk_id !== e.chunk_id) problems.push(tag + "chunk_id 得到 " + g.chunk_id);
      if (g.score !== e.score) {
        problems.push(tag + "score 期望 " + e.score + "，得到 " + g.score);
      }
      if (g.path !== e.path) problems.push(tag + "path 期望 " + short(e.path) + "，得到 " + short(g.path));
      if (g.heading !== e.heading) problems.push(tag + "heading 期望 " + short(e.heading) + "，得到 " + short(g.heading));
      if (g.line_start !== e.line_start || g.line_end !== e.line_end) {
        problems.push(tag + "line 期望 " + e.line_start + "-" + e.line_end +
          "，得到 " + g.line_start + "-" + g.line_end);
      }
      if (g.excerpt !== e.excerpt) {
        problems.push(tag + "excerpt 期望 " + short(e.excerpt) + "，得到 " + short(g.excerpt));
      }
      if (!jsonEq(g.matched_terms, e.matched_terms)) {
        problems.push(tag + "matched_terms 期望 " + short(e.matched_terms) +
          "，得到 " + short(g.matched_terms));
      }
      if (!jsonEq(g.score_parts, e.score_parts)) {
        problems.push(tag + "score_parts 期望 " + short(e.score_parts) +
          "，得到 " + short(g.score_parts));
      }
      if (g.heading_hit !== e.heading_hit) {
        problems.push(tag + "heading_hit 期望 " + e.heading_hit + "，得到 " + g.heading_hit);
      }
    }
    report(problems.length === 0, "case：" + c.name + "（" + c.query + "）", problems.join("；"));
  }
}

/* ---------------- 第 2 部分：与 expected_results.json 对拍 ---------------- */

function extractEntries(data) {
  if (Array.isArray(data)) return data;
  const keys = ["queries", "results", "cases", "expected", "entries", "rows"];
  for (const key of keys) {
    if (data && Array.isArray(data[key])) return data[key];
  }
  return null;
}

function pick(obj, keys) {
  for (const key of keys) {
    if (obj && obj[key] !== undefined) return obj[key];
  }
  return undefined;
}

function runParity() {
  const expectedPath = path.resolve(here, "..", "..", "verification", "expected_results.json");
  if (!existsSync(expectedPath)) {
    console.log("SKIP  parity：未找到 " + expectedPath);
    console.log("      （主控生成 verification/expected_results.json 后重跑本脚本即可对拍）");
    return;
  }
  let data;
  try {
    data = JSON.parse(readFileSync(expectedPath, "utf8"));
  } catch (error) {
    report(false, "expected_results.json 解析", String(error.message));
    return;
  }
  const entries = extractEntries(data);
  if (!entries || !entries.length) {
    report(false, "expected_results.json 结构无法识别",
      "未找到每条查询的数组（尝试过 queries/results/cases/expected/entries/rows 或根数组）");
    return;
  }

  const indexPath = path.join(distDir, "data", "index_export.json");
  const index = JSON.parse(readFileSync(indexPath, "utf8"));

  for (const entry of entries) {
    const query = pick(entry, ["query", "q", "text"]);
    const expectedHits = pick(entry, ["results", "hits", "top", "top5", "expected", "expected_top5"]);
    if (typeof query !== "string" || !Array.isArray(expectedHits)) {
      report(false, "parity 条目结构无法识别", short(entry));
      continue;
    }
    const got = StudyBench.runSearch(index, query, 5);
    const problems = [];
    const n = Math.min(5, Math.max(expectedHits.length, got.results.length));
    for (let i = 0; i < n; i++) {
      const e = expectedHits[i];
      const g = got.results[i];
      if (!e) {
        problems.push("第 " + (i + 1) + " 位：期望缺项，实际 " + g.chunk_id);
        continue;
      }
      const wantId = pick(e, ["chunk_id", "chunk", "id"]);
      const wantScore = pick(e, ["score", "s"]);
      if (!g) {
        problems.push("第 " + (i + 1) + " 位：期望 " + wantId + "，实际缺项");
        continue;
      }
      if (g.chunk_id !== wantId) {
        problems.push("第 " + (i + 1) + " 位：chunk_id 期望 " + wantId + "，得到 " + g.chunk_id);
      }
      if (wantScore !== undefined && Number(g.score.toFixed(6)) !== Number(Number(wantScore).toFixed(6))) {
        problems.push("第 " + (i + 1) + " 位：score 期望 " + wantScore + "，得到 " + g.score);
      }
    }
    report(problems.length === 0, "parity：" + query, problems.join("；"));
  }
}

/* ---------------- 汇总 ---------------- */

runFixture();
runParity();

console.log("——");
console.log("总计：PASS " + nPass + " / FAIL " + nFail + (nFail ? "（exit 1）" : "（exit 0）"));
process.exit(nFail ? 1 : 0);
