# 学研台 StudyBench · 实现契约（并行开发的唯一接口依据）

> 本文件由主控（君上）裁定，**改动需经主控**。所有子任务按此实现；实现与契约冲突时以契约为准，
> 并回报 `DONE_WITH_CONCERNS` 说明冲突点。

## 0 项目一句话

把散落在文件夹里的课程笔记、实验报告、竞赛资料变成**可检索的知识**（seekdb 存储 + 全文/中文 2-gram/结构化混合检索），
把多线程任务的进度与下一步变成**可复用的记忆**（PowerContext Source/Artifact），两条命令串起「找得到 + 不忘事」。

- 产品名：**学研台 StudyBench**；CLI 名 `studybench`，别名 `sb`（文档里统一写 `studybench`）。
- 仓库落点：`2026-competition-ecosystem` 分支的 `qoder/` 目录（生态题要求）。
- 运行环境：**WSL2 Ubuntu 24.04 + ext4**（pylibseekdb 无 Windows wheel）。Windows 侧只做编辑与 git。

## 1 目录与文件所有权（并行时严禁越界）

```
qoder/
├── CONTRACTS.md                 # 主控
├── README.md                    # 材料6 一页技术说明（翰林）
├── RUN.md                       # 运行说明（翰林）
├── RUN-QODER.md                 # Qoder 侧手册（主控/翰林）
├── studybench/                  # Python 包（A：引擎；B：记忆）
│   ├── pyproject.toml           # A
│   ├── studybench/
│   │   ├── __init__.py          # A
│   │   ├── __main__.py          # A
│   │   ├── cli.py               # A（argparse 全部子命令接线；B 的命令用惰性 import）
│   │   ├── terms.py             # A（分词/2-gram/停用词，契约 §4）
│   │   ├── store.py             # A（seekdb 建库/DDL/写入/查询）
│   │   ├── ingest.py            # A（markdown → chunks + doc 元数据）
│   │   ├── search.py            # A（候选召回 + BM25 重排 + 引用）
│   │   ├── export.py            # A（index_export.json，契约 §5）
│   │   ├── evidence.py          # A（由 query_log / 状态库生成 records 文件）
│   │   ├── state.py             # B（PowerContext 任务记忆）
│   │   ├── tasks.py             # B（tasks.json 读取与校验）
│   │   └── digest.py            # B（周报生成）
│   └── tests/
│       ├── test_terms.py test_ingest.py test_store.py test_search.py test_export.py   # A
│       └── test_state.py test_digest.py test_tasks.py                                 # B
├── corpus_demo/                 # D（12 篇脱敏演示语料 + _tasks/tasks.json + _queries.json）
├── site/                        # C
│   ├── src/index.html styles.css app.js
│   ├── test/parity.mjs          # C（Node 侧一致性校验）
│   └── dist/                    # C（可发布目录：index.html styles.css app.js data/index_export.json）
├── verification/                # 主控（sample.md / expected_results.json / logs/）
├── records/                     # A、B、主控（自动生成，禁止手写数值）
└── scripts/
    ├── run_in_wsl.sh            # 主控（WSL 内：同步到 ext4 + 跑 CLI）
    └── sb.sh                    # 主控（Windows 侧包装：bash qoder/scripts/sb.sh <args>）
```

**并行期间禁止**：`git add/commit`（主控统一提交）、改他人文件、改 `corpus_demo/`（D 独占）、
安装新的 Python 依赖（需要时回报主控）。

## 2 运行方式（所有子任务统一，勿自创）

Windows Git Bash 侧：

```bash
bash qoder/scripts/sb.sh --help
bash qoder/scripts/sb.sh ingest --src qoder/corpus_demo
bash qoder/scripts/sb.sh search "完全二叉树叶子结点和度为2的结点关系" --top 3
```

`sb.sh` 内部：把 `qoder/` rsync 到 WSL 的 `~/sb-run/qoder`（ext4），用 `~/sb-venv/bin/python`
以 `PYTHONPATH=<pkg dir>` 跑 `python -m studybench`。**seekdb 库目录必须在 ext4**（默认
`~/sb-run/.runtime/sb.db`，可用 `--db` 覆盖；不要把库放在 `/mnt/*`）。

测试：

```bash
bash qoder/scripts/sb.sh selftest          # = python -m pytest qoder/studybench/tests -q
```

依赖已装好：`pylibseekdb 1.3.0.post4`、`pydantic>=2.10,<3`、`rfc8785`、`typing-extensions`、`pytest 9.2.0`。
PowerContext 用 **PyPI 官方包** `powercontext[builtin]==1.4.1`（装进同一 venv，`import powercontext` 直接可用；
`SB_POWERCONTEXT_SRC` 仅作源码覆盖的可选项，正常路径不需要）。

## 3 seekdb 数据模型（A 实现，B 只读 `tasks` 不碰检索表）

库名 `sb`。四张表 + 一个全文索引（已在 WSL 实测 DDL 全部通过）：

```sql
CREATE TABLE docs(
  doc_id VARCHAR(64) PRIMARY KEY, path VARCHAR(512) NOT NULL, title VARCHAR(255) NOT NULL,
  course VARCHAR(128) DEFAULT '', kind VARCHAR(64) DEFAULT '', mtime VARCHAR(32) DEFAULT '',
  sha256 CHAR(64) NOT NULL, UNIQUE KEY uk_path(path));

CREATE TABLE chunks(
  chunk_id VARCHAR(96) PRIMARY KEY, doc_id VARCHAR(64) NOT NULL, seq INT NOT NULL,
  heading VARCHAR(255) NOT NULL, line_start INT NOT NULL, line_end INT NOT NULL,
  text MEDIUMTEXT NOT NULL, n_chars INT NOT NULL, searchable_text MEDIUMTEXT NOT NULL,
  KEY idx_doc(doc_id));

CREATE FULLTEXT INDEX ft_chunks ON chunks (searchable_text) WITH PARSER SPACE;

CREATE TABLE chunk_terms(               -- BM25 的 tf/df 来源
  chunk_id VARCHAR(96) NOT NULL, term VARCHAR(64) NOT NULL, tf INT NOT NULL,
  PRIMARY KEY(chunk_id, term), KEY idx_term(term));

CREATE TABLE query_log(                 -- 使用数据与检索证据
  qid BIGINT AUTO_INCREMENT PRIMARY KEY, ts VARCHAR(32) NOT NULL, q TEXT NOT NULL,
  top_chunk VARCHAR(96), n_hits INT, elapsed_ms INT);
```

- `chunk_id = "<doc_id>#c<seq:02d>"`，`doc_id = "d<sha1(path)[:8]>"`（稳定、幂等重导）。
- `searchable_text` = `heading` + 空格 + 该块 2-gram/词项空格串（供 seekdb FULLTEXT 召回，
  `WITH PARSER SPACE` 按空格切词）。**同一份词项同时写 `chunk_terms`**，两者必须一致。
- `n_chars = len(text)`（不含 heading）。
- 幂等：`ingest` 先按 `docs.path` 删除旧 doc 的全部 chunks/chunk_terms 再写；`--reset` 清空全库。
- 只读路径禁止 DDL；`store.py` 对外暴露 `open_db(path)`、`ensure_schema()`、`upsert_document()`、
  `iter_chunks()`、`log_query()`、`stats()`。

## 4 分词与打分（**Python 与 JS 必须逐条一致**，这是站点 parity 测试的依据）

### 4.1 归一化与切词 `terms.tokenize(text) -> list[str]`

1. `s = unicodedata.normalize("NFKC", text)`（JS: `s.normalize("NFKC")`）。
2. 遍历字符分「游程」：CJK 游程 = `[\u3400-\u4dbf\u4e00-\u9fff]` 连续；ASCII 词 = `[A-Za-z0-9]` 连续。
   其余字符（空白、标点、全角符号、emoji）为分隔。
3. ASCII 词：`ascii_lower()` 后取 **长度 ≥ 2** 的词；长度 1 丢弃。
4. CJK 游程：取全部 **2-gram**（相邻两字）；若游程长度为 1，取该单字。
5. 去停用词：`terms.STOPWORDS`（单字 CJK 与 ASCII 停用词，见 §4.4）；**只过滤整词项**，
   2-gram 即使含停用字也保留（如「的数」「点的」保留）。
6. 返回**按首次出现顺序去重**的词项列表（顺序影响不了分数，但导出/日志要稳定）。

`terms.tf_map(text) -> dict[str,int]` 统计词频（同一套分词）。

### 4.2 BM25（n_chars 长度归一）

```
idf(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
score(c) = Σ_{t ∈ query_terms ∩ terms(c)} idf(t) * tf_eff(t,c) * (k1 + 1)
                                          / (tf_eff(t,c) + k1 * (1 - b + b * n_chars(c) / avg_len))
k1 = 1.2, b = 0.75
tf_eff(t,c) = tf_text(t,c) + 2 * tf_heading(t,c)      # 标题命中权重 ×2，已并入落库的 tf
N = chunk 总数，avg_len = mean(n_chars)
```

- 少于 1 个查询词项 → 直接返回空结果（CLI 提示「查询无可检索词项」）。
- 排序：`score` 降序 → `heading_hit`（查询词项命中 heading 的个数）降序 → `mtime` 降序 → `chunk_id` 升序。
- 字符串比较一律按 Unicode 码点（Python 默认 = JS 默认）。

### 4.3 召回与过滤

- 候选召回：seekdb `SELECT chunk_id FROM chunks WHERE MATCH(searchable_text) AGAINST ('<词项空格串>')`，
  单个词项加双引号避免布尔语法误伤；召回为空时退化为 `chunk_terms` 的 `term IN (...)` 覆盖查询。
- 结构化过滤（`--course` / `--kind` / `--since`）用 `docs` 表 JOIN，不参与打分。
- 输出每条命中：`chunk_id, score(6 位小数), doc.path, heading, line_start, line_end, excerpt(≤160 字，命中词前后截取), matched_terms`。

### 4.4 停用词（硬编码于 `terms.py`，并写入导出的 `meta.stopwords`）

```
CJK 单字：的 了 是 在 和 与 对 用 为 及 或 等 就 都 也 要 会 能 把 被 从 而 其 之 个 中 上 下 不 有 我 你 他 这 那 有 所 以
ASCII：the a an of to in on for and or is are was were be been it this that with as at by from
```

（实现时按集合去重；上面有重复项是刻意的提醒，去重后入库。）

## 5 `index_export.json`（A 产出，C 消费；**字段与语义冻结**）

`studybench export --out <path>` 写出站点可用的自包含索引（只含**演示语料**，绝不导出个人工作区）：

```json
{
  "version": 1,
  "meta": {"project": "学研台 StudyBench", "corpus": "demo", "generated_at": "2026-10-30T01:00:00+08:00",
           "n_docs": 12, "n_chunks": 96, "avg_len": 132.7, "k1": 1.2, "b": 0.75,
           "stopwords": ["的", "了", "..."]},
  "docs": [{"doc_id": "d1a2b3c4", "path": "数据结构/树与二叉树.md", "title": "树与二叉树",
            "course": "数据结构", "kind": "笔记", "mtime": "2026-10-26"}],
  "chunks": [{"chunk_id": "d1a2b3c4#c03", "doc_id": "d1a2b3c4", "seq": 3,
              "heading": "性质三：n0 = n2 + 1", "line_start": 42, "line_end": 58,
              "text": "...", "n_chars": 143}],
  "postings": {"性质": {"d1a2b3c4#c03": 3}, "完全": {"d1a2b3c4#c03": 2}},
  "df": {"性质": 7, "完全": 5}
}
```

要求：`postings` 的键是词项，值是 `{chunk_id: tf_eff}`；`df` 与 `postings` 键集一致；
文件 ≤ 3 MB；`text` 原样保留（站点展示摘录与引用）。

## 6 CLI 命令表（A 接线；B 的命令签名见 §7）

```
studybench ingest  --src <dir> [--db <path>] [--course <name>] [--kind <name>] [--reset]
studybench search  "<query>" [--db <path>] [--course X] [--kind Y] [--since YYYY-MM-DD] [--top N] [--json]
studybench index   [--db <path>] [--json]                 # 文档数/块数/词项数/平均块长
studybench export  --out <path> [--db <path>]             # §5
studybench log     [--db <path>] [--tail 10] [--json]     # query_log 尾部（使用数据）
studybench task    add|update|status|resume ...           # §7
studybench digest  [--week 2026-W44] [--out <path>] [--tasks <json>]
studybench evidence --out-dir records [--db <path>]       # 生成 seekdb-query-record.md + powercontext-state-record.md
studybench selftest                                       # 提示用：跑 pytest
```

- 退出码：0 成功；2 参数/输入错误；3 依赖或数据库错误；4 无结果（search 专用，stdout 仍输出空结果结构）。
- `--json` 输出**单行 JSON**（便于脚本与证据归档），默认输出人读版（含表格与引用）。
- 所有 `search` 必须写 `query_log`（含空结果，`n_hits=0`）。

## 7 PowerContext 记忆层（B 实现）

**必须真用主仓 `src/powercontext` 公共接口**（`powercontext.sources.Source/SourceRef`、
`powercontext.artifacts.Artifact/ArtifactDraft`、`powercontext.context.Sources/Artifacts`），
不得自造 Parquet/JSON 私有格式替代；后端用主仓自带关系型后端（SQLite 文件，路径
`~/sb-run/.runtime/powercontext.db`，由 `--db`/`SB_PC_DB` 指定）。若主仓接口在本分支不可用，
允许像 `minimax/context_module/ctxm/state.py` 那样做**同形降级**，但必须在 README「已知限制」注明并回报主控。

数据形状：

- 一个任务 = 一个 `Source`（`kind="task"`，`external_id=task_id`），metadata 存
  `title/course/due/priority/status`（JSON）。
- 一次进度更新 = 一个 `Artifact`（`kind="progress"`，`source=该任务`），body JSON：
  `{"done": [...], "doing": [...], "next": [...], "blockers": [...], "decisions": [{"ts","text"}], "updated_at": "..."}`。
- `resume` = 读该任务最近 3 个 progress artifact，输出「上次做到哪 / 现在卡在哪 / 下一步」。
- `status` = 每任务取最新 artifact 渲染看板，按 `due` 升序、`blockers` 非空置顶。

对外签名（`cli.py` 按此接线，A 不关心内部）：

```python
def add_task(db_path: str, spec: dict) -> dict           # spec: task_id,title,course,due,priority
def update_task(db_path: str, task_id: str, patch: dict) -> dict   # done/doing/next/blocker/decision/status
def list_tasks(db_path: str) -> list[dict]               # 含 latest progress 摘要
def resume_task(db_path: str, task_id: str) -> dict      # {task, last_updated, done, doing, next, blockers, decisions}
```

`tasks.json` 形状（D 产出，B 读取）：

```json
{"tasks": [{"task_id": "t-tou", "title": "物理实验：扭摆法数据处理", "course": "物理实验",
            "due": "2026-10-27", "priority": "high", "status": "done",
            "done": ["拟合 Ix-x^2 图", "不确定度计算"], "doing": [], "next": ["交报告"], "blockers": []}]}
```

周的界说：ISO 周（周一至周日，本地时区 +08:00），`--week 2026-W44`；默认当前周。

## 8 周报 `digest`（B）

`digest.build_digest(db_path, week) -> str`，Markdown，固定四段（标题含周号与日期区间）：

1. **本周完成**（status=done 或本周有 `done` 增量）
2. **进行中**（doing/next 非空）— 每条带「下一步」
3. **风险与阻塞**（blockers 非空，或 `due` 落在下周且未完成）
4. **下周计划**（next 归并去重）

要求：纯确定性模板（不调用任何 LLM）；空段落写「本周无」而不是省略；表格/列表二选一保持稳定。

## 9 演示语料（D 产出）

- `qoder/corpus_demo/` 下 **12 篇中文 markdown**，按课程/类型分目录：`数据结构/`、`物理实验/`、`概率论/`、
  `科研/`、`竞赛/`、`工作流/`。每篇 `# 标题` + 4–10 个 `## 小节`，每小节 250–700 字真实可用的技术内容
  （公式用行内 `$...$`；不要空话凑字数）。总块数 90–110，总字符 2.5 万–4 万。
- **全部脱敏**：不出现真实姓名、学号、教师姓名、邮箱、手机号、GitHub 用户名、真实分数排名的个人归属；
  示例数据一律编造并标注「示例数据」。
- `corpus_demo/_tasks/tasks.json`：6 个任务（2 done、2 doing、1 blocked、1 下周到期），字段见 §7。
- `corpus_demo/_queries.json`：10 条演示查询（中文口语化，5–20 字），每条给 `query`、`expect_heading`
  （预期命中的小节标题，用词可与正文不同，**但必须是语料里真实存在的 2-gram 可召回内容**）、
  `why`（一句话：为什么这条能体现「找得到」的价值）。至少 3 条要跨课程区分（同词不同课）。

## 10 站点（C 产出）

- 发布目录：`qoder/site/dist/`（**纯静态、零外链、零 CDN、无构建步骤**）：`index.html`、`styles.css`、
  `app.js`、`data/index_export.json`。
- 内容分区（顺序固定）：Hero（一句话价值 + 两个数字）→ 问题与人群 → 核心功能（检索 / 记忆 / 周报三卡）
  → **试用区（真检索：输入框 + 演示查询 chips + 结果卡片含 `path:line` 引用与得分分解）**
  → 技术分工表（seekdb / PowerContext / Qoder 三行，每行「承担什么 + 证据在哪」）
  → 真实运行记录（终端实录片段，等宽、可横向滚动）→ 架构图（内联 SVG）→ 页脚（仓库链接占位 + 许可 + 脱敏声明）。
- 试用区必须：`fetch('data/index_export.json')` → 用 §4 的**同一套分词与 BM25**（JS 实现，`app.js` 内）打分，
  结果排序需与 Python 侧一致（`site/test/parity.mjs` 校验：读 `verification/expected_results.json`，
  对每条查询比较 top-5 顺序与 6 位小数得分，全部相等才 PASS）。
- 视觉：中文优先的编辑型排版（衬线标题 + 无衬线正文），深色底或浅色底择一贯穿；移动端 375px 不横向滚动；
  无外链字体（用系统字体栈）；所有数字与引用来自真实产物，不得编造指标。
- 无障碍/性能：`<html lang="zh-CN">`、对比度达标、首屏不依赖 JS 也能读到正文。

## 11 验收口径（御史按此判）

1. `bash qoder/scripts/sb.sh selftest` 全绿（引擎 + 记忆层单测）。
2. `ingest → search → task update → resume → digest → export` 全链路在 WSL ext4 上跑通，日志归档。
3. `verification/expected_results.json` 与站点 parity 测试一致（top-5 顺序 + 分数）。
4. `records/` 三类记录由命令自动生成（含真实 query_log 行、真实 Artifact 版本号），非手写。
5. `site/dist/` 断网可直接 `file://` 或静态服务器打开；无外链请求；375px 无横向滚动。
6. 语料无个人身份信息（姓名/学号/邮箱/手机号/真实账号）。
7. README 的技术分工表与代码事实一致（seekdb 真承担存储与召回；PowerContext 真承担状态保存）。
