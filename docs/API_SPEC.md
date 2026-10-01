# 接口契约

DSH 工具、MCP 与 CLI 共享实现和业务响应封装（`{ok, data} / {ok:false, error:{code,message}}`）。项目参数允许根、子目录或登记 Worktree；共用解析器区分当前 checkout 与协调根。文件目标支持相对/绝对路径，并独立验证所属项目。无模型推理。

## DSH 工具（8）

插件通过 `ctx.tools.register` 暴露，语义与 MCP 工具完全一致：

| 工具 | 参数 | 语义 |
| --- | --- | --- |
| project_init | project_root, project_id?, name?, project_type?, include[]?, migrate_runtime? | 普通初始化必须提供 project_id/name；migrate_runtime=true 仅显式迁移运行库，不初始化文档/input；未知结构拒绝 |
| governance_check | project_root, stage=start\|frontend\|finish, change_class?, requirement_id?, frontend_impact?, frontend_scope?, test_command?, base_ref?, memory_written?, memory_not_needed? | Finish 必须传入任务起点 base_ref，覆盖完整任务差异；返回 allowed + findings，无 tests_passed/docs_synced/approved 参数 |
| approval_record | project_root, gate, subject, scope?, decision=approved\|rejected, decided_by, reason? | 记录用户批准/拒绝；frontend gate 同时把 approval 块写入 docs/design/UI_SPEC.md（governance_check 读取该事实） |
| context_refresh | project_root | 重建 PROJECT_CONTEXT.md 派生缓存 |
| worktree_manage | project_root, action=prepare\|check\|finish\|cleanup\|list, name?, task_id?, base_ref? | disposable worktree 生命周期；cleanup 需合并证明，无 force |
| memory_search | project_root, query, limit | 从有效 JSONL 刷新索引后检索；事实无效时失败，不静默使用旧索引 |
| memory_record | project_root, record_type, title, summary, source, source_commit?, tags?, candidate? | 写 JSONL（主会话）或提交 candidate（子 Agent） |
| memory_candidate | project_root, action=list\|accept\|reject, candidate_id? | 主会话处理子 Agent candidate：列表 / 并入 JSONL / 丢弃 |

## DSH 宿主契约

- **事件监听**：`tools/pre-execute`（唯一的派发前拒绝点，覆盖全部工具）、`agent/created`（会话建立）。`fs/write-intent` / `fs/edit-intent` 是单槽写意图决策，不能拒绝操作，插件不注册；内核仍接受这两类载荷以便诊断。
- **人工命令**：`/aios-check`、`/aios-finish`、`/aios-status`、`/aios-memory`，经 `ctx.commands.register` 注册。
- **Skill Provider**：`ctx.skills.registerProvider` 读取 `plugins/ai-engineering-os/skills/*/SKILL.md`。
- **提示注入**：`ctx.systemPrompt.section` 输出宪法摘要与当前 Gate 状态。
- **插件配置**：`strict`（默认 true）、`uninitializedProjects`（默认 `strict`）、`kernelCommand`（默认 `aios`）、`timeoutMs`（默认 10000）、`failMode`（默认 `closed`）。
- **全局策略**：就是 profile 补丁条目里的 `config`（`strict`、`kernelCommand`、`timeoutMs`、`failMode`）；插件不读第二份策略文件，`strict` 由插件随每次载荷以 `strict` 字段传给内核，内核不落盘。

## CLI 命令

`aios init / check / finish / migrate / approval record / context refresh / memory search|record|reindex|candidates|candidate / worktree prepare|check|finish|cleanup|list / mcp / doctor / authorize-dsh / authorize-hook`。

- `check [--change-class --requirement-id]` = 仓库治理（GitHub 就绪 + 卫生 + output 纯净 + .gitignore 合规）+ docs 检查 + Code Start 预览（含调研分层），阻塞退出码 40。
- `finish --base-ref <task-start-ref> [--change-class bugfix] [--test-command "..."] --memory-written|--memory-not-needed` = Finish Gate；缺少基线或其他阻塞退出码 40，空仓库基线为 EMPTY_TREE。
- `migrate <project-root>` = 把 `.codex-os/` 迁移到 `.aios/`（一致性备份 + 移动，非复制）；未知结构拒绝，无 force 兜底。`init --migrate-runtime` 仍只迁移已知旧库。
- `authorize-dsh` = stdin DSH 载荷 → `{decision, rule_id, targets, reason, next_step}`；始终是只读诊断，不执行操作，也不代表宿主授权；载荷不可读时非零退出（插件对变更类操作按失败封闭处理）。
- `authorize-hook` = 保留的 Codex 兼容桥：stdin Hook JSON → 官方 Hook JSON；与 `authorize-dsh` 共用同一内核与同一离线规则集，避免两套判定漂移。
- `approval record` / `context refresh` = 补齐与 DSH 工具面同构的终端入口，复用同一用例。
- `init <project-root> --migrate-runtime` 只迁移已知旧库；见 DATABASE.md。正常 init 不向已有 input/ 补写 .gitkeep。
- Doctor 的 `ok: null` 表示未知（插件安装/加载不能由本地文件证明）；必需 SQLite 检查不再要求未使用的 FTS5。

## 错误码

配置类 CONFIG_INVALID；Gate 类返回 findings（code/message/path/blocking），决策本身不报错；Memory 类 MEMORY_*；Worktree 类 WORKTREE_*；数据库类 MIGRATION_*；宿主桥类 AIOS_RUNTIME_UNAVAILABLE / AIOS_RUNTIME_TIMEOUT / AIOS_RUNTIME_INVALID_RESPONSE。
