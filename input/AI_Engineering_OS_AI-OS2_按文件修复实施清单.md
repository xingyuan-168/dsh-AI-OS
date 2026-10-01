# AI Engineering OS（AI-OS(2)）按文件修复实施清单

> **用途**：本文件直接交给 Codex，作为当前 `AI-OS(2)` 源码的修复任务书。
>
> **基线**：Governance Core 轻量化方向已经确定，本轮只修缺口、删残留，不再重新设计新平台。
>
> **最高原则**：
>
> **Codex 是专业工程执行者；AI Engineering OS 只是工程治理层。**
>
> AIOS 只约束“能不能做、什么时候做、做完必须留下什么”，不规定 Codex“专业工作具体怎么做”。

---

# 1. 本轮必须解决的问题

当前重构已经大幅减重，但还有以下真实缺口：

1. Code Start Gate 没真正接到源码写入边界，Codex忘记主动检查时仍可能直接写正式源码。
2. Open Source Research 只检查文件/`## Decision`，空模板或旧研究可能假通过。
3. Frontend Gate 可由调用者直接传 `approved=true` 绕过，且批准只存在 SQLite。
4. `output/**` 被当成受保护只读路径，与“最终交付目录”定义冲突。
5. Worktree `finish()` 直接标记 `merged`，但并未验证真实合并。
6. Worktree cleanup 在未确认 merge 的情况下仍可能删 Worktree/branch。
7. Hook 只凭路径包含 `.worktrees/` 就认为是可信 disposable Worktree，没有查登记。
8. `.codex/agents/*.toml` 仍引用已删除 Skill、G0-G3、Evidence、Workflow 等旧体系。
9. Authorization Kernel 仍残留 RoleBoundary、Workflow transition、OCI sandbox 等旧架构语义。
10. Memory candidate 只有 submit/list，没有 accept/reject/consume/cleanup 闭环。
11. ProjectConfig 仍残留 `active_workflow`、`environment_mode`、`default_agent_profile` 等失效字段。
12. `.codex-os/` 仍堆积旧 gates、execution logs、artifacts、backup DB、tmp scripts。
13. 旧 ADR 仍被列为“当前有效”，与 ADR-0016 冲突。
14. `docs/design/UI_SPEC.md` 仍描述旧 Workflow/Evidence/Agent UI，并引用已删除 `USER_FLOW.md`。
15. Finish Gate 主要相信 `--tests-passed` / `--docs-synced` 自我声明。
16. Repository Check 没有真正完成 `.gitignore` 最小合规检查。
17. 临时目录判断偏 Windows，Linux/macOS temp 识别不完整。
18. `pyproject.toml` / CHANGELOG / 用户确认之间存在版本语义冲突。

本轮不得增加新的产品能力。

---

# 2. 修复顺序

按以下顺序执行：

```text
P0-1  Code Start 真正强制
P0-2  Open Source Research 防假通过
P0-3  Frontend Approval 防绕过 + Git 持久化
P0-4  output/ 权限修正
P0-5  Worktree finish / merge / cleanup 安全语义
P0-6  Disposable Worktree 登记校验
P0-7  删除/重写旧 Agent Profiles
P0-8  Authorization Kernel 再瘦身

P1-1  Memory candidate 闭环
P1-2  Config / OCI 残留清除
P1-3  .codex-os 物理垃圾清理
P1-4  ADR / UI_SPEC / CHANGELOG 清理
P1-5  Finish 最薄真实检查
P1-6  .gitignore 合规检查
P1-7  跨平台 temp 修复
P1-8  对应测试补齐
```

每项完成后跑最窄相关测试，不等全部完成再排错。

---

# 3. `src/codex_ai_os/core/gates.py`

## 问题 3.1：Open Source Research 假通过

当前逻辑过弱：

```text
Research 文件存在
+
有 ## Decision
=
完成
```

这会导致空模板直接通过，也会导致一份旧 Research 永久解锁以后所有重大需求。

## 必须修改

对必须研究的任务，至少验证：

```text
当前 requirement 标识/描述存在
至少一个 Candidate，或明确说明没有合适候选
Decision ∈ use | fork | extract | build
Reason 非空
Research 对应当前 requirement
```

建议使用极简 Markdown 元数据，不要建新的 Research Runtime。

例如：

```markdown
## Requirement
requirement_id: REQ-xxx
summary: ...

## Candidates
...

## Decision
decision: build
reason: ...
```

或者一个简短 HTML/YAML metadata 块。

### 禁止

不要新增：

- Research DB；
- Evidence Bundle；
- Candidate 表；
- SBOM；
- dependency/security audit；
- 复杂需求分类器。

## 问题 3.2：`research_done=True` override

正式公共入口不得通过一个布尔参数直接绕过 Research。

### 修改

- 正式 MCP/CLI 不信任 `research_done=True`。
- 测试需要 mock 时使用内部 helper，不暴露成用户/Agent绕过开关。

## 验收测试

```text
research-required + 空模板                -> DENY
research-required + 只有 ## Decision      -> DENY
Decision 无 reason                        -> DENY
旧 requirement 的研究                     -> DENY
当前 requirement 完整研究                 -> ALLOW
bugfix/typo/test-only/small-maintenance    -> Research 豁免
```

---

# 4. `src/codex_ai_os/cli/mcp_server.py`

## 问题 4.1：Frontend Approval 可直接绕过

当前 `_frontend_approved()` 中：

```python
if approved is not None:
    return approved
```

必须删除这个正式绕过路径。

### 修改

`governance_check(stage="frontend")` 不再接受调用者用 `approved=true` 决定结果。

Approval 必须来自正式批准事实。

允许 breaking change，优先直接删参数。

## 问题 4.2：Approval 只存在 SQLite

用户对 UI 的批准是长期项目事实，不能只放本机 state.db。

### 修改

`approval_record` 在用户明确批准后，把极简事实写入：

```text
docs/design/UI_SPEC.md
```

例如：

```yaml
approval:
  type: frontend
  scope: admin-dashboard
  status: approved
  approved_at: 2026-09-10
```

SQLite 可以继续做索引，但不是唯一事实源。

### 必须支持 scope

不同 UI 需求不能互相继承 Approval：

```text
dashboard-v1 approved
≠
new-settings-page approved
```

## 问题 4.3：Worktree cleanup 暴露 `force`

公共 MCP 不应默认暴露可丢代码的 force cleanup。

### 修改

删除 `force`，或把它变成只有用户明确人工批准才能调用的内部 emergency path。

正常 cleanup 必须先验证真实 merge。

---

# 5. `src/codex_ai_os/application/governance_policy.py`

## 问题 5.1：`output/**` 被错误当作只读敏感路径

当前 `SENSITIVE_PROTECTED_PATHS` 包含：

```text
output/**
```

这与产品定义冲突。

### 正确规则

```text
input/
  read  = allow
  write/delete/rename = deny

output/
  final deliverable write = allow
  temp/cache/debug/source-copy = Finish hygiene deny
```

### 修改

从全局 write deny 中移除：

```text
output/**
```

`output/` 应由 Finish/Repository Hygiene 做纯净性治理，而不是只读。

## 问题 5.2：RoleBoundary 过重且过时

当前还有：

```text
backend-engineer
frontend-engineer
product-manager
architect
qa
reviewer
memory-manager
```

这属于旧 Agent Runtime 思维。

### 修改

优先删除 RoleBoundary 模型。

最终 Path Policy 只需要理解：

```text
input
output
governance files
runtime state
main worktree
trusted disposable worktree
user assets
```

不需要 fictitious principal role。

## 问题 5.3：policy hash

如果 hash 只为旧 Evidence/审计链存在，删除。

不要为了“看起来企业级”保留无用户价值的 hash 机制。

---

# 6. `src/codex_ai_os/application/authorization.py`

## 必须删除的旧语义

当前仍有：

```text
workflow transitions are governed by the workflow engine
OCI sandbox policy still applies
Persistent OCI volume deletion requires an independent operator workflow
```

这些体系已经被删除。

### 修改后 Authorization 只负责

1. 共享 Git 历史危险命令；
2. 用户主工作区破坏性命令；
3. `input/` 用户资产；
4. 少量治理规则文件保护；
5. trusted disposable worktree 的合理放权。

Docker/Compose 危险删除可以继续防护，但语义应是：

> 可能破坏项目持久数据。

不要再说 OCI Runtime / operator workflow。

## 必须确认正常能力放行

测试确保：

```text
pip install
uv sync
npm install
pnpm
yarn
cargo build
pytest
ruff
pyright
普通 build
sed -i
正常 Git
```

不被 AIOS全局拦截。

---

# 7. `src/codex_ai_os/application/hook_gateway.py`

## 问题 7.1：硬编码 `principal="backend-engineer"`

多处把所有操作都视为 backend-engineer。

### 修改

如果 RoleBoundary 删除，直接移除 principal 参数。

Hook Gateway 只传：

```text
tool
cwd
target paths
command
operation
```

## 问题 7.2：Code Start 没有真正接线

这是本轮最高优先级之一。

当操作属于正式源码写入时：

```text
ApplyPatch
Write/Edit
Bash 产生正式源码写入
```

必须调用无状态 Code Start Evaluator。

如果 Gate deny：

```text
真正 DENY
```

而不是 additionalContext 提醒。

### 不允许重新造状态机

不要保存：

```text
gate passed
workflow phase
transition
execution authority
```

需要时无状态重算即可。

### 正式源码路径

不要只写死 `src/`。

在 `project.yaml` 允许一个简单的：

```yaml
code_paths:
  - src
  - plugins
```

默认可有少量常见路径，但不要做复杂语言探测。

---

# 8. `plugins/ai-engineering-os/hooks/pre_tool_use.py`

这是本轮最关键 Hook 文件。

## 问题 8.1：假 `.worktrees/` 也获得宽松权限

当前：

```python
if "/.worktrees/" in posix:
    return True
```

不安全。

### trusted disposable worktree 必须同时满足

```text
1. 能解析 coordinator project root
2. state DB 中存在对应 worktree 登记
3. DB path 与当前 cwd realpath 一致
4. git worktree list --porcelain 中真实存在
```

缺任一项都不是 trusted worktree。

## 问题 8.2：跨平台 temp

使用：

```python
tempfile.gettempdir()
```

作为标准入口，再以 TEMP/TMP 环境变量补充。

必须覆盖：

- Windows；
- Linux；
- macOS。

## 问题 8.3：Code Start 必须 enforce

对正式源码写入：

```text
Gate A deny -> PreToolUse deny
```

不能只提醒 Codex先运行 `codex-os check`。

## 问题 8.4：Memory candidate 命令必须从 Worktree 可用

当前提示：

```text
codex-os memory record --candidate
```

必须保证从登记 Worktree cwd 调用时能定位 coordinator root。

不要出现 Skill要求子 Agent执行一个实际不可执行的命令。

## 验收

```text
.worktrees/fake/                 -> 不放权
登记且真实的 worktree            -> 允许合理 cleanup
Linux tempfile.gettempdir()     -> 正确识别
Windows TEMP                    -> 正确识别
macOS tempdir                   -> 正确识别
无 GitHub + 修改正式源码          -> DENY
```

---

# 9. `plugins/ai-engineering-os/hooks/session_start.py`

当前方向基本正确，保留：

```text
Keep Codex's native engineering workflow
```

并继续禁止 execution authority 语义。

### 仅微调

当前提示：

```text
verify GitHub readiness (codex-os check)
```

改成更准确的：

> Codex 可主动运行 `codex-os check` 预看原因，但客观治理边界由 Hook/Runtime 自动强制。

### 不要扩展

SessionStart 不要：

- 创建 task/workflow；
- 写 DB审计；
- 跑全量验证；
- 自动生成 Evidence；
- 要求加载几十份文档。

---

# 10. `src/codex_ai_os/core/worktree.py`

## 问题 10.1：`finish()` 错把 ready 当 merged

当前：

```python
return self._set_status(record.name, "merged")
```

但没有真实 merge。

### 修改

只保留简单状态：

```text
active
ready
```

`finish()`：

- Worktree存在；
- clean；
- 有 commit；
- 设置 `ready`。

## 问题 10.2：cleanup 前必须证明已经 merge

用 Git 原生 ancestor 判断：

```text
git merge-base --is-ancestor <branch-tip> <target-branch>
```

或等价方法。

未包含：

```text
WORKTREE_NOT_MERGED
```

拒绝删除。

## 问题 10.3：force 风险

正常公共路径不允许 force 删除未合并/未提交工作。

不要让 `force=True` 成为 Agent快捷绕过。

## 数据最小需求

Worktree 记录只需要必要信息，例如：

```text
path
branch
target_branch
head_commit（如需要）
status
```

不要重新引入 integration branch / DAG / join barrier。

## 验收

```text
dirty finish                   -> DENY
clean committed finish         -> ready
未merge cleanup                -> DENY
merge后 cleanup                -> ALLOW
未提交内容 cleanup             -> DENY
不存在/伪造 worktree           -> DENY
cleanup后 DB row清理           -> PASS
```

---

# 11. `src/codex_ai_os/infrastructure/database.py`

保持轻量。

允许核心表大致只有：

```text
tasks
approvals
worktrees
memory_index
```

如果 Worktree安全校验需要，可增加少量字段，不新增复杂表。

### 严禁恢复

```text
workflow_runs
task_groups
task_dependencies
evidence
host_operations
release_records
operation_attempts
executions
完整 events audit stream
```

当前允许 breaking change，不重新背负多代迁移链。

---

# 12. `src/codex_ai_os/infrastructure/memory.py`

## 当前正确部分

保留：

```text
docs/memory/memory.jsonl = Git事实源
SQLite memory_index = 可重建索引
```

## 当前缺口：candidate 没有 consume 闭环

增加非常小的能力：

```text
accept_candidate(id)
reject_candidate(id)
```

接受流程：

```text
candidate
→ 主 Codex review
→ append memory.jsonl
→ reindex
→ 删除 candidate
```

拒绝：

```text
删除 candidate
```

不要为 candidate 建状态机/DB生命周期。

## Finish

Finish 时：

- 有未处理 candidate -> 提示；
- 已处理 candidate -> 不得残留垃圾。

---

# 13. `src/codex_ai_os/infrastructure/config.py`

统一所有 root resolution：

```text
main cwd -> project root
真实登记 worktree cwd -> coordinator root + worktree context
fake .worktrees path -> 不映射
```

Memory candidate、Hook、Gate、CLI都应复用同一套解析逻辑。

不要靠目录字符串猜。

---

# 14. `src/codex_ai_os/domain/config.py`

这是旧架构残留重点。

当前有：

```text
OCI_FIRST
active_workflow
approval_policy
default_agent_profile
environment_mode
allowed_mounts
```

### 大幅删除

最终 `ProjectConfig` 只保留真实被当前 Core 使用的字段，例如：

```text
schema_version
project_id
name
root
source_of_truth
git_push_policy
github_hosts
code_paths
target_branch
```

没人使用的字段直接删，不做“未来可能有用”兼容。

---

# 15. `.codex-os/project.yaml`

当前旧字段：

```yaml
risk_level: high
active_workflow: new-project
approval_policy: critical-gates-human
default_agent_profile: standard
environment_mode: oci-first
```

全部重新核对，未被轻量 Core真实使用的删除。

建议只保留：

```yaml
schema_version: "1.0"
project_id: PROJECT-AI-ENGINEERING-OS
name: AI Engineering OS
root: .
source_of_truth: docs
git_push_policy: remote_required
target_branch: main
github_hosts:
  - github.com
code_paths:
  - src
  - plugins
```

具体字段以真实使用为准，不为模板好看而加。

---

# 16. 直接删除的旧运行配置/垃圾

以下是旧 Runtime 残留，直接删除，不归档。

## `.codex-os/environment.yaml`

删除。属于旧 OCI Runtime。

## `.codex-os/execution-policy.yaml`

删除。`sandbox: podman / allow_host_execution: false` 已与当前架构冲突。

## `.codex-os/test-traceability.yaml`

删除。属于旧 Evidence/Traceability。

## `.codex-os/gates/`

整个删除：

```text
G0.yaml
G1.yaml
G2.yaml
G3.yaml
G4.yaml
oci-first/
```

## `.codex-os/artifacts/`

全部旧 Evidence/Verification/repair artifact 删除。

## `.codex-os/logs/`

全部旧 execution stdout/stderr 删除。

## `.codex-os/state/backups/`

旧 migration/handoff DB backup 删除。

以后如迁移前临时备份：

- 临时创建；
- 成功后删除；
- 不长期堆积项目目录。

## `.codex-os/tmp/`

当前：

```text
wt_smoke.py
repo_smoke.py
hook_smoke.py
gate_smoke.py
secret_scan_incremental.py
cli_smoke.py
record_release.py
decision_check.py
db_smoke.py
dogfood.py
```

处理原则：

- 正式 tests 已覆盖 -> 删除；
- 真正长期复用 -> 移到正式 test helper/scripts；
- 其余删除。

`record_release.py` 直接删除。

## 所有 `__pycache__` / `*.pyc`

全部删除。

包括被删除模块遗留的：

```text
release.pyc
g4.pyc
workflow.pyc
verification_cache.pyc
evidence.pyc
docker.pyc
podman.pyc
coordination.pyc
```

同时删除：

```text
.pytest_cache/
.ruff_cache/
```

这些由工具重建。

---

# 17. `.codex/agents/` 整体处置

当前 8 个 Profile 大量引用不存在的 Skill 和旧体系。

**默认推荐：删除整个 `.codex/agents/`。**

原因：

> “Codex 原生子 Agent”不等于“AIOS必须预定义8个企业岗位”。

当前 Profile 的确存在旧引用：

- `architecture-design`
- `backend-implementation`
- `frontend-implementation`
- `database-design`
- `testing`
- `code-review`
- `security-review`
- G0/G1/G2/G3
- Evidence
- active workflow
- allowed task paths

这些都已经与当前 Core 不符。

## 如果确实要保留 reviewer

最多保留一个极薄 Codex-native reviewer，例如：

```toml
name = "reviewer"
description = "Read-only reviewer for correctness and regression risk."
sandbox_mode = "read-only"
developer_instructions = """
Review the concrete diff and requirements.
Do not edit files.
Return severity-ordered findings and missing tests.
"""
```

不得引用 AIOS旧 Skill、Gate状态机、Evidence或Runtime。

---

# 18. `AGENTS.md`

整体已经正确，不重写成大规范。

### 需修

当前“实现边界”仍写：

```text
Workflow/Gate/审批/SQLite 全部自研自持
```

删除 `Workflow` 语义。

补一句：

> Code Start 客观边界由 Hook/Runtime自动强制，不依赖 Codex主动记得运行 check。

不要继续增加更多宪法条目。

---

# 19. `README.md`

### 同步以下事实

1. Code Start 是真实强制边界，不只是主动 check。
2. Worktree：
   - finish = ready；
   - Codex/Git完成 review+merge；
   - AIOS cleanup只验证 target已包含 branch tip。
3. `output/` 可写最终交付。
4. 若 Finish CLI接口修改，同步示例。
5. `.codex/agents/` 若删除，不再宣传固定角色 Profile。

---

# 20. `docs/OPEN_SOURCE_RESEARCH.md`

当前文档可以保留作为 ADR-0016 本轮 Research。

### 增加

- `requirement_id` 或等价 scope；
- 明确当前 Decision属于 Governance Core重构。

防止以后被误当通用通行证。

不要增加重型安全/供应链字段。

---

# 21. `docs/FRONTEND_GATE.md`

补：

- Approval长期事实存于 UI_SPEC metadata；
- SQLite只是索引；
- `approved=true` 不能 override；
- Approval有 scope；
- 新 scope 不继承旧 approval。

---

# 22. `docs/design/UI_SPEC.md`

**直接删除当前文件。**

原因：

它仍描述旧：

- Workflow；
- 状态；
- Evidence；
- 日志；
- Agent；
- 历史事件；
- 暂停/恢复/重试/合并；
- `USER_FLOW.md`。

当前 AIOS 没有这个正式 UI，保留只会污染事实。

未来真开发 AIOS UI时重新：

```text
Prototype -> UI_SPEC -> 用户批准
```

---

# 23. `docs/ADR/README.md` 与旧 ADR

当前 README 把多份旧 ADR 列为“当前有效”，但其中仍有：

```text
G0-G4
Workflow
Evidence
OCI
Release
Task Group
Join Barrier
```

### 修改

只保留与 ADR-0016 不冲突的真正当前决策。

对以下旧 ADR 逐个检查：

```text
ADR-0001
ADR-0003
ADR-0005
ADR-0009
ADR-0010
ADR-0011
ADR-0015
```

如果核心依赖被删除的 Runtime：

**直接删除。**

Git历史就是归档。

不要维护“部分有效、部分失效”的长篇旧规范，让 Codex自己猜哪一段有效。

ADR-0016 是当前主基线。

---

# 24. `docs/CHANGELOG.md`

当前存在明显冲突：

```text
[1.0.0] 已定稿
```

同时：

```text
Unreleased: 版本号待用户确认
```

必须统一。

### 原则

如果用户尚未正式确认 1.0.0：

- 不要把它写成已正式定稿；
- 保持 Unreleased；
- 修复完成、Dogfood、用户确认后再一次性定版本。

如果 Git 中已有真实 tag/release，则先核实，不要猜。

另外“89项测试全绿”不要作为跨环境永久事实；最多写“当次基线环境验证通过”。

---

# 25. `docs/GOVERNANCE_RULES.md`

同步本轮真实规则：

- Code Start在写边界强制；
- Research按当前 requirement；
- Frontend approval不可override；
- `input/`只读；
- `output/` final write允许；
- Worktree cleanup必须真实merge；
- disposable worktree必须登记+Git真实存在；
- 无 Workflow/OCI/Evidence runtime。

---

# 26. `docs/WORKTREE.md`

状态改为：

```text
prepare -> active
finish -> ready
Codex/Git -> review + merge
cleanup -> 验证 target包含 branch tip -> 删除
```

明确：

```text
finish != merged
```

不要重新加入：

- integration branch runtime；
- G4；
- DAG；
- join barrier；
- scheduler。

---

# 27. `docs/MEMORY.md`

补 candidate 闭环：

```text
submit
-> main review
-> accept/reject
-> accept写 JSONL
-> reindex
-> 删除 candidate
```

未处理 candidate在 Finish提示，不长期累积。

---

# 28. `docs/API_SPEC.md`

同步公共接口变化：

- `governance_check` 不接受 approval/research布尔绕过；
- `worktree_manage cleanup` 不提供普通 force；
- Memory candidate accept/reject说明；
- MCP继续≤8。

---

# 29. `docs/DATABASE.md`

只描述实际轻量表。

若 worktrees 增加 target branch/head commit，只补这些字段。

禁止恢复审计数据库设计。

---

# 30. `src/codex_ai_os/templates/project_docs.py`

### Open Source Research模板

模板可以有：

```text
Decision
decision:
reason:
```

但空值绝不能通过 Gate。

### Frontend

不要因为项目含 frontend 就提前生成“假批准”的 UI_SPEC。

真正进入新 UI需求时才生成/更新 Prototype + UI_SPEC。

### 文档数量

不增加新的模板文档。

---

# 31. `src/codex_ai_os/application/repository.py`

## 补 `.gitignore` 最小合规检查

至少确认语义覆盖：

```text
__pycache__
*.pyc
.pytest_cache
.ruff_cache
.venv
node_modules
build
dist
*.log
.codex-os/state
.codex-os/logs
.codex-os/cache
.codex-os/tmp
.codex-os/artifacts
.worktrees
```

允许等价 pattern。

不要做复杂 gitignore parser。

## 用户未提交修改冲突

原则继续保持：

> 用户正常未提交工作不因为 dirty status 就全局阻塞。

但如果当前任务声明将修改：

```text
src/auth.py
```

而用户也有未提交：

```text
src/auth.py
```

应：

- 用 Worktree隔离；
- 或请求确认；
- 不能静默覆盖。

不要实现自动 dependency planner。

---

# 32. 新增或补充 `src/codex_ai_os/core/checks.py`

如果当前不存在，可以新增，但必须极薄。

只允许：

```text
targeted test command
ruff
git diff --check
repository hygiene
incremental detect-secrets
必要时 typecheck
```

### 禁止

不得出现：

- ExecutionService；
- execution ID；
- command hash；
- Evidence DB；
- artifacts hash；
- retry state machine；
- OCI runner；
- SBOM；
- dependency audit；
- Verification Cache。

## Finish

逐步淘汰：

```text
tests_passed=True
docs_synced=True
```

这种纯自我声明。

AIOS至少应真实运行/读取最小 check exit code。

不要让 AIOS猜不同语言如何测试；targeted test命令可以由 Codex/项目配置提供。

---

# 33. `src/codex_ai_os/cli/app.py`

## Finish接口

减少 `--tests-passed`、`--docs-synced` 这种自证。

改为运行最薄真实检查。

## Memory

增加同一 `memory` 顶层命令下：

```text
candidate accept
candidate reject
```

不需要新增顶级CLI命令。

## Worktree

删除普通 cleanup的 `--force`，或限制为明确人工危险模式。

## 版本

本轮不要自动 bump。

---

# 34. `pyproject.toml`

当前：

```toml
version = "1.0.0"
```

但 CHANGELOG语义冲突。

本轮先修功能，不创造新版本。

用户最终确认后一次同步：

```text
pyproject
plugin metadata
CHANGELOG
Git tag
```

### 依赖

Runtime：

```text
mcp
pydantic
pyyaml
typer
```

目前合理。

Dev：

```text
pytest
ruff
pyright
detect-secrets
```

合理。

`pytest-cov` 如果只是观察 coverage可保留，但不得恢复硬 fail_under。

`hatchling` 是构建系统依赖，不必为了“减重”机械删除。

---

# 35. Plugin Skills

当前 8 个数量合理，不再增加：

```text
document-impact
finish-checklist
frontend-design-review
governance-entry
html-prototype
memory-protocol
open-source-research
worktree-protocol
```

逐个搜索并清掉作为现行流程的旧词：

```text
G0/G1/G2/G3/G4
Evidence Bundle
Workflow Runtime
Execution Manager
OCI-first
Release Candidate
Task DAG
```

如果只是说明“这些已被废弃”可以出现。

`html-prototype` 可保留，因为直接服务“前端先原型”。

---

# 36. 测试按文件修复

不要追求测试数量，补高价值正反案例。

## `tests/unit/test_gates.py`

新增：

```text
空 Research模板 -> DENY
只有Decision标题 -> DENY
reason为空 -> DENY
requirement mismatch -> DENY
当前requirement完整 -> ALLOW
bugfix/typo/test-only -> Research豁免
Frontend不能approved=true绕过
```

## `tests/unit/test_authorization.py`

删除旧：

- Workflow transition；
- OCI policy；
- RoleBoundary。

新增：

```text
input write deny
output final write allow
normal pip/npm/build allow
main destructive command deny
trusted worktree cleanup allow
fake .worktrees 不放权
```

## `tests/unit/test_hook_gateway.py`

新增：

```text
无GitHub + 正式src写入 -> DENY
无GitHub + docs写入 -> ALLOW
有GitHub + Research满足 -> 正式写入 ALLOW
input写 -> DENY
output最终交付写 -> ALLOW
```

## `tests/integration/test_plugin_hooks.py`

新增：

```text
fake .worktrees
registered real worktree
tempfile.gettempdir()
Linux/macOS/Windows temp
normal pip/npm/build
Code Start enforcement
memory single writer
```

## `tests/unit/test_worktree.py`

新增：

```text
finish -> ready
未merge cleanup -> DENY
merge后 cleanup -> ALLOW
dirty cleanup -> DENY
未合并commit不能force丢失
DB/Git状态不一致 -> DENY
```

## `tests/integration/test_memory_store.py`

新增：

```text
candidate submit
accept
JSONL append
reindex
candidate delete
reject cleanup
worktree cwd candidate submit
子Agent不能直接写JSONL
```

## `tests/unit/test_repository.py`

新增：

```text
gitignore最小规则
等价pattern
input合法
output污染
src_v2 block
api/v1 allow
用户正常dirty不全局阻塞
declared write path与用户dirty冲突
```

## `tests/unit/test_agent_profiles.py`

如果删除 `.codex/agents/`：

**这个测试直接删除。**

不要继续为了旧岗位体系强制 Profile存在。

## `tests/unit/test_config.py`

删除：

```text
active_workflow
OCI
environment_mode
default_agent_profile
ExecutionPolicy
```

相关测试。

## `tests/unit/test_doctor.py`

跨平台测试不要依赖审计机器恰好是Python 3.12。

如果正式包仍要求 `>=3.12,<3.13`，通过 mock版本或目标CI验证。

---

# 37. 最终仓库物理清理

本轮必须实际删除，不只是 gitignore：

```text
.codex-os/gates/
.codex-os/artifacts/
.codex-os/logs/
.codex-os/state/backups/
.codex-os/tmp/
.codex-os/environment.yaml
.codex-os/execution-policy.yaml
.codex-os/test-traceability.yaml

所有 __pycache__/
所有 *.pyc
.pytest_cache/
.ruff_cache/
```

保留：

```text
.codex-os/project.yaml
```

本地运行时可存在但必须ignore：

```text
.codex-os/state/state.db
.codex-os/context/PROJECT_CONTEXT.md
```

---

# 38. 本轮明确禁止重新引入

修复过程中不得再次增加：

```text
Workflow Engine
G0-G4
阶段状态迁移
Evidence Bundle
ExecutionService
Host Operation
OCI Runtime
SBOM
Trivy
Verification Cache
Release Runtime
Release Candidate
Agent Scheduler
Task DAG
Task Group
Integration Branch Runtime
复杂 Approval Engine
复杂 Research Classifier
复杂 Gitignore Parser
Memory Workflow Engine
Candidate 状态机
```

如果 Codex认为必须新增其中某项，先停止实施，说明：

1. 它具体解决本清单哪个问题？
2. 为什么 Git/Codex/SQLite/简单函数无法解决？
3. 预计新增多少代码/状态？
4. 是否会限制 Codex 原生能力？

未经用户确认不得引入。

---

# 39. 建议提交拆分

不要做一个巨型commit。

建议：

```text
fix(gates): enforce code-start and requirement-scoped research
fix(frontend): make approvals durable and non-bypassable
fix(worktree): verify merge before cleanup
refactor(auth): remove role workflow and OCI remnants
fix(memory): complete candidate consume flow
refactor(config): remove obsolete workflow and execution settings
chore(repo): purge legacy runtime artifacts and caches
docs(governance): remove superseded runtime facts
test(governance): cover hard gates and allow-path regressions
```

可以按实际依赖适度合并，但每个commit保持逻辑完整。

---

# 40. 完成验收

## Gate

- [ ] 无 GitHub 时直接写正式源码真正被 Hook 阻止
- [ ] 无 GitHub 时仍可分析/Research/文档
- [ ] 空 Research不能通过
- [ ] 旧 Research不能解锁新需求
- [ ] Research豁免正常
- [ ] Frontend不能通过参数伪造批准
- [ ] UI批准有Git长期事实

## Codex自由度

- [ ] input只读
- [ ] output最终交付可写
- [ ] pip/npm/pnpm/yarn/cargo/build/test正常
- [ ] 正常Git正常
- [ ] 正常文件编辑正常

## Worktree

- [ ] fake `.worktrees` 不放权
- [ ] trusted Worktree要求DB登记+Git真实存在
- [ ] finish=ready
- [ ] 未merge不能cleanup
- [ ] merge后可cleanup
- [ ] 不会force丢失未合并代码
- [ ] 无orphan worktree

## 架构残留

- [ ] 无Workflow Engine语义
- [ ] 无OCI Runtime语义
- [ ] 无backend-engineer硬编码
- [ ] 无旧Profile/失效Skill引用
- [ ] 无G0-G4/Evidence现行流程引用

## Memory

- [ ] Worktree可提交candidate
- [ ] main可accept/reject
- [ ] accept写JSONL+reindex
- [ ] 已处理candidate删除
- [ ] 不长期积累candidate垃圾

## Config/仓库

- [ ] `active_workflow`删除
- [ ] `environment_mode/OCI_FIRST`删除
- [ ] `default_agent_profile`删除
- [ ] `.codex-os`旧gates/logs/artifacts/backups/tmp清理
- [ ] pycache/pytest_cache/ruff_cache清理

## Docs

- [ ] 旧UI_SPEC删除
- [ ] 冲突ADR清理
- [ ] CHANGELOG版本语义一致
- [ ] Governance/Worktree/Memory/API与代码一致

## Testing

- [ ] 重点正例和负例覆盖
- [ ] 不恢复17项Verification
- [ ] 不恢复Evidence
- [ ] 不重复跑测试只为“证据”
- [ ] Linux/macOS temp识别通过

---

# 41. 最终成功标准

本轮修复完成后，不用“代码行数、测试数量、文档数量”证明成功。

只回答三个问题：

### A. 七个核心治理规则是否真正有效，而不是依赖 Codex 自觉？

### B. Codex 的正常专业能力是否没有被 AIOS 误伤？

### C. 修复后 AIOS 是否仍然比旧系统更轻，没有重新长出 Runtime 平台？

最终应达到：

```text
Codex 自由完成专业工程工作
          +
AIOS 在少数关键边界自动约束
          =
Codex 更规范，而不是更笨
```

这就是本轮唯一目标。
