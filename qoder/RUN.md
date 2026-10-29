# RUN · 学研台 StudyBench 从零跑通（干净 Linux）

**适用对象**：x86_64 Linux（物理机 / WSL2 / 容器均可），已 checkout 本分支，Python 3.12。
**硬约束**：pylibseekdb 只发布 Linux/macOS x86_64 wheel，Windows 宿主装不上——Windows 用户请进 WSL2（Ubuntu 24.04 实测通过）；seekdb 库目录必须落在 **ext4**（默认 `~/sb-run/.runtime/`），不要放 `/mnt/*`（9p 挂载打不开）。

以下每条命令与「预期输出」都在 WSL2 Ubuntu 24.04（Python 3.12.3）上实跑核对过（2026-10-30）；输出中的耗时、时间戳属机器相关量，会因环境而异，其余数字应逐字一致。

**约定**：`<repo>` 指分支签出根目录；除 ⑨ 与 parity 校验外，所有命令都在 `<repo>/qoder` 目录下执行。

---

## ① 依赖

需要 [uv](https://docs.astral.sh/uv/)（没有 uv 见 ⑩ 的 venv+pip 备选）。创建虚拟环境并安装三个固定来源的依赖：

```bash
cd <repo>/qoder
uv venv --python python3.12 .venv
uv pip install --python .venv/bin/python \
  'pylibseekdb @ https://files.pythonhosted.org/packages/19/e9/49507c0859bf0898f99f2b0978baba6cfaca9563e4ba20242be014ee7e6c/pylibseekdb-1.3.0.post4-cp312-abi3-manylinux_2_28_x86_64.whl' \
  'powercontext[builtin]==1.4.1' \
  'pytest==9.2.0'
```

`uv pip install` 会输出一批以 `+ ` 开头的安装行（其中必有 `+ pylibseekdb==1.3.0.post4`、`+ powercontext==1.4.1`、`+ pytest==9.2.0`）。装完用一行命令核验：

```bash
.venv/bin/python -c "import importlib.metadata as m; print(m.version('pylibseekdb'), m.version('powercontext'), m.version('pytest'))"
```

预期输出：

```
1.3.0.post4 1.4.1 9.2.0
```

## ② 运行入口与目录

```bash
cd <repo>/qoder
sb() { PYTHONPATH=studybench .venv/bin/python -m studybench "$@"; }
sb --help
```

预期输出：

```
usage: studybench [-h] command ...

学研台 StudyBench：seekdb 检索 + PowerContext 任务记忆（契约 §6）

positional arguments:
  command
    ingest    把 markdown 目录索引进 seekdb
    search    检索（结果含 path:line 引用与得分分解）
    index     索引规模：文档数/块数/词项数/平均块长
    export    导出 index_export.json（契约 §5）
    log       query_log 尾部（使用数据）
    task      任务记忆（PowerContext，契约 §7）
    digest    周报（契约 §8）
    evidence  生成 records 检索/状态记录
    selftest  运行 pytest（= bash qoder/scripts/sb.sh selftest）

options:
  -h, --help  show this help message and exit
```

说明：

- `sb` 只是 shell 函数封装，等价完整命令 `PYTHONPATH=studybench .venv/bin/python -m studybench …`；新开终端需重新定义一次。
- 运行时状态（不入仓库）：seekdb 库默认 `~/sb-run/.runtime/sb.db`，任务状态库默认 `~/sb-run/.runtime/powercontext.db`，目录会自动创建；`--db` / `--pc-db` 可覆盖。两者都必须在 ext4 上。

## ③ 初始化 + ingest

```bash
sb ingest --src corpus_demo
```

预期输出：

```
已索引 12 篇文档、96 个块
库：/home/<你>/sb-run/.runtime/sb.db
```

ingest 幂等：重跑会覆盖同路径文档的旧块。规模自检：

```bash
sb index
```

预期输出：

```
文档 12 篇｜块 96 个｜词项 11983 个｜平均块长 372.7
```

## ④ 检索

```bash
sb search "满二叉树和完全二叉树区别" --top 5
```

预期输出（实跑实录；耗时因机器而异）：

```
共 15 条命中，显示前 5 条（耗时 1882 ms，库 96 块，平均块长 372.7）

1. [28.069435] 数据结构/树与二叉树.md:7-9
   小节：满二叉树与完全二叉树
   得分分解：满二(7.831753) + 二叉(4.983046) + 叉树(5.239221) + 完全(4.140020) + 全二(5.875396)
   摘录：满二叉树指每一层结点数都达到最大值的二叉树：深度为 $k$ 的满二叉树恰有 $2^k-1$ 个结点。完全二叉树要求更宽松：只允许最后一层不满，且最后一层结点必须从左到右连续排列。因此满二叉树一定是完全二叉树，反之不成立。判断技巧：给结点按层编号后，完全二叉树的编号与同深度满二叉树完全一致，中间不能"跳号"。完全二叉…
```

再跑两条跨课程区分的查询（每条贴真实 top-1）：

```bash
sb search "归并排序为什么稳定" --top 5
# top-1：[17.259432] 数据结构/排序算法.md:11-13　小节：归并排序与分治（共 41 条命中）
sb search "kruskal为什么要按边权排序" --top 5
# top-1：[28.706917] 数据结构/图与最小生成树.md:15-17　小节：Kruskal：并查集与边排序（共 39 条命中）
```

10 条演示查询及考察点见 `corpus_demo/_queries.json`；分数应与 `verification/expected_results.json` 逐位一致（6 位小数）。`--json` 输出单行 JSON；`--course` / `--kind` / `--since` 做结构化过滤、不参与打分；每次 search 都写一行 `query_log`。

## ⑤ 任务记忆（PowerContext）

```bash
sb task add --task-id t-verify-a --title "数据结构复习：树与二叉树" --course 数据结构 --due 2026-11-05 --priority high
sb task update t-verify-a --done "重推 n0=n2+1" --next "做哈夫曼题"
sb task resume t-verify-a
sb task status
```

预期输出（时间戳为执行时刻）：

```
- t-verify-a [doing] 数据结构复习：树与二叉树
    课程 数据结构｜到期 2026-11-05｜优先级 high｜revision 1
```

```
- t-verify-a [doing] 数据结构复习：树与二叉树
    课程 数据结构｜到期 2026-11-05｜优先级 high｜revision 2
    已完成：重推 n0=n2+1
    下一步：做哈夫曼题
```

```
# t-verify-a｜数据结构复习：树与二叉树
上次更新：2026-10-30T02:36:30+08:00
上次做到哪：重推 n0=n2+1
现在卡在哪：无
下一步：做哈夫曼题
最近版本：r1@2026-10-30T02:36:28+08:00 → r2@2026-10-30T02:36:30+08:00
```

`status` 对状态库全部任务渲染看板（blockers 非空置顶、due 升序）。每次 `update` 追加一个不可变 revision（未给的字段继承当前版本，`--blocker` / `--decision` 为追加语义）。

## ⑥ 周报

```bash
sb digest --tasks corpus_demo/_tasks/tasks.json --week 2026-W44
```

预期输出（`--tasks` 先把 6 个演示任务导入状态库再渲染；2026-W44 即 2026-10-26 ~ 2026-11-01。「本周完成」的明细取决于任务导入日期与所查周，日期不同列表会变，四段结构固定）：

```
# 学研台周报 2026-W44（2026-10-26 ~ 2026-11-01）

## 本周完成

- 数据结构复习：树与二叉树（t-verify-a · 数据结构 · due 2026-11-05）：重推 n0=n2+1
- 整理排序算法笔记并完成自测（t-sb-001 · 数据结构 · due 2026-10-21）：整理八种排序对比表；手写快排、归并与堆排序实现；默写两个稳定性反例序列
- 二维随机变量习题集一轮（t-sb-002 · 概率论 · due 2026-10-25）：边缘密度与独立性判定练习；卷积公式与函数分布大题
- …（此段在开发机实跑共 6 条）

## 进行中

- 数据结构复习：树与二叉树（t-verify-a · 数据结构 · due 2026-11-05）：下一步 做哈夫曼题
- 扭摆法实验报告：数据处理与不确定度（t-sb-003 · 物理实验 · due 2026-10-31）：下一步 撰写误差分析小节
- …

## 风险与阻塞

- OceanBase 大赛复赛提交（t-sb-004 · 竞赛 · due 2026-11-10）：阻塞 干净环境复测部署脚本失败：依赖版本与赛题环境不一致，需等官方镜像更新后重跑
- …

## 下周计划

- 做哈夫曼题（数据结构复习：树与二叉树）
- 撰写误差分析小节（扭摆法实验报告：数据处理与不确定度）
- …（此段在开发机实跑共 8 条）
```

空段写「本周无」不省略；省略 `--week` 取当前 ISO 周；`--out <path>` 写文件，缺省打印到 stdout。

## ⑦ 导出索引

```bash
sb export --out /tmp/index_export.json
```

预期输出：

```
已导出 12 篇文档、96 个块、11983 个词项 → /tmp/index_export.json（813171 字节）
```

该文件与仓库随附的 `records/index_export.json` 同构（除生成时间戳）。如需让站点使用刚导出的索引，把它复制为 `site/dist/data/index_export.json` 即可。

## ⑧ 生成记录

```bash
sb evidence --out-dir /tmp/sb-records
```

预期输出（行数 / 任务数按本机实际执行量变化）：

```
已生成 /tmp/sb-records/seekdb-query-record.md
已生成 /tmp/sb-records/powercontext-state-record.md
query_log 行数：3｜任务数：7
```

默认输出目录是 `records/`——仓库随附的证据就在那里，演示时建议指向 `/tmp` 以免覆盖随仓库证据。

## ⑨ 站点本地预览

```bash
python3 -m http.server 8000 --directory site/dist
```

浏览器打开 `http://127.0.0.1:8000`（实测 `index.html` 与 `data/index_export.json` 均返回 200）。站点纯静态、零外链，断网时直接打开 `site/dist/index.html`（`file://`）也能用。试用区在浏览器内用 `data/index_export.json` 打分；与 Python 侧的一致性在**仓库根**执行下面命令校验（需 Node.js）：

```bash
node qoder/site/test/parity.mjs
```

预期输出末行：

```
总计：PASS 27 / FAIL 0（exit 0）
```

## ⑩ 故障排查

- **Windows 宿主**：装不上 pylibseekdb（无 Windows wheel）。进 WSL2 后按本手册操作；开发机另有包装脚本，在仓库根执行 `bash qoder/scripts/sb.sh --help`（内部把 `qoder/` rsync 到 WSL ext4 副本后运行，实测 exit=0）。
- **报「无法打开 seekdb 库 …」**：库目录放到了 `/mnt/*`（9p 挂载打不开 seekdb）。把库放回 ext4 默认位置 `~/sb-run/.runtime/`，或用 `--db` 指一个 ext4 路径。
- **没有 uv**：venv+pip 备选（实测可行，且不需要 sudo）：

  ```bash
  python3.12 -m venv --without-pip .venv
  curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python -
  .venv/bin/python -m pip install \
    'pylibseekdb @ https://files.pythonhosted.org/packages/19/e9/49507c0859bf0898f99f2b0978baba6cfaca9563e4ba20242be014ee7e6c/pylibseekdb-1.3.0.post4-cp312-abi3-manylinux_2_28_x86_64.whl' \
    'powercontext[builtin]==1.4.1' \
    'pytest==9.2.0'
  ```

  说明：若 `python3.12 -m venv` 直接报「ensurepip is not available」（系统缺 python3.12-venv 包），`--without-pip` + get-pip 这条路线可绕开，无需安装系统包。
- **中文检索异常 / 想重建全文索引**：全文索引用 NGRAM 分词器（seekdb 的 SPACE 分词器最小词长 3，切不出中文 2-gram），DDL 在首次 ingest 建库时自动创建；改过分词相关代码后用 `sb ingest --src corpus_demo --reset` 清空全库并重建四表与全文索引，预期输出 `已索引 12 篇文档、96 个块（已清空全库重导）`。
- **单测自检**：`PYTHONPATH=studybench .venv/bin/python -m pytest studybench/tests -q`，预期 `69 passed`（开发机实录 282s，seekdb 建库较慢属正常）；等价命令 `sb selftest`。
- **退出码**：0 成功；2 参数/输入错误；3 依赖或数据库错误；4 search 无结果（stdout 仍输出空结果结构）。
