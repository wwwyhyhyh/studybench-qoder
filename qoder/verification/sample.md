# 验证样例

两个可复跑的验证样例：**样例一**验证检索「找得到」（中文口语查询 → 命中小节 + `path:line` 引用 + 得分分解），**样例二**验证任务记忆「不忘事」（进度快照版本链 → `resume` 续做）。

- 所有预期数值取自随仓库的 `verification/expected_results.json`（引用处标注 `文件:行号`）。
- 「实际记录」是开发机（WSL2 Ubuntu 24.04，ext4）2026-10-30 的真实运行留档，都在 `verification/logs/` 与 `records/`。
- 依赖安装与 `sb` 函数定义见 `RUN.md` ①②（干净 Linux 全程见 `RUN.md`）；下面只列样例自身的命令。

---

## 样例一 · 检索：「满二叉树和完全二叉树区别」直接命中对比小节

### 初始数据

- 语料：`corpus_demo/` 下 12 篇脱敏 markdown（数据结构、物理实验、概率论、数据库、科研、竞赛、工作流 7 个课程目录）。
- seekdb 库：空（默认 `~/sb-run/.runtime/sb.db` 不存在即全新；ingest 会自动建库）。

### 输入命令

```bash
sb ingest --src corpus_demo
sb search "满二叉树和完全二叉树区别" --top 5
```

### 执行步骤

1. `ingest` 把 12 篇 markdown 按 `##` 小节切块，写 `docs` / `chunks` / `chunk_terms` 三表并创建 NGRAM 全文索引；
2. `search` 对查询串做同一套分词，先用全文索引召回候选，再用 BM25（k1=1.2、b=0.75，`tf_eff = tf_text + 2×tf_heading`）重排，输出 6 位小数得分分解与摘录；
3. 本次 search 写入一行 `query_log`（`sb log` 可查）。

### 预期结果

top-5 与 `verification/expected_results.json:8-44` 完全一致：

| # | 分数 | 位置（path:line_start） | 小节 | chunk_id | expected_results.json |
| --- | --- | --- | --- | --- | --- |
| 1 | 28.069435 | 数据结构/树与二叉树.md:7 | 满二叉树与完全二叉树 | debd232c7#c01 | :9-:15 |
| 2 | 20.010815 | 数据结构/树与二叉树.md:3 | 二叉树的定义与基本形态 | debd232c7#c00 | :16-:22 |
| 3 | 13.63341 | 数据结构/树与二叉树.md:11 | 关键性质：n0 = n2 + 1 | debd232c7#c02 | :23-:29 |
| 4 | 10.365128 | 数据结构/树与二叉树.md:31 | 堆与优先队列 | debd232c7#c07 | :30-:36 |
| 5 | 10.349773 | 数据结构/树与二叉树.md:23 | 由遍历序列重建二叉树 | debd232c7#c05 | :37-:43 |

命中总数 15；top-1 得分分解为「满二(7.831753) + 二叉(4.983046) + 叉树(5.239221) + 完全(4.140020) + 全二(5.875396)」。开发机实录中 top-1 摘录起于「满二叉树指每一层结点数都达到最大值的二叉树」（见 `verification/logs/search.log:8`）。

### 实际记录

- `verification/logs/ingest.log`：`已索引 12 篇文档、96 个块`（exit=0）；
- `verification/logs/index.log`：`文档 12 篇｜块 96 个｜词项 11983 个｜平均块长 372.7`；
- `verification/logs/search.log:1-29`：本样例查询的完整实录（同文件还含「归并排序为什么稳定」「kruskal为什么要按边权排序」两条实录，top-1 分别为 17.259432 与 28.706917，与 `expected_results.json` 第二、三组一致）；
- `records/seekdb-query-record.md:9-11`：query_log 落库证据（qid=1、top_chunk=debd232c7#c01、命中 33——该行为开发机另一条查询「完全二叉树叶子结点和度为2的结点关系」的留档，说明同一机制持续留痕）。

### 重置方法

```bash
sb ingest --src corpus_demo --reset
```

清空全库重导，预期输出 `已索引 12 篇文档、96 个块（已清空全库重导）`（实测一致）；随后重跑本样例的 search 应得到同一张表。也可以直接删掉库目录（默认 `~/sb-run/.runtime/sb.db`）后重跑 RUN.md ③ 的 ingest。

---

## 样例二 · 任务记忆：进度快照版本链与「接着做」

### 初始数据

- 状态库：全新（默认 `~/sb-run/.runtime/powercontext.db` 不存在即全新；也可用 `--pc-db` 指定一个新路径，如 `sb task --pc-db /tmp/pc-sample.db add …`，实测全新建库）。
- 不依赖样例一；检索库与状态库相互独立。

### 输入命令

```bash
sb task add --task-id t-verify-a --title "数据结构复习：树与二叉树" --course 数据结构 --due 2026-11-05 --priority high
sb task update t-verify-a --done "重推 n0=n2+1" --next "做哈夫曼题"
sb task resume t-verify-a
```

### 执行步骤

1. `task add`：一个任务 = 一个 PowerContext `Source`（`studybench.task`），同时写入 revision r1 的进度快照（`Artifact`，`progress` family）；
2. `task update`：追加一次进度 = 追加一个不可变新 revision（未给的字段继承当前版本；`--blocker` / `--decision` 为追加语义）；
3. `task resume`：读该任务最近 3 个 revision，输出「上次做到哪 / 现在卡在哪 / 下一步」与版本历史。

### 预期结果

- `add` 输出含 `revision 1`；`update` 输出含 `revision 2`，并新增 `已完成：重推 n0=n2+1` 与 `下一步：做哈夫曼题` 两行（看板行格式与 `RUN.md` ⑤ 所录一致）；
- `resume` 输出五段（时间戳为执行时刻，属机器相关量）：

```
# t-verify-a｜数据结构复习：树与二叉树
上次更新：<执行时刻>
上次做到哪：重推 n0=n2+1
现在卡在哪：无
下一步：做哈夫曼题
最近版本：r1@<执行时刻> → r2@<执行时刻>
```

### 实际记录

`records/powercontext-state-record.md:38-44`：任务 t-verify-a 最新 revision r2、版本历史 `r1 → r2`、已完成「重推 n0=n2+1」、下一步「做哈夫曼题」，与预期结果逐项一致。该记录由 `sb evidence` 自动生成，其头部（`:4-:6`）同时留档了状态库路径、模型层（`powercontext`，存储引擎 `sqlite3`，见 `studybench/studybench/state.py` 文件头声明）与任务数。

### 重置方法

换一个全新状态库路径即可（`--pc-db /tmp/pc-sample.db` 这类），或删除状态库文件（默认 `~/sb-run/.runtime/powercontext.db`）后重跑本样例。

---

## 延伸核对（可选）

- **周报**：`sb digest --tasks corpus_demo/_tasks/tasks.json --week 2026-W44` 输出固定四段（本周完成 / 进行中 / 风险与阻塞 / 下周计划），完整实录见 `RUN.md` ⑥。
- **站点一致性**：在仓库根执行 `node qoder/site/test/parity.mjs`（需 Node.js），它读 `verification/expected_results.json`，对 10 条演示查询逐条比对浏览器端与 Python 的 top-5 顺序与 6 位小数得分，预期末行 `总计：PASS 27 / FAIL 0（exit 0）`（2026-10-30 实测）。
