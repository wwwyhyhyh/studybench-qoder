#!/usr/bin/env python3
"""把真实终端实录与仓库链接注入站点（src 与 dist 同步改写）。

用法：python qoder/scripts/inject_site_logs.py
来源：qoder/verification/logs/{ingest,index,search,memory,export}.log
"""
from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "verification" / "logs"
TARGETS = [ROOT / "site" / "src" / "index.html", ROOT / "site" / "dist" / "index.html"]
REPO_URL = "https://github.com/Castorice104/PowerContext-2026/tree/2026-competition-ecosystem/qoder"
REPO_HTML = (
    f'<a href="{REPO_URL}" rel="noopener">github.com/Castorice104/PowerContext-2026'
    '<span class="foot-dim">（qoder/ 目录 · 私有仓库，如需访问请联系提交者开通）</span></a>'
)


def sanitize(text: str) -> str:
    """把开发机用户名等本机路径泛化，避免站点曝光个人目录。"""
    return text.replace("/home/vertin", "/home/<user>").replace("C:\\Users\\Lenovo", "C:\\Users\\<user>")


def head(path: Path, n: int) -> list[str]:
    if not path.exists():
        return [f"[缺少 {path.name}]"]
    return path.read_text(encoding="utf-8").splitlines()[:n]


def first_query_block(path: Path, keep_hits: int = 3) -> list[str]:
    """取 search.log 里第一条查询 + 前 keep_hits 条命中。"""
    lines = head(path, 400)
    out: list[str] = []
    hits = 0
    for line in lines:
        if re.match(r"^\d+\.\s", line):
            hits += 1
            if hits > keep_hits:
                out.append(f"…（其余命中与 9 条演示查询略，完整见 {path.name}）")
                break
        out.append(line)
        if line.startswith("摘录：") and hits == keep_hits:
            out.append(f"…（其余命中与 9 条演示查询略，完整见 {path.name}）")
            break
    return out


def digest_block(path: Path, keep: int = 10) -> list[str]:
    """从 memory.log 里取「digest 命令行 + 周报前 keep 行」，不截掉标题。"""
    lines = head(path, 200)
    for i, line in enumerate(lines):
        if line.startswith("$ studybench digest") or line.startswith("$ bash qoder/scripts/sb.sh digest"):
            return lines[i : i + keep]
    return lines[-keep:]


def build() -> str:
    blocks: list[tuple[str, list[str]]] = [
        ("① 建索引：markdown → seekdb（幂等，可重跑）", head(LOGS / "ingest.log", 5)),
        ("② 索引规模与词项统计", head(LOGS / "index.log", 4)),
        ("③ 中文口语查询 → 全文索引召回 → BM25 重排", first_query_block(LOGS / "search.log", 3)),
        ("④ 任务进度：不可变 revision 链 + 复读续做", head(LOGS / "memory.log", 19)),
        ("⑤ 周报：确定性四段模板", digest_block(LOGS / "memory.log", 10)),
        ("⑥ 导出站点索引（浏览器端同构打分的数据源）", head(LOGS / "export.log", 4)),
    ]
    parts: list[str] = []
    for title, lines in blocks:
        body = "\n".join(html.escape(sanitize(line)) for line in lines if line.strip() != "")
        parts.append(
            f'<span class="term-dim"># {html.escape(title)}</span>\n{body}'
        )
    parts.append(
        '<span class="term-dim"># 以上为真实输出截断版；完整日志见 qoder/verification/logs/，'
        "期望值见 verification/expected_results.json。</span>"
    )
    return "\n\n".join(parts)


def main() -> None:
    payload = build()
    for target in TARGETS:
        text = target.read_text(encoding="utf-8")
        new, n1 = re.subn(
            r'(<pre class="term" id="runlog" aria-label="[^"]*">)(.*?)(</pre>)',
            lambda m: m.group(1) + "\n" + payload + "\n" + m.group(3),
            text,
            flags=re.S,
        )
        new, n2 = re.subn(r"<!-- REPO:REPLACE -->", REPO_HTML, new)
        # 幂等：占位已被替换过时，改写既有链接文案
        if n2 == 0:
            new, n2 = re.subn(
                r'<a href="' + re.escape(REPO_URL) + r'" rel="noopener">.*?</a>', REPO_HTML, new, flags=re.S
            )
        target.write_text(new, encoding="utf-8")
        print(f"{target.relative_to(ROOT)}: logs={n1} repo={n2}")
        if n1 != 1 or n2 != 1:
            raise SystemExit("替换数量异常，请检查模板")


if __name__ == "__main__":
    main()
