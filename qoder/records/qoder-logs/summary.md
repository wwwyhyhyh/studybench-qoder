
## 跑批记录（20261030-124704，qoder 1.1.81）

| # | 任务 | 元数据 | 耗时 | 改动 | 门禁 | 提交 |
| --- | --- | --- | --- | --- | --- | --- |
| T1 | studybench doctor 自检子命令 | model=? tokens=? | 461s | qoder/studybench/studybench/cli.py qoder/records/qoder-logs/ qoder/studybench/studybench/doctor.py qoder/studybench/tests/test_doctor.py  | PASS | b7d99c69 |
| T2 | studybench verify 期望值校验子命令 | model=? tokens=? | 206s | qoder/records/qoder-logs/summary.md qoder/studybench/studybench/cli.py qoder/records/qoder-logs/T2.jsonl qoder/studybench/studybench/verify.py qoder/studybench/tests/test_verify.py  | PASS | 2dc1e6f8 |
| T3 | 相关笔记推荐 related 子命令 | model=? tokens=? | 137s | qoder/records/qoder-logs/summary.md qoder/studybench/studybench/cli.py qoder/records/qoder-logs/T3.jsonl qoder/studybench/studybench/related.py qoder/studybench/tests/test_related.py  | PASS | 3184861f |
| T4 | 站点新增使用数据区 | model=? tokens=? | 99s | qoder/records/qoder-logs/summary.md qoder/site/dist/index.html qoder/site/dist/styles.css qoder/site/src/index.html qoder/site/src/styles.css qoder/records/qoder-logs/T4.jsonl  | PASS | edb5739e |

## 跑批记录（20261030-131101，qoder 1.1.81）

| # | 任务 | 元数据 | 耗时 | 改动 | 门禁 | 提交 |
| --- | --- | --- | --- | --- | --- | --- |
| T5 | 核心模块代码评审 | 见 T5.jsonl | 191s | qoder-review.md | PASS* | — |
| T6 | RUN.md 命令对账 | 见 T6.jsonl | 169s | qoder/RUN.md | PASS* | — |

> *T5/T6 说明：两条的会话均正常完成且产物合格，但当场门禁误判——T5 是门禁死抠全路径（评审用短名 store.py），T6 是工作树残留了主控未提交的 T5 产物与门禁修正。主控复核产物后修正门禁并分两笔提交（见 git log），非重跑。
