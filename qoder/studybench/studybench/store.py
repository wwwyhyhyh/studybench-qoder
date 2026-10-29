"""seekdb 存储层（qoder/CONTRACTS.md §3 + 裁决·锚点1 修订）。

全文召回：``searchable_text`` 存自然文本，NGRAM 分词索引 +
``MATCH(...) AGAINST ('词1 词2 ...')`` 自然语言模式（OR 召回）；
召回为空时由调用方退 ``chunk_terms`` 覆盖查询。

职责：建库 / DDL / 幂等写入 / 查询。只读路径禁止 DDL——读命令只
:func:`open_db` + :meth:`Store.require_schema`，写命令才
:meth:`Store.ensure_schema`。

pylibseekdb 的 ``Cursor.execute`` 只接受单条 SQL 字符串、不支持参数绑定，
且 DML 的返回值不是受影响行数（恒为 0）；因此：

- 所有字面量经 :func:`escape_sql` 内联转义；
- 写操作后需要确认时用 ``SELECT COUNT(*)`` 复查；
- 事务用 ``autocommit=False`` 连接 + 每个公开写方法末尾显式 ``commit()``。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Sequence

import pylibseekdb

#: seekdb 数据库名（契约 §3）。
DB_NAME = "sb"

#: 契约时区（§7/§8：本地时区 +08:00）。
TIMEZONE = timezone(timedelta(hours=8))

_TABLE_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS docs(
      doc_id VARCHAR(64) PRIMARY KEY, path VARCHAR(512) NOT NULL, title VARCHAR(255) NOT NULL,
      course VARCHAR(128) DEFAULT '', kind VARCHAR(64) DEFAULT '', mtime VARCHAR(32) DEFAULT '',
      sha256 CHAR(64) NOT NULL, UNIQUE KEY uk_path(path))
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks(
      chunk_id VARCHAR(96) PRIMARY KEY, doc_id VARCHAR(64) NOT NULL, seq INT NOT NULL,
      heading VARCHAR(255) NOT NULL, line_start INT NOT NULL, line_end INT NOT NULL,
      text MEDIUMTEXT NOT NULL, n_chars INT NOT NULL, searchable_text MEDIUMTEXT NOT NULL,
      KEY idx_doc(doc_id))
    """,
    """
    CREATE TABLE IF NOT EXISTS chunk_terms(
      chunk_id VARCHAR(96) NOT NULL, term VARCHAR(64) NOT NULL, tf INT NOT NULL,
      PRIMARY KEY(chunk_id, term), KEY idx_term(term))
    """,
    """
    CREATE TABLE IF NOT EXISTS query_log(
      qid BIGINT AUTO_INCREMENT PRIMARY KEY, ts VARCHAR(32) NOT NULL, q TEXT NOT NULL,
      top_chunk VARCHAR(96), n_hits INT, elapsed_ms INT)
    """,
)

#: 裁决·锚点1：全文索引改用 NGRAM 分词器（中文 2-gram 由 seekdb 全文索引承担）。
_FULLTEXT_DDL = (
    "CREATE FULLTEXT INDEX ft_chunks ON chunks (searchable_text) "
    "WITH PARSER NGRAM"
)


class StoreError(RuntimeError):
    """数据库不可用 / 未初始化 / SQL 执行失败。"""


def escape_sql(value: object) -> str:
    """把 Python 值转成 SQL 字面量（NULL / 整数 / 转义字符串）。"""

    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _in_list(values: Sequence[object]) -> str:
    return ",".join(escape_sql(value) for value in values)


def now_iso() -> str:
    """契约时区（+08:00）下的当前时刻 ISO 串（秒级）。"""

    return datetime.now(TIMEZONE).isoformat(timespec="seconds")


class Store:
    """一个 seekdb 库目录的连接句柄（``<db_dir>`` + 库名 ``sb``）。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        expanded = Path(self.db_path).expanduser()
        try:
            expanded.parent.mkdir(parents=True, exist_ok=True)
            self._instance = pylibseekdb.open(str(expanded))
            bootstrap = self._instance.connect(autocommit=True)
            try:
                bootstrap.cursor().execute("CREATE DATABASE IF NOT EXISTS " + DB_NAME)
            finally:
                bootstrap.close()
            self._conn = self._instance.connect(DB_NAME)
            self._cursor = self._conn.cursor()
        except pylibseekdb.SeekdbError as error:
            raise StoreError(f"无法打开 seekdb 库 {self.db_path}: {error}") from error

    # -- 生命周期 -----------------------------------------------------

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._conn.close()
        except pylibseekdb.SeekdbError:
            pass
        try:
            self._instance.close()
        except pylibseekdb.SeekdbError:
            pass

    # -- 基础执行 -----------------------------------------------------

    def execute(self, sql: str) -> list[tuple]:
        try:
            self._cursor.execute(sql)
            return self._cursor.fetchall()
        except pylibseekdb.SeekdbError as error:
            raise StoreError(f"SQL 执行失败: {error}（{sql[:160]}…）") from error

    def one(self, sql: str) -> tuple | None:
        rows = self.execute(sql)
        return rows[0] if rows else None

    # -- DDL 与幂等写入 ------------------------------------------------

    def ensure_schema(self) -> None:
        """建四张表 + 全文索引（幂等；只允许写路径调用，契约 §3 + 裁决·锚点1）。"""

        for ddl in _TABLE_DDL:
            self.execute(ddl)
        self._recreate_fulltext_index()
        self._conn.commit()

    def _recreate_fulltext_index(self) -> None:
        """DROP 后按 NGRAM 重建 ft_chunks。

        旧库/旧索引（SPACE 解析器）借此迁移；DROP 在索引缺失时报 1091，忽略即可。
        """

        try:
            self.execute("DROP INDEX ft_chunks ON chunks")
        except StoreError:
            pass
        self.execute(_FULLTEXT_DDL)

    def require_schema(self) -> None:
        """只读路径守卫：检索表缺失时给出可操作错误（不做 DDL）。"""

        try:
            self.execute("SELECT chunk_id FROM chunks LIMIT 1")
        except StoreError as error:
            raise StoreError(
                f"seekdb 库未初始化（{self.db_path}）——请先运行 studybench ingest"
            ) from error

    def reset(self) -> None:
        """``--reset`` 清空全库（契约 §3）。"""

        for table in ("chunk_terms", "chunks", "docs", "query_log"):
            self.execute("DELETE FROM " + table)
        self._conn.commit()

    def upsert_document(self, doc: dict, chunks: Sequence[dict]) -> None:
        """按 ``docs.path`` 幂等写入一个文档及其全部块（契约 §3）。

        先删旧 doc 的全部 chunk_terms / chunks / docs 行，再整批写入，
        最后一次性 commit（中途失败不会留下半份索引）。
        """

        old = self.one("SELECT doc_id FROM docs WHERE path = " + escape_sql(doc["path"]))
        if old is not None:
            old_id = str(old[0])
            self.execute(
                "DELETE FROM chunk_terms WHERE chunk_id LIKE " + escape_sql(old_id + "#%")
            )
            self.execute("DELETE FROM chunks WHERE doc_id = " + escape_sql(old_id))
            self.execute("DELETE FROM docs WHERE doc_id = " + escape_sql(old_id))
        self.execute(
            "INSERT INTO docs (doc_id, path, title, course, kind, mtime, sha256) VALUES ("
            + ",".join(
                escape_sql(doc[key])
                for key in ("doc_id", "path", "title", "course", "kind", "mtime", "sha256")
            )
            + ")"
        )
        for chunk in chunks:
            self.execute(
                "INSERT INTO chunks (chunk_id, doc_id, seq, heading, line_start, line_end, "
                "text, n_chars, searchable_text) VALUES ("
                + ",".join(
                    escape_sql(chunk[key])
                    for key in (
                        "chunk_id",
                        "doc_id",
                        "seq",
                        "heading",
                        "line_start",
                        "line_end",
                        "text",
                        "n_chars",
                        "searchable_text",
                    )
                )
                + ")"
            )
            items = sorted(chunk["terms"].items())
            if items:
                values = ",".join(
                    f"({escape_sql(chunk['chunk_id'])},{escape_sql(term)},{int(tf)})"
                    for term, tf in items
                )
                self.execute("INSERT INTO chunk_terms (chunk_id, term, tf) VALUES " + values)
        self._conn.commit()

    # -- 读取 ---------------------------------------------------------

    def iter_docs(self) -> list[dict]:
        rows = self.execute(
            "SELECT doc_id, path, title, course, kind, mtime, sha256 FROM docs"
        )
        return [
            {
                "doc_id": str(row[0]),
                "path": str(row[1]),
                "title": str(row[2]),
                "course": str(row[3]),
                "kind": str(row[4]),
                "mtime": str(row[5]),
                "sha256": str(row[6]),
            }
            for row in rows
        ]

    def iter_chunks(self) -> list[dict]:
        rows = self.execute(
            "SELECT chunk_id, doc_id, seq, heading, line_start, line_end, text, n_chars "
            "FROM chunks"
        )
        return [
            {
                "chunk_id": str(row[0]),
                "doc_id": str(row[1]),
                "seq": int(row[2]),
                "heading": str(row[3]),
                "line_start": int(row[4]),
                "line_end": int(row[5]),
                "text": str(row[6]),
                "n_chars": int(row[7]),
            }
            for row in rows
        ]

    def iter_term_rows(self) -> Iterator[tuple[str, str, int]]:
        """全部 (chunk_id, term, tf) 行，词项升序（导出 postings/df 用）。"""

        rows = self.execute(
            "SELECT chunk_id, term, tf FROM chunk_terms ORDER BY chunk_id, term"
        )
        for row in rows:
            yield str(row[0]), str(row[1]), int(row[2])

    def stats(self) -> dict:
        """文档数 / 块数 / 词项数 / 平均块长（契约 §6 index）。"""

        n_docs = int(self.one("SELECT COUNT(*) FROM docs")[0])
        n_chunks_rows = self.execute("SELECT n_chars FROM chunks")
        n_chunks = len(n_chunks_rows)
        n_terms = int(self.one("SELECT COUNT(DISTINCT term) FROM chunk_terms")[0])
        total_chars = sum(int(row[0]) for row in n_chunks_rows)
        avg_len = total_chars / n_chunks if n_chunks else 0.0
        return {
            "docs": n_docs,
            "chunks": n_chunks,
            "terms": n_terms,
            "avg_len": avg_len,
        }

    # -- 检索召回（契约 §4.3）------------------------------------------

    def fulltext_recall(self, terms: Sequence[str]) -> list[str]:
        """FULLTEXT 召回（裁决·锚点1 修订）：NGRAM 索引 + 自然语言模式。

        ``AGAINST ('词1 词2 ...')``——词项空格分隔，不加 ``+``、不加双引号、
        不用布尔操作符。自然模式为 OR 召回，实测对 2 字 CJK、≥3 字 CJK 串、
        ≥3 字符 ASCII 词全部可召回（单字 CJK 除外，此时按契约退回
        :meth:`term_coverage`）。seekdb 引擎异常（如索引缺失）同样按空召回处理。
        """

        if not terms:
            return []
        against = " ".join(str(term) for term in terms)
        sql = (
            "SELECT chunk_id FROM chunks WHERE MATCH(searchable_text) AGAINST ("
            + escape_sql(against)
            + ")"
        )
        try:
            rows = self.execute(sql)
        except StoreError:
            return []
        return [str(row[0]) for row in rows]

    def term_coverage(self, terms: Sequence[str]) -> list[str]:
        """退路召回：chunk_terms 的 term IN (...) 覆盖查询（契约 §4.3）。"""

        if not terms:
            return []
        rows = self.execute(
            "SELECT DISTINCT chunk_id FROM chunk_terms WHERE term IN (" + _in_list(terms) + ")"
        )
        return [str(row[0]) for row in rows]

    def fetch_chunk_rows(self, chunk_ids: Sequence[str]) -> list[dict]:
        """候选块 + docs JOIN（结构化过滤与引用展示需要的字段）。"""

        if not chunk_ids:
            return []
        rows = self.execute(
            "SELECT c.chunk_id, c.doc_id, c.seq, c.heading, c.line_start, c.line_end, "
            "c.text, c.n_chars, d.path, d.course, d.kind, d.mtime "
            "FROM chunks c JOIN docs d ON c.doc_id = d.doc_id "
            "WHERE c.chunk_id IN (" + _in_list(chunk_ids) + ")"
        )
        return [
            {
                "chunk_id": str(row[0]),
                "doc_id": str(row[1]),
                "seq": int(row[2]),
                "heading": str(row[3]),
                "line_start": int(row[4]),
                "line_end": int(row[5]),
                "text": str(row[6]),
                "n_chars": int(row[7]),
                "path": str(row[8]),
                "course": str(row[9]),
                "kind": str(row[10]),
                "mtime": str(row[11]),
            }
            for row in rows
        ]

    def fetch_term_rows(self, terms: Sequence[str]) -> list[tuple[str, str, int]]:
        """查询词项在全部块中的 (term, chunk_id, tf) 行（df 与 tf 一次取齐）。"""

        if not terms:
            return []
        rows = self.execute(
            "SELECT term, chunk_id, tf FROM chunk_terms WHERE term IN (" + _in_list(terms) + ")"
        )
        return [(str(row[0]), str(row[1]), int(row[2])) for row in rows]

    # -- 使用数据（契约 §6 log）----------------------------------------

    def log_query(
        self, ts: str, q: str, top_chunk: str | None, n_hits: int, elapsed_ms: int
    ) -> None:
        self.execute(
            "INSERT INTO query_log (ts, q, top_chunk, n_hits, elapsed_ms) VALUES ("
            + ",".join(
                (
                    escape_sql(ts),
                    escape_sql(q),
                    escape_sql(top_chunk),
                    str(int(n_hits)),
                    str(int(elapsed_ms)),
                )
            )
            + ")"
        )
        self._conn.commit()

    def query_log_tail(self, limit: int = 10) -> list[dict]:
        rows = self.execute(
            "SELECT qid, ts, q, top_chunk, n_hits, elapsed_ms FROM query_log "
            "ORDER BY qid DESC LIMIT " + str(int(limit))
        )
        return [
            {
                "qid": int(row[0]),
                "ts": str(row[1]),
                "q": str(row[2]),
                "top_chunk": None if row[3] is None else str(row[3]),
                "n_hits": int(row[4]),
                "elapsed_ms": int(row[5]),
            }
            for row in rows
        ]


def open_db(db_path: str | Path) -> Store:
    """契约 §3 对外入口：打开（不建表）一个 seekdb 库句柄。"""

    return Store(db_path)
