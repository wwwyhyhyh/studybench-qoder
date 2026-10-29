# 使用效果材料 · 真实运行数据（自动采集）

- 采集时间：2026-10-30 03:10（+08:00）
- 采集环境：WSL2 Ubuntu 24.04.4 / Python 3.12.3 / pylibseekdb 1.3.0.post4 / powercontext 1.4.1[builtin]
- 采集方式：`studybench index`、`studybench log`、以及一次在 WSL 内直接调用 `studybench.search` 的计时脚本（原样命令见文末）

## 1 索引规模

| 指标 | 数值 | 来源 |
| --- | --- | --- |
| 文档数 | 12 篇 | `studybench index` |
| 检索块（`##` 小节） | 96 个 | `studybench index` |
| 词项行数（`chunk_terms`） | 20070 行 | `SELECT COUNT(*) FROM chunk_terms` |
| 去重词项数 | 11983 个 | `SELECT COUNT(DISTINCT term)` |
| 平均块长 | 372.7 字符 | `studybench index` |
| 导出索引体积 | 813171 字节（≈794 KB，≤3 MB 上限） | `records/index_export.json` |

## 2 检索使用量（`query_log` 表实测）

| 指标 | 数值 |
| --- | --- |
| 累计检索次数 | 110 次 |
| 有命中的检索 | 108 次（98.2%） |
| 去重查询语句 | 22 条 |
| 平均命中块数 | 27.2 块 / 次 |

> 这 110 条是**截至 03:10 的快照**（开发与验证过程中的真实调用：10 条演示查询的多次重放、断言语义探针、
> 站点 parity 对拍），全部由 `store.log_query()` 写入 seekdb 的 `query_log` 表。留档见
> `records/seekdb-query-record.md`（该文件生成于 03:24，固定取最近 100 条）。
> 注意：`ingest --reset` 会清空 `query_log`，之后再跑检索只会从少量行重新累积——所以「复现」应看
> 已提交的记录文件，或自己重跑一批查询后对照本节的统计口径，而不是指望现库仍有 110 行。
> 「110」是快照值而非当前总数；`evidence` 固定取最近 100 条属展示上限，不是数据丢失。

## 3 时延（同一进程内，避开嵌入式引擎冷启动）

| 指标 | 数值 |
| --- | --- |
| 引擎冷启动（每进程一次） | 2039.1 ms |
| 检索 p50 | 29.6 ms |
| 检索 p95 | 34.5 ms |
| 检索 min / max | 27.6 / 172.6 ms |
| 样本量 | 30 次（10 条演示查询 × 3 轮） |

读法：`studybench search` 作为一次性 CLI 调用，端到端约 2.1 s，其中约 2.0 s 是嵌入式 seekdb
实例的进程级初始化，真正的中文召回 + BM25 重排只要约 30 ms。若放在常驻进程里（站点就是这种形态），
用户感知的是 30 ms 级。

## 4 检索质量（10 条演示查询）

- `verification/expected_results.json`：10/10 条查询的预期小节均落在各自 top-5 内，**10/10 条为 top-1**。
- 站点与 Python 引擎一致性：`node qoder/site/test/parity.mjs` → PASS 27 / FAIL 0
  （其中 10 条为真实语料对拍，比较 top-5 顺序与 6 位小数得分）。
- 每条结果的引用都是真实的 `path:line_start-line_end`，可在 `corpus_demo/` 里逐条核对。

## 5 记忆层使用量（PowerContext）

- 存储后端：`powercontext.builtin.persistence/sqlite`（官方内置关系型后端，非自造格式）。
- 单测覆盖：任务创建 / 重复创建幂等 / 进度 revision 递增 / 重启后仍可读 / `resume` 读最近 3 版 / 周报四段。
- 全仓自测：`pytest` **70 项**全绿（引擎 44 + 记忆层 26；`terms.py` 超长词项回归用例新增后由 69→70）。

## 6 真实工作区实测（只有统计量，不含任何内容）

演示语料只有 96 块，不足以证明「真实笔记也能跑」。因此另外在本机真实的个人学习工作区
（约 500 个 markdown 笔记）上跑了一次**独立库**（临时路径，跑完即删）：

| 指标 | 数值 |
| --- | --- |
| 可解析 markdown 文档 | 436 篇（含课程笔记、实验报告、竞赛资料、作业说明） |
| 检索块 | 3424 个 |
| 词项行 / 去重词项 | 约 20 万行 / 155873 个 |
| 全量建索引耗时 | 119.2 s（嵌入式 seekdb，单线程） |
| 检索 p50 / p95 | **59.8 ms / 144.2 ms**（5 条真实口语查询，top-5） |

**这一步抓到并修掉了一个 demo 语料永远暴露不了的缺陷**：真实笔记里粘过 inline SVG 的
data URI，切出一个 **439 字符的 ASCII 串**，远超 `chunk_terms.term VARCHAR(64)`，导致
`INSERT` 直接报 `Data too long for column 'term'` 并中断整篇文档的入库。
修复见 `terms.py`（`MAX_ASCII_TERM = 48`，超长 ASCII 串按噪声丢弃）与 `store.py`
（列宽 128 + 入库前二次兜底），并有回归用例 `test_overlong_ascii_token_is_dropped`。
修复后同一工作区一次建索引成功，零跳过。

> 隐私边界：本节只记统计量与耗时；没有把任何笔记内容、文件路径或检索摘录写进仓库或站点。
> 真实工作区的库是临时库，跑完已删除，站点上的数据仍只来自 `corpus_demo`。

## 7 复现命令

```bash
bash qoder/scripts/sb.sh index
bash qoder/scripts/sb.sh log --tail 10
bash qoder/scripts/sb.sh py -c "
import os, time, json, statistics
from studybench.store import Store
from studybench.search import search
db=os.environ['SB_DB']
t=time.perf_counter(); Store(db); print('open_ms', round((time.perf_counter()-t)*1000,1))
qs=[q['query'] for q in json.load(open('corpus_demo/_queries.json'))['queries']]
lat=[]
for _ in range(3):
    for q in qs:
        t=time.perf_counter(); search(db,q,top=5); lat.append((time.perf_counter()-t)*1000)
print('p50_ms', round(statistics.median(lat),1), 'p95_ms', round(sorted(lat)[int(len(lat)*0.95)-1],1))
"
```

> 说明：这是**单机演示规模**（12 篇 / 96 块）。数字不做外推；换更大语料后需重新采集，采集脚本同上。
