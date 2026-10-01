# 治理规则

## 三 Gate（无状态评估器）

评估器位于 `src/codex_ai_os/core/gates.py`，同输入同输出，不持有隐藏状态。

- **Code Start**（`governance_check(stage="start")`）：GitHub remote 存在且可达（精确识别 github.com 与 GitHub 官方 SSH endpoint ssh.github.com，后者支持 ssh:// 的 443 端口；不接受相似域名或通配符，仍对原始 origin 执行 ls-remote）；"脏乱"精确判定——只有复制式目录/文件、被跟踪的污染内容、未解决冲突才阻塞，用户自己的未提交工作不算脏乱；开源调研分层适用，调研文档必须以 requirement_id 开头并给出 summary、scope（行内列表或块列表，至少一项）、updated_at（YYYY-MM-DD）与 Decision/reason（无布尔绕过）。无 GitHub 时允许读 input/、分析、调研、规划、文档；禁止正式 src/ 实现。
- **Frontend Approval**（`stage="frontend"`）：new_page / new_interaction_flow / major_ui_refactor 需要原型、UI_SPEC 和匹配 scope、原型摘要、规格正文摘要的批准块。copy_change / css_fix / component_bugfix 豁免。批准和拒绝均写入文档；拒绝撤销原批准，设计变更或旧块无摘要时要求用户重新确认，不自动补签。
- **Finish**（`stage="finish"`）：必须提供任务开始时保留在 Codex 原生上下文中的 `base_ref`；缺失返回 FINISH_BASE_REQUIRED，不回退当前 HEAD。初始空仓库明确使用 EMPTY_TREE。基线以来的已提交、已暂存、未暂存、未跟踪改动全部参与 code_paths 判断（含中文与重命名的 NUL 路径解析）。正式代码变更要求 change_class，研究类另需 requirement_id，并按配置中的 GitHub 主机复核 Code Start。空白检查覆盖 committed/staged/unstaged。声明的 test_command 失败阻塞，未声明显示 TEST_COMMAND_SKIPPED；已配置但缺失的 Ruff 阻塞，不能把未运行称为通过。另检查卫生、一次性文件和未处理 candidate 提醒。文档一致性由 Codex 原生 review，不接受 tests_passed/docs_synced 自证参数。

不可确定性观察的检查（如"需求范围已明确"）是 AGENTS.md 的过程纪律，不进运行时。

## 默认验证

默认验证 ≤5 项：目标测试、ruff、`git diff --check`、仓库卫生（`codex-os check`）、必要时 pyright。每个逻辑变更还须通过仓库 Secret Scan：提交前运行 `python scripts/secret_scan_incremental.py --staged` 检查 Git 索引中的实际提交内容；显式文件缺失、无法读取或扫描失败均失败，不输出有效通过。

## 实现边界

- Python 3.12 + uv.lock 锁定依赖；Gate/审批/SQLite 全部自研自持，无第二模型客户端。
- 设计护栏默认保持轻量：MCP 工具/CLI 命令/活跃文档/Skills/Gate/SQLite 表数量保持现状，新增能力必须先证明必要性并经人工 review，失效能力及时删除；只做人工对照，不写运行时检测代码。
- 不做：strict assurance Profile、SBOM、镜像扫描、dependency audit、Verification Cache、Release 发布器、Host Operation lease、每命令 Evidence、自有 Agent/Tool Runtime、DAG 调度、自研 Secret 引擎、复杂审批系统、复杂 Research 系统、复杂 Memory 状态机。

## 路径策略

- 受保护路径（治理通道内禁写）：`input/**`、`.git/**`、`.codex-os/state/**`、`**.env`、`**/credentials/**`。
- 治理规则路径（一律禁写）：`AGENTS.md`、`.codex-os/project.yaml`、`plugins/ai-engineering-os/**`。
- `input/` 是受保护的用户输入目录，不是禁止目录；扫描副本式脏乱时跳过 input/。
- `output/` 不是禁写目录：它是最终交付物目录，其纯净（无缓存/日志/副本）由 Finish 与仓库卫生检查判定。

## Hook 语义（保护用户资产，而非禁止专家工具）

- 无条件拦截：force push、删远端 ref、update-ref -d、compose down -v、volume rm/prune、对根/家目录递归强删。
- 局部 Git 操作：`reset --hard`、`checkout --`、`clean -f`、`branch -D` 仅在登记且与 Git 实际清单一致的 disposable checkout 中具备局部放行条件；`branch -d` 不再被当作 `-D`。切换 cwd 或指定 Git -C 不会继承原位置权限；无法可靠解析的上下文拒绝并说明原因。
- 文件清理：Codex 根据任务上下文确认归属和用户授权；AIOS 检查精确、可解析目标。仅系统临时目录或 checkout 的 build/dist/.codex-os/tmp 下具体叶目标可进入自动检查，整个这些根、盘符根、家目录、仓库根、input/.git/output、跟踪文件、链接/junction 和含受保护子项均拒绝；“未跟踪”不构成删除授权。不建立任务凭证系统。复杂表达式或变量目标返回缺少的证据，不因 cwd 位于临时区就放行。
- Memory 单写者：disposable worktree 内禁写 `docs/memory/`，只允许提交 candidate。
- pip/npm/pnpm/yarn/poetry/cargo/sed -i 等正常工程命令全面放行。
- CLI、MCP、SessionStart、PreToolUse 共用根解析。逐目标确定治理项目，子目录、登记 Worktree、绝对/中文路径及 apply_patch 的 Update File + Move to 源/目标均受保护。明确但无法解析的 Shell 写入拒绝；间接生成的结果由 Finish 完整差异复核。
- 正常 Hook 只输出空对象或官方 deny/context 协议，不输出不支持的 ask，不把所有脏文件认作用户修改。Runtime 缺失/超时/异常/无效 JSON 时，明确写入或破坏操作返回带规则编号的拒绝，非敏感操作只提示未完成检查。外层 15 秒、Runtime 10 秒、一次请求网络预算最多 5 秒；没有第二套完整离线规则。
- `authorize-hook --explain` 为只读诊断：AIOS 规则编号、目标、原因、建议；绝不执行传入命令，也不代表宿主授权。宿主可独立拒绝执行或禁用 Hook。遇到宿主拒绝不得改 cwd、Shell、语言绕过；缺少具体宿主规则时如实说明未知。

## 规则优先级

1. 用户当前明确要求 → 2. AGENTS.md / 硬治理规则 → 3. 已确认项目事实 → 4. 任务上下文 → 5. AIOS 建议。用户要求破坏事实或绕过安全规则时，指出冲突并请求确认，不静默执行。
