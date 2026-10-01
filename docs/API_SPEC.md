"""
# 接口契约

MCP 与 CLI 共享实现和业务响应封装（`{ok, data} / {ok:false, error:{code,message}}`）。项目参数允许根、子目录或登记 Worktree；共用解析器区分当前 checkout 与协调根。文件目标支持相对/绝对路径，并独立验证所属项目。无模型推理。

## MCP 工具（8）

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

## CLI 命令（7 + 1 桥）

`codex-os init / check / finish / memory search|record|reindex|candidates|candidate / worktree prepare|check|finish|cleanup|list / mcp / doctor / authorize-hook`。

- `check [--change-class --requirement-id]` = 仓库治理（GitHub 就绪 + 卫生 + output 纯净 + .gitignore 合规）+ docs 检查 + Code Start 预览（含调研分层），阻塞退出码 40。
- `finish --base-ref <task-start-ref> [--change-class bugfix] [--test-command "..."] --memory-written|--memory-not-needed` = Finish Gate；缺少基线或其他阻塞退出码 40，空仓库基线为 EMPTY_TREE。
- `init <project-root> --migrate-runtime` 只迁移已知旧库；见 DATABASE.md。正常 init 不向已有 input/ 补写 .gitkeep。
- `authorize-hook` = stdin JSON → 官方 Hook JSON；无阻塞输出 `{}`，拒绝只使用 deny，不使用 ask/allow 代替宿主授权。`--explain` 输出业务 envelope，其 data 含 layer=aios、decision、rule_id、targets、reason、next_step；不执行命令。
- Doctor 的 `ok: null` 表示未知（插件安装/Hook 信任/当前任务加载不能由本地文件证明）；必需 SQLite 检查不再要求未使用的 FTS5。

## 错误码

配置类 CONFIG_INVALID；Gate 类返回 findings（code/message/path/blocking），决策本身不报错；Memory 类 MEMORY_*；Worktree 类 WORKTREE_*；数据库类 MIGRATION_*。
