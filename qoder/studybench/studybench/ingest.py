"""markdown → chunks + doc 元数据（qoder/CONTRACTS.md §3、§9）。

切块规则：``# 标题`` 之后、第一个 ``## 小节`` 之前的非空引言（如有）作为
第 0 块（heading = 文档标题），每个 ``## 小节`` 各成一块；``###`` 及更深
标题留在小节正文内。``line_start`` 指向 heading 行（1 基），``line_end``
指向该块最后一个非空正文行。

词项落库（契约 §4.2）：``tf_eff = tf_text + 2 * tf_heading`` 直接作为
``chunk_terms.tf``（BM25 的 tf/df 与 §5 导出的唯一来源，裁决后保持不变）；
``searchable_text`` 存自然文本 ``heading + "\\n" + text``（裁决·锚点1），
由 NGRAM 全文索引承担召回。

元数据优先级：``--course/--kind`` 命令行标志 > 文件头 front-matter
（``---`` 块中的 ``course:/kind:/title:``）> 路径推导（首层目录名）> 空串。
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .store import Store
from .terms import tf_map


def doc_id_for(rel_path: str) -> str:
    """``d<sha1(path)[:8]>``（契约 §3：稳定、幂等重导）。"""

    digest = hashlib.sha1(rel_path.encode("utf-8")).hexdigest()
    return "d" + digest[:8]


def chunk_terms(heading: str, text: str) -> dict[str, int]:
    """词项 → tf_eff（tf_text + 2*tf_heading，契约 §4.2，直接落库）。"""

    counts: dict[str, int] = {}
    for term, count in tf_map(text).items():
        counts[term] = counts.get(term, 0) + count
    for term, count in tf_map(heading).items():
        counts[term] = counts.get(term, 0) + 2 * count
    return counts


def searchable_text(heading: str, text: str) -> str:
    """自然文本（裁决·锚点1）：``heading + "\\n" + text``。

    由 NGRAM 全文索引直接对自然中文建 2-gram 索引承担召回；
    ``chunk_terms``（BM25 的 tf/df 与 §5 导出）保持不变。
    """

    return heading + "\n" + text


def _span(raw: list[str], base: int) -> tuple[int, int, str] | None:
    """裁掉首尾空行，返回 (line_start, line_end, text)（1 基、含端点）。"""

    start, end = 0, len(raw) - 1
    while start <= end and not raw[start].strip():
        start += 1
    while end >= start and not raw[end].strip():
        end -= 1
    if start > end:
        return None
    return base + start + 1, base + end + 1, "\n".join(raw[start : end + 1])


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """可选 ``---`` 头部：仅识别 course / kind / title 三个键。"""

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        return {}, text
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if sep and key in ("course", "kind", "title") and value:
            meta[key] = value
    return meta, "\n".join(lines[end + 1 :])


def parse_markdown(text: str, fallback_title: str) -> tuple[str, list[dict]]:
    """解析为 (标题, [section])；section 含 heading / line_start / line_end / text。"""

    lines = text.splitlines()
    title = fallback_title.strip() or "未命名"
    title_line: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# ") or stripped.startswith("#\t"):
            title = stripped[1:].strip() or title
            title_line = index
            break
        if stripped.startswith("##") or stripped:
            break

    h2_indexes = [
        index
        for index, line in enumerate(lines)
        if line.lstrip().startswith("##") and not line.lstrip().startswith("###")
    ]

    sections: list[dict] = []
    first_h2 = h2_indexes[0] if h2_indexes else len(lines)
    preamble_start = title_line + 1 if title_line is not None else 0
    preamble = _span(lines[preamble_start:first_h2], preamble_start)
    if preamble is not None:
        sections.append(
            {
                "heading": title[:255],
                "line_start": title_line + 1 if title_line is not None else preamble[0],
                "line_end": preamble[1],
                "text": preamble[2],
            }
        )
    for order, heading_line in enumerate(h2_indexes):
        raw_heading = lines[heading_line].lstrip()[2:].strip()
        next_line = (
            h2_indexes[order + 1] if order + 1 < len(h2_indexes) else len(lines)
        )
        body = _span(lines[heading_line + 1 : next_line], heading_line + 1)
        sections.append(
            {
                "heading": (raw_heading or f"第{order + 1}节")[:255],
                "line_start": heading_line + 1,
                "line_end": body[1] if body is not None else heading_line + 1,
                "text": body[2] if body is not None else "",
            }
        )
    return title, sections


def build_doc(
    rel_path: str,
    file_path: Path,
    course_flag: str | None,
    kind_flag: str | None,
) -> tuple[dict, list[dict]] | None:
    """一个 markdown 文件 → (doc 元数据, chunks)；空文件返回 None。"""

    raw = file_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{rel_path} 不是 UTF-8 编码的 markdown：{error}") from error
    front, body = _split_front_matter(text)
    md_title, sections = parse_markdown(body, Path(rel_path).stem)
    if not sections:
        return None

    parts = rel_path.split("/")
    course = course_flag or front.get("course") or (parts[0] if len(parts) > 1 else "") or ""
    kind = kind_flag or front.get("kind") or ""
    doc_id = doc_id_for(rel_path)
    doc = {
        "doc_id": doc_id,
        "path": rel_path,
        "title": (front.get("title") or md_title)[:255],
        "course": course[:128],
        "kind": kind[:64],
        "mtime": datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y-%m-%d"),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    chunks: list[dict] = []
    for seq, section in enumerate(sections):
        heading = section["heading"]
        body_text = section["text"]
        chunks.append(
            {
                "chunk_id": f"{doc_id}#c{seq:02d}",
                "doc_id": doc_id,
                "seq": seq,
                "heading": heading,
                "line_start": section["line_start"],
                "line_end": section["line_end"],
                "text": body_text,
                "n_chars": len(body_text),
                "searchable_text": searchable_text(heading, body_text),
                "terms": chunk_terms(heading, body_text),
            }
        )
    return doc, chunks


def _collect_markdown_files(src: Path) -> list[Path]:
    files = [
        path
        for path in src.rglob("*.md")
        if path.is_file()
        and not any(part.startswith((".", "_")) for part in path.relative_to(src).parts)
    ]
    return sorted(files, key=lambda path: path.relative_to(src).as_posix())


def _resolve_src(src: str) -> Path:
    """解析 ``--src``：路径不存在且以 ``qoder/`` 开头时剥掉前缀再试（裁决·锚点2）。

    WSL 内 CWD 是 qoder/ 根，用户按契约写 ``--src qoder/corpus_demo``
    时应能解析到 ``corpus_demo``。
    """

    src_path = Path(src).expanduser()
    if not src_path.is_dir():
        parts = src_path.parts
        if len(parts) > 1 and parts[0] == "qoder":
            candidate = Path(*parts[1:])
            if candidate.is_dir():
                return candidate
    return src_path


def ingest_directory(
    src: str,
    db_path: str,
    course: str | None = None,
    kind: str | None = None,
    reset: bool = False,
) -> dict:
    """把一个目录的全部 markdown 索引进 seekdb（幂等；契约 §3、§6）。

    返回 ``{"src", "db", "docs", "chunks", "skipped", "reset"}``。
    """

    src_path = _resolve_src(src)
    if not src_path.is_dir():
        raise ValueError(f"--src 不是目录：{src}")
    store = Store(db_path)
    try:
        store.ensure_schema()
        if reset:
            store.reset()
        n_docs = 0
        n_chunks = 0
        skipped: list[str] = []
        for file_path in _collect_markdown_files(src_path):
            rel = file_path.relative_to(src_path).as_posix()
            built = build_doc(rel, file_path, course, kind)
            if built is None:
                skipped.append(rel)
                continue
            doc, chunks = built
            store.upsert_document(doc, chunks)
            n_docs += 1
            n_chunks += len(chunks)
        return {
            "src": str(src_path),
            "db": str(db_path),
            "docs": n_docs,
            "chunks": n_chunks,
            "skipped": skipped,
            "reset": bool(reset),
        }
    finally:
        store.close()
