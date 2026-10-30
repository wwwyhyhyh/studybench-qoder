# 学研台 StudyBench 核心模块代码评审

总体结论：在演示规模（12 篇语料、百级块）下四个模块功能正确且单测面覆盖到位，未发现 Critical；风险集中在「安全/健壮性边界」（SQL 字面量与 LIKE 转义、ingest 幂等并发窗口、全文索引重建窗口、`asyncio.run` 重入）与「契约-实现漂移」（`avg_len=0` 兜底、`chunk_terms.term` 列宽、mtime 时区），其中 6 条 Important 值得本轮修复或回报主控裁定。

评审范围：`store.py`、`search.py`、`ingest.py`、`state.py`；口径对照 `CONTRACTS.md` §3/§4/§7。只读评审，未改代码。

## Critical

无。四模块没有数据丢失、越权或可远程触发的注入路径；`upsert_document` 的 LIKE 拼接目前被 `doc_id` 的十六进制字符集关闭（见 I-1 的边界说明），不构成 Critical。

## Important

### I-1 `store.py:84` SQL 字面量转义只覆盖「反斜杠开启」这一种 sql_mode —— 缺陷（安全边界，当前未触发）

```python
return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"
```

影响：转义完全依赖 MySQL/OceanBase 的 `NO_BACKSLASH_ESCAPES` 关闭（默认如此），但应用在任何地方都没有固定 `sql_mode`。一旦服务端/连接参数启用 `NO_BACKSLASH_ESCAPES`，输入 `a\' OR 1=1 --` 会被转成 `'a\\\' OR 1=1 --'`，字符串在第三个反斜杠后的引号处提前闭合，剩余部分成为 SQL——这是真实可复现的逃逸，不只是理论。另外该函数不转义 `%`/`_`，任何使用者把它塞进 LIKE 都会被数据改写语义。`upsert_document:197` 的 `LIKE old_id||'#%'` 现在安全，只是因为 `doc_id` 恒为 `d`+sha1 十六进制（见 `ingest.py:28-32`），属于「靠调用方不变式兜底」而非转义层保证。

建议：引号用 SQL 标准的 `''` 双写（两种 sql_mode 下都成立），把 LIKE 转义拆成独立 `escape_like()`（额外转义 `%`、`_`、`\`），并在 `Store.__init__` 显式设置 sql_mode 或至少把假设写进 docstring。

### I-2 `store.py:193-208` + `ingest.py:245-252` ingest 幂等是 check-then-act，跨连接无原子性 —— 缺陷（并发窗口）/ 取舍

```python
old = self.one("SELECT doc_id FROM docs WHERE path = " + escape_sql(doc["path"]))
if old is not None:
    ...
self.execute("INSERT INTO docs (doc_id, path, ...) VALUES (...)")
```

影响：两个 ingest 进程同时处理同一 `corpus_demo` 时，双方都 SELECT 不到旧 doc，随后先提交者成功，后提交者撞 `uk_path` 抛 `StoreError`；`ingest_directory` 没有逐文件容错，整批直接失败（退出码 3）。同一路径交叉执行「删旧-写新」时也可能读到别人写完一半的块。当前 CLI 是单进程一次性命令，所以判为取舍可接受；但 `scripts/run_in_wsl.sh` 若被并行调用就会踩到。

建议：捕获 `uk_path` 冲突后转为「按 path 查到 doc_id 再删写」重试一次；或在 ingest 入口对库目录加进程锁。若维持现状，至少在 `ingest_directory` 文档里写明「同一库禁止并发 ingest」。

### I-3 `store.py:157-167` 每次 ingest 都 DROP/CREATE 全库全文索引 —— 缺陷（迁移逻辑常态化）

```python
try:
    self.execute("DROP INDEX ft_chunks ON chunks")
except StoreError:
    pass
self.execute(_FULLTEXT_DDL)
```

影响：这段的意图是「SPACE→NGRAM 迁移」，但它挂在 `ensure_schema()` 上，而 `ensure_schema()` 被每次 `ingest` 无条件调用（`ingest.py:239`）。后果有三：① 每次 ingest 都要对全库重建索引，成本 O(语料) 而非 O(变更文档)；② DROP 与 CREATE 之间存在窗口，期间并发 `search` 的 `MATCH` 会抛错，被 `store.py:322-326` 静默吞掉并退化到 `term_coverage`；③ 该退化的候选集与站点导出 `postings` 的打分路径不同，会让 `verification/expected_results.json` 的 parity 偶发、静默漂移（尤其 ingest 与 parity 校验并发时）。

建议：先查 `information_schema` / `SHOW INDEX` 判断索引是否存在及 parser 是否为 NGRAM，只在缺失或 parser 不符时重建；迁移做成一次性 `--migrate` 或在 ingest 完成后统一执行一次。

### I-4 `state.py:468,519,543,576,606` 五个公开函数都用 `asyncio.run` 包裹 —— 取舍 + 缺陷（宿主边界）

```python
    return asyncio.run(run())
```

影响：当前仓库里全部是同步 CLI 调用，因此实际不会触发，属可接受的实现取舍；但任何已运行事件循环的宿主（未来 Web/调度器、`pytest-asyncio` 测试、被 `digest`/`evidence` 的异步化改造复用）调用一次就抛 `RuntimeError: asyncio.run() cannot be called from a running event loop`。附带代价是每次调用新建事件循环、SQLite 连接，并重复执行 `ScopeApplication(...).bootstrap_default()`（`state.py:331`），多任务批量场景是 N 次初始化。

建议：保留同步签名，但把核心写成 `async def _xxx_async(...)`；同步壳用 `asyncio.get_running_loop()` 检测——无 loop 时 `asyncio.run`，有 loop 时抛带指引的 `RuntimeError`（或丢到单线程执行器）。若坚持现状，请在 §7 文档注明「仅限同步宿主」。

### I-5 `state.py:499-504` blockers 只追加、不可解除 —— 缺陷（业务可恢复性）

```python
blockers=(
    list(current.blockers)
    + _as_str_list(patch["blocker"] if "blocker" in patch else patch["blockers"])
    if "blocker" in patch or "blockers" in patch
    else list(current.blockers)
),
```

影响：`_PATCH_KEYS` 里没有任何「移除/清空 blocker」的入口，`update_task(..., {"blockers": []})` 也只是追加空列表。配合 `list_tasks` 的排序键 `0 if item["blockers"] else 1`（`state.py:536`），一个任务只要被标过一次 blocked 就永久置顶，无法通过正常命令标记「已解除」，看板会持续失真。`decisions` 只追加是合理的审计语义，`blockers` 不是。

建议：给 `blockers` 定义覆盖语义（传列表即替换），或新增 `resolve_blocker`/`blockers: null` 语义；同时顺手拦掉「patch 非空但每个键都求值为空」的无意义 revision（当前会白增一版）。

### I-6 `store.py:193-200` 幂等以 path 为键，重命名/移动文件会留下幽灵文档 —— 取舍（契约只定义按 path 幂等）

```python
old = self.one("SELECT doc_id FROM docs WHERE path = " + escape_sql(doc["path"]))
```

影响：`doc_id = sha1(path)`，文件改名或换目录后 path 与 doc_id 同时变化，旧 `docs/chunks/chunk_terms` 不会被匹配删除，也不会被任何清理逻辑回收；检索与 `index_export.json` 会同时保留旧、新两份内容，旧记录的 `path` 指向已不存在的文件——「找得到」给出的引用会打不开。删除源文件同理，只有 `--reset` 能清。契约 §3 只规定了按 path 幂等，没有规定 prune，所以这是有意的范围取舍；但在真实笔记库里改名是高频操作，代价不小。

建议：增加 `ingest --prune`（以本次扫描到的 path 全集反查 docs，删除不在集合内的 doc），或在报告里列出「库中已无源文件」的 path，交由用户决定是否清理。

## Minor

### M-1 `search.py:100-101` 摘录定位用归一化词项去匹配原文 —— 缺陷

```python
positions = [pos for pos in (text.find(term) for term in matched_terms) if pos >= 0]
```

影响：`term` 来自 `tokenize()`，已做 NFKC + ASCII 小写（`terms.py:60,81`），而 `text` 是原文。查询 `BM25`、`SeekDB` 或全角写法时 `find` 恒为 -1，摘录退化为「从开头截 160 字」，§4.3「命中词前后截取」失守。不影响得分与站点 parity（摘录不进打分），但引用质量下降。

建议：对原文做同样的 NFKC/小写并维护偏移映射，或按原文子串做大小写不敏感扫描后再定位。

### M-2 `search.py:122` `top` 是死参数 —— 取舍/缺陷（API 误导）

```python
    top: int = 10,
```

影响：函数体内从未使用 `top`，真正的截断发生在 `SearchOutcome.as_dict(top=...)`（`cli.py:92,127`）。直接调用库函数的代码传 `top=3` 会拿到全部命中，容易误以为已截断。

建议：删掉该参数，或改为在 `search()` 内截断并同步 `n_hits` 语义（注意 §6 要求空结果结构含真实 `n_hits`，两者需区分「总命中」与「展示条数」）。

### M-3 `search.py:133-134` `avg_len=0` 的兜底在契约之外，parity 有分叉风险 —— 取舍

```python
avg_len = (sum(n_chars_rows) / n_chunks) if n_chunks else 0.0
avg_norm = avg_len if avg_len > 0 else 1.0
```

影响：契约 §4.2 的分母是 `avg_len`，没有定义 0 的情况；Python 侧用 1.0 兜底，得分为 0。若站点 `app.js` 直接按公式除以 `avg_len`，全空库/全空块时会得到 `NaN`/`Infinity`，与 Python 不一致。当前演示语料 `avg_len>0`，不触发，属可接受取舍；但这是 parity 的隐性契约缺口。

建议：把「`avg_len<=0` 时取 1.0」写进 §4.2，并同步到 JS 实现与 `verification/` 说明。

### M-4 `ingest.py:107-111` 二级标题识别不感知代码围栏，且 `###` 文档不切块 —— 缺陷（边界）

```python
h2_indexes = [
    index
    for index, line in enumerate(lines)
    if line.lstrip().startswith("##") and not line.lstrip().startswith("###")
]
```

影响：```` ``` ```` 围栏内以 `## ` 开头的示例行会被当成真标题，把代码块从中间切开，`line_start/line_end` 与引用随之错位；反过来，通篇用 `###` 组织的小节会被合并成一个「引言块」，失去小节粒度（`##标题` 不带空格也被当成标题解析）。演示语料暂未踩中，但「工作流」类笔记出现 markdown 示例的概率不低。

建议：扫描时维护三反引号/波浪线围栏状态；标题层级以「出现的最小 level」为准聚类，而不是硬编码 `##`。

### M-5 `ingest.py:171` mtime 用系统本地时区（naive），与全项目固定 +08:00 不一致 —— 缺陷（时区）

```python
"mtime": datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y-%m-%d"),
```

影响：`store.now_iso` 和 `state._now` 都固定 `+08:00`（`store.py:31,94`），唯独 mtime 跟随进程本地时区。WSL 默认 UTC 时，23:00–24:00 修改的文件会记成前一天，直接影响 `--since` 过滤与 `mtime` 排序，并把偏差带进站点导出的 `docs[].mtime`。

建议：`datetime.fromtimestamp(ts, tz=CST)`（CST 已在 state 侧定义，可下沉到 store/ingest 共用），保证三种时间口径一致。

### M-6 `ingest.py:200-201` 静默排除 `.`/`_` 前缀路径，且不计入 skipped —— 取舍（但无提示）

```python
if path.is_file()
and not any(part.startswith((".", "_")) for part in path.relative_to(src).parts)
```

影响：排除 `_tasks/`、`.git/` 是必要的；代价是用户自己的 `_notes.md` 或 `_draft/` 会被无声忽略，而返回结构里的 `skipped` 只统计空文件，`docs + skipped` 与目录中 md 文件数对不上，排查时无迹可循。

建议：把因前缀规则排除的 `.md` 也列进 `skipped`（或新增 `excluded` 字段并写原因），保留当前过滤行为不变。

### M-7 `store.py:400` `--tail` 负值直接拼进 LIMIT —— 缺陷（参数校验）

```python
"ORDER BY qid DESC LIMIT " + str(int(limit))
```

影响：`sb log --tail -1` 会执行 `LIMIT -1`，seekdb 报语法/参数错误后包成 `StoreError`，CLI 以退出码 3（数据库错误）结束；按 §6 这应是 2（参数错误）。`cli.py:197` 直接透传，未见下界校验（对比 `search` 的 `--top` 有校验，`cli.py:80-81`）。

建议：在 `query_log_tail` 内 `limit = max(0, int(limit))`，并在 CLI 补 `--tail ≥ 1` 校验统一报参数错误。

### M-8 `store.py:291-295` 与 `search.py:131` 为算均值把整列 `n_chars` 拉回 Python —— 取舍（小语料可接受）

```python
n_chunks_rows = self.execute("SELECT n_chars FROM chunks")
n_chunks = len(n_chunks_rows)
...
avg_len = total_chars / n_chunks if n_chunks else 0.0
```

影响：每次 `search`、每次 `stats`（`doctor`/`evidence` 还会再调）都做一次全表行传输，内存与耗时随块数线性增长；12 篇语料下无感，但 `search` 是热路径，属于会随语料膨胀的隐性成本。

建议：改用 `SELECT COUNT(*), AVG(n_chars) FROM chunks` 一次聚合（注意 `AVG` 的空表返回 NULL 需兜底，且浮点求和顺序可能与 Python `sum` 有末位差异，需先确认 parity 容差）。

### M-9 `store.py:49` `chunk_terms.term VARCHAR(128)` 与契约 §3 的 `VARCHAR(64)` 漂移 —— 契约漂移（需主控确认）

```python
chunk_id VARCHAR(96) NOT NULL, term VARCHAR(128) NOT NULL, tf INT NOT NULL,
```

影响：分词侧 ASCII 上限 48 字符（`terms.py:38`），CJK 词项恒为 2 字，64 与 128 都不会截断，功能上无差别；但 §3 是「改动需经主控」的冻结 DDL，实现自行放宽并让 `_MAX_TERM_CHARS=128` 与之配套，属于未回报的契约漂移，后续任何人按契约建库/迁移都会对不上。

建议：要么把列宽收回 64、`_MAX_TERM_CHARS` 收到 64，要么由主控更新 §3 并注明放宽理由。

### M-10 `store.py:322-326` `fulltext_recall` 吞掉一切 `StoreError` —— 取舍（§4.3 退路）+ 可观测性缺陷

```python
try:
    rows = self.execute(sql)
except StoreError:
    return []
```

影响：§4.3 确实要求「召回为空时退化为 term_coverage」，但这里把「索引不存在 / 权限 / 磁盘 / 语法错误」与「真的零召回」压成同一个分支：检索静默降级、无日志、无计数，I-3 的窗口与 parity 漂移因此无法从产物中定位。

建议：只对「索引缺失/未建」这一类错误返回空，其它错误上抛或至少写一条 warning（可进 `query_log` 或 stderr），保留降级能力但让降级可见。

### M-11 `state.py:327-337` `__aenter__` 中途失败不归还已打开的 profile —— 缺陷（资源泄漏）

```python
self._profile_context = SQLiteProfile.open(SQLiteConfig(url=url), tables=BUILTIN_TABLES)
self.profile = await self._profile_context.__aenter__()
self.scope_id = (await ScopeApplication(self.profile.database).bootstrap_default()).scope_id
```

影响：`async with _Session(...)` 只在 `__aenter__` 正常返回后才保证 `__aexit__`。若 `bootstrap_default()`（建库/迁移/scope 初始化）抛错，profile 已打开但没有任何路径关闭它；结合 I-4 每次调用新建事件循环，反复失败会累积 SQLite 连接与文件锁。

建议：在 `__aenter__` 内 try/except，失败时 `await self._profile_context.__aexit__(...)` 后再重抛（注意幂等，避免 `__aexit__` 被调用两次）。

### M-12 `state.py:403-405` 与 `462-465` 元数据 status 不随进度更新、add 冲突静默 —— 取舍（语义需说明）

```python
status = (body.status if body is not None else "") or _metadata_of(source)["status"]
```

影响：`update_task(status="done")` 只写进 progress body，`TaskSource.metadata.status` 永远是 `add_task` 时的初值；`resume_task` 返回的 `task.status`（`state.py:563`）因此可能与最新 body 的 status 矛盾（同一任务两处口径不同）。另外重复 `add` 时 `except RevisionConflictError: pass` 会让调用方拿到「别人写的」最新 revision 却无任何提示——同 spec 时是无害幂等，spec 已变时则会掩盖问题。

建议：在 §7 明确 status 的唯一真源是 latest artifact，`resume` 输出里去掉或标注 metadata.status 为「初始值」；add 冲突分支至少区分「spec 相同（静默）」与「spec 不同（报错）」，或直接比较已有 source metadata 后再决定。
