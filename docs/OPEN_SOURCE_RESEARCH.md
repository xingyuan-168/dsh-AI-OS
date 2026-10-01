# Open Source Research

## Requirement

requirement_id: REQ-DSH-2.0
summary: 把治理层从 Codex 宿主迁移到 DeepSeek Harness 宿主：用 DSH Cordis 插件提供强制点，替换全部 Codex 专用清单与命名，并让治理对所有项目默认生效。
scope:
  - host-integration
  - enforcement-layer
  - naming-and-migration
updated_at: 2026-10-01

## Candidates

### @deepseek-ai/dsh-* 插件契约（Cordis 事件与服务）

- URL: 本机 DSH 安装（profile bundle 层 `@deepseek-ai/dsh-base` / `@deepseek-ai/dsh-web-app`）
- License: 随宿主分发
- 解决什么：提供宿主原生强制点——waterfall `tools/pre-execute`（放行/拒绝/取消/询问）、`fs/write-intent`、`fs/edit-intent`（写入时刻裁决）、serial `agent/created`、`system-prompt/assemble`；服务 `tools.register/guard`、`skills.registerProvider`、`systemPrompt.section`、`commands.register`。
- 可直接复用：是——宿主扩展点本身即集成面，无需自研注入机制。
- 可二开：是——插件以 npm 包形式装进 profile 的补丁层。
- 值得学习：把"裁决"与"执行"分离的 waterfall 语义；写入时刻（write-intent）在 Codex 侧并不存在。
- 风险：插件契约属于宿主版本面（当前 0.2.0-rc.2），升级可能变更签名；必须以 fail-closed 兜底。

### @deepseek-ai/dsh-experimental-auto-review

- 描述：Per-tool LLM authorization review for the DeepSeek Harness Auto permission preset。
- 解决什么：按工具做 LLM 授权复核，缓解"自动放行"预设的风险。
- 可直接复用：否——治理必须是确定性、可复现、可审计的（同输入同输出、给出规则编号）；LLM 裁决不可复现，也无法表达"GitHub remote 不可达即阻塞"这类不变量。
- 值得学习：工具级复核的粒度选择；我们采用同一粒度但用确定性内核。
- 风险：把治理判定交给模型，等于把安全性建立在概率上；且它是 Auto 权限预设的配套组件，不是独立治理层。

### @deepseek-ai/dsh-permission-presets 与 sandbox 能力

- 解决什么：用户可选权限预设（审批模式 / 沙箱范围），是宿主侧的安全边界。
- 可直接复用：否——预设由用户选择、可由用户放宽，且不感知项目治理事实（GitHub 前置、调研分层、前端批准、Worktree 登记）。
- 值得学习：边界分层思路；我们据此确立 Tier 0/1/2：宿主预设负责"运行时安全"，AIOS 负责"工程治理不变量"，两者互补且互不冒充。
- 风险：若把治理塞进用户可关的预设，就会出现"关掉预设即无治理"，违背本项目目标。

### 保留 Codex 形态（.codex/hooks.json、plugin.json、MCP 声明）

- 解决什么：无需改动即可继续工作。
- 可直接复用：否——DSH 不加载 `.codex/` 清单，也不读取 `${PLUGIN_ROOT}` 与 `hookSpecificOutput` 协议；保留只会留下"看起来有治理、实际无强制"的假象。
- 风险：最高——静默失效。已否决。

### 内核全量重写为 TypeScript 插件

- 解决什么：消除 Python 运行时依赖。
- 可直接复用：否——等于重写三 Gate、授权内核、SQLite、Memory、Worktree 与全部回归测试。
- 风险：与 ADR-0016 的轻量护栏正面冲突，且丢失既有测试覆盖。已否决。

## Decision

decision: build
reason: 采用"薄适配层 + 既有确定性内核"：DSH 插件只做宿主事件→内核请求的转发与 fail-closed 兜底，三 Gate、授权内核、路径策略、SQLite、Memory、Worktree 全部沿用既有实现与测试，不新增第二套离线规则，也不引入第二运行时。`use` 仅用于宿主插件契约本身（Cordis 事件与服务）与已记录的 detect-secrets 轻依赖；LLM 复核与权限预设明确不作为治理判定来源。
