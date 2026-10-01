# 数据库

SQLite 只保存运行状态与可重建索引；Markdown/Git 保存事实正文。数据库位于 `.aios/state/state.db`，运行状态被 Git 忽略；项目配置 `.aios/project.yaml` 仍由 Git 管理。

## 单迁移 0001（四表 + 索引）

- `tasks` — id, title, branch, status(open|in_progress|blocked|done), created_at, updated_at。worktree prepare 自动登记任务。
- `approvals` — id, subject, gate(code_start|frontend|finish), decision(approved|rejected), decided_by, reason, created_at。
- `worktrees` — id, task_id→tasks, name/path/branch/target_branch（name/path/branch 均 UNIQUE）, disposable, status(active|ready|cleaned), created_at, updated_at。cleanup 注销删除行。
- `memory_index` — id, record_type, title, summary, source, source_commit, tags, status, superseded_by, line_number, indexed_at。可由 docs/memory/memory.jsonl 随时重建。

## 迁移与保护

- 仅保留一个编号迁移；schema_migrations 记录 version/name/checksum/applied_at，迁移前校验已应用迁移 checksum。
- 普通调用只创建空库或验证当前结构，不自动重建。已确认历史提交 12b723b 的旧 schema/checksum/完整结构指纹可通过 `init --migrate-runtime` 或 `project_init(migrate_runtime=true)` 显式导出并重建。其他未知表、视图、校验值、结构或损坏均保持原样报错，不能按“旧版”推测删除。
- 显式迁移先取得写锁、确认没有活动 Worktree，再通过 SQLite Backup API 创建包括已提交 WAL 数据的一致性备份；完整性验证和 SHA-256 sidecar 成功后才在单个 SQL 事务内更换结构。禁止直接删除主库/WAL。忙库、活动 Worktree、备份失败均停止并保留原库。备份保留旧任务记录供恢复，不自动灌入新版派生库；需要时从 Git JSONL 重建 Memory 索引。
- 迁移模式不创建/改写 input/ 和任何项目事实文档；未知结构需先人工审查，不提供 force 兜底。
- 连接参数：WAL、foreign_keys=ON、busy_timeout=5000；迁移在 BEGIN IMMEDIATE 内执行并做 foreign_key_check 与 integrity_check。

## 宿主迁移（.codex-os → .aios）

`aios migrate <project-root>` 处理 Codex 时代的运行库：

- 识别 `.codex-os/project.yaml` 与 `.codex-os/state/state.db`；先做上述一致性备份到 `.aios/state/backups/`。
- `project.yaml` 经 Git 感知的移动（非复制）落到 `.aios/project.yaml`，`schema_version` 升到 `1.3`；`state.db` 与 `state/memory-candidates/` 移动到 `.aios/state/`。
- 迁移后 `.codex-os/` 目录不应残留；若残留只可能是未识别产物，此时保留并报告，不删除。
- 未知结构、忙库、活动 Worktree、备份失败一律拒绝迁移并保留原库。
- 既有 `codex/wt-*` 分支的 Worktree 登记继续有效（工作树模块同时接受两代前缀）；新建登记使用 `aios/wt-*`。
