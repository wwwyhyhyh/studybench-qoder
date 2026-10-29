# Qoder 开发任务 prompt（IDE 手工版）

> 用途：若不想用脚本跑批，可在 Qoder 桌面端/IDE 打开本仓库，把下面每条 prompt 依次粘进对话，
> 每条做完照「门禁」一栏自己跑一次命令，通过后提交。跑批脚本版见 `scripts/qoder_dev_batch.sh`。
> 生成时间：2026-10-30 03:25（`bash qoder/scripts/qoder_dev_batch.sh --dry-run` 的原样输出）


## T1 · studybench doctor 自检子命令

你在仓库 E:/CodeX/PowerContext-2026 里工作。项目是「学研台 StudyBench」：seekdb 检索 + PowerContext 任务记忆的 Python CLI，代码在 qoder/ 下。先读 qoder/CONTRACTS.md 了解口径。硬约束：只改下面点名的文件；中文注释；不新增第三方依赖；不联网；不执行 git；改完用 bash qoder/scripts/sb.sh 下的命令自测（该脚本会在 WSL 里跑，Windows 侧直接调用即可）。

新增子命令 studybench doctor。只改/新建这三个文件：qoder/studybench/studybench/cli.py（注册子命令）、qoder/studybench/studybench/doctor.py（实现）、qoder/studybench/tests/test_doctor.py。
doctor 逐项检查并打印 [OK]/[FAIL] 与细节：①Python 版本 >=3.12；②pylibseekdb 可 import 且能在临时目录开库（用完删临时目录）；③powercontext 可 import，并打印 studybench.state.STORAGE_BACKEND；④seekdb 库文件存在且 chunks 表可查（用 store.Store + require_schema）；⑤studybench index 的三项统计；⑥corpus_demo/_queries.json 存在且 >=10 条。全 OK 退出码 0，任一 FAIL 退出码 3。
测试至少 3 条：正常路径、pylibseekdb 缺失分支（monkeypatch import）、库未初始化分支。请务必实际跑一次 bash qoder/scripts/sb.sh doctor 确认输出。


## T2 · studybench verify 期望值校验子命令

你在仓库 E:/CodeX/PowerContext-2026 里工作。项目是「学研台 StudyBench」：seekdb 检索 + PowerContext 任务记忆的 Python CLI，代码在 qoder/ 下。先读 qoder/CONTRACTS.md 了解口径。硬约束：只改下面点名的文件；中文注释；不新增第三方依赖；不联网；不执行 git；改完用 bash qoder/scripts/sb.sh 下的命令自测（该脚本会在 WSL 里跑，Windows 侧直接调用即可）。

新增子命令 studybench verify。只改/新建：qoder/studybench/studybench/cli.py、qoder/studybench/studybench/verify.py、qoder/studybench/tests/test_verify.py。
行为：读 qoder/corpus_demo/_queries.json 的每条查询，调用 studybench.search.search(db, query, top=5)，产出与 qoder/verification/expected_results.json **完全同构**的 JSON（字段 generated_at/db/results[].query/expect_heading/top5[].chunk_id/score/path/heading/line_start，score 保留 6 位小数）。默认写入 verification/expected_results.json；加 --check 时与现有文件逐条比对（比较 top5 的 chunk_id 顺序与 6 位小数 score），全部一致退出 0，有差异打印差异表退出 4，文件缺失退出 3。
测试至少 3 条：同构字段、--check 全等、--check 差异（用 fixture 构造）。请实际跑 bash qoder/scripts/sb.sh verify --check 确认 exit 0。


## T3 · 相关笔记推荐 related 子命令

你在仓库 E:/CodeX/PowerContext-2026 里工作。项目是「学研台 StudyBench」：seekdb 检索 + PowerContext 任务记忆的 Python CLI，代码在 qoder/ 下。先读 qoder/CONTRACTS.md 了解口径。硬约束：只改下面点名的文件；中文注释；不新增第三方依赖；不联网；不执行 git；改完用 bash qoder/scripts/sb.sh 下的命令自测（该脚本会在 WSL 里跑，Windows 侧直接调用即可）。

新增子命令 studybench related --chunk <chunk_id> [--top N]。只改/新建：qoder/studybench/studybench/cli.py、qoder/studybench/studybench/related.py、qoder/studybench/tests/test_related.py。
行为：从 chunk_terms 取该块的词项（按 tf 降序取前 30 个），到其他块里按词项重合度（交集大小，再按 IDF 加权，口径与 search.py 的 _idf 一致）打分排序，排除自身与同文档同块，输出 top N（默认 5）的 chunk_id/score(6 位小数)/path/heading/line_start，风格与人读输出和 --json 与 search 保持一致。无命中退出 4。
测试至少 3 条：正常命中、chunk 不存在（退出 2）、空结果（退出 4）。请实际跑一次 related 确认有结果。


## T4 · 站点新增使用数据区

你在仓库 E:/CodeX/PowerContext-2026 里工作。项目是「学研台 StudyBench」：seekdb 检索 + PowerContext 任务记忆的 Python CLI，代码在 qoder/ 下。先读 qoder/CONTRACTS.md 了解口径。硬约束：只改下面点名的文件；中文注释；不新增第三方依赖；不联网；不执行 git；改完用 bash qoder/scripts/sb.sh 下的命令自测（该脚本会在 WSL 里跑，Windows 侧直接调用即可）。

在站点新增「使用数据」区块。只改：qoder/site/src/index.html、qoder/site/src/styles.css、qoder/site/dist/index.html、qoder/site/dist/styles.css（src 与 dist 必须同步一致）。
位置：放在「真实运行记录」区之前。内容：5 个统计卡，数字**只许**用这 5 个，逐个原样搬运，不得改写或换算——110 次检索、96 个检索块、29.6 ms 检索 p50、10/10 演示查询命中、69 项自动测试；数字的出处标注写 records/usage-metrics.md。
样式沿用现有 CSS 变量与栅格，375px 不横向滚动；不得引入任何外链资源或新脚本。改完请自己核对 src 与 dist 两份 index.html 的该区块文字一致。


## T5 · 核心模块代码评审

你在仓库 E:/CodeX/PowerContext-2026 里工作。项目是「学研台 StudyBench」：seekdb 检索 + PowerContext 任务记忆的 Python CLI，代码在 qoder/ 下。先读 qoder/CONTRACTS.md 了解口径。硬约束：只改下面点名的文件；中文注释；不新增第三方依赖；不联网；不执行 git；改完用 bash qoder/scripts/sb.sh 下的命令自测（该脚本会在 WSL 里跑，Windows 侧直接调用即可）。

对本项目核心模块做一次严肃代码评审，产出 qoder/records/qoder-review.md（只写这一个文件，不要改代码）。
评审范围：qoder/studybench/studybench/{store.py,search.py,ingest.py,state.py}。要求：①每条发现必须给 文件:行号 与 具体代码片段；②分级 Critical/Important/Minor 并说明影响；③至少 6 条，其中至少 2 条是真实可改进项（例如 SQL 字面量转义边界、LIKE 前缀匹配的注入面、BM25 长度归一化在 n_chars=0 时的除零、ingest 幂等的并发窗口、asyncio.run 在事件循环内的重入）；④区分「缺陷」与「取舍」，是取舍就写明为什么当前实现可接受；⑤不要复述代码结构，不要写客套话。文首给一句总体结论。


## T6 · RUN.md 命令对账

你在仓库 E:/CodeX/PowerContext-2026 里工作。项目是「学研台 StudyBench」：seekdb 检索 + PowerContext 任务记忆的 Python CLI，代码在 qoder/ 下。先读 qoder/CONTRACTS.md 了解口径。硬约束：只改下面点名的文件；中文注释；不新增第三方依赖；不联网；不执行 git；改完用 bash qoder/scripts/sb.sh 下的命令自测（该脚本会在 WSL 里跑，Windows 侧直接调用即可）。

把 qoder/RUN.md 里的每条命令与 qoder/studybench 的实际实现对账，修正不一致（只改 qoder/RUN.md 这一个文件）。
做法：逐条读 RUN.md 的命令与参数，对照 qoder/studybench/studybench/cli.py 的 argparse 定义、以及 qoder/scripts/run_in_wsl.sh 的 CWD 约定；把写错的路径、参数名、预期输出改正。保持原有结构与中文风格；如果某条命令你无法确认，保留并在该行末尾加 HTML 注释 <!-- 待核：原因 -->。不要新增章节，不要改别的文件。

（dry-run：未打 tag、未写 summary、未跑自测、未调用任何会话）
