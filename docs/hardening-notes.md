# Hardening notes (why these changes exist)

## 1) 单一事实来源：SQLite

原方案里：
- `orchestrator/queue/*.json`
- `.clawdbot/active-tasks.json`

这类“文件当数据库”会在并发写/崩溃/重复消费时出现幽灵状态。

这里先用 SQLite：
- task 状态机（queued/running/succeeded/failed/...）
- deps 依赖边
- events 事件流（可回放/审计）

保留 JSON 只做 **view/cache**，不再做 truth。

## 2) 幂等 enqueue

调度入口（ChatOps/HTTP webhook）一定要有 idempotency key：
- Discord 事件 ID
- 或者用户提供的业务 key（repo+branch+issueId）

否则网络重放/重试会重复派发。

## 3) 重试准入（Retry gate）

目标：
- 避免“错误假设 → 越修越偏 → 重试风暴”

最小策略：
- attempt <= max_attempts
- 只对可修复类别（lint/type/build）自动重试
- CI/test 默认不自动 fix-and-retry，除非出现强 infra 信号（502/503/ratelimit）

## 4) 可恢复 worker

worker 认 DB 的 status；进程挂了重启即可恢复。

以后再加：
- supervisor (systemd/容器)
- 分布式锁/多 worker
- 资源配额（CPU/内存/并发限制）

## 5) 接入 git worktree / tmux / GitHub

这部分先留接口：
- `runner_cmd` 模板里可填：
  - tmux 启动
  - codex/claude CLI
  - openclaw agent RPC

监控 PR/CI 建议用 `gh` + GitHub API，状态写回 DB。
