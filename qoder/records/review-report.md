# 御史验收审查报告 · 学研台 StudyBench（Qoder 赛道）

- 审查对象：`E:\CodeX\PowerContext-2026\qoder\` 全目录（本地产物，未 push）
- 审查时间：2026-10-30 03:00 – 03:40（+08:00）
- 审查方式：只读审查 + 可执行验证（WSL2 Ubuntu 24.04 / sb-venv 实测），未修改任何代码/文档/配置，未做 git 写操作，未联网
- 报告人：wb-reviewer

---

## 判决：FAIL

存在 2 条 Important（0 Critical / 2 Important / 8 Minor）。两条 Important 均不影响「引擎与证据的真实性」这一核心结论——实测证据链非常扎实；I1 是 Qoder 跑批脚本一处必然失败的门禁，I2 是提交材料的三处未落定（均为已如实标注的待办）。补齐后可转 PASS。

## 判据逐条结论

| # | 判据 | 结论 | 关键证据 |
| --- | --- | --- | --- |
| 1 | 可复现 | PASS | `bash qoder/scripts/sb.sh selftest` 实测 **69 passed in 304.73s**（exit 0）；全新库链路 ingest→search→task→resume→digest→export→evidence 全部亲手跑通；`verification/logs/` 五份日志与命令自洽（ingest/index/export 时戳衔接、search.log 10 条 exit=0、memory.log r1→r2 时戳单调、digest 含 t-qoder 与 /tmp/sb-demo-pc.db 一致）；`records/seekdb-query-record.md` 的 qid=1 行与实库逐字段同源（qid/ts/q/top_chunk/n_hits=33/elapsed_ms=2474 完全一致） |
| 2 | 技术真实性·seekdb | PASS | `store.py` 四表 + NGRAM FULLTEXT DDL（`_FULLTEXT_DDL`）；ingest 真实写入 docs/chunks/chunk_terms；search 走 `MATCH(searchable_text) AGAINST(...)` 召回（探针实测：二叉树查询召回 13 块、分光计查询 4 块），空时退 `chunk_terms` 覆盖查询；BM25 的 tf/df 来自 `chunk_terms`。`records/index_export.json`：用 `terms.py` 独立重算全部 96 块的 postings/df，**零偏差**；df 抽查手算：满二=1、叉树=7、kruskal=3，与导出值一致；96 块 text 与语料原文全量比对一致（line_start=小节标题行、text=其后正文）；文件 813171 字节实测相符 |
| 3 | 技术真实性·PowerContext | PASS | `state.py:74-118` import 官方 `powercontext.*` 公共接口与 `powercontext.builtin.persistence`（SQLiteProfile/BUILTIN_TABLES/SourceRepository/ArtifactRepository/ScopeApplication），导入失败即终止、无降级路径；实测 `state.POWERCONTEXT_LOCATION=/home/vertin/sb-venv/.../powercontext/__init__.py`（PyPI 官方 1.4.1）、`STORAGE_BACKEND=powercontext.builtin.persistence/sqlite`；状态库实为官方 51 张 `pc_*` 表，pc_artifacts 有 4 行真实 revision（t-official r1-r4）。自造链验证：`sb.sh task --pc-db /tmp/rv.db` add→r1、update→r2、**新进程** resume 读出 r1→r2（用后已删） |
| 4 | 站点 | PASS | dist 与 src 三文件逐字节一致；零外链资源（唯一 `https` 是页脚仓库超链接，非资源加载；无 `src="http`/`url(http`/`@import`）；`node qoder/site/test/parity.mjs` 实测 **PASS 27 / FAIL 0（exit 0）**；hero/试用区数字经 `data-meta` 从 `data/index_export.json` meta 填充（app.js `fillMeta`），非硬编码；375px 无横向滚动（样式推断：720px 下 split-table 转堆叠卡、`.term`/`.table-scroll` 内部滚动、`body{overflow-x:clip}` 兜底，无超宽固定宽度）；`LOGS:REPLACE`/`REPO:REPLACE` 已无残留 |
| 5 | 文档一致性 | PASS | RUN.md/sample.md 每条命令与 `cli.py` argparse 逐一核对一致（含 `--src`/`--pc-db`/`--tasks`/`--out`；CWD 约定与 `run_in_wsl.sh` 的 cd DEST、`_resolve_src` 的 qoder/ 前缀剥离吻合）；数字核对：12 篇/96 块/11983 词项/372.7 平均块长/813171 字节/69 项测试全部实测相符；110 次检索可精确对账（见 M2）；p50 29.6ms 为计时数据未独立复现（见 M7）。CONTRACTS.md 一行过时（见 M3） |
| 6 | 提交材料六项 | PASS（就绪度缺口见 I2） | README 材料表六行落点齐全明确；`qoder-dev-record.md` 待填项（UID/版本/截图）逐处标注、§3 如实为「等待跑批」、§5 诚实分工声明区分 Qoder 与人工，且明确「不把人工成果记成 Qoder 成果」 |
| 7 | 脱敏 | PASS（1 Minor） | 正则扫 corpus_demo 与 site/dist：无邮箱/手机号/学号/姓名模式命中；tasks.json 全为编造演示任务并按契约含 2 done/2 doing/1 blocked/1 下周到期；语料「示例数据」标注到位。唯一残留：site/dist 内嵌实录含 `/home/vertin/...`（见 M1） |
| 8 | Qoder 侧脚本 | FAIL | `bash -n` 四脚本全过；隔离环境实测 `--dry-run`：6 条 prompt 全部打印、qoder CLI 仅被 `--version` 调用 2 次（无请求类子命令）、不联网不扣额度成立；RUN-QODER.md 六条任务表/发布四步/回滚段与脚本入参逐项对得上。**但 T3 门禁引用不存在的 JSON 键，跑批必然在 T3 停批（I1）；--dry-run 有三个未披露副作用（M4）** |
| 9 | 红线扫描 | PASS | 无凭据值（token 仅以占位符出现，长随机串扫描无命中）；无越权删除/作用域外破坏；git 操作限本地 add/commit/tag-f/revert 建议，无 push、无不可逆命令；对外发布（qoder_publish_site.sh）有 `--yes` 显式门控且未执行；运行时状态写 WSL `~/sb-run/` 与 /tmp，符合文档声明 |

---

## Important（2 条）

### I1 · scripts/qoder_dev_batch.sh:103 — T3 门禁引用不存在的 JSON 键 `hits`，跑批必然在 T3 停批

- **证据**：T3 门禁为
  `bash qoder/scripts/sb.sh related --chunk "$(bash qoder/scripts/sb.sh search '完全二叉树' --json | python -c 'import sys,json;print(json.load(sys.stdin)["hits"][0]["chunk_id"])')"`。
  而 `search --json` 输出的是 `SearchOutcome.as_dict()`（`studybench/search.py:82-92`），顶层键为 `query/terms/n_hits/n_chunks/avg_len/elapsed_ms/results`，经 `cli.py:89-90` 原样单行输出——**没有 `hits` 键**。`json.load(...)["hits"]` 必抛 KeyError → python 退出非 0 → `eval "$gate"` 失败 → 脚本按 ：76-84 打印「门禁未通过，停批」并 `exit 1`。
- **影响**：T3 必挂 → T4/T5/T6 永远不执行；RUN-QODER.md 宣称的六条任务流程在该脚本当前形态下走不通（且会留下一个 failed.patch 现场与无谓的额度消耗——T3 会话本身已跑完）。
- **证据形式说明**：此结论来自 JSON 键集的代码对读，未实际执行真跑批（需 Qoder 登录态）；KeyError 由键集直接决定，与环境无关。
- **修复建议**：把 `["hits"]` 改为 `["results"]`（顺带可加 `--top 1` 减少输出）；改后用 `bash qoder/scripts/sb.sh search '完全二叉树' --json | python -c 'import sys,json;print(json.load(sys.stdin)["results"][0]["chunk_id"])'` 自验。

### I2 · 提交材料三处未落定：站点 URL、代码仓库 URL、Qoder 开发记录正文（§3 空骨架）

- **证据**：`README.md:29-30` 材料表前两行为 `<!-- 待填 -->`；`records/qoder-dev-record.md:11,14`（UID、版本待填）与 `:30`（§3 表格仅有一行「等待跑批」）；`RUN-QODER.md:12` 自述「还缺：Qoder 登录态」；站点未发布（无 URL 可填）。
- **影响**：按当前状态直接提交，则六项材料中 1（站点URL）、2（代码仓库URL）、5（Qoder 开发记录）实质空缺。属**就绪度缺口**而非真实性问题——所有待填处标注清楚，RUN-QODER.md 提供了完整补齐路径（§1 登录 → §2 跑批 → §3 发布 → 回填）。
- **修复建议**：按 RUN-QODER.md §1→§2→§3 顺序执行（先修 I1 再跑批）；跑批后把 summary.md 誊入 dev-record §3、填 UID 与截图位；发布后回填 README 材料表与提交平台。另按 RUN-QODER.md §5.1 确认仓库对评委可见（见 M6）。

## Minor（8 条）

1. **M1 · site/dist/index.html:186（site/src 同源）**：内嵌终端实录含开发机用户名路径 `库：/home/vertin/sb-run/.runtime/sb.db`。判据 7 将「个人路径」列入脱敏范围；RUN.md 同位置写作 `/home/<你>/`。建议 `inject_site_logs.py` 注入时把 `/home/vertin` 泛化为 `/home/<user>` 后重注入。
2. **M2 · records/usage-metrics.md:3,22**：采集时间戳 03:10，但「110 次 / 108 命中(98.2%) / 去重 22 / 平均 27.2」实为 02:58（计时脚本完成）后、03:01（再发生 30 次检索）前的快照；实测现库已 140 行（140=110+30 可精确对账；按 qid 序取前 110 行，四项数字与文中**逐项吻合**）。数字真实，但今日复现者读库会得 140。建议注明快照时点或刷新数据。
3. **M3 · CONTRACTS.md:77**：「PowerContext 走主仓源码：PYTHONPATH 需同时含仓库根（src/ 在仓库根）」与实际不符——`powercontext` 位于 `<repo>/src/powercontext`，`PYTHONPATH=$REPO_WSL`（不含 `/src`）导入不到它；实测实际加载 venv 内 PyPI 官方 1.4.1（与 README/RUN.md 一致）。冻结文件需主控修订该行。
4. **M4 · scripts/qoder_dev_batch.sh:29,87-88,125-126**：`--dry-run` 并非 RUN-QODER.md:41 所述「只看 prompt」：还会 (a) `git tag -f qoder-baseline-*`、(b) 向 `records/qoder-logs/summary.md` 追加表头、(c) 完整跑一次 selftest（隔离环境复现三副作用；真 selftest 实测约 5 分钟）。「不发请求、不扣额度」本身成立（stub 实测 qoder 仅 `--version` ×2）。建议 dry-run 分支跳过这三步或在文档披露。
5. **M5 · scripts/inject_site_logs.py:49 + site/dist/index.html:233-235**：⑤ 周报摘录切片 `memory.log[29:40]` 截掉了周报标题与「## 本周完成」行，站点实录从列表中间开始，观感缺上下文。建议切片上移或补一行省略说明。
6. **M6 · site/dist/index.html:307**（待确认）：页脚称仓库「评审期已授权」，其可见性无法在本机验证；RUN-QODER.md:96-100 自己也把「仓库对评委不可见」列为会直接挂掉的坑。缺：平台侧仓库可见性确认。
7. **M7 · records/usage-metrics.md:33-38**（待确认）：p50 29.6ms / p95 34.5ms / 冷启动 2039.1ms 为计时类数据，未独立复现。方向与实测一致（CLI 单次端到端 ~2.1s ≈ 冷启动 2.0s + 检索 ~30ms；search.log 2078ms 吻合），复现脚本已随文给出。缺：同机重跑计时脚本。
8. **M8 · records/powercontext-state-record.md:4,8-37**：快照描述的状态库（4 任务：t-demo/t-demo-b/t-demo-c/t-verify-a）已不存在——现库仅 t-official（r1-r4@02:37），状态库在快照生成（01:37:44）后被重建。快照本身机制真实（生成时间、结构与本次自造链一致），但评审者重跑 `evidence` 将得到不同内容，t-demo×3 同文任务已无法复核。建议重新生成随仓库记录，或在文中注明状态库已重置。

## 提醒（范围外，不计级）

- `records/*.md` 两份与 `verification/expected_results.json:3` 亦含 `/home/vertin` 路径（判据 7 只点 corpus_demo 与 site/dist，故未计入 M1）。
- seekdb `query_log.qid` AUTO_INCREMENT 跳号严重（实测 min=1、max=89000001、count=140）——引擎行为，不影响任何文档声明，qid 排序仍单调。
- 审查期间 03:06 `studybench/tests/` 有外部改动：审查开始时在场的 `_probe_natural.py`、`_verify_natural.py` 被删除（非审查者所为；无 `test_` 前缀不影响 69 项收集与 selftest 结果）。请君上确认是否为团队清理。
- 站点页脚仓库链接含 GitHub 账号名（Castorice104）——属提交仓库本身归属信息，不计为脱敏问题。

## 实测记录（供复核）

- selftest：`bash qoder/scripts/sb.sh selftest` → **69 passed in 304.73s**（exit 0）。
- 全新库链路：`ingest_directory('corpus_demo','/tmp/rv-sb.db',reset=True)` → 12 docs/96 chunks；三条查询（满二叉树…/归并排序…/kruskal…）top-5 与 `verification/expected_results.json` **全等**（28.069435/17.259432/28.706917）；export → 12/96/11983 词项/813171 字节（临时库与导出用后已删）。
- 记忆链路：`sb.sh task --pc-db /tmp/rv.db` add→r1、update→r2、新进程 resume 读出 r1→r2（已删）。
- digest：空库四段「本周无」；`--tasks corpus_demo/_tasks/tasks.json` 导入后四段输出与 memory.log 实录同构（临时库已删）。
- evidence：`--out-dir /tmp/rv-rec` 两文件生成正常（用后已删；未触碰仓库 records/）。
- parity：`node qoder/site/test/parity.mjs` → PASS 27 / FAIL 0（exit 0）。
- 探针：FULLTEXT 召回 13/4 块；状态库 51 张官方 `pc_*` 表、pc_artifacts 4 行、pc_sources 1 行。
- 导出对拍：postings/df 全量重算零偏差；df 抽查 满二=1/叉树=7/kruskal=3；96 块 text 与语料全量一致；`records/` 与 `site/dist/data/` 两份 index_export.json 除 generated_at 外逐字节等价；`--dry-run` 于隔离临时仓库实测（qoder 以 stub 替身、sb.sh 以 stub 替身，真仓库零改动）。

---

## 复审（2026-10-30 03:40 · 对象：修复提交 ee993df1）

范围：仅对上轮 9 条判 ADDRESSED / NOT ADDRESSED + 修复范围内新问题扫描 + 两项回归确认。未重新漫游全案；除本文件外零写入，git 仅只读查询。

### 复审判决：FAIL（仅 1 条新 Important，见 N-A；修复面极小）

### 逐条判决

| 条目 | 判决 | 证据（一行） |
| --- | --- | --- |
| I1 | **ADDRESSED** | 门禁改函数 `gate_t1..gate_t6`（qoder_dev_batch.sh:34-56）；`["hits"]` 残留 0；gate_t3 改读 `verification/expected_results.json` 的 `results[0].top5[0].chunk_id`（实测该行 Python exit 0 → `debd232c7#c01`）；4 脚本 `bash -n` 全过；隔离环境 dry-run 打印 6 条 prompt |
| M1 | **ADDRESSED** | site/src 与 site/dist `grep -c /home/vertin` 均为 0，实测渲染为 `库：/home/&lt;user&gt;/...`（sanitize() 泛化后 html.escape）；src=dist 三文件逐字节一致 |
| M2 | **ADDRESSED** | usage-metrics.md:27-31 注明「截至 03:10 的快照 / 复核时实测 140 行=110+30 / 按 qid 升序取前 110 行逐项吻合 / evidence 固定取最近 100 条属展示上限」，与本人实测完全一致（措辞瑕疵见 N3） |
| M3 | **ADDRESSED** | CONTRACTS.md:77-78 改为「PyPI 官方包 powercontext[builtin]==1.4.1…SB_POWERCONTEXT_SRC 仅作可选覆盖」，与实测 POWERCONTEXT_LOCATION（venv site-packages）一致 |
| M4 | **ADDRESSED** | 隔离环境复测 dry-run：6 条 prompt、qoder 仅 `--version` ×1、**无任何 sb.sh 调用（自测未跑）**、git tag 0→0、summary.md 未生成；真跑分支保留（:29-31/:115-118/:148-155 的 DRY=0 守卫） |
| M5 | **ADDRESSED** | inject_site_logs.py 新增 `digest_block()`：从 `$ studybench digest` 行起取 10 行；站点 ⑤ 块现为「命令行 + 周报标题 + ## 本周完成」（dist:232-235），不再从列表中间开始 |
| M6 | **ADDRESSED** | 页脚（src:307=dist:307）改为「私有仓库，如需访问请联系提交者开通」，不再声称已授权 |
| M8 | **ADDRESSED（但引入 N-A）** | 两份 records 于 03:24 重生成：状态记录 = t-official r1@02:37:21→r4@02:37:31，与本复审上轮实库读取逐字段一致；检索记录 = 最近 100 条，首行=实库最新行（qid 90000001@03:23:38）逐字段同源。**下游引用未同步（N-A）** |
| I2 | **ADDRESSED（作为如实待办）** | README 材料表：站点URL行补回填命令 `bash qoder/scripts/qoder_publish_site.sh --yes`；代码仓库行明确分支+「提交前须对评委开放，见 RUN-QODER.md §5」；dev-record 行注明 §3 跑批自动填、§1/§4 人工补。§3 本身仍空但如实（等待跑批），无伪装完成。材料落定本身依赖君上 Qoder 登录态，未在本机闭环——按「已知待办如实、可执行」标准达标，不视为「材料已齐」 |

### 回归确认（两项均通过）

1. `node qoder/site/test/parity.mjs` → **PASS 27 / FAIL 0（exit 0）**，未破坏（app.js 与 expected_results.json 均不在修复提交改动面内）。
2. `qoder_publish_site.sh` 不在修复提交改动面内，`--yes` 门控原样保留（:18 `YES=0` / :59 干跑退出）；本次复审未执行任何发布。

### 修复范围内新发现

- **N-A（Important）· M8 的下游引用未同步**：`verification/sample.md:50` 仍引 `records/seekdb-query-record.md:9-11` 为「qid=1、命中 33」——现 :9-11 是表头+qid=90000001 行（qid=1 已在 100 条窗口之外）；`verification/sample.md:99` 仍引 `records/powercontext-state-record.md:38-44` 的 t-verify-a r1→r2——现记录仅 17 行、只含 t-official r1→r4，被引行不存在（其「存储引擎 sqlite3」描述也已过时，现记录为 `powercontext.builtin.persistence/sqlite`）；`README.md:22` 分工表仍写「真实任务版本链 r1→r2 实录」。qid=1 行实测仍在库中（(1, 01:36:08, 完全二叉树叶子结点和度为2的结点关系, debd232c7#c01, 33)）、t-verify-a 机制仍可复现，失效的是「随仓库记录中的位置引用」——验证样例与一页说明两份提交材料出现 doc-vs-doc 失配。修复：更新 sample.md:50/:99 与 README.md:22 的引用（改指现行记录行，或改为「实库可查+复现命令」表述）。
- **N1（Minor）· gate_t4 较原门禁弱化**（qoder_dev_batch.sh:46-49）：移除了原 `href="https?://…\.(css|js)` 检查，`<link href="https://…css">` 类外链资源不再被拦（src=/url(/@import 仍拦）。建议补回该模式。
- **N2（Minor）· gate_t3 编码依赖**（qoder_dev_batch.sh:40）：`open('qoder/verification/expected_results.json')` 未显式 `encoding='utf-8'`，本机实测可跑（exit 0），但依赖 Windows locale 编码，其他环境存在 UnicodeDecodeError 误挂门禁的风险。建议加 `encoding='utf-8'`。
- **N3（nit）· usage-metrics.md:29 归因不精确**：「复核新增 30 次」——该 30 行（03:01-03:02）发生于本次复审首次读库之前，复审者未向默认库写入任何检索；数字与对账本身准确，建议改中性表述（如「快照后新增 30 次（开发自验）」）。
- **N4（观察）**：`records/screenshots/`（3 张真实渲染截图 + README，含 375px 视口 `scrollWidth==clientWidth==375` 的 headless 实测记录，正面补强上轮的 375px 样式推断）目前**未被 git 跟踪**，提交前需 `git add`，否则不随仓库交付。
- **销项**：上轮提醒「审查期间 tests/_probe_natural.py、_verify_natural.py 被删」已在 ee993df1 正式入账（提交 stat 含这两处删除），来源澄清，提醒关闭。

---

## 终审（2026-10-30 · 对象：修复提交 66d35a42，限定 delta 范围）

范围：仅 66d35a42 相对 ee993df1/8a43c757 的 15 文件 delta 及其直接影响面（48 字符规则、门禁两处、文档引用改造、§6 实测、导出 JSON）。未重跑 pytest 全量（提交者自述 70 passed；本审实跑 test_terms.py 7 passed）。除本文件追加外零写入；git 与 WSL 演示库均为只读查询（检索验证会向演示库 query_log 追加行，属运行态、不入仓库）。

### 终审判决：**FAIL（1 Important + 3 Minor；Important 为单行文档修复，修掉即转 PASS）**

### A–G 逐条

| 判据 | 判决 | 证据（实测） |
| --- | --- | --- |
| A src/dist 一致 + 零外链 | **PASS** | `cmp` 三文件（app.js/index.html/styles.css）逐字节一致；gate_t4 新 grep 模式对 dist 零匹配；dist 唯一外部 URL 为 index.html:307 页脚 GitHub 仓库 `<a>` 超链接（非资源引用）；合成样本 `<link href="https://...">` 可被新模式命中（N1 确已补回） |
| B dry-run 无副作用 | **PASS** | 实跑 exit 0，打印 6 条 prompt + 尾注；前后 `git status --porcelain` 均 0 行；`git tag -l 'qoder-baseline-*'` = 0；summary.md 未生成；门禁函数定义但 DRY=1 在 :67 提前 return（gate_t3 的 python 一行另实测 exit 0）。副作用仅 `qoder --version`（:23）与 `mkdir -p` 已存在目录。注：qoder 未安装时 dry-run 会 exit 2（:23 前置依赖，非本提交引入） |
| C parity 27/0 | **PASS** | `node qoder/site/test/parity.mjs` → PASS 27 / FAIL 0，exit 0 |
| D 前端检索未破坏 | **PASS** | 实查 `sb.sh search "满二叉树和完全二叉树区别"` → top1 `debd232c7#c01` / `28.069435` / line 7，与 expected_results.json results[0].top5[0] 六位小数逐字段相等；JS 侧由 parity「满二叉树和完全二叉树区别」PASS 覆盖；佐证：本提交前后 index_export.json 的 postings/df/docs/chunks 全等（仅 meta.generated_at 02:20:46→03:36:39），demo 最长词项仅 17 字符，48 字符规则不改变 demo 行为；test_terms.py 7 passed。现状说明：CLI 尚无 doctor/verify/related（T1–T3 属跑批待做、门禁先行），`sb.sh verify --check` 现阶段 exit 2 属预期，非回归 |
| E 文档引用 + §6 自洽 | **PASS（附 3 Minor）** | 6 份文档 `records/*.md:行号` 引用 grep 零残留；sample.md :50/:99 改内容型核对、README 分工表同步 t-official r1→r4。§6 外部印证：E:\GLM 实测 510 个 md（≈「约 500」）；全部 md 最长 ASCII 游程实测恰为 **439 字符**，与缺陷叙事精确吻合；3424 块≈7.9 块/篇（demo 8.0）；119.2s/436 篇≈0.27s/篇、p50 59.8ms 对 35× 语料（demo 29.6ms）幅度合理、无夸大；20 万行/155873 去重比 1.28 合理；「修复后零跳过」与 terms 48 上限 + store 128 兜底口径一致 |
| F 脱敏 | **FAIL（1 Important）** | usage-metrics.md:63 写入真实工作区路径 `E:\GLM`，判据「§6 无路径」被违反，且与同节 :80「没有把任何…文件路径…写进仓库」自相矛盾；`git grep -F GLM` 证实 8a43c757 全仓无此字样，本提交首次引入。站点 src/dist 无个人路径（/home/*、Users、vertin、Lenovo、AppData、E:\GLM 全零匹配）；§6 其余仅统计量，/tmp/sb-real.db 为通用临时路径 |
| G 红线扫描 | **未触碰** | 15 文件 diff 无凭据值（仅 PAT 变量名，既有）；无破坏性删除/不可逆 git 操作/对外发布；改动全部在 qoder/ 作用域内；两份 index_export.json 仅 generated_at 变化；新增 qoder-prompts.md 为 6 条任务 prompt 原样导出，无敏感信息；上轮复审报告入账属记录归档 |

### 新增问题清单

- **F-1（Important）· usage-metrics.md:63 泄露真实工作区路径 `E:\GLM`**：违反判据 F「§6 只写统计量、无路径」，并与本节 ：80 隐私声明直接矛盾。修复（单行）：改为「本机真实的个人学习工作区（约 500 个 markdown）」。
- **E-1（Minor）· usage-metrics.md:58 §5 数字未随新用例更新**：仍写「pytest 69 项全绿（引擎 43 + 记忆层 26）」，同提交新增回归用例后应为 70（提交信息自述 70 passed；§6 亦已宣布该用例）。
- **E-2（Minor）· usage-metrics.md:28-31 §2「可 log --tail 复现」已失效**：实测现库 query_log 仅 1 行（03:36 重置重建后；本人验证检索 = qid 91000001）。「110/140」快照措辞诚实，但「复现」现只能经 committed 留档 records/seekdb-query-record.md（100 条）实现，建议改「留档见 records/…」；「自然模式召回探针与站点对拍又写入 30 条」的归因在库重置后无法对现库复核，按上轮取证（M2 已核数）采信。
- **E-3（nit）· sample.md:50 核对指引方向有歧义**：「与文件里最新一行的 n_hits 对上」，而记录表明确「按 qid 倒序」——重生成后最新一行是**首行数据**而非文件末行，建议改「qid 最大的一行（表按 qid 倒序，即首行数据）」。

### 销项与范围外提醒

- 上轮 N-A（下游引用失配）/N1（gate_t4 弱化）/N2（gate_t3 编码）/N3（归因措辞）/N4（截图未跟踪）逐条复核：**N-A ADDRESSED**（sample.md 两处 + README 改内容型引用，行号引用全仓零残留）、**N1 ADDRESSED**（link-href 模式补回且实测可命中）、**N2 ADDRESSED**（encoding='utf-8' 已加，实测 exit 0）、**N3 ADDRESSED**（措辞已改中性，归因细节见 E-2 备注）、**N4 ADDRESSED**（screenshots 3 张已随 8a43c757 入库，git ls-files 实证）。
- 提醒（范围外，不计入判决）：records/seekdb-query-record.md:5 等记录头部仍含 WSL 用户名路径 `/home/vertin/...`——本提交未触碰，系上轮 M1 只对站点脱敏、未覆盖 records/ 目录的遗留面，交付前可斟酌统一。
