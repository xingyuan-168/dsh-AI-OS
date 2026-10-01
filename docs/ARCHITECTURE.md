# 架构

Windows 本地、可审计的 DeepSeek Harness 工程治理层。Python 3.12，自研自持（Gate、审批、SQLite），无第二模型客户端；LangGraph 等仅作设计参考，禁止作为依赖引入。DSH 集成面是一个只做转发的 Cordis 插件，不含判定逻辑。

## 分层

- `cli/` — Typer 命令（init/check/finish/migrate/memory/worktree/mcp/doctor/authorize-dsh/approval/context）与 MCP stdio server（8 工具）。输出统一 ok/error envelope。
- `application/` — 用例：project 初始化、repository 治理检查、doctor 诊断、授权内核（ADR-0011）、最小路径策略内核（governance_policy）、DSH 载荷规范化（dsh_gateway）。
- `core/` — 无状态治理核心：`gates.py`（三 Gate 评估器）、`checks.py`（Finish 薄真实检查）、`worktree.py`（disposable worktree 生命周期）。
- `infrastructure/` — SQLite（单迁移 0001：tasks/approvals/worktrees/memory_index）、JSONL Memory、文档管理、配置、路径编解码。
- `adapters/` — 外部系统：GitRunner（唯一 Git 子进程封装）。
- `domain/` — 配置模型、治理值对象、版本常量。
- `templates/` — 新项目最小文档集（baseline + 条件生成）。
- `plugins/ai-engineering-os/` — DSH Cordis 插件：8 个治理 Skill、宿主事件监听、工具/命令/Skill Provider 注册、`aios` 子进程桥。

## DSH 宿主集成

插件把宿主事件规范化为内核请求，再经 `aios authorize-dsh`（stdin JSON）交给同一个确定性内核；否定判定由插件转换为宿主可执行的拒绝。

- 监听：`tools/pre-execute`（工具调用前）、`fs/write-intent` / `fs/edit-intent`（写入时刻）、`agent/created`（会话建立）。
- 注册：`ctx.tools.register` 8 个治理工具、`ctx.commands.register` 人工命令、`ctx.skills.registerProvider` Skill 目录、`ctx.systemPrompt.section` 宪法注入。
- 失败封闭：内核缺失/超时/异常/无效 JSON 时，变更类操作拒绝并给出规则编号，只读操作只提示检查不可用；不复制第二套离线规则。
- 插件不执行命令、不代表宿主授权；DSH 可独立拒绝或禁用插件。

## 边界

- Markdown/Git 保存事实；`.aios/project.yaml` 是 Git 管理的配置，state/context 等运行状态忽略。SQLite 普通访问不重建；显式迁移使用一致性备份和 SQL 事务。JSONL 写锁与原子替换保护 Memory，索引永不替代事实。
- AIOS 暴露确定性 CLI 用例与 DSH 工具，永远不做模型推理、不做 Agent/工具运行时、不做 DAG 调度。
- Docker/Podman 不是 AIOS 的执行引擎：project_init 仅提供可选的项目开发环境模板（Dockerfile + compose.yaml）。
- 任务基线由 DSH 原生上下文携带到 Finish，不引入任务凭证/调度状态。
