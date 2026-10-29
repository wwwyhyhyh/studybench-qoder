# Qoder 侧操作手册（明早 15 分钟版）

> 这条线只有两步是机器做不了的：**用你的 Qoder 账号登录**、**确认公开发布**。
> 其余（开发跑批、门禁、提交、打包、发布、设公开）都已经脚本化。
> 全程不 push 代码；发布前脚本会先做脱敏与产物自检。

## 0 现状（先看这个）

- 项目已完整可跑：`qoder/studybench`（引擎 + 记忆层，69 项测试全绿）、`qoder/corpus_demo`（12 篇脱敏语料 / 96 块）、
  `qoder/site/dist`（静态站，浏览器端检索与 Python 同分，parity 27/27）、`qoder/verification`（期望值 + 终端实录）。
- 已装：Qoder CLI `1.1.81`（`qoder --version` 可验）、WSL venv（pylibseekdb + powercontext[builtin]）。
- 还缺：**Qoder 登录态** → 没有它，开发跑批与站点发布都动不了。

## 1 生成 Qoder 凭据（约 2 分钟）

二选一：

**A. 只要 CLI（推荐，最快）**

1. 浏览器打开 <https://qoder.com/account/integrations>，登录（用**个人账号**，别用企业/团队账号——企业版站点无法公开）。
2. 创建 Personal Access Token，复制。
3. 在 Git Bash 里：

```bash
export QODER_PERSONAL_ACCESS_TOKEN="粘贴你的token"
qoder sites list        # 能返回 {"ok":true,...} 就说明通了
```

> 想持久化可写进 `~/.bashrc`，但**不要把 token 写进仓库任何文件**（提交材料明确禁止真实凭据）。

**B. 装 Qoder 桌面端（若要截图/演示视频）**

1. 下载 <https://qoder.com/download> 的 Windows `.exe`（User 版免管理员）。
2. 登录后：左下角头像 → 设置 → 个人资料，**记下 Qoder UID**（要填进提交表与开发记录）。
3. 用 Qoder 打开 `E:\CodeX\PowerContext-2026`，后续跑批也可以在 IDE 里让它按任务清单做，截图更方便。

## 2 跑 Qoder 开发批（约 20–30 分钟，消耗 Credits）

```bash
cd /e/CodeX/PowerContext-2026
bash qoder/scripts/qoder_dev_batch.sh --dry-run   # 先看 6 条任务的 prompt（不发请求、不扣额度）
bash qoder/scripts/qoder_dev_batch.sh             # 真跑
```

六条任务（每条都是真改动 + 自动门禁 + 本地提交）：

| # | 任务 | 门禁 |
| --- | --- | --- |
| T1 | `studybench doctor` 环境自检子命令 | `sb.sh doctor` 退出 0 |
| T2 | `studybench verify` 期望值校验子命令 | `sb.sh verify --check` 退出 0 |
| T3 | `studybench related` 相关笔记推荐 | `sb.sh related ...` 有结果 |
| T4 | 站点「使用数据」区块 | parity 通过 + 无外链资源 |
| T5 | 核心模块代码评审 | `records/qoder-review.md` ≥2.5KB 且带行号 |
| T6 | RUN.md 命令对账 | 只改 RUN.md |

- 门禁**失败即停批**并保留现场，按屏幕提示回滚该条再继续；每条成功的任务会 commit，日志在
  `qoder/records/qoder-logs/`，汇总表在 `qoder/records/qoder-logs/summary.md`。
- 额度：免费体验版 300 Credits + 每日签到 100，六条任务通常够；控制台 `/usage` 可看余量。
- **不想用脚本？** 六条 prompt 已导出到 `qoder/records/qoder-prompts.md`，可在 Qoder 桌面端/IDE 里逐条粘贴，
  每条做完照「门禁」自己跑一次命令再提交（效果等同，只是要手动截图）。
- 跑完把 `summary.md` 的表复制进 `qoder/records/qoder-dev-record.md` §3，并补 §1 的 UID、§4 的截图路径。

> **如果 Qoder 跑批失败或额度不够**：不用硬撑。把失败那条的日志留在 `qoder/records/qoder-logs/`，
> 在开发记录 §3 里如实写「T3 未完成（原因）」。**不要**把人工写的东西记成 Qoder 产出。

## 3 发布站点（约 3 分钟）

```bash
cd /e/CodeX/PowerContext-2026
bash qoder/scripts/qoder_publish_site.sh            # 干跑：查登录、查产物、打印将上报的 JSON
bash qoder/scripts/qoder_publish_site.sh --yes      # 真发布 + 设为「任何人都可访问」
```

脚本做四件事：`prepare_site`（打包 `qoder/site/dist` 为不可变草稿）→ 轮询 `get_publish_status`
→ `publish_site` → `get_site_access` + `update_access_policy(mode=public, confirmPublic=true)`。

**若脚本在某步失败**，改用 IDE：Qoder 里打开项目 → 左侧「站点」→ 添加站点 → 在输入框引用 `@sites`
并说「把 `qoder/site/dist` 这个纯静态目录发布为站点，公开可访问」→ 点右侧「发布」→ 等状态变「已发布」
→ 分享 → 更改访问范围 → 任何人都可访问 → 允许公开访问。

发布后必做三件事：

1. **无痕窗口**打开站点 URL，确认未登录也能看、试用区能搜出结果。
2. 记下 URL，填进 `qoder/README.md` 的材料表与提交平台。
3. **评审结束前不要暂停/删除站点**；以后改了站点要再点一次「发布」才生效。

## 4 提交材料对照表

| 平台要的 | 在哪 |
| --- | --- |
| Qoder Sites URL（公开） | 发布后填 → `qoder/README.md` 材料表 |
| 代码仓库 | 本仓库 `2026-competition-ecosystem` 分支的 `qoder/` 目录 |
| 运行说明 | `qoder/RUN.md`（干净 Linux 从零跑通） |
| 验证样例 | `qoder/verification/sample.md` + `expected_results.json` + `logs/` |
| Qoder 开发记录（截图 + UID） | `qoder/records/qoder-dev-record.md`（§3 由跑批填，§1/§4 你填） |
| 使用效果材料 | `qoder/records/usage-metrics.md`（110 次检索 / p50 29.6ms / 10-10 命中 / 69 项测试） |

## 5 两个会让验收直接挂掉的坑

1. **仓库对评委不可见**。当前是团队私有仓库；提交前要么把仓库设为 public，要么在平台里给评委开权限。
   赛题原文要求「代码仓库（公开或对评委开放）」——只有你自己能看等于没交。
2. **用企业账号发布站点**。企业/团队账号的站点只能组织内分享，评委打不开。必须个人账号。

## 6 回滚

```bash
git tag -l 'qoder-baseline-*'          # 跑批前打的基线
git log --oneline -8                   # 每条 Qoder 任务一个提交
git revert <sha>                       # 想撤某条任务
```
