# 测试计划

## 默认验证（≤5）

1. 目标测试（narrowest mapped tests）。
2. `ruff check src plugins tests`。
3. `git diff --check`。
4. 仓库卫生 `aios check .`。
5. 必要时 pyright（schema/公共 API 变更）。

另加仓库 Secret Scan：提交前 `python scripts/secret_scan_incremental.py --staged`，检查索引而非仅工作区；缺失/不可读/扫描错误失败。

## 测试映射（必须保留的正负案例）

- Gate A 脏乱精确判定：用户未提交工作放行；副本目录/文件拦截；api/v1/ 不误伤。
- 开源调研分层：豁免类误拦 = 失败；必查类漏拦 = 失败；调研文档缺 requirement_id/summary/scope/updated_at/Decision 元数据 = 失败；stale requirement_id = 失败；空模板 = 失败。
- 前端 Gate 分层：豁免路径直接放行；Gated 路径缺原型/UI_SPEC 均阻塞；批准来自 UI_SPEC 的 approval 块（scope 精确匹配），调用方布尔无法绕过。
- input/ 只读：治理通道写 input/ 被拒；副本扫描跳过 input/；output/ 可写但纯净由卫生检查判定。
- DSH 事件桥：`tools/pre-execute` 载荷放行/拒绝；`fs/write-intent` 与 `fs/edit-intent` 的目标、源、Move to 均受保护；内核缺失/超时/异常/无效 JSON 时变更类操作拒绝、只读操作只提示检查不可用；不输出宿主不支持的裁决语义。
- 危险命令：main 指向安全临时叶目标可通过客观检查；temp 指向外部资产拒绝；宽泛根、跟踪文件、保护子项、链接、变量/复合表达式拒绝；branch -d 与 -D 区分；Git -C 不继承错误上下文。删除载荷只做诊断，真实删除仅发生于专门创建的 Worktree 夹具。
- Finish 薄检查：声明的 --test-command 失败 = 阻塞；未声明不阻塞；TESTS_NOT_PASSED/DOCS_NOT_SYNCED 不再存在；MEMORY_CANDIDATES_PENDING 非阻塞。
- Memory：record 校验（Secret 拒绝、去重、类型/状态枚举）、reindex、单写者（worktree 内 docs/memory/ 写入被拒、candidate 放行）、candidate accept 并入/reject 丢弃/未知 id 报 MEMORY_CANDIDATE_MISSING、损坏 JSONL 阻塞写入。
- 迁移：`.codex-os/` → `.aios/` 含一致性备份与 schema_version 升级；未知结构/忙库/活动 Worktree 拒绝且保留原库；既有 `codex/wt-*` 登记仍有效、新建使用 `aios/wt-*`。
- Worktree：prepare 登记 / finish 拒绝脏树且置 ready / cleanup 未合并拒绝（merge 证明后通过）/ 注销后名称复用。
- 数据库：普通读取不重建、已知指纹显式迁移、一致性备份包含 WAL 提交数据；未知结构/损坏/忙库/活动 Worktree/备份失败保留原库。
- repository：GitHub 缺失/不可达/主机不符、output/ 纯净、docs/archive 拒绝、.gitignore 覆盖 15 项运行时产物（等价写法允许）。
- 插件契约：8 个 Skill 齐备且每个 `SKILL.md` ≤60 行；插件清单/入口/provider 接线存在；Python 示例绑定真实工具签名。

## 运行规则

不在“full pytest”之后重复跑 plugin/MCP 子集凑证据；一个逻辑变更跑它映射的用例即可。
