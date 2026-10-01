<!-- aios-document: {"schema_version":"1.3","document_version":"1.0.0","status":"accepted","owner":"architect","requirement_refs":["REQ-DSH-2.0"]} -->

# ADR-0018：DSH 宿主迁移与全局强制模型

## 状态

Accepted（取代此前以 Codex 宿主为前提的集成假设；不改变 ADR-0016 的轻量边界与 ADR-0017 的失败语义）。

## 上下文

治理层此前是为 Codex 定制的：强制力来自 `.codex/hooks.json` 的 SessionStart / PreToolUse 清单、`.codex-plugin/plugin.json` 的插件注册，以及 `.mcp.json` 声明的 MCP 工具面。本机实际宿主是 DeepSeek Harness，它**不加载**这些清单，也不理解 `${PLUGIN_ROOT}` / `hookSpecificOutput` / `permissionDecision` 协议。结果是治理文档仍在，但强制点全部失效——这是"看起来有治理、实际无强制"的状态。

DSH 提供的原生强制点是 Cordis 事件与服务：

- waterfall `tools/pre-execute`：允许 / 拒绝 / 取消 / 询问，覆盖**全部**工具（Codex 侧只能靠 matcher 枚举 4 类）。
- waterfall `fs/write-intent` 与 `fs/edit-intent`：单槽**写意图**决策，决定写入的期望版本，**不能拒绝任何操作**。Codex 侧没有等价物，但它也不能当强制点使用——能观测不等于能拒绝。
- serial `agent/created` 与 waterfall `system-prompt/assemble`：会话建立时注入宪法与当前 Gate 状态。
- 服务：`tools.register/guard`、`skills.registerProvider`、`systemPrompt.section/context`、`commands.register`。

同时用户要求治理对**所有项目**默认生效，而不是仅在显式初始化的仓库里生效。

## 选项

- **A. 保留 Codex 形态**：不满足任何新需求，且治理静默失效。否决。
- **B. 内核全量重写为 TypeScript 插件**：消除 Python 依赖，但等于重写 35 个模块与全部回归测试，与 ADR-0016 的轻量护栏正面冲突，并丢失既有测试覆盖。否决。
- **C. 薄适配层：DSH Cordis 插件 + 既有 Python 内核**：插件只做"宿主事件 → 内核请求"的规范化与转发，裁决仍由唯一确定性内核给出。选中。
- **D. 只改文档与设置、不做宿主强制**：无法保证"所有项目必须执行"，退化为自律。否决。

## 决定

1. **采用 C**：新增 DSH Cordis 插件（`plugins/ai-engineering-os/`），监听 `tools/pre-execute`（唯一可拒绝的派发前裁决点，覆盖全部工具）与 `agent/created`（会话建立），并注册 8 个原生工具、人工命令与 1 个 Skill Provider。`fs/write-intent` / `fs/edit-intent` 不能拒绝操作，故不注册；内核仍接受这两类载荷以便诊断。插件通过 `aios` CLI 以 stdin JSON 调用内核，内核缺失/超时/异常/无效响应时按 fail-closed 处理：变更类操作拒绝并给出规则编号，只读操作仅提示检查不可用。
2. **不新增第二套离线规则**：DSH 载荷经 `application/dsh_gateway.py` 规范化为内核既有请求类型，`authorization.py` / `governance_policy.py` / `cleanup_policy.py` / `core/gates.py` 保持不变。
3. **三层强制模型**：
   - Tier 0 基线：任何工作区恒定开启，项目配置不可关闭（用户资产保护、受保护路径、Memory 单写者）。
   - Tier 1 已治理项目：存在 `.aios/project.yaml` 时在写入时刻强制三 Gate。
   - Tier 2 全局严格模式：`~/.dsh/aios.yaml` 的 `strict: true`（默认）使未初始化项目同样套用 Tier 1；插件在内存中物化确定性默认配置，**不静默写盘**。
4. **全量重命名**：`codex_ai_os`→`aios`、`codex-os`→`aios`、`.codex-os/`→`.aios/`、`codex/wt-`→`aios/wt-`、文档标记 `codex-os-document`→`aios-document`。
5. **提供自动迁移**：检测 `.codex-os/project.yaml` 后，走 ADR-0017 既有机制——SQLite 一致性备份 + SHA-256 sidecar，移动（非复制）配置与运行库到 `.aios/`，升级 `schema_version` 到 1.3；未知结构、忙库、活动 Worktree 一律拒绝且不重建。既有 `codex/wt-*` 登记行继续被判为合法，仅新建使用新前缀。

## 后果

- **正面**：治理在真实宿主上重新具备强制力，且覆盖全部工具与写入时刻；Codex 专用清单与命名清零；所有项目默认受基线约束。
- **负面**：插件依赖宿主插件契约（当前 0.2.0-rc.2），宿主升级可能变更事件签名，需要回归；`aios` CLI 必须在 PATH 上，否则插件进入 fail-closed（安全但会阻塞写入）；未初始化项目在严格模式下会被要求先满足 Code Start，需用 `aios init` 记录项目事实。
- **不可逆性**：重命名为破坏性变更（导入路径与控制台命令），旧调用方需同步迁移。
- **复核条件**：宿主插件契约发生 BREAKING 变更、或 `tools/pre-execute` / `agent/created` / `system-prompt/assemble` 语义变化时，重新评估本 ADR。

## 关联

- ADR-0011：授权内核与三层强制模型——内核仍是唯一裁决点，本 ADR 只替换宿主侧信道。
- ADR-0016：轻量边界不变，治理不新增 Agent/Tool 运行时。
- ADR-0017：迁移与失败语义不变，自动迁移复用其备份与拒绝规则。
