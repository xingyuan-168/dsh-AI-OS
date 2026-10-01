# AI Engineering OS

AI Engineering OS 是 DeepSeek Harness 的**工程治理层**：无状态三 Gate（Code Start / Frontend Approval / Finish）在任务开始、前端实现前、任务结束时回答"允许 / 不允许及为什么"。它不指导 DSH 怎么做专业工作——理解仓库、编码、调试、构建、测试、子 Agent 调度都是 DSH 的原生能力。

治理以 **DSH Cordis 插件的形态装进 profile**，因此对所有项目默认生效；插件只做裁决与转发，Gate 逻辑仍由本仓库的确定性内核提供。

## 能力

- **GitHub 前置**：正式 src/ 实现前必须有可达的 GitHub remote；没有时允许读 input/、分析、调研、规划、写文档。
- **仓库卫生**：复制式版本目录/文件、被跟踪的污染内容、未解决冲突精确判定并阻塞；用户自己的未提交工作永不阻塞。
- **开源调研分层**：新项目/新模块/重大功能/新技术栈/新集成必须先在 docs/OPEN_SOURCE_RESEARCH.md 记录 requirement_id、summary 与 use / fork / extract / build 决策；空模板/stale id 一律阻塞。
- **前端人工确认**：新页面/新交互流/重大 UI 重构先出 docs/design/PROTOTYPE.html + UI_SPEC，用户批准作为 approval 块持久化进 UI_SPEC（scope 精确匹配）；文案/CSS/组件修复豁免。
- **Worktree 隔离**：disposable worktree 登记进 SQLite 供插件判定（伪造目录失败封闭）；完成后 review、merge，cleanup 需 merge 证明，无 force。
- **轻量 Memory**：docs/memory/memory.jsonl 是唯一事实源（Git 跟踪），SQLite memory_index 可随时重建；单写者规则——子 Agent 只提交 candidate。
- **保护用户资产**：共享 Git 破坏操作拒绝；清理检查精确目标及跟踪文件、保护路径、链接，不凭 cwd 放行。DSH 判断任务归属与宿主审批，AIOS 不代替宿主。

## DSH 宿主集成

| 强制点 | DSH 机制 | 作用 |
| --- | --- | --- |
| 工具调用前 | `tools/pre-execute` | 唯一可拒绝的派发前裁决点；覆盖全部工具（含写入与 Shell），破坏性/越界操作返回 deny |
| 会话建立 | `agent/created` + `systemPrompt.section` | 注入宪法与当前 Gate 状态 |
| 工具面 | `ctx.tools.register` | 8 个治理工具 |
| 命令面 | `ctx.commands.register` | `/aios-check`、`/aios-finish`、`/aios-status`、`/aios-memory` |
| 技能面 | `ctx.skills.registerProvider` | 8 个治理 Skill |
| 安装 | `plugin_manager install_bundle` + profile 补丁层 | 写进 `~/.dsh/profiles/<profile>/` |

强制分层（Tier 0 基线 / Tier 1 已治理项目 / Tier 2 全局严格模式）见 [AGENTS.md](AGENTS.md) 与 [治理规则](docs/GOVERNANCE_RULES.md)。

## 本地开发

```powershell
uv sync
uv run ruff check src plugins tests
uv run pytest
uv run aios doctor --json
```

## 命令

```text
aios init <project-root> --project-id PROJECT-001 --name example
aios check <project-root> [--change-class --requirement-id]
aios finish <project-root> --base-ref <task-start-sha> --change-class bugfix --test-command "pytest" --memory-not-needed
aios migrate <project-root>
aios authorize-dsh
aios approval record --project-root <path> --gate frontend --subject frontend --scope <scope> --decided-by <who> --decision approved
aios context refresh <project-root>
aios memory search|record|reindex|candidates|candidate --accept|--reject
aios worktree prepare|check|finish|cleanup|list
aios doctor
aios mcp
```

业务命令支持 --json（统一 ok/error envelope）。DSH 插件公开 8 个工具：project_init、governance_check、approval_record、context_refresh、worktree_manage、memory_search、memory_record、memory_candidate；`aios mcp` 保留为其他宿主的可选 stdio 传输，与插件共用同一实现。

仓库级 DSH 插件位于 plugins/ai-engineering-os/（8 个治理 Skill + Cordis 宿主插件）。插件通过 `aios authorize-dsh` 调用内核，Runtime 无法返回有效结果时明确写入/破坏操作拒绝，读取只提示检查不可用。源码验证不等于插件已安装或加载；这些状态由 DSH 管理，变更部署后应在新会话验证。

任务开始保存 Git SHA（空仓库为 EMPTY_TREE），Finish 用它覆盖已提交与尚未提交的全部变更。运行库不自动重建；显式迁移只接受已知历史结构，先一致性备份，不改文档/input。初始化已有 input/ 不补写占位文件。详见 [数据库契约](docs/DATABASE.md)。

## 事实源

- [仓库指令](AGENTS.md)：十条宪法与 Git 纪律。
- [文档索引](docs/README.md)：全部活跃文档的地图与阅读顺序。
- [治理规则](docs/GOVERNANCE_RULES.md)：三 Gate、路径策略、DSH 事件语义。
- [架构决策](docs/ADR/)：ADR-0016 定义轻量架构，ADR-0017 澄清安全边界，ADR-0018 记录 DSH 宿主迁移与全局强制模型。

input/ 保存原始需求，只读参考；冲突以当前接受的 ADR 为准。
