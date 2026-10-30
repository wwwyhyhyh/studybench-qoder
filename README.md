# 学研台 StudyBench

> **OceanBase 数据库大赛（第六届）· Qoder 生态赛道** 作品
> 把散落在文件夹里的课程笔记变成**可检索的知识**，把多线程任务的进度变成**可复用的记忆**。

- **作品说明（先读这个）** → [`qoder/README.md`](qoder/README.md)
- **运行说明** → [`qoder/RUN.md`](qoder/RUN.md)
- **验证样例** → [`qoder/verification/sample.md`](qoder/verification/sample.md)
- **在线站点（任何人可访问）** → https://studybench-e1bvhnt3g1g.qoder.website/
- **Qoder 开发记录** → [`qoder/records/qoder-dev-record.md`](qoder/records/qoder-dev-record.md)
- **使用效果材料** → [`qoder/records/usage-metrics.md`](qoder/records/usage-metrics.md)

## 技术分工

| 组件 | 承担什么 |
| --- | --- |
| **seekdb**（OceanBase 内核，嵌入式 pylibseekdb） | 文档/块/词项存储、NGRAM 全文索引中文召回、BM25 重排、结构化过滤、检索留痕 |
| **PowerContext**（PyPI `powercontext[builtin]`） | 任务记忆：任务 = `Source`，每次进度更新 = 一个不可变 `Artifact` revision；周报生成 |
| **Qoder** | 开发与站点托管：契约先行的六条 CLI 跑批任务 + Qoder Sites 发布 |

## 30 秒上手（WSL2 / Linux）

```bash
# 依赖：pylibseekdb（仅 Linux/macOS x86_64 wheel）+ powercontext[builtin] + pytest
uv venv --python python3.12 .venv
uv pip install --python .venv/bin/python \
  'pylibseekdb @ https://files.pythonhosted.org/packages/19/e9/49507c0859bf0898f99f2b0978baba6cfaca9563e4ba20242be014ee7e6c/pylibseekdb-1.3.0.post4-cp312-abi3-manylinux_2_28_x86_64.whl' \
  'powercontext[builtin]==1.4.1' 'pytest==9.2.0'

cd qoder
PYTHONPATH=studybench ../.venv/bin/python -m studybench ingest --src corpus_demo
PYTHONPATH=studybench ../.venv/bin/python -m studybench search "分光计调到什么程度算调好" --top 3
```

> 本仓库只含本作品（`qoder/` 目录）；团队多赛道合仓与完整提交上下文见官方提交仓库。
> 全部语料为脱敏演示数据，不含任何真实个人信息。许可：MIT。
