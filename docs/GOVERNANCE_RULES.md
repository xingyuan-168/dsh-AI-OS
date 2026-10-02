# 治理规则

## 三 Gate（无状态评估器）

评估器位于 `src/aios/core/gates.py`，同输入同输出，不持有隐藏状态。

- **Code Start**（`governance_check(stage="start")`）：GitHub remote 存在且可达（精确识别 github.com 与 GitHub 官方 SSH endpoint ssh.github.com，后者支持 ssh:// 的 443 端口；不接受相似域名或通配符，仍对原始 origin 执行 ls-remote）；"脏乱"精确判定——只有复制式目录/文件、被跟踪的污染内容、未解决冲突才阻塞，用户自己的未提交工作不算脏乱；开源调研分层适用，调研文档必须以 requirement_id 开头并给出 summary、scope（行内列表或块列表，至少一项）、updated_at（YYYY-MM-DD）与 Decision/reason（无布尔绕过）。调研文档按需求逐次替换 Requirement 块：旧 requirement 永远不解锁新需求。无 GitHub 时允许读 input/、分析、调研、规划、文档；禁止正式 src/ 实现。
- **Frontend Approval**（`stage="frontend"`）：new_page / new_interaction_flow / major_ui_refactor 需要原型、UI_SPEC 和匹配 scope、原型摘要、规格正文摘要的批准块。copy_change / css_fix / component_bugfix 豁免。批准和拒绝均写入文档；拒绝撤销原批准，设计变更或旧块无摘要时要求用户重新确认，不自动补签。
- **Finish**（`stage="finish"`）：必须提供任务开始时保留在 DSH 原生上下文中的 `base_ref`；缺失返回 FINISH_BASE_REQUIRED，不回退当前 HEAD。初始空仓库明确使用 EMPTY_TREE。基线以来的已提交、已暂存、未暂存、未跟踪改动全部参与 code_paths 判断（含中文与重命名的 NUL 路径解析）。正式代码变更要求 change_class，研究类另需 requirement_id，并按配置中的 GitHub 主机复核 Code Start。空白检查覆盖 committed/staged/unstaged。声明的 test_command 失败阻塞，未声明显示 TEST_COMMAND_SKIPPED；已配置但缺失的 Ruff 阻塞，不能把未运行称为通过。另检查卫生、一次性文件和未处理 candidate 提醒。文档一致性由 DSH 原生 review，不接受 tests_passed/docs_synced 自证参数。

不可确定性观察的检查（如"需求范围已明确"）是 AGENTS.md 的过程纪律，不进运行时。

## 默认验证

默认验证 ≤5 项：目标测试、ruff、`git diff --check`、仓库卫生（`aios check`）、必要时 pyright。每个逻辑变更还须通过仓库 Secret Scan：提交前运行 `python scripts/secret_scan_incremental.py --staged` 检查 Git 索引中的实际提交内容；显式文件缺失、无法读取或扫描失败均失败，不输出有效通过。

## 实现边界

- Python 3.12 + uv.lock 锁定依赖；Gate/审批/SQLite 全部自研自持，无第二模型客户端。DSH 插件层只做事件转发与 fail-closed 兜底，不持有判定逻辑。
- 设计护栏默认保持轻量：DSH 工具/CLI 命令/活跃文档/Skills/Gate/SQLite 表数量保持现状，新增能力必须先证明必要性并经人工 review，失效能力及时删除；只做人工对照，不写运行时检测代码。
- 不做：strict assurance Profile、SBOM、镜像扫描、dependency audit、Verification Cache、Release 发布器、Host Operation lease、每命令 Evidence、自有 Agent/Tool Runtime、DAG 调度、自研 Secret 引擎、复杂审批系统、复杂 Research 系统、复杂 Memory 状态机。

## 路径策略

- 受保护路径（治理通道内禁写）：`input/**`、`.git/**`、`.aios/state/**`、`**.env`、`**/credentials/**`。
- 治理规则路径（一律禁写）：`AGENTS.md`、`.aios/project.yaml`、`plugins/ai-engineering-os/**`。
- `input/` 是受保护的用户输入目录，不是禁止目录；扫描副本式脏乱时跳过 input/。
- `output/` 不是禁写目录：它是最终交付物目录，其纯净（无缓存/日志/副本）由 Finish 与仓库卫生检查判定。

## DSH 事件语义（保护用户资产，而非禁止专家工具）

插件把宿主事件规范化为内核请求，判定仍由唯一确定性内核给出。事件到规则编号的对应关系：

| DSH 事件 | 触发时机 | 处理 |
| --- | --- | --- |
| `tools/pre-execute` | 任意工具调用前 | 返回 deny 或放行；**唯一可拒绝的派发前裁决点**，覆盖全部工具，不按工具名枚举 |
| `agent/created` + `systemPrompt.section` | 会话建立 | 注入宪法与当前 Gate 状态 |
| `tools/execute` / `tools/post-execute` | 执行期与结果期 | 观测，不改变裁决 |

`fs/write-intent` 与 `fs/edit-intent` 是**单槽写意图决策**（决定写入的期望版本），不能拒绝任何操作，因此插件不注册它们——在那里挂监听会看起来像写入时刻保护，实际提供不了。插件接受这两类载荷仅用于诊断与未来宿主版本。

- 无条件拦截：force push、删远端 ref、update-ref -d、compose down -v、volume rm/prune、对根/家目录递归强删。
- 局部 Git 操作：`reset --hard`、`checkout --`、`clean -f`、`branch -D` 仅在登记且与 Git 实际清单一致的 disposable checkout 中具备局部放行条件；`branch -d` 不再被当作 `-D`。切换 cwd 或指定 Git -C 不会继承原位置权限；无法可靠解析的上下文拒绝并说明原因。
- 文件清理：DSH 会话根据任务上下文确认归属和用户授权；AIOS 检查精确、可解析目标。仅系统临时目录或 checkout 的 build/dist/.aios/tmp 下具体叶目标可进入自动检查，整个这些根、盘符根、家目录、仓库根、input/.git/output、跟踪文件、链接/junction 和含受保护子项均拒绝；"未跟踪"不构成删除授权。不建立任务凭证系统。复杂表达式或变量目标返回缺少的证据，不因 cwd 位于临时区就放行。
- Memory 单写者：disposable worktree 内禁写 `docs/memory/`，只允许提交 candidate。
- pip/npm/pnpm/yarn/poetry/cargo/sed -i 等正常工程命令全面放行。
- CLI、DSH 插件、工具面共用根解析。逐目标确定治理项目，子目录、登记 Worktree、绝对/中文路径及写意图中的源/目标均受保护。明确但无法解析的目标拒绝；间接生成的结果由 Finish 完整差异复核。
- 插件只返回宿主支持的裁决（deny / 放行），不输出宿主不支持的语义，也不把所有脏文件认作用户修改。内核缺失/超时/异常/无效 JSON 时，明确写入或破坏操作返回带规则编号的拒绝，非敏感操作只提示未完成检查。外层 15 秒、内核 10 秒、一次请求网络预算最多 5 秒；没有第二套完整离线规则。
- `aios authorize-dsh` 为只读诊断：输入 DSH 载荷，输出 AIOS 规则编号、目标、原因、建议；绝不执行传入操作，也不代表宿主授权。载荷无法读取时非零退出，插件据此对变更类操作失败封闭。DSH 宿主可独立拒绝执行或禁用插件。遇到宿主拒绝不得改 cwd、Shell、语言绕过；缺少具体宿主规则时如实说明未知。

## 安装与强制

本包是一个 **DSH bundle**：一个携带配置层的 npm 包。官方对 bundle 与 profile 的分工很明确——**作者产出 bundle，用户启动 profile，没有东西同时是两者**（[打包与安装插件](https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/publish.md)）。

### 三个文件

```
plugins/ai-engineering-os/
├── package.json       # 声明 dsh.bundle.patch
├── cordis.patch.yml   # profile 列出该 bundle 时应用的层
└── src/index.js       # 插件入口（patch 行按包名引用到它）
```

- `package.json` 必须有 `"dsh": { "bundle": { "patch": "./cordis.patch.yml" } }`，且 **`files` 必须包含该 patch 文件**（官方点名的最常见漏项：漏了它，包能装上但配置层不会被挂载）。
- 包内 patch 用 **insert** 语法插入自己的行：
  ```yaml
  - insert:
      - id: ai-engineering-os
        name: ai-engineering-os
        config: { strict: true, kernelCommand: aios, timeoutMs: 10000, failMode: closed }
  ```
  覆盖式条目（`- id / name / config`）只按 id 命中**已存在**的行；用它新增行会静默匹配不到，什么都不发生。

### 安装

`plugin_manager install_bundle` 以本地路径 spec 安装：

- `file:<repo>/plugins/ai-engineering-os`：pnpm 把目录**复制**进 `node_modules`，改了源码要删掉副本重装才会同步。
- `link:<repo>/plugins/ai-engineering-os`：pnpm 建**符号链接**，源码即装即用。推荐开发时用这个。

成功时管理器会把依赖与 bundle 名写进 profile：`dependencies` 加一项、`dsh.profile.bundles` 追加 `ai-engineering-os`。若返回 `not-bundle`，就是 `dsh.bundle` 没被识别。

### 层顺序与覆盖

生效配置按顺序合成：**各 bundle 的 patch（按 `dsh.profile.bundles` 顺序）→ profile 自己的 `cordis.patch.yml` → `$DSH_HOME/cordis.patch.yml` → 各 `--patch` 覆盖层**，越靠后越优先。补丁按行**整行替换** `config`，不做深合并——所以在 profile 里覆盖本插件那一行时，必须重述该行需要的每个 key。

### 激活与验证

- 运行中的宿主可以按条目 id 重新应用：`plugin_manager set_plugin(target="include:ai-engineering-os")`（注意是 `include:` 前缀的 entryId，用包名会得到 `unknown-plugin`）。
- 但**重载会复用已缓存的旧模块**：改完 `src/*.js` 后靠重载不会读到新代码（实测：错误堆栈仍指向改动前的行号）。**改插件源码后必须重启 DSH**。
- 激活与否的证据强度不同，必须分开陈述：`aios doctor` 的 `plugin-manifest` 只证明包在磁盘上、`dsh-profile` 只证明 profile 声明了它（两者都返回 `ok: null`）；`plugin_manager list_plugins` 证明条目在 Loader 树里；真正的强制只由**新会话的实际行为**证明。
- 源码验证不等于已安装，安装不等于已加载，加载不等于宿主未禁用。

### 排障

| 现象 | 处置 |
| --- | --- |
| 条目数没变化 | `dsh.bundle` 或包内 `cordis.patch.yml` 没被识别：核对键名与 `files` 是否包含该文件 |
| `install_bundle` 返回 `not-bundle` | 同上；另外 profile 里可能残留上一轮的**旧副本**，删掉 `node_modules/ai-engineering-os` 再装 |
| `set_plugin` 用包名报 `unknown-plugin` | 改用 `include:<rowId>` 形式寻址 |
| 插件 active，但整轮请求失败：`Invalid schema for function ...: schema must be a JSON Schema of 'type: "object"', got 'type: null'` | 工具的 `parameters` 被原样发给模型，必须是 JSON Schema（根为 `type: "object"`）；传 reference 的"按键 DSL"会得到 `type: null`。用 `toParameterSchema()` 转换：定义按键书写，注册前生成 `{ type: 'object', properties, required[] }` |
| `fiberPhase: failed`，报错含 `cannot get property "X" without inject` | 插件读了没在 `inject` 里声明的服务：Cordis 上下文是**抛错代理**，"先探测再使用"的写法本身就失败。把该服务加进 `inject`（基础 profile 由 `@deepseek-ai/dsh-base` 提供 `tools`/`commands`/`skills`/`systemPrompt`），或用 `ctx.get(name)` 防御式读取 |
| `fiberPhase: failed`（其它报错） | 插件 `apply` 抛错（宿主会隔离）：读 `~/.dsh/profiles/<profile>/.plugin-manager/logs/` 最近一次 operation 的报错堆栈；对照官方 `docs/reference/subsystems/{tools,commands,skills,system-prompt}.md` 的注册契约修正 `src/surfaces.js` |
| 改了源码但报错没变 | 模块缓存：重启 DSH；用 `link:` 安装可省掉重新复制 |
| 拦截不生效但插件 active | 宿主进程 PATH 里可能没有 `aios`：把该行的 `kernelCommand` 改为绝对路径（如 `C:/Users/<user>/.local/bin/aios.exe`） |
| 无关项目写不了 `src/` | 在 profile 补丁层覆盖该行，把 `strict` 设为 `false`（记得重述全部 key），未初始化项目即退回只受 Tier 0 约束 |
| 需要完全回滚 | `plugin_manager remove_bundle ai-engineering-os`（必要时再删 profile manifest 里的 `dependencies`/`bundles` 项与 `node_modules/ai-engineering-os`）；CLI 与仓库事实不受影响 |

### 插件暴露的注册面

插件只在一处强制、其余为便利面。契约形状来自官方 reference，且由 `tests/integration/test_plugin_surfaces.py` 用桩 ctx 逐项断言：

- `tools/pre-execute`：唯一的派发前拒绝点。
- 8 个工具：`{ name, description, parameters, output: { schema, render }, execute }`。
- 3 个人工命令：`{ name, description, handler(invocation) }`，返回 `{ kind: 'success' | 'error', text }`。
- 1 个 Skill Provider：`{ name, list(options), get(candidate, options) }`，候选需要 `rank` / `locator` / `invocation` / `source` / `provider`。
- 1 个 prompt section：`{ name, order, text }`，`order` 必须有限。

每个注册面各自 try/catch 隔离：某个便利面形状不符不会连带让强制面失效。

三层强制模型见 AGENTS.md「强制分层」。Tier 0 基线在**任何工作区**恒定开启，项目配置不可关闭；Tier 1 需要 `.aios/project.yaml`；Tier 2（默认开启）使未初始化项目同样套用 Tier 1，且只在内存中物化默认配置，不静默写盘。

## 规则优先级

1. 用户当前明确要求 → 2. AGENTS.md / 硬治理规则 → 3. 已确认项目事实 → 4. 任务上下文 → 5. AIOS 建议。用户要求破坏事实或绕过安全规则时，指出冲突并请求确认，不静默执行。
