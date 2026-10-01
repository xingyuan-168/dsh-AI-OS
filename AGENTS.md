# AI Engineering OS 宪法（AGENTS.md）

本仓库是 **DeepSeek Harness 的工程治理层**：无状态三 Gate（Code Start / Frontend Approval / Finish）只回答"允许/不允许及为什么"，不指导 DSH 怎么做专业工作。治理以 DSH 插件形式装进 profile，对所有项目默认生效。以下十条为硬治理规则，违反任何一条都不得继续。

## 十条宪法

1. **不改变 DSH 原生工程方式**：AIOS 只治理"能否做、何时做、做完留什么"；理解仓库、编码、调试、构建、测试、子 Agent（subagent / workflow）调度、Plan Mode 都是 DSH 的原生能力，AIOS 不重新实现。
2. **正式编码前必须通过 Code Start Gate**：GitHub remote 存在可达；开源调研分层完成并记录 Decision；仓库无复制式脏乱、无未解决冲突。无 GitHub 时允许读 input/、分析、调研、规划、写文档，禁止正式 src/ 实现。客观边界由 DSH 插件（`tools/pre-execute`、`fs/write-intent`）自动强制，`aios check` 可主动预看阻塞原因。
3. **input/ 只读**：不得修改、重命名、删除 input/ 内容；output/ 只放最终交付物，不放缓存、日志、源码副本。
4. **禁止复制式版本管理**：不创建 src_v2/、backup/、copy/、final/、old/ 等副本目录或 *_final.py、*_v1.* 等副本文件；Git 历史是唯一归档，被否决的设计放 archive 分支。
5. **受影响文档必须同步**：只改受本次变更影响的文档；一行后端修复不得强制重写十个文档；事实只保存在 Git 管理的文档中，任何派生缓存永不作为事实源。
6. **前端先批准**：新页面/新交互流/重大 UI 重构必须先有 docs/design/PROTOTYPE.html + docs/design/UI_SPEC.md 并获用户明确批准；改文案、修 CSS、修组件 Bug 豁免。
7. **并行任务用 Worktree 隔离**：DSH 原生子 Agent 各自进入 .worktrees/ 下的登记 Worktree，不写主工作区与其他 Worktree；完成后 review、merge、及时 cleanup，不留孤儿 Worktree。
8. **一次性文件即用即删**：临时脚本、缓存、调试产物任务结束删除，不进 Git；确有复用价值才晋升到 scripts/ 或 tools/。
9. **有价值的才进 Memory**：只记 decision/bug/lesson/pattern（可选 project-summary）；单写者规则——子 Agent 只提交 candidate，主会话在 Finish 时统一写入 docs/memory/memory.jsonl；拒绝 Secret 与聊天内容。
10. **保护用户资产**：主工作区禁止 force push、删远端 ref、update-ref -d、递归强删用户文件；破坏性但局部的操作（reset --hard、clean -f、branch -D）仅在自己的 disposable Worktree 或系统临时目录内允许。DSH 宿主可独立拒绝执行或禁用插件，AIOS 不代替宿主审批。

## 强制分层

- **Tier 0 基线**（恒定开启，任何工作区，项目配置不可关闭）：用户资产保护（force push / 删远端 ref / update-ref -d / volume rm-prune / 对根或家目录递归强删）、受保护路径（`input/**`、`.git/**`、`**.env`、`**/credentials/**`）、Memory 单写者。
- **Tier 1 已治理项目**（存在 `.aios/project.yaml`）：三 Gate 在写入时刻强制。
- **Tier 2 全局严格模式**（`~/.dsh/aios.yaml` 的 `strict: true`，默认开启）：未初始化项目同样套用 Tier 1，插件在内存中物化确定性默认配置，不静默写盘。

## Git 节奏

完整逻辑任务一个 Conventional Commit（docs:/chore:/feat:/fix:/refactor:/test: + 可选 scope）；handoff 或合并前必须 commit；里程碑 push 到 `dsh-AI-OS`。禁止 force push 与改写已推送历史；push 失败保持本地提交并如实报告，重试前核对远端 ref 与祖先关系。

## 验证与实现边界

默认验证项、Secret Scan 与实现边界（含"不做"清单）见 docs/GOVERNANCE_RULES.md「默认验证」「实现边界」两节。设计护栏只有一条原则：默认保持轻量，新增 DSH 工具/CLI 命令/文档/Skill 必须先证明必要性，失效能力及时删除，不写运行时检测代码。

## 必读顺序

1. 本文件。
2. docs/README.md —— 事实文档索引，按任务需要加载对应文档，不再有长链必读。
3. 任务相关契约：docs/GOVERNANCE_RULES.md、docs/WORKTREE.md、docs/FRONTEND_GATE.md、docs/MEMORY.md。
4. 已接受 ADR（docs/ADR/）。
