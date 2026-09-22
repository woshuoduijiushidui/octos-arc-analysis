# H06 实施 Milestone：验证失败后聚焦修复

- 状态：M3 已完成；M0 的官方实验冻结项及 M4-M8 待实施
- 面向对象：后续 coding agent
- 设计依据：[H06 竞品调研](./h06-verification-failure-focused-repair-competitor-research.md)
- 关联约束：[H03 实施清单](../h03/h03-implementation-milestone.md)、[H05 实施清单](../h05/h05-implementation-milestone.md)、[H07 竞品调研](../h07/h07-no-progress-strategy-switch-competitor-research.md)、[H08 竞品调研](../h08/h08-execution-budget-competitor-research.md)、[优化总表](../harness-optimization-table.md)
- 编写日期：2026-09-22
- 调研基线：`octos-arc origin/main@27d057c206c0f8250b60309905737f7e26ee0ba9`
- 写作时本地 H05 已提交分支：`feat/local-edit-strict-match@bb53c733ff6a40b477e5b6502dcb512a28be32ca`

本文是实施 todo list，不代表 H06 代码已经完成。只有同时具备代码、自动化测试和可追溯证据时，
才能把 `[ ]` 改成 `[x]`。类型名和文件位置可按开工时最新主线调整，但同任务续行、确定性放行、
失败关闭、预算上限和实验隔离不得静默弱化。

## 0. 后续 Agent 先读这一节

H06 要解决的是 MCP 当前的终态缺口：

```text
合法任务
  -> Agent 产生候选结果并准备结束
  -> 运行允许的确定性交付检查
  -> 全部通过：Ready
  -> 可修复失败且仍有预算：
       把有界 typed 错误追加到当前 run_task 的 messages
       -> 同一个 Agent 局部修复
       -> 重新运行完整 hard gate
  -> 不可修失败、无进展或预算耗尽：Failed
```

“同一个 Agent”在本清单中有严格含义：必须复用同一次 `run_task_inner` 的消息向量、累计 usage、
文件状态和循环状态。只复用同一个 `Agent` 对象、再调用一次 `run_task`，会重新构造 initial
messages，不算完成 H06。

评估顺序固定为：

1. 最终官方测试通过数、全通过率、回归数和重复运行稳定性。
2. false Ready、越权修复、修改测试/validator、错误 artifact 放行和错误候选恢复，目标均为零。
3. 全任务累计 provider token，包含首次实现、失败响应、修复、重试、压缩和恢复调用。
4. 请求数、修复轮数、validator 执行次数、I/O 和耗时用于解释结果；耗时不计入成绩。

### 0.1 A/B 定义

| 组别 | 内容 | 唯一要回答的问题 |
| --- | --- | --- |
| A | 最新共同底座，保留 MCP 验证失败后直接 Failed | 当前有多少失败其实可在同一任务中修复 |
| B | A + H06 typed completion gate + 同任务续行 + 最多 2 次自适应修复 + 完整重验 | 新增通过是否值得额外的全任务 token，且不产生假成功或回归 |

首轮只做 A/B，不把 1 轮、2 轮、不同票据格式拆成多个正式实验组。B 内记录每轮转化率；
只有第二轮成本或收益不清楚时，才追加轮数消融。

### 0.2 执行原则

1. 开工先检查两个仓库的分支、工作树和未跟踪文件；不得清理或覆盖用户已有 H05-H09 文档与代码。
2. 执行 `git fetch origin main`，从当时最新 `origin/main` 创建新的 `feat/verification-repair` 分支或独立 worktree。不要直接在当前 H05 分支继续实现。
3. 若最新主线未包含 H03/H05 中 H06 实际需要的能力，只移植已验证的最小依赖，单独提交并冻结共同底座 `A_SHA`；依赖收益不得算入 H06。
4. H07、H08、H10 尚未实现的部分不是 H06 开工前提。H06 首版只使用本清单规定的局部失败签名、轮次上限和现有 usage；未来接入时不得形成第二套冲突状态。
5. 开发期开关建议为 `OCTOS_VERIFICATION_REPAIR`，默认关闭；启用值、未知值和解析位置遵循仓库已有环境开关惯例。最多 2 轮先作为同一 policy 的固定实验值，不急于增加第二个环境变量。
6. 首版范围是 MCP `run_octos_session` 的 completion gate。Python `arc/main.py` 的 acceptance/final loop 只作参考和回归，不重写其流程。
7. 不新增通用 hook/plugin 系统，不让模型自评通过，不通过第二个 LLM verifier 判断确定性 validator 结果。
8. 每个 Milestone 完成后做本地 Git 提交并记录 SHA；不推送远程、不创建 PR，除非用户另行要求。
9. 不修改官方需求、测试、response schema、workspace policy、required tier、模型、reasoning、总预算或超时来换取通过。
10. 真实环境运行前加载当前 shell 的配置（WSL Bash 为交互式 `~/.bashrc`，zsh 为 `~/.zshrc`）。缺少 `ARCBENCH_API_KEY` 或 provider 配置时，明确记录缺失项，不把未运行写成失败或零成本。

| Milestone | 主要产出 | 对应分组 |
| --- | --- | --- |
| M0 | 最新共同底座、真实调用图、基线反例和状态边界 | A |
| M1 | typed completion decision、失败分类和有界 RepairTicket | B 基础 |
| M2 | 抽取 MCP 交付检查，保持直接 Failed 行为不变 | A 等价重构 |
| M3 | Agent 终止拦截与一次 fake gate 同任务续行 | B 核心 |
| M4 | MCP 真实 validator/artifact/schema 接线与单轮修复 | B |
| M5 | 最多两轮、进展判定、预算和候选保护 | B |
| M6 | 观测、24 项确定性验收、联合回归与 B 冻结 | B |
| M7 | 固定官方任务 A/B 对照 | A/B |
| M8 | 采用结论、最新主线集成和独立回滚 | 选中方案 |

## 1. 分支、开关和共同底座

### 1.1 M0 必须冻结的版本

- [x] 记录 `octos-arc`、`octos-arc-analysis` 当前分支、HEAD、远端跟踪、dirty 和未跟踪文件；不自动 stash、reset 或删除。
- [x] 拉取最新 `origin/main`，记录 `MAIN_SHA`，从它创建 H06 独立分支/worktree。
- [x] 核对 H01-H05 已合入与未合入能力，只移植 H06 必需的 typed validator、H03 有界证据和 H05 文件变化事实；每组依赖分别记录来源 SHA。
- [x] 依赖移植完成后运行专项回归并冻结 `A_SHA`。此时 H06 开关关闭，MCP 行为必须仍是验证失败后直接 Failed。
- [x] 记录 Rust/Python/Node 版本、实际二进制路径及 SHA-256、有效 sandbox/tool policy、MCP transport 和测试 fixture。
- [ ] 固定官方实验任务、输入/测试/schema 哈希、模型、reasoning、请求预算、修复轮数和重复次数。

建议开关合同：

| 开关 | 默认 | 作用 |
| --- | --- | --- |
| `OCTOS_VERIFICATION_REPAIR` | off | 启用 MCP completion failure 的同任务有限修复 |

- [ ] 开关只在进程/dispatch 配置边界解析一次，形成 typed policy 后传入 Agent；不得在每次 gate 检查中反复读环境变量。
- [ ] `off` 时不注册 completion repair、不增加模型消息、不增加 provider 请求，外部 MCP outcome 与 A 兼容。
- [ ] 未知值按 off 处理并留下有界诊断，不静默开启实验功能。
- [ ] 单测可直接注入 `max_repair_rounds=0/1/2` 的 policy；生产 B 固定为 2，避免为实验参数扩张公开配置面。

### 1.2 优先阅读的真实代码路径

| 职责 | 优先阅读位置（相对 `octos-arc/`） |
| --- | --- |
| task loop 与 `EndTurn` | `crates/octos-agent/src/agent/loop_runner.rs` |
| Agent 配置与可选组件 | `crates/octos-agent/src/agent/mod.rs` |
| 现有 LLM verifier 注入 | `crates/octos-agent/src/agent/verifier.rs` |
| Task/TaskResult durable ABI | `crates/octos-core/src/task.rs` |
| typed validator 结果 | `crates/octos-agent/src/validators.rs` |
| workspace contract 终检 | `crates/octos-agent/src/workspace_contract.rs`、`agent/loop_runner.rs` |
| MCP dispatch 与 artifact/schema | `crates/octos-cli/src/commands/mcp_serve.rs` |
| MCP outcome 与生命周期 | `crates/octos-agent/src/mcp_server.rs`、`task_supervisor.rs` |
| 当前一次性 recovery 参考 | `crates/octos-agent/src/tools/spawn.rs::run_task_with_m8_9_recovery` |
| H02/H03/H05 状态 | `task_file_state.rs`、`output_recovery.rs`、文件工具 metadata |
| 可选工作区快照 | `crates/octos-agent/src/snapshot.rs`、`agent/execution.rs` |
| 核心 loop 测试 | `crates/octos-agent/src/agent/loop_runner_tests.rs` |
| MCP 真实入口测试 | `crates/octos-cli/tests/mcp_serve_integration.rs` |
| Python 参考闭环 | `arc/main.py::acceptance_loop/final_acceptance` |

## 2. 不可破坏的约束

- [ ] 非法 `arc_task`、非法路径和输入 schema 继续在创建 provider/Agent 前拒绝；H06 不得让它们进入修复环。
- [ ] 只有 harness 实际运行的允许检查可以形成 RepairTicket；模型文本、文件内容和外层自由文本不能伪造 gate 通过或失败。
- [ ] required hard gate 必须全部通过才能 Ready；optional/soft 失败保持 warning，不触发修复，也不能被升级为 hard。
- [ ] validator `Fail` 与 `Timeout/Error` 分开处理。默认只有可定位的 `Fail` 可修；timeout、执行错误、策略拒绝和工具缺失直接 terminal failure。
- [ ] provider/config/sandbox 错误、取消、max iterations 和总预算耗尽不进入 H06 模型修复。
- [ ] 每次修复后重跑完整 hard gate；不能只跑先前失败项，也不能复用旧 pass 结果直接 Ready。
- [ ] RepairTicket 只能要求修改原任务允许的工作区/产物；不得建议修改测试、validator、workspace policy、required tier 或 response schema。
- [ ] artifact 每轮重新解析、canonicalize、检查存在性、大小、UTF-8/JSON 和 schema；旧文件或旧 receipt 不能冒充当前候选。
- [ ] 修复续行必须发生在同一次 `run_task_inner`；同一 `Agent` 上第二次调用 `run_task` 只能作为对照或旧路径，不能作为 B 的实现。
- [ ] 原始用户需求不重新拼进 RepairTicket。追加消息保持 prompt 前缀稳定，并复用 H01 的不可变契约和 H03 的证据引用。
- [ ] 不新增默认 LLM verifier 调用。现有 opt-in verifier 的开关、计费和行为在 H06 off 时完全不变。
- [ ] H05 的 stale、局部编辑、no-op 和 `file_modified` 事实保持权威；H06 不从“工具 success”或回复文字推断磁盘已经变化。
- [ ] H07 的 provider retry、等待和普通工具 loop 不计作 H06 修复轮；一次 RepairTicket 真正进入模型历史才消耗一轮。
- [ ] H08 完成前，H06 不创造新的全任务 token 池或 grace call；最多 2 轮仍受现有 iteration/token/cancel 边界约束。
- [ ] H10 完成前，无法确认的失败 usage 记 unknown，不能记成 0。正常修复请求必须累计进同一 `TaskResult.token_usage`。
- [ ] 中间 gate 失败不是终态；MCP 只能在最终确定后发布一次 `Ready`、`Failed` 或 `Cancelled`。
- [ ] 开关关闭时，不改变普通 chat/stdio、spawn、legacy `run_task`、Python ARC 和现有 MCP 错误前缀。

## 3. 最小数据和接口合同

名称可按仓库惯例调整，但不要创建两套含义相同的结果结构。优先放在 `octos-agent` 的小型
内部模块中；`octos-cli` 负责把 MCP 配置组装成 gate，不反向让 `octos-agent` 依赖 CLI。

### 3.1 候选与 gate decision

候选检查至少需要：

```text
CompletionCandidate
  task_id
  working_dir
  proposed_output
  files_modified
  files_to_send
  iteration
  cumulative_usage
  candidate_revision
```

gate decision 至少稳定区分：

```text
Pass(receipt)
Repairable(ticket, receipt)
TerminalFailure(failure, receipt)
```

- [ ] `Pass` 只能由确定性 gate 产生；模型不能在输出中声明该枚举。
- [ ] `receipt` 绑定 candidate revision/fingerprint，包含本次 validator outcomes、artifact 路径/内容状态和 gate policy 版本。
- [ ] MCP 最终 outcome 必须使用与最终候选匹配的 receipt；不得重新读取另一个版本后仍沿用旧 pass。
- [ ] 不使用进程全局 mutable “last result”。优先返回 invocation-local typed gated result，或使用等价的显式所有权接口。
- [ ] 不随意扩展 `octos_core::TaskResult` durable ABI。若确需修改，先核对 ABI 文档、schema version、所有构造点和反序列化兼容。

### 3.2 RepairTicket

模型可见票据只包含修复需要的事实：

| 字段 | 语义 |
| --- | --- |
| `schema_version`、`ticket_id` | 版本与审计身份 |
| `task_id`、`candidate_revision` | 票据属于哪个候选 |
| `repair_round`、`max_repair_rounds` | 当前和总轮数 |
| `gate_id`、`kind`、`status`、`required_tier` | typed 失败类别 |
| `reason`、`stderr_tail`、`evidence_ref` | 有界证据；大正文使用 H03 引用 |
| `expected_artifact`、`observed_artifact`、`schema_error` | 交付失败的准确位置 |
| `passed_gate_ids` 或摘要 | 告知哪些已通过行为不得破坏 |
| `failure_signature` | 判断同类失败是否重复 |
| `allowed_action` | 只修源码/产物，不改测试和 gate |

- [ ] 使用确定性 renderer，不调用模型总结 ticket。
- [ ] ticket 总字节上限在 M0 根据真实 prompt 路径冻结，且不得超过 H03 的单结果最终可见预算；原因、路径、stderr 和恢复提示全部计入。
- [ ] 先保留错误码、gate ID、轮数、修复限制和证据引用，再裁剪正文。
- [ ] validator 输出和 artifact 内容按不可信数据处理；使用明确边界，不能让其中的“忽略规则”“修改测试”等文字成为 harness 指令。
- [ ] 多失败按稳定顺序输出；同 gate 重复证据去重，不重复内联相同 stderr。

### 3.3 可修复分类和失败签名

| 结果 | 默认分类 |
| --- | --- |
| required validator `Fail` 且有项目内证据 | repairable |
| artifact missing | repairable |
| artifact JSON/schema invalid | repairable |
| artifact 位置错误 | 仅安全目标已确定时 repairable，否则 terminal |
| optional/soft failure | warning，不修复 |
| validator `Timeout/Error` | terminal |
| config/provider/sandbox/cancel/budget | terminal |
| 非法任务、越权输入、隐藏测试 | 不进入 gate 修复 |

- [ ] classifier 只消费 typed 状态和可信边界信息，不解析英文 error prefix 反推类别。
- [ ] `failure_signature` 使用排序后的 gate ID、kind、status、稳定 reason code/schema pointer 等；排除时间戳、duration、随机文件名和日志顺序。
- [ ] 原始 stderr/evidence hash 可用于确认内容是否变化，但不能把日志中的随机 ID 当成进展。
- [ ] 一个 batch 中同时存在 repairable 与 terminal hard failure 时整体 terminal，不浪费模型调用。

### 3.4 终态原因

内部至少可区分：

```text
passed
repair_round_limit
no_workspace_change
unchanged_failure
task_budget_exhausted
gate_timeout
gate_error
cancelled
rollback_unavailable
```

现有 MCP 对外 `contract_failed:`、`artifact_missing:`、`artifact_schema_invalid:`、
`session_failed:` 前缀保持兼容。新增内部原因优先进入结构化事件/证据，不随意改变调用方已解析的
错误字符串。

## 4. Milestone M0：冻结底座、调用图和基线反例

**目标：**在改代码前证明验证在哪里运行、消息何时丢失、哪些状态能复用，并冻结 A。

证据记录：[H06 M0 共同底座与 A 反例](./h06-m0-baseline.md)。

- [ ] 完成第 1.1 节，记录 `MAIN_SHA`、依赖移植 SHA 和 `A_SHA`。
- [x] 追踪 native ARC 与 legacy prompt 两条 MCP 路径：输入校验、Agent 构造、`run_task`、workspace contract、completion validators、artifact resolve/location/schema、outcome 返回。
- [x] 追踪 `EndTurn` 时 assistant response 是否已经进入 `messages`、`TaskResult` 在何处构造、usage/iteration 在何处累计、`TaskCompleted` 事件何时发出。
- [x] 证明第二次调用 `run_task` 会重新构造 initial messages；记录哪些 Agent 状态会保留、哪些首轮消息会丢失。
- [x] 核对现有 LLM verifier 与 workspace contract 的顺序，冻结 H06 开启/关闭时的顺序要求；不得重复运行模型 verifier。
- [x] 核对 MCP observer/TaskSupervisor 允许的非终态转换，决定修复期间保持 `Running`、切换 `Verifying` 后返回 `Running`，或仅发内部 gate event；不得先发布 terminal Failed。
- [x] 核对 completion validators 与 core project-root validators 是否重叠，记录命令、phase、workspace root、ledger 和副作用；B 中同一 gate 不得无意执行两遍。
- [x] 核对 artifact 路径优先级、64 KiB 文本读取上限、JSON/schema 错误和 `files_to_send` 语义。
- [x] 核对 `SnapshotManager` 的启用方式、`.gitignore`、nested repo、无 Git、并发锁和 restore 边界；明确是否能安全保护 H06 候选。
- [x] 冻结 RepairTicket 模型可见字节上限、失败数上限、stderr tail 和 evidence ref 规则。
- [x] 用现有 `ScriptedLlmProvider` 固定至少五个 A 反例：required `Fail`、artifact missing、schema invalid、validator timeout/error、非法 `arc_task`。
- [x] 记录每个反例的 provider 请求数、lifecycle、最终 prefix、validator_results、artifact 字段和 token cost；非法输入必须为零 provider 请求。
- [x] 运行现有 MCP/Agent/validator 回归并记录基线失败；新增测试可以固定现状，但不能把主分支永久留红。

**设计停止点：**若 completion gate 无法在不破坏 `TaskResult` ABI 的前提下把最终 receipt 返回 MCP，
先在 M0 证据中比较“gated result wrapper”和“invocation-local handle”两种最小方案，再选一个。
不得用全局变量或第二次无版本绑定的验证绕过问题。

**完成条件：**A 可重放；调用图、gate 插入点、receipt 返回方式、ticket 上限、生命周期和候选保护能力均已冻结。

## 5. Milestone M1：typed gate contract、分类器与 RepairTicket

**依赖：**M0。**目标：**先建立纯数据合同，不改变 Agent 或 MCP 控制流。

- [x] 在真正共享的最小模块定义 candidate、check outcome、decision、receipt、ticket 和 terminal reason；复用 `ValidatorOutcome`，不复制其状态/required/evidence 字段。
- [x] 为 artifact exists/location/text/JSON/schema 建立 typed check kind；不再依赖 `artifact_schema_invalid:` 等英文前缀做内部分支。
- [x] 实现纯 classifier：hard `Fail` 可修；optional 不阻塞；`Timeout/Error` terminal；混合 batch 采用最严格结果。
- [x] 实现稳定 failure signature，过滤 duration、timestamp、随机路径后缀和无关顺序。
- [x] 实现有界、确定性的 RepairTicket renderer；输出包含禁止修改测试/policy/schema 的约束。
- [x] 大 evidence 只给 H03 引用和短摘要；引用不可用时明确 `recoverable=false`，不虚构路径。
- [x] ticket 记录 candidate revision，旧 ticket 不能应用到新候选。
- [x] 添加纯单测：单/多 failure、optional、timeout/error、稳定排序、签名去噪、Unicode、长路径、超大 stderr、恶意日志文本和极小预算。
- [x] 证明 renderer 不产生额外 provider 请求，且相同输入字节级稳定。

**完成条件：**任意现有 validator/artifact 结果都能得到唯一、typed、有界的 decision；尚未启用修复，生产行为与 A 相同。

后续接线注意：M2-M4 必须从同一次检查构造 `CompletionReceipt` 的 task ID、candidate revision 和 policy version；工作区产生新候选时推进 revision。只有 invocation-local H03 store 确认可 recall 后才填入 `RecoveryReference`，否则票据保留 `recoverable=false`。`render(&self, budget) -> String` 是同步纯函数，没有 provider 句柄或 I/O；真实 MCP gate 与模型续行留待 M2-M4。

WSL 交互式 Bash 已核对非敏感配置：`MODEL`/`OCTOS_MODEL=deepseek-v4-flash`、`OPENAI_BASE_URL=https://api.arc-bench.com/v1`、`OCTOS_ARC_REASONING=auto`。本次 M1 未读取密钥或发起真实模型请求；M7 前仍需核验真实密钥、官方任务的 MCP 入口、response schema 与总请求预算。

## 6. Milestone M2：抽取 MCP completion gate，保持 A 行为

**依赖：**M1。**目标：**把多个直接 return 分支变成一个可复用检查器，但仍只检查一次并直接结束。

- [x] 抽取当前 completion validators、artifact resolve、位置、读取、JSON/schema 检查；保持执行顺序、sandbox、路径优先级和错误前缀。
- [x] gate 输入显式携带 native ARC schema、legacy expected artifact、contract、tools/sandbox 和 candidate files；不得从进程全局重新查找任务。
- [x] gate 输出包含本次完整 validator_results、artifact 状态和 candidate-bound receipt。
- [x] required validator 失败后仍保留完整 typed outcomes；optional failure 不阻止 artifact 检查和 Ready。
- [x] artifact 缺失、过大/非 UTF-8、JSON 错误、schema 错误和安全位置错误保持现有外部结果。
- [x] `task_result.success=false` 仍不得验证磁盘上的旧 artifact；max iteration、provider error 等路径保持原短路。
- [x] legacy prompt 路径保持兼容；没有 response schema 时不新增 schema 检查。
- [x] H06 off 和 M2 on-but-no-continuation 的 provider 请求、lifecycle、MCP outcome 和文件结果与 A 等价。
- [x] 删除被抽取逻辑的重复分支；不要保留两套 artifact validator 逐渐漂移。
- [x] 回归现有 `mcp_serve_integration` 全文件，并增加 gate 单测覆盖所有旧分支。

**完成条件：**MCP 的成功/失败行为和 A 一致，但每次候选验证已经统一产生 typed decision + receipt，可供 M3 使用。

后续接线注意：M2 的单次 MCP 验证把 candidate revision 固定为 1，`TaskResult` 尚未暴露真实 iteration，因此暂填 0。M3 的 Agent 终止拦截接入时必须传入真实 iteration；M4 每产生新候选须推进 revision，并从同一候选的 receipt 构造最终 MCP outcome。无法解析任何 artifact 路径属于 terminal；只有已知目标路径但文件缺失才可发修复票据。M2 仍只验证一次，不执行模型续行。

## 7. Milestone M3：Agent 终止拦截与一次同任务续行

**依赖：**M2。**目标：**先用 fake gate 证明真正的 same-run continuation，再接真实 MCP。

- [x] 为 `Agent::run_task_inner` 增加可选的 async completion gate seam；默认不存在时保持旧字节行为，不扩张为通用插件系统。
- [x] 提供新的 gated 调用入口或等价 typed wrapper；旧 `run_task` 签名和所有旧 caller 保持兼容。
- [x] 在 `EndTurn` 候选形成后、真正 `TaskCompleted`/return 前调用 gate；具体与现有 LLM verifier/workspace contract 的顺序采用 M0 冻结结果。
- [x] `Repairable` 时，先把本轮 assistant candidate 按现有顺序记入历史，再追加一条 harness 生成的 user-role/internal RepairTicket。
- [x] 追加后走同一 loop 的 `continue`；不得新建 `Task`、不得重新拼完整需求、不得调用第二个 Agent。
- [x] 修复续行沿用同一个 `messages`、`LoopTurnState`、retry state、loop detector、file/output state、compaction 和 cumulative usage。
- [x] 一张 ticket 真正进入下一次 provider request 才计为一轮；gate 自身不消耗模型轮次。
- [x] fake gate 第一次返回 Repairable、第二次返回 Pass；断言 provider 第二次请求包含原历史和唯一 ticket，原需求没有被重复拼接。
- [x] 断言两次模型响应 usage 累计到一个最终结果，iteration 单调增加，`TaskCompleted` 只发一次。
- [x] fake gate 返回 TerminalFailure 时不产生第二个 provider 请求；取消和预算检查仍优先终止。
- [x] ticket 被 compaction/最终 prompt 投影时保持关键字段；若 H03/H01 未在底座中，至少保证有界、不可误解，不能假装具备恢复能力。

**完成条件：**不依赖 MCP 文件检查，单靠 fake gate 已证明“EndTurn → ticket → 同一消息历史继续 → Pass/terminal”的核心状态机。

后续接线注意：M3 的 `run_task_with_completion_gate` 返回任务结果及 invocation-local 最终 decision；budget/cancel 等在下一次请求前终止时也返回带原 receipt 的 terminal decision。M4 应把 M2 的真实 MCP gate 接到此入口，使用最终候选的 receipt 生成 outcome；普通 `run_task` 与 MCP 当前入口仍无模型续行。gate 收到 `core_contract_failure`，须把它纳入同一候选的硬门槛判断。

## 8. Milestone M4：接通 MCP 真实检查与单轮聚焦修复

**依赖：**M3。**目标：**先只允许一次真实修复，关闭端到端缺口。

- [x] MCP 在 H06 on 时使用 M2 的 completion gate 调用 gated `run_task`；off 时继续旧入口。
- [x] 首版可修类型只包括：required validator `Fail`、artifact missing、可安全修复的位置问题、JSON/schema invalid。
- [x] `Timeout/Error`、配置/provider/sandbox、取消、budget 和非法输入保持 terminal，不触发第二次模型请求。
- [x] 真实 ticket 包含失败 gate、期望 artifact/schema 位置、短 reason/stderr、H03 evidence ref 和已通过 gate 摘要。
- [x] ticket 不包含完整原任务、完整 schema、完整 stdout/stderr、密钥或绝对用户目录；模型已有的不可变合同不重复发送。
- [x] Agent 修复后重新运行全部 hard validators、artifact location 和 schema；只有同一候选 receipt 全部通过才 Ready。
- [x] 最终 `McpSessionOutcome.validator_results`、artifact_path/content、cost 和 error 来自最终候选，不混用第一次失败数据。
- [x] 中间失败不向 observer 发布 terminal Failed；最终只发布一次 Ready/Failed/Cancelled。
- [x] 用 `ScriptedLlmProvider` 完成真实链路：首个 EndTurn 触发 missing/schema/validator Fail，第二个响应通过文件工具修复，再次 EndTurn 后 Ready。
- [x] 在最终 provider 请求中断言 RepairTicket 存在、原任务未重复、失败证据有界、工具权限未变化。
- [x] 加负例：同样脚本在 H06 off 时仍一次请求后 Failed，证明 A/B 开关有效。

**完成条件：**至少 missing artifact、schema invalid 和 required validator Fail 各有一个同任务单轮修复成功测试；不可修失败零额外模型请求。

后续接线注意：生产入口以 `octos mcp-serve --h06-completion-repair` 开启，默认关闭；M4 最多发送一张 ticket。已存在文件的覆盖受文件版本保护，模型应先用 `read_file` 观察当前内容再用 `write_file` 修复。M4 不伪造 H03 引用：只有 invocation-local store 已确认可 recall 时 ticket 才带引用；本轮 validator/artifact 检查未产生可验证的 H03 引用，因此票据明确标记 `recoverable=false`，短诊断采用固定安全文案，原始 stderr 不进入模型上下文。

## 9. Milestone M5：两轮上限、进展判断、预算和候选保护

**依赖：**M4。**目标：**在不引入通用 H07/H08 重构的前提下，让 B 有界并避免明显回归。

### 9.1 修复轮和停止规则

- [ ] 生产 B 固定 `max_repair_rounds=2`；off/0、单轮和双轮由同一 policy 表达。
- [ ] 第一次 repairable failure 在任务仍可继续时允许一轮。
- [ ] 第二轮只允许两种情况：hard pass 集合严格改善；或工作区确实变化但稳定 failure signature 相同，使用唯一一次“换策略”机会。
- [ ] 工作区未变化且 signature 相同立即停止为 `no_workspace_change`，不为必然相同的代码再付一次验证/模型成本。
- [ ] signature 变化但 hard pass 集合未改善，只视为 `evidence_changed`；最多允许下一轮，不把它当验证成功。
- [ ] 出现新 hard failure 或丢失已通过 gate，标记 `regressed`；不得仅按失败总数掩盖回归。
- [ ] provider retry、等待轮询和普通工具 loop 使用原有计数，不消耗 H06 repair round。
- [ ] H07 将来存在统一 `ProgressObservation` 时改为消费它；删除 H06 重复归一化，不保留两个不同判断器。

### 9.2 预算

- [ ] 注入 ticket 前检查至少还允许一次真实模型 iteration；无法继续时直接返回 `task_budget_exhausted`。
- [ ] 不为 H06 增加 grace call，不提高 `max_iterations`、`max_tokens`、`chat_max_tokens` 或 proxy 请求上限。
- [ ] 两轮修复的所有正常 response usage 进入原 `LoopTurnState/TaskResult` 累计值，MCP cost 只做一次最终投影。
- [ ] provider/transport 错误保留 partial/unknown 语义；H10 未完成前不为兼容字段伪造真实零消耗。
- [ ] H08 接入后，修复必须使用它分配的交付保留额；H06 不再维护独立 token 余额。

### 9.3 候选保护

- [ ] M0 已证明目标工作区是否可由现有 `SnapshotManager` 完整覆盖，包括 `.gitignore` artifact、nested repo、无 Git 和并发锁场景。
- [ ] 若覆盖成立，在第一次修复前保存候选；只有新候选不减少已通过 hard gate 且至少新增一个 pass 时更新 best。
- [ ] 修复结束仍 Failed 时恢复 best，并重新验证恢复后的候选；最终 outcome 必须绑定恢复后 receipt。
- [ ] snapshot/restore 失败时不得宣称已恢复，也不得用部分文件副本冒充原子工作区恢复。
- [ ] 若现有 snapshot 无法覆盖 H06 合法目标，不临时手写半套回滚。暂停 M5，记录缺口并在本清单中明确选择：限制到可证明隔离的 disposable workspace，或另行设计完整候选机制。
- [ ] 在候选保护未证明前，B 不得默认开启，也不得宣称满足“保留最佳状态”。

**完成条件：**双轮路径严格有界；无变化、同签名、回归、预算不足和 restore failure 都有 typed 终态，且不会产生 false Ready。

## 10. Milestone M6：观测、确定性验收与 B 冻结

### 10.1 最小观测

- [ ] 每次 gate 记录 task/candidate ID、round、decision、失败类别、hard pass/fail 数、signature 和 gate duration。
- [ ] 每次修复记录 ticket 可见字节、evidence 引用数、provider usage、文件是否变化和最终停止原因。
- [ ] 记录首次验证到最终 Ready 的转化、第一/第二轮成功、无变化、同签名、回归和 restore 结果。
- [ ] 普通日志不输出完整源码、完整 schema、完整 stderr、凭据或模型 reasoning。
- [ ] 观测写入失败不改变 gate decision，也不能把真实 failure 改成 Ready。

### 10.2 必须覆盖的验收矩阵

| ID | 场景 | 判定点 |
| --- | --- | --- |
| T01 | 首次完整通过 | 1 次模型完成；零 RepairTicket；Ready 与 A 一致 |
| T02 | required validator `Fail`，一轮修好 | 同任务续行；完整重验后 Ready |
| T03 | artifact missing，一轮补齐 | 期望路径准确；无旧 artifact 冒充 |
| T04 | JSON/schema invalid，一轮修好 | ticket 有界；最终内容符合原 schema |
| T05 | artifact 安全位置可修/不可修 | 只允许安全目标；越权输入 terminal |
| T06 | 多个 required failures | 稳定排序、合并 ticket；全部通过才 Ready |
| T07 | optional/soft failure | 不触发修复，不阻止 Ready |
| T08 | validator `Timeout` | 零额外模型请求；typed terminal |
| T09 | validator `Error`/policy deny/tool missing | 零额外模型请求；权限不放宽 |
| T10 | 非法 `arc_task` | provider 调用数为零 |
| T11 | `TaskResult.success=false`/预算耗尽且旧 artifact 存在 | 不验证或交付旧 artifact，不进入修复 |
| T12 | fake gate 一次 Repairable 后 Pass | 第二次请求保留同一消息历史，原需求不重复 |
| T13 | 修复后完整 gate 出现新回归 | 不能 Ready；候选比较真实 |
| T14 | 第一轮改善、第二轮通过 | 最多两张 ticket，usage/iteration 累计 |
| T15 | 无文件变化且签名相同 | 提前停止，不发无意义第二轮 |
| T16 | 文件变化但签名相同 | 只允许一次换策略，然后停止 |
| T17 | 大 stderr/多失败/长路径/Unicode | ticket 总量有界，关键字段与引用完整 |
| T18 | evidence 含提示注入文本 | 只作数据，不修改 gate/测试/权限 |
| T19 | compaction、H03 recall、H02/H05 状态 | ticket 和证据可达；不产生错误读取/写入授权 |
| T20 | lifecycle 与取消竞态 | 中间无 terminal；最终状态只发布一次 |
| T21 | 两个并发 MCP invocation | round、ticket、receipt、snapshot 和 evidence 不串任务 |
| T22 | 累计 usage 与 provider retry/error | 正常用量不漏算；未知不记零 |
| T23 | H06 off、legacy prompt、普通 `run_task`、spawn | A 行为和公共 API 兼容 |
| T24 | best snapshot/restore 或明确受限模式 | 最终磁盘版本与最终 receipt 对应 |

- [ ] T01-T24 均有自动化测试或有证据的“不适用”；T01-T16、T20-T23 不能标不适用。
- [ ] T02-T04/T12/T14 至少通过真实 `RealSessionDispatch + ScriptedLlmProvider` 捕获最终 requests，不以纯 helper 单测代替。
- [ ] 回归 validator、workspace contract、Agent loop、MCP server wire format、H02/H03/H05 受影响路径。
- [ ] 检查 H06 off 的工具 schema、prompt、请求数和 outcome；固定输入增量应为零。
- [ ] 审查 `A_SHA..HEAD`，不含 H07 通用循环、H08 全局预算、H10 计费重构、Python acceptance 改写或无关格式化。
- [ ] 本地提交并冻结 `B_SHA`、二进制 SHA-256、功能开关、ticket policy、测试清单和限制。
- [ ] 在分析仓库新增 M0-M6 对应验证记录时，每个文件只记录真实证据，不提前勾选未完成项。

**完成条件：**B 通过 T01-T24；所有成功均有最终 hard gate receipt；所有修复有界、同任务、可计量，H06 off 与 A 兼容。

## 11. Milestone M7：固定官方任务 A/B 对照

### 11.1 开跑条件

- [ ] M6 冻结的完整 B 已通过确定性门槛，且用户确认可以运行付费真实模型实验。
- [ ] 证明所选官方任务实际经过 H06 的 MCP `run_octos_session` 路径；现有 `arc/main.py` 使用 stdio/OUP，直接运行它不能测出 MCP-only H06 的效果。
- [ ] 按运行 shell 加载环境（WSL 交互式 Bash 使用 `~/.bashrc`，zsh 使用 `~/.zshrc`），确认 `ARCBENCH_API_KEY`、provider endpoint、`OCTOS_BIN`、二进制 SHA-256、端口和隔离目录。
- [ ] A/B 使用相同需求、测试、response schema、workspace policy、模型、reasoning、工具权限、sandbox、请求/token/iteration 预算和超时。
- [ ] 每个 task×variant 使用独立 workspace/data/session；固定重复次数，建议至少 3 次并交错顺序。
- [ ] 预注册任务类别：一次通过、构建失败、artifact missing、schema invalid、多 gate failure、不可修基础设施失败和容易回归的已有工程。

### 11.2 每次运行记录

- [ ] `MAIN_SHA/A_SHA/B_SHA`、实际运行 SHA、git dirty、二进制路径与哈希。
- [ ] task、输入/测试/schema/policy 哈希、模型、reasoning、repetition、run order 和全部有效开关。
- [ ] 首次候选结果、每轮 ticket/decision/signature、文件变化、gate outcomes 和最终 receipt。
- [ ] 最终官方逐例结果、全通过、回归和重复稳定性。
- [ ] provider input/output/cache/reasoning token、请求数、retry、unknown usage。
- [ ] 首轮/第二轮修复转化、无变化、同签名、regression、restore 和终止原因。
- [ ] validator 次数、ticket/evidence 字节、artifact 版本和最终工作区版本。

### 11.3 采用顺序

1. 先比较最终官方通过数、全通过率、回归和重复稳定性。
2. false Ready、越权修复、修改测试/policy、错误恢复和 receipt/version 不一致必须为零。
3. 正确率不下降后，再比较全任务累计 token；包含未转化的修复成本。
4. 分别报告“每新增一个通过任务的增量 token”和“没有转化任务的额外 token”。
5. 本地执行时间、validator 次数和 I/O 只用于解释，不作为评分收益。

- [ ] 不以单个最好 run、最终回复长度、ticket 变短或缓存命中率代替全任务 token。
- [ ] 不删除失败样本，不把 H06 导致的 timeout/OOM/死锁归为外部故障。
- [ ] B 若正确率下降，即使 token 更少也不采用；B 若提高正确率但增加 token，按项目目标报告真实取舍。
- [ ] 第二轮几乎无新增通过且消耗明显时，再做 `max_rounds=1` 消融；不在主实验前增加第三组。

**完成条件：**A/B 有完整、可追溯的有效 run；得到采用 B、保持 A 或证据不足的明确结论。

## 12. Milestone M8：采用、最新主线集成与回滚

- [ ] 汇总 B 的确定性门槛和官方 A/B 结果；证据不足时保持默认 off，不因代码已经完成而强行采用。
- [ ] 重新拉取最新 `origin/main`，在不改写冻结 SHA 的前提下集成选中方案，记录 `INTEGRATION_SHA`。
- [ ] 核对最新 H01-H05、H07-H10、workspace contract、MCP lifecycle、tool policy、snapshot 和 durable ABI 的组合。
- [ ] 若集成改变 gate 顺序、ticket、预算、修复轮、候选保护或模型输入，重跑对应确定性和官方对照；旧 B 结果不能自动证明新组合。
- [ ] 保留独立回滚：关闭 H06 只恢复直接 Failed，不关闭 H02/H03/H05，也不改变 validator 或 artifact 安全检查。
- [ ] 删除未采用且无维护价值的实验死代码；保留调研、Milestone、验证记录和未采用原因。
- [ ] 更新优化总表中的实际状态、默认值和实验结论；不创建内容重复的平行文档。
- [ ] 跑受影响全量测试、格式、Clippy、Python tests 和官方 smoke，区分基线失败与新增失败。
- [ ] 每个 Milestone 的代码与分析证据分别本地提交，记录 SHA；远程推送仍等待用户指令。

**完成条件：**选中方案在最新主线组合下仍满足正确率、安全和 token 门槛；关闭 H06 可独立恢复 A 行为。

## 13. 测试、提交与交接要求

### 13.1 候选验证命令

先用 `-- --list` 或测试文件清单确认过滤器确实命中；零测试不能算通过。以下是候选命令，
coding agent 应按实际新增测试名补充：

```bash
cargo test -p octos-agent --lib validators
cargo test -p octos-agent --lib agent::loop_runner_tests
cargo test -p octos-agent --lib snapshot
cargo test -p octos-agent --test mcp_server
cargo test -p octos-cli --test mcp_serve_integration
cargo test -p octos-cli --lib
cargo fmt --all -- --check
cargo clippy -p octos-agent -p octos-cli --all-targets -- -D warnings
git diff --check

cd arc
python3 -m unittest discover -s tests
```

若修改了 `octos-core::TaskResult` 或其他 durable ABI，增加对应 schema/version/replay 测试，并运行所有
构造点和消费者所在 crate。若只增加新的 gated wrapper，仍需证明旧 `run_task` 调用者不变。

已知环境问题必须重新核实，不能预先忽略：严格 Clippy 可能命中主线遗留告警；Python 3.9
不支持 `tarfile.extract(filter=...)`；macOS sandbox/TTY/文件锁可能影响全量测试。先在 `A_SHA`
复现，能复现才标为基线问题。

### 13.2 每个 Milestone 的本地提交

- [ ] 一个 commit 只完成一个可验证 Milestone，或一个为保持绿色所需的更小切片。
- [ ] 提交信息描述实际行为，例如“统一 MCP 交付检查结果”“在任务结束前反馈可修复验证失败”“限制验证修复轮次”。
- [ ] 提交前运行相关专项测试、`cargo fmt --all -- --check` 和 `git diff --check`。
- [ ] 不提交真实凭据、大模型密钥、临时 workspace、snapshot store、无界日志或官方实验生成物。
- [ ] 分析仓库的验证记录与代码仓库提交分开；不推送远程。

### 13.3 每个 Milestone 的交接格式

- [ ] 用通俗中文说明完成了什么、还没完成什么，以及没有改哪些路径。
- [ ] 列出修改文件、关键入口、依赖 SHA、功能开关、默认值和数据合同。
- [ ] 列出准确测试命令、通过/失败/跳过数量和退出码；基线失败与新增失败分开。
- [ ] 列出 gate decision、RepairTicket、usage、lifecycle 和候选版本的证据位置。
- [ ] 列出代码 commit、分析 commit、工作树状态和下一 Milestone 起点；没有证据的项目不勾选。

后续 agent 不应把 M1-M5 压成一次大重构。先用纯类型和行为等价抽取固定旧路径，再证明
fake gate 的 same-run continuation，最后接真实 MCP 并增加第二轮。若实际源码推翻本清单的
接口假设，先更新 M0 证据和本清单，再采用满足同一安全合同的更小实现；不得退回“自由文本
失败 + 第二次 run_task”这种高重复、低可审计方案。
