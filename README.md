# ai-devops-orchestrator (hardening-first scaffold)

目标：把“小红书那套多 Agent 编排”的关键短板先补上（状态一致性/幂等/恢复/重试准入/权限边界），再谈 UI 和花活。

## 解决的问题（对照原方案的易碎点）

- 用 **SQLite** 替代 `active-tasks.json` + `queue/*.json` 作为唯一事实来源（single source of truth）
- **幂等 enqueue**：同一任务不会被重复派发/重复消费
- **可恢复 daemon**：崩溃后可以从 DB 恢复运行态（而不是靠 tmux + 文件猜状态）
- **重试准入**：不是“失败就重试”，而是按失败类别/信号做决策（含最大次数）
- **DAG 校验**：plan/subtask 的 `dependsOn` 合法性 + 环检测

## 目录

- `orchestrator/`：核心代码（DB、plan schema、queue、daemon、retry policy）
- `bin/`：CLI 入口脚本
- `docs/`：设计说明
- `tests/`：最小测试

## 运行（先不动你现有系统）

本仓库先提供：
- 计划/子任务 schema 校验
- SQLite 状态机 + queue + worker

等你确认 repo 路径/agent runner 命令后，再接：
- git worktree 创建
- tmux 或 subprocess runner
- GitHub PR/CI monitor
