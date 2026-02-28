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

## 运行（最小可跑）

### 1) 安装测试依赖

```bash
pip install -r requirements-dev.txt
pytest -q
```

### 2) 入队一个示例计划

```bash
python bin/orchestratorctl.py --db state/orch.db enqueue \
  --plan examples/plan.sample.json --idempotency demo1
```

### 3) 启动 daemon（接入内置 runner）

```bash
python -m orchestrator.daemon \
  --db state/orch.db \
  --logs state/logs \
  --poll 1 \
  --runner "python bin/run_task.py --db {db_path} --task-id {task_id}"
```

### 3.1) PR/CI 状态回写（可选，依赖 gh）

```bash
python bin/monitor_pr_ci.py --db state/orch.db
```

只同步单个任务：

```bash
python bin/monitor_pr_ci.py --db state/orch.db --task-id subtask-backend-1
```

### 4) 查看任务状态

```bash
python bin/orchestratorctl.py --db state/orch.db list
```

## 路由策略（当前实现）

- `codex-* / backend / frontend / coding` → `codex exec --full-auto`
- `review*` → `openclaw agent --agent reviewer`
- `design*` → `openclaw agent --agent designer`
- `triage*` → `openclaw agent --agent triage`

> 注意：`codex` 路由需要 `worktree_path` 或 `repo_path`（或环境变量 `ORCH_WORKDIR`）可用。

## Worktree 生命周期（当前实现）

- 对 `codex-*` 路由任务：如果任务缺少 `worktree_path` 且有 `repo_path`，会自动创建 `repo_path/.orchestrator/worktrees/<task_id>`。
- 自动创建的 worktree 会回写到 DB（`tasks.worktree_path`、`tasks.worktree_branch`、`tasks.worktree_managed=1`）。
- 任务进入终态（`succeeded` 或最终 `failed`）时，会安全清理托管 worktree。

## 失败分类（当前实现）

- daemon 会读取 runner stdout/stderr 合并日志并分类写回：`lint | test | build | ci | agent | unknown`。
- 结果写入 `tasks.failure_kind` 与 `tasks.failure_detail`。

## 下一步

- retry gate 接入更细粒度信号（flaky/test infra/compile/lint）
