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
