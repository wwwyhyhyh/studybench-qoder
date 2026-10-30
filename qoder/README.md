# 学研台 StudyBench · 一页技术说明

**把散落在文件夹里的课程笔记变成可检索的知识，把多线程任务的进度变成可复用的记忆**——CLI `studybench`（生态题作品，代码在本目录 `qoder/`），两条命令串起「找得到 + 不忘事」。

## 解决什么问题

- **笔记散、搜不到**：常见检索工具按空格/英文分词，「分光计调到什么程度算调好」这类中文口语查询无从下手；学研台用 seekdb 全文索引（NGRAM 分词）召回 + BM25 重排，一句话直接命中小节，给出 `path:line` 引用与得分分解。
- **任务多、接不上**：隔周回到一个多线程任务，不记得做到哪、卡在哪；每次 `task update` 落一个不可变进度快照（PowerContext Artifact，版本链可追溯），`task resume` 读最近 3 版直接输出「上次做到哪 / 现在卡在哪 / 下一步」。
- **汇报靠回忆**：周报手工拼凑易漏易编；`digest` 从任务记忆汇出固定四段周报（本周完成 / 进行中 / 风险与阻塞 / 下周计划），纯确定性模板，不调用任何 LLM。

## 核心功能

1. **混合检索 `search`**：seekdb 四表存储（docs / chunks / chunk_terms / query_log）+ NGRAM 全文索引中文召回 + 结构化过滤（`--course` / `--kind` / `--since`）+ BM25 重排（k1=1.2、b=0.75，`tf_eff = tf_text + 2×tf_heading`，标题命中权重 ×2）；输出 6 位小数得分分解、`path:line` 引用与摘录；每次检索写一行 `query_log` 留痕。
2. **任务记忆 `task add/update/status/resume`**：任务 = PowerContext `Source`（`studybench.task`），进度 = `Artifact`（`progress` family）不可变 revision；`status` 看板按 blockers 置顶、due 升序；`resume` 续做。
3. **周报与索引导出 `digest` / `export`**：`digest` 固定四段确定性周报；`export` 产出自包含 `index_export.json`（813171 字节，≤ 3 MB），浏览器端复刻同一套分词与 BM25。

## 技术分工

| 组件 | 承担什么 | 证据 |
| --- | --- | --- |
| **seekdb**（pylibseekdb 1.3.0.post4 嵌入式，OceanBase 内核） | 文档/块/词项存储与中文召回：`docs`、`chunks`、`chunk_terms`、`query_log` 四表 + **NGRAM 全文索引**（SPACE 分词器最小词长 3 不适用中文 2-gram，故改用 NGRAM，见 `store.py` 裁决注释）+ 结构化过滤；BM25 在其词项统计上重排 | `studybench/studybench/store.py`（`_FULLTEXT_DDL`）；`records/seekdb-query-record.md`（query_log 实录）；`verification/logs/{ingest,index,search,export}.log`；`records/index_export.json`（12 篇 / 96 块 / 11983 词项 / 平均块长 372.7） |
| **PowerContext**（PyPI `powercontext==1.4.1[builtin]`） | 任务记忆与周报：`Source` 存任务规格、`Artifact` 存不可变进度 revision（`progress` family），组合根走 `context.Sources` / `context.Artifacts`，**存储引擎用官方 `powercontext.builtin.persistence`**（`SourceRepository` / `ArtifactRepository`，SQLite 文件），重启后版本链可读、可续写 | `studybench/studybench/state.py` 文件头声明（`BACKEND = "powercontext"`，`STORAGE_BACKEND = "powercontext.builtin.persistence/sqlite"`）；`records/powercontext-state-record.md`（真实任务 t-official 的 r1→r4 版本链实录） |
| **Qoder** | 开发协作与站点托管：并行开发按 `CONTRACTS.md` 契约推进（表结构/打分公式/CLI/验收口径全部先行冻结）；站点发布目录 `site/dist/` 为纯静态（Qoder Sites 免费版仅支持静态托管），零外链、断网可 `file://` 打开 | `CONTRACTS.md`；`site/dist/`（index.html、styles.css、app.js、data/index_export.json）；`site/test/parity.mjs`（读 `verification/expected_results.json`，实测 `PASS 27 / FAIL 0`：浏览器端与 Python 的 top-5 顺序及 6 位小数得分完全一致） |

## 提交材料映射

| 材料 | 位置 |
| --- | --- |
| 站点 URL | **https://studybench-e1bvhnt3g1g.qoder.website/**（已发布，访问范围=任何人可访问；发布目录 `qoder/site/dist/`，重发命令 `bash qoder/scripts/qoder_publish_site.sh --yes`） |
| 代码仓库 | 本仓库 `2026-competition-ecosystem` 分支的 `qoder/` 目录（团队私有 → **提交前须对评委开放**，见 RUN-QODER.md §5） |
| 运行说明 | [RUN.md](RUN.md)（干净 Linux 从零跑通，全部命令实跑核对） |
| 验证样例 | [verification/sample.md](verification/sample.md)（配 `verification/expected_results.json` 与 `verification/logs/`） |
| Qoder 开发记录 | [records/qoder-dev-record.md](records/qoder-dev-record.md)（§3 由 `bash qoder/scripts/qoder_dev_batch.sh` 跑批后自动填；§1 UID 与 §4 截图需人工补） |
| 使用效果材料 | `records/usage-metrics.md`（演示语料 110 次检索 / p50 29.6ms / 10-10 命中；**另在真实个人工作区 436 篇笔记、3424 块上实测：建索引 119s、检索 p50 59.8ms**，仅统计量不含内容）＋ `records/`（记录均由命令自动生成）＋ `verification/logs/`（终端实录） |

## 目录结构

```
qoder/
├── CONTRACTS.md            # 实现契约：表结构 / 打分公式 / CLI / 验收口径
├── README.md               # 本文件
├── RUN.md                  # 干净 Linux 从零跑通手册
├── studybench/             # Python 包（requires-python >=3.12）
│   ├── studybench/         # cli / terms / store / ingest / search / export / evidence / state / tasks / digest
│   └── tests/              # 82 项单测（引擎 + 记忆层，pytest 9.2.0 全绿）
├── corpus_demo/            # 12 篇脱敏演示语料（7 个课程目录）
│   ├── _tasks/tasks.json   # 6 个演示任务
│   └── _queries.json       # 10 条演示查询（含预期命中小节与考察点）
├── site/                   # 站点：src/ 源码、test/parity.mjs 一致性校验
│   └── dist/               # 发布目录：index.html、styles.css、app.js、data/index_export.json
├── verification/           # sample.md、expected_results.json、logs/*.log
├── records/                # CLI 自动生成的使用记录（禁止手写数值）
└── scripts/                # sb.sh（Windows Git Bash → WSL2 包装）、run_in_wsl.sh
```

运行时状态不在仓库内：seekdb 库默认 `~/sb-run/.runtime/sb.db`，状态库默认 `~/sb-run/.runtime/powercontext.db`，首次运行自动创建，`--db` / `--pc-db` 可覆盖。

## 已知限制（如实）

1. **Windows 不能直接运行**：pylibseekdb 只发布 Linux/macOS x86_64 wheel，Windows 宿主装不上；需 WSL2 或原生 Linux，且 seekdb 库目录必须落在 ext4，不能放 `/mnt/*`（9p 挂载打不开）。
2. **中文走 NGRAM 而非 SPACE**：seekdb 的 SPACE 分词器最小词长 3，切不出中文 2-gram，故全文索引用 NGRAM 分词器（`store.py` 内注释「裁决·锚点1」，与契约 §3 初稿不同）；BM25 词频仍以同一套 2-gram 词项落 `chunk_terms`。
3. **站点是静态镜像**：浏览器端用导出的 `index_export.json` 复刻同一套分词与 BM25（parity 实测一致），不是在线数据库查询；`query_log` 与任务记忆只在 CLI 侧。
4. **PowerContext 用官方 builtin 后端**：`powercontext==1.4.1[builtin]` 从 PyPI 安装，存储走官方 `powercontext.builtin.persistence` 的异步仓储（同步 CLI 内以 `asyncio.run()` 包裹），因此状态库是官方 schema（多表），不是自造格式；旧版自写同形库文件升级后不通用，需新建。
5. **评测机无 uv 时**：用 venv+pip 备选安装（含 `--without-pip` + get-pip 的免 sudo 路线），见 RUN.md「故障排查」。

## 许可

MIT。
