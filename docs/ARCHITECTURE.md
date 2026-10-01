# 架构

Windows 本地、可审计的 Codex 工程治理层。Python 3.12，自研自持（Gate、审批、SQLite），无第二模型客户端；LangGraph 等仅作设计参考，禁止作为依赖引入。

## 分层

- `cli/` — Typer 命令（init/check/finish/memory/worktree/mcp/doctor/authorize-hook）与 MCP stdio server（8 工具）。输出统一 ok/error envelope。
- `application/` — 用例：project 初始化、repository 治理检查、doctor 诊断、hook 网关、授权内核（ADR-0011）、最小路径策略内核（governance_policy）。
- `core/` — 无状态治理核心：`gates.py`（三 Gate 评估器）、`checks.py`（Finish 薄真实检查）、`worktree.py`（disposable worktree 生命周期）。
- `infrastructure/` — SQLite（单迁移 0001：tasks/approvals/worktrees/memory_index）、JSONL Memory、文档管理、配置、路径编解码。
- `adapters/` — 外部系统：GitRunner（唯一 Git 子进程封装）。
- `domain/` — 配置模型、治理值对象、版本常量。
- `templates/` — 新项目最小文档集（baseline + 条件生成）。
- `plugins/ai-engineering-os/` — Codex 插件：8 个治理 Skills、SessionStart/PreToolUse hooks、MCP 启动脚本。

## 边界

- Markdown/Git 保存事实；`.codex-os/project.yaml` 是 Git 管理的配置，state/context 等运行状态忽略。SQLite 普通访问不重建；显式迁移使用一致性备份和 SQL 事务。JSONL 写锁与原子替换保护 Memory，索引永不替代事实。
- AIOS 暴露确定性 CLI/MCP 用例，永远不做模型推理、不做 Agent/工具运行时、不做 DAG 调度。
- Docker/Podman 不是 AIOS 的执行引擎：project_init 仅提供可选的项目开发环境模板（Dockerfile + compose.yaml）。
- Hook 的 stdlib 适配器调用单一 Runtime 授权内核；明确写入/破坏操作遇到缺失、超时或无效结果输出 deny，其他操作报告未知，不复制离线内核。共享根解析和实际目标检查覆盖子目录/Worktree/跨 cwd 路径。宿主可禁用 Hook，也可独立拒绝 AIOS 放行的操作；诊断不冒充宿主审批。任务基线由原生上下文携带到 Finish，不引入任务凭证/调度状态。
