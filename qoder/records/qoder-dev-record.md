# Qoder 开发记录（材料 5）

> 本文件是提交材料「Qoder 开发记录」的正文骨架。**Qoder 跑批脚本会自动把每次会话的
> 模型、耗时、token、改动文件与门禁结果追加到 §3 的表格与 `records/qoder-logs/`**；
> §1、§4 需要君上填账号 UID 与截图路径（脚本会提示位置）。

## 1 账号与工具

| 项 | 值 |
| --- | --- |
| Qoder 账号 UID | <!-- 待填：Qoder 客户端 设置 → 个人资料，或 qoder.com 账号页 --> |
| 登录账号 | Veritas Vertin（qoder.com 国际版，个人版；2026-10-30 `qoder login` 浏览器授权） |
| 账号类型 | 个人版（比赛要求：企业/团队账号的站点无法公开访问） |
| 工具形态 | **Qoder CLI**（赛题允许的「Qoder 开发」形态之一），IDE 可用同一账号登录复核 |
| 版本 | `qoder --version` → **1.1.81** |
| 认证方式 | 本机 `qoder login` 登录态（`~/.qoder`）；PAT 仅 CI 场景需要 |

## 2 开发方式：契约冻结 + Qoder 跑批 + 自动门禁

本项目把「接口与验收口径」先冻结成 [`../CONTRACTS.md`](../CONTRACTS.md)（表结构、分词与 BM25 公式、
CLI 命令表、导出 JSON、验收清单），再让 Qoder 在仓库内按任务逐条实施与复核，每条任务都有
**可执行的通过判据**（脚本门禁），不通过则回滚该条并记录。这样 Qoder 的产出是可审计的，
不是「看起来像 AI 写的」就算数。

跑批入口：`bash qoder/scripts/qoder_dev_batch.sh`（详见 [`../RUN-QODER.md`](../RUN-QODER.md)）。

## 3 会话记录（2026-10-30 实跑；原始 JSONL 逐条在 records/qoder-logs/）

| # | 任务 | 模型 | 耗时 | credits | turns | 改动文件 | 门禁 | 提交 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T1 | `studybench doctor` 自检子命令 | 会话默认¹ | 461 s | 0¹ | 32 | cli.py / doctor.py / test_doctor.py | PASS | b7d99c69 |
| T2 | `studybench verify` 期望值校验 | 会话默认¹ | 206 s | 2.16 | 36 | cli.py / verify.py / test_verify.py | PASS | 2dc1e6f8 |
| T3 | `studybench related` 相关推荐 | 会话默认¹ | 137 s | 1.27 | 18 | cli.py / related.py / test_related.py | PASS | 3184861f |
| T4 | 站点「使用数据」区 | 会话默认¹ | 99 s | 1.07 | 18 | site/{src,dist}/{index.html,styles.css} | PASS | edb5739e |
| T5 | 核心模块代码评审（6 Important + 5 Minor） | 会话默认¹ | 191 s | 1.44 | 12 | records/qoder-review.md | PASS*² | 0d6a97c4 |
| T6 | RUN.md 命令对账（82 项计数等） | 会话默认¹ | 169 s | 1.63 | 28 | RUN.md | PASS*² | 54710ada |
| — | 全量自测暴露 T1 缺陷 → 主控补丁³ | — | — | — | — | doctor.py | 81→82 passed | 3cd3c187 |

¹ CLI 的 `--output-format json` 结果信封不含模型名字段，如实记「会话默认」；credits/turns 取自各 T*.jsonl 的 result 行。
² 当场门禁误判（T5 死抠文件全路径、T6 被工作树残留干扰），产物经复核合格后收账——判定与理由见 `qoder-logs/summary.md` 尾注。
³ 见提交 3cd3c187：门禁只跑 doctor 正常路径，全量自测才发现「未初始化库」分支把原始 SQL 错误透出，补一行指引修复。此行如实记为**主控所做**，不是 Qoder 会话。

合计 credits ≈ 7.6（免费额度内）。原始日志：`records/qoder-logs/T1..T6.jsonl` + `summary.md`。

## 4 截图与录屏（人工）

| 场景 | 路径/说明 |
| --- | --- |
| 站点桌面端 | `records/screenshots/site-1280.png`（真实渲染） |
| 站点移动端 375px | `records/screenshots/site-375.png`（CDP 视口模拟，实测无横向溢出） |
| 站点试用区真实检索 | `records/screenshots/site-tryit.png`（top-1 得分 36.193389，与 CLI 同分） |
| Qoder CLI 会话（`qoder -p` 执行中） | <!-- 待填：跑批时截 2–3 张，放 records/screenshots/ --> |
| Qoder 站点面板（发布成功状态） | <!-- 待填 --> |
| 站点公开访问（无痕窗口） | 已验证：https://studybench-e1bvhnt3g1g.qoder.website/ 匿名可访问（curl 无凭据 http=200，`data/index_export.json` 813171 字节可下，试用区检索命中 19/96 块、top-1 得分 36.193389） |

> 说明：CLI 跑批的**文本级证据**（prompt + JSON 响应 + 提交 diff）已在 §3 与 `records/qoder-logs/`；
> 截图是评审侧的补充观感证据，不替代日志。

## 5 诚实分工声明

- **由 Qoder 完成**：见 §3 表格逐条（子命令、站点区块、代码评审、文档对账等），每条都有提交与门禁。
- **由人工/主控完成**：`CONTRACTS.md` 的口径冻结、验收裁决、以及 Qoder 跑批失败时的回滚与重派。
- 不在本文件里把人工成果记成 Qoder 成果；也不把「只装了组件」写成「用了组件」。
