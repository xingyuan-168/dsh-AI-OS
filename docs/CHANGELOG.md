# 变更记录

## [1.0.0] - 2026-09-10

### governance-core 轻量化大重构（ADR-0016，breaking change）

版本定稿：Dogfood 四案例全部通过（无 GitHub 阻塞/放行、正常后端流程、前端批准与豁免、子 Agent worktree 隔离与清理），当次基线环境验证通过，复杂度预算达标（MCP 7/8、CLI 7+1/8、Skills 8/9、活跃 docs 13/10~15、Gate 3、SQLite 5/6 表）。

## Unreleased

### 插件激活状态（2026-10-01 实测）

- 截至 DSH 0.2.0-rc.2 **没有在线激活路径**：`plugin_manager set_plugin(target="ai-engineering-os")` 返回 `unknown-plugin`（条目尚未进合成树），重复 `install_bundle` 仍为 `not-bundle` / `changed: false`，直接改 `cordis.patch.yml` 也不会触发重新合成。
- 因此插件的加载**必须重启 DSH**；重启前强制层不生效，`aios` CLI 本身不受影响。
- 已落成事实与排障表：`docs/GOVERNANCE_RULES.md`「安装与强制」「排障」；使用方式见 `README.md`「如何使用」。

### DSH 宿主迁移与全局强制（2026-10-01，ADR-0018，breaking change）

- 破坏性重命名：命令 `codex-os` → `aios`，导入 `codex_ai_os.*` → `aios.*`，发行名 → `aios-governance`，运行库 `.codex-os/` → `.aios/`，worktree 分支前缀 → `aios/wt-`（既有 `codex/wt-*` 登记继续有效）。
- 宿主集成整体替换：删除 `.codex/config.toml`、`.codex/hooks.json`、`.codex-plugin/plugin.json`、`.mcp.json`、`hooks/`、8 个 `skills/*/agents/openai.yaml`、`.agents/plugins/marketplace.json`、`scripts/launch_mcp.cmd`；新增 DSH Cordis 插件（`package.json` + `src/*.js`），插件只转发、裁决全部来自内核。
- 强制点修正：`tools/pre-execute` 是唯一可拒绝的派发前裁决点，覆盖全部工具；`fs/write-intent` / `fs/edit-intent` 是单槽写意图决策，不能拒绝任何操作，因此不注册。
- 三层强制模型：Tier 0 基线在任何工作区生效（含未初始化项目：受保护路径、用户资产保护、Memory 单写者）；Tier 1 三 Gate 需要 `.aios/project.yaml`；Tier 2 `strict` 让未初始化项目套用 Tier 1，且只在内存中物化确定性默认策略，不写盘、不改项目。
- 新增 `aios authorize-dsh`、`aios migrate`、`aios approval record`、`aios context refresh`；`authorize-hook` 保留为 Codex 兼容桥，与 `authorize-dsh` 共用同一内核，避免两套判定漂移。
- 迁移：`.codex-os/` → `.aios/` 先做 SHA-256 一致性备份再移动；未识别结构拒绝，未识别条目保留并报告；本仓库自身运行库已迁移。
- 文档、Skill 与 ADR 全部改为 DSH 措辞；ADR-0018 记录迁移决策与被否决方案；调研记录 REQ-DSH-2.0。
- 修复：pytest 临时根落在受治理仓库内时，根解析会越过夹具读到真实项目事实（曾把夹具记录写进受跟踪的 `docs/memory/memory.jsonl`）——basetemp 现在固定在 `.aios/pytest`，并对 Git 发现设置 ceiling、对需要隔离的用例给出显式项目边界；`python -m aios` 之前绕过 UTF-8 stdio 设置，会把 JSON 桥输出写成非 UTF-8 字节。

### 安全边界与数据保全修复（2026-09-24，ADR-0017）

- 清理按真实目标检查；统一项目/Worktree 解析和 Move to 保护，修正 branch -d/-D。薄 Hook 统一内核，错误明确拒绝；移除 ask 与脏文件归属推断，增加只读 --explain 和 15/10/5 秒超时预算。
- 前端批准/拒绝均更新事实并绑定内容摘要；旧批准需重新确认，补齐 css_fix 豁免。
- 数据库仅对已知指纹显式迁移，SQLite 一致性备份保留 WAL；未知/异常不重建。Memory 失败保留候选，写锁防止覆盖，检索刷新索引并统一 Secret 校验。
- Worktree 非强制 remove/branch -d，失败保留恢复记录；Finish 必需基线并覆盖完整任务差异；Secret Scan 检查实际暂存内容，缺失不再视为通过。
- 同步 8 个 Skill 契约，新增签名回归；保护已有 input，修正 Windows launcher/Docker 模板、Doctor 未知状态；修复类型契约而不放宽检查规则。
- 本轮为源码修改，不包含全局插件重装、Hook 信任、实际项目迁移或宿主审批设置变更。

### GitHub 官方 SSH endpoint 兼容（2026-09-17）

- 门禁与仓库检查共用精确主机解析；将 `ssh.github.com`（SSH URL 可指定 443）规范化为 `github.com`，不接受通配符、相似域名、任意 SSH 主机或非官方端口。
- 保留原始 `origin` 的 `git ls-remote` 可达性检查；补充官方端点、伪装域名、非法端口及不可达回归测试。


### governance-core 审计修复（fix/governance-hardening）

- fix(gates): Code Start 强制 GitHub remote + 复制式脏乱判定；开源调研文档要求 requirement_id 开头并给出 summary 与 Decision/reason，空模板/stale id/缺 reason 均阻塞，无布尔绕过。
- fix(frontend): 批准事实持久化为 docs/design/UI_SPEC.md 的 `approval:` 块（scope 精确匹配），删除调用方 approved 布尔绕过。
- fix(worktree): cleanup 先证明合并（`merge-base --is-ancestor <tip> <target>`），脏树与未合并一律拒绝；finish 置 ready（ready ≠ merged）；force 参数全面删除；Hook 只信任登记的真实 worktree，伪造 .worktrees/ 失败封闭，temp 判定跨平台。
- refactor(auth): 授权内核只判操作不判角色（principal/TRANSITION/policy_hash/RoleBoundary/GovernanceMode 删除）；output/ 可写，其纯净由卫生检查判定；OCI 话术改为"可能破坏项目持久数据"语义。
- fix(finish): 删除 --tests-passed/--docs-synced 自证；新增 core/checks.py 薄真实检查（声明的 --test-command、配置了 ruff 才跑 ruff、git diff --check、卫生、candidate 提醒非阻塞）。
- fix(memory): candidate 闭环——accept 校验并入/reject 丢弃/未知 id MEMORY_CANDIDATE_MISSING；CLI memory candidate 与 MCP 第 8 工具 memory_candidate。
- refactor(config): ProjectConfig 只保留运行时读取的字段（project_type 驱动模板，新增 code_paths），risk_level/环境/执行策略字段与 .codex/agents 角色档案删除。
- chore(repo): 删除 .codex-os/gates、environment.yaml、execution-policy.yaml、test-traceability.yaml；secret 扫描脚本晋升 scripts/secret_scan_incremental.py；.gitignore 合规检查（15 项运行时产物，等价写法允许）。
- docs: ADR 0001/0003/0009 随被删运行时退役；AGENTS.md/README/API_SPEC/GOVERNANCE_RULES/WORKTREE/MEMORY/DATABASE/TEST_PLAN/ARCHITECTURE 同步。

### governance-core 第二轮审计加固（fix/aios3-hardening）

- fix(gates): 开源调研事实增加 scope（行内/块列表）与 updated_at（YYYY-MM-DD）必填校验。
- feat(finish): Code Start 第二层复核——未提交/已暂存改动触及 code_paths 时必须携带 --change-class（研究类另需 --requirement-id）复跑 Code Start，间接写入（脚本生成源码）在完成时被拦截；无状态设计不变。
- fix(frontend): approval 块持久化 approved_by（decided_by 传递），SQLite 仍只是索引。
- docs(governance): AGENTS.md 收敛为十条宪法 + Git 节奏 + 原则化护栏，验证与实现边界细节下沉 GOVERNANCE_RULES；ADR-0010/0011/0015 标注部分 Superseded（只改状态行，不改历史正文）。
- chore(repo): 删除 .codex-os/tmp 一次性编辑脚本与本地缓存残留。
