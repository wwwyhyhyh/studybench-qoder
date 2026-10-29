"""export.py 单测：index_export.json 字段冻结 / postings=df / tf_eff（契约 §5）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from studybench import export, ingest
from studybench.ingest import doc_id_for, parse_markdown
from studybench.store import Store
from studybench.terms import STOPWORDS, tf_map

MINI = Path(__file__).parent / "fixtures" / "mini"

REL_DS = "数据结构/树与二叉树.md"


def _export(tmp_path: Path, db: str) -> tuple[Path, dict]:
    out = tmp_path / "index_export.json"
    export.export_index(db, str(out))
    payload = json.loads(out.read_text(encoding="utf-8"))
    return out, payload


def _mini_db(tmp_path: Path) -> str:
    db = str(tmp_path / "sb.db")
    ingest.ingest_directory(str(MINI), db)
    return db


def test_export_meta_and_version(tmp_path: Path) -> None:
    db = _mini_db(tmp_path)
    _, payload = _export(tmp_path, db)
    assert payload["version"] == 1
    meta = payload["meta"]
    assert meta["project"] == "学研台 StudyBench"
    assert meta["corpus"] == "demo"
    assert meta["generated_at"].endswith("+08:00")
    assert meta["n_docs"] == 3 and meta["n_chunks"] == 9
    assert isinstance(meta["avg_len"], float) and meta["avg_len"] > 0
    assert meta["k1"] == 1.2 and meta["b"] == 0.75
    assert meta["stopwords"] == list(STOPWORDS)
    # 与检索侧同一 avg_len（站点 BM25 parity 依赖）。
    with Store(db) as store:
        assert meta["avg_len"] == store.stats()["avg_len"]


def test_export_docs_chunks_frozen_fields(tmp_path: Path) -> None:
    db = _mini_db(tmp_path)
    _, payload = _export(tmp_path, db)
    assert all(
        set(doc) == {"doc_id", "path", "title", "course", "kind", "mtime"}
        for doc in payload["docs"]
    )
    assert all(
        set(chunk)
        == {
            "chunk_id",
            "doc_id",
            "seq",
            "heading",
            "line_start",
            "line_end",
            "text",
            "n_chars",
        }
        for chunk in payload["chunks"]
    )
    # 排序确定：docs 按 doc_id、chunks 按 (doc_id, seq)。
    assert [doc["doc_id"] for doc in payload["docs"]] == sorted(
        doc["doc_id"] for doc in payload["docs"]
    )
    keys = [(chunk["doc_id"], chunk["seq"]) for chunk in payload["chunks"]]
    assert keys == sorted(keys)
    for chunk in payload["chunks"]:
        assert chunk["chunk_id"] == f"{chunk['doc_id']}#c{chunk['seq']:02d}"
        assert chunk["n_chars"] == len(chunk["text"])
    # text 原样保留（站点展示摘录与引用）。
    source_text = (MINI / REL_DS).read_text(encoding="utf-8")
    _, sections = parse_markdown(source_text, "树与二叉树")
    doc_id = doc_id_for(REL_DS)
    exported = [c for c in payload["chunks"] if c["doc_id"] == doc_id]
    assert [chunk["text"] for chunk in exported] == [section["text"] for section in sections]
    assert [chunk["line_start"] for chunk in exported] == [
        section["line_start"] for section in sections
    ]


def test_postings_keys_match_df_and_tf_eff(tmp_path: Path) -> None:
    """postings 值是 tf_eff；df 与 postings 键集一致（契约 §5）。"""

    db = _mini_db(tmp_path)
    _, payload = _export(tmp_path, db)
    postings = payload["postings"]
    df = payload["df"]
    assert set(postings) == set(df)
    for term, by_chunk in postings.items():
        assert df[term] == len(by_chunk)
        assert all(isinstance(value, int) and value >= 1 for value in by_chunk.values())

    # 逐块重算 tf_eff = tf_text + 2*tf_heading 验证落库口径（契约 §4.2）。
    source_text = (MINI / REL_DS).read_text(encoding="utf-8")
    _, sections = parse_markdown(source_text, "树与二叉树")
    doc_id = doc_id_for(REL_DS)
    for seq, section in enumerate(sections):
        expected = dict(tf_map(section["text"]))
        for term, count in tf_map(section["heading"]).items():
            expected[term] = expected.get(term, 0) + 2 * count
        chunk_id = f"{doc_id}#c{seq:02d}"
        for term, tf in expected.items():
            assert postings[term][chunk_id] == tf


def test_export_size_and_summary(tmp_path: Path) -> None:
    db = _mini_db(tmp_path)
    out, payload = _export(tmp_path, db)
    assert 0 < out.stat().st_size <= 3 * 1024 * 1024


def test_export_empty_database(tmp_path: Path) -> None:
    db = str(tmp_path / "sb.db")
    with Store(db) as store:
        store.ensure_schema()
    _, payload = _export(tmp_path, db)
    assert payload["meta"]["n_docs"] == 0 and payload["meta"]["n_chunks"] == 0
    assert payload["meta"]["avg_len"] == 0.0
    assert payload["postings"] == {} and payload["df"] == {}


def test_export_oversized_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """超过 3 MB 直接报错，绝不导出超大个人工作区（契约 §5）。"""

    db = _mini_db(tmp_path)
    monkeypatch.setattr(export, "MAX_EXPORT_BYTES", 10)
    with pytest.raises(ValueError, match="3 MB"):
        export.export_index(db, str(tmp_path / "too_big.json"))
