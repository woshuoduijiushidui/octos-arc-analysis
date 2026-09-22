# H07 实施 Milestone：typed 进展判断与有界策略切换

- 状态：M0-M1 已完成；M2-M9 待实施
- 面向对象：后续 coding agent
- 设计依据：[H07 竞品调研](./h07-no-progress-strategy-switch-competitor-research.md)
- 关联约束：[H05 实施清单](../h05/h05-implementation-milestone.md)、[H03 实施清单](../h03/h03-implementation-milestone.md)、[优化总表](../harness-optimization-table.md)
- 编写日期：2026-09-22
- 调研基线：`octos-arc origin/main@27d057c206c0f8250b60309905737f7e26ee0ba9`
- 当前可复核 H05 版本：B `8287e8f8ae63a27a58ab5898ecb2753b9b946c45`；C `bb53c733ff6a40b477e5b6502dcb512a28be32ca`
- 当前分析仓库：`d3e6dd91789ec0491e382604edeb3bfa50cf3b5a`

本文是实施 todo list，不代表 H07 代码已经完成。只有代码、自动化验证、运行证据和本地提交
均已存在时，才能把 `[ ]` 改成 `[x]`。类型名和文件位置可以根据开工时最新主线调整，但
正确率优先、规则优先、状态有界、入口一致和实验隔离不得静默弱化。

## 0. 后续 Agent 先读这一节

H07 不是简单地“调用多了就停”，而是判断一次操作有没有带来真实进展：

```text
工具执行成功 ≠ 任务有进展
文件写过 ≠ 文件内容真的变化
错误文字变化 ≠ 获得了新证据
参数变化 ≠ 换了策略
只有可信状态、证据或验证结果变化，才能更新进展判断
```

最终目标：

1. 明显重复先由确定性规则处理，不增加模型请求。
2. 参数变化但本质相同的停滞，要求模型换一个可验证的方法。
3. 可选模型复盘每个停滞 episode 最多一次，并且每个 turn 也有总上限。
4. 复盘后仍重复就停止，返回有界、不可自动重试的原因。
5. 合法异步等待、provider 瞬时失败和外层官方测试修复分别处理。

评估顺序固定为：

1. 官方测试最终通过数、回归数和重复运行稳定性。
2. 有效调试被提前终止、合法等待被误杀、真实进展未被识别，目标均为零。
3. 全任务累计 input/output/cache/reasoning token，包含复盘、失败请求和外层修复。
4. 工具执行数、模型请求数、提示/拒绝/策略切换/终止次数只用于解释结果。
5. 耗时只作诊断，不计入成绩。

### 0.1 B 和 C 的合并方式

**实现合并，实验不合并。**

| 组别 | 代码与配置 | 唯一要回答的问题 |
| --- | --- | --- |
| A | 共同底座；H07 新能力关闭，保留当前 exact/cycle 保护 | 当前正确率、token 和循环基线是多少 |
| B | `BC_SHA`；typed observation、等价 episode、规则提示/拒绝开启；H07 语义复盘关闭 | 不增加模型复盘时，确定性规则能减少多少无效调用 |
| C | 与 B 使用完全相同的 `BC_SHA`；只开启 H07 语义复盘 | 每个停滞最多一次复盘是否带来足够正确率收益 |

要求：

- B/C 不创建两套 detector，不复制状态机，不维护两条代码分支。
- B/C 使用同一个二进制，只改变一个已记录的 reflection 开关。
- C 只能是 B 的条件增强；不能同时改变阈值、prompt、模型、预算或工具列表。
- 现有周期性 convergence 配置在 A/B/C 间保持相同。C 只增加“语义停滞触发”的入口。
- 若语义触发与周期触发同时到期，只执行一次 checkpoint，并记录合并后的原因。

### 0.2 执行原则

1. 开工前执行 `source ~/.zshrc`，然后 `git fetch origin main`，从当时最新 `origin/main` 创建 `feat/no-progress-strategy-switch` 或独立 worktree。
2. 不直接在当前 `feat/local-edit-strict-match` 上开发 H07，不覆盖 H05 或其他并行任务的未提交内容。
3. 若最新主线尚未包含 H07 需要的 H05 typed mutation metadata，只移入已验证的必要依赖，单独提交并记录来源 SHA；依赖收益不得算作 H07 收益。
4. H05 最终 S 尚未选定时可以做确定性开发，但不能开始 H07 付费 A/B/C；正式实验的共同底座必须固定同一个 H05 方案。
5. 每个 Milestone 完成后本地提交；不推送远程、不创建 PR，除非用户另行明确要求。
6. 不修改官方需求、测试、判分器、模型、reasoning、工具权限、预算、修复轮数或超时来制造收益。
7. 不新增每步 LLM evaluator，不把 verifier 默认挂到所有 Agent，也不为 H07 新建另一套外层 repair controller。
8. 不解析任意自然语言中的“tests passed”“file changed”来授予强进展；只有可信 typed 来源可以写强状态。

| Milestone | 主要产出 | 对应分组 |
| --- | --- | --- |
| M0 | 最新共同底座、调用图、基线反例和精确边界 | A |
| M1 | bounded `ProgressObservation` 与结果提取 | B/C 共同代码，行为仍关闭 |
| M2 | exact 重复顺序修正及 conversation/task 一致 | B |
| M3 | 等价 no-progress key、bounded episode 和策略状态 | B |
| M4 | H05 文件事实、read 证据和 productive grace 校准 | B |
| M5 | verified wait、provider retry 隔离和不可重试终止 | B |
| M6 | B/C 共用策略梯子与 C 的一次 convergence 复盘 | B/C |
| M7 | 真实入口、观测、24 项回归和 `BC_SHA` 冻结 | B/C |
| M8 | 固定官方任务 A/B/C 对照 | A/B/C |
| M9 | 采用、最新主线集成和回滚 | 选中方案 |

## 1. 分支、开关和真实入口

### 1.1 M0 必须重新冻结的版本

本文写作时：

- `octos-arc origin/main` 为 `27d057c2`。
- H05 B 为 `8287e8f8`，H05 C 为 `bb53c733`。
- `loop_detect.rs`、`loop_runner.rs`、`convergence.rs`、`loop_state.rs`、`arc/main.py` 和 `arc/acceptance.py` 在 H05 C 与 `origin/main` 间没有差异。

这些 SHA 只用于复核调研结论，不能代替未来开工时的最新主线。

- [x] 检查 `octos-arc` 和 `octos-arc-analysis` 的分支、工作树、未跟踪文件及未推送提交；不自动清理用户改动。
- [x] 从最新 `origin/main` 创建 H07 分支或独立 worktree，记录 `MAIN_SHA`。
- [x] 核对 H01-H05 已合入能力和 H05 最终选择；必要依赖先单独移植、验证并冻结 `A_SHA`。
- [x] 证明 `A_SHA` 尚未开启 H07 新行为，现有 exact/cycle、peer polling、file churn、retry bucket 和 convergence 行为可重放。
- [x] 固定官方实验任务、需求/测试哈希、模型、reasoning、工具列表、session scope、预算、修复轮数、超时和重复次数。
- [x] 记录 Rust/Python/Node 版本、实际 `OCTOS_BIN`、二进制 SHA-256、现有 convergence 配置及全部有效 H01-H05 开关。

### 1.2 建议的功能开关

若最新主线已有统一 policy/config 入口，可调整名字，但必须保留“总能力”和“付费复盘”两个独立开关：

| 开关 | 实验默认 | 作用 |
| --- | --- | --- |
| `OCTOS_NO_PROGRESS` | off | 开启 B 的 typed observation、episode、提示、拒绝和终止 |
| `OCTOS_NO_PROGRESS_REFLECTION` | off | 在 B 已开启时，允许 C 对语义停滞触发一次 checkpoint |

- [ ] 开关在 Agent/config 构造时解析一次并注入，不在每次工具调用里反复读取环境变量。
- [ ] 未知值按 off 处理并留下有界诊断；reflection 开启但 core 关闭时不得半开启。
- [ ] H07 总开关关闭时，现有 loop detector、工具输出、请求数和终止行为与 A 等价。
- [ ] 不把每个阈值都暴露为环境变量；测试通过构造 policy 注入阈值，生产只保留必要的实验开关。
- [ ] `OCTOS_FILE_CHURN_THRESHOLD`、现有 convergence interval 和 verifier 配置在 A/B/C 中保持固定。

### 1.3 优先核对的代码路径

| 职责 | 优先阅读位置（相对 `octos-arc/`） |
| --- | --- |
| exact/result/cycle/file/peer 检测 | `crates/octos-agent/src/loop_detect.rs` |
| conversation 与 task 主循环 | `crates/octos-agent/src/agent/loop_runner.rs` |
| tools-disabled checkpoint | `crates/octos-agent/src/agent/convergence.rs` |
| provider/tool retry bucket 与 grace | `crates/octos-agent/src/agent/loop_state.rs` |
| Agent 配置和测试注入 | `crates/octos-agent/src/agent/mod.rs` |
| 工具执行、结果清洗和 typed metadata | `crates/octos-agent/src/agent/execution.rs` |
| `ToolResult` 与文件事实 | `crates/octos-agent/src/tools/mod.rs` |
| H05 mutation metadata | `tools/mutation_report.rs`、`edit_file.rs`、`diff_edit.rs`、`write_file.rs` |
| H03 source/view metadata | `output_recovery.rs`、`tools/read_file.rs`、`tools/recall.rs` |
| peer/background 状态 | `tools/peer_gather.rs`、`tools/peer_list.rs`、`tools/check_background_tasks.rs`、`tools/spawn.rs` |
| task 自动恢复和生命周期分类 | `tools/spawn.rs::run_task_with_m8_9_recovery`、`classify_child_session_lifecycle_kind` |
| typed harness events | `harness_events.rs`、`harness_errors.rs` |
| 外层验收收敛，只读回归 | `arc/main.py`、`arc/acceptance.py` |

## 2. 不可破坏的约束

- [ ] `success=true`、长输出、退出码 0、参数不同和文件工具被调用都不能单独成为强进展。
- [ ] `validation_improved` 只能来自 harness 授权的 typed validator/test 结果；模型文本和普通 shell 文本不得伪造。
- [ ] `state_changed` 只说明权威状态发生变化，不自动清除 validation stall，也不宣称任务完成。
- [ ] `evidence_changed` 必须保留错误类别、位置、expected/actual 或其他会改变下一步的字段；时间戳、耗时、随机 ID 和重试号不能伪装成新证据。
- [ ] 未知或缺字段时保守降级为 `unknown/text_fallback`；不能猜测成功，也不能仅因无法分类就终止。
- [ ] H05 `outcome=no_change` / `file_modified=false` 不增加 file churn，不获得 productive grace。
- [ ] 真修改按最终确认版本计数；调用参数不同但最终版本相同不重复算 mutation。
- [ ] 合法等待必须绑定当前仍存活的具体 handle；仅有“正在运行”文字、旧状态文件或历史意图不够。
- [ ] provider 请求失败发生在任务观察之前，不创建 no-progress episode；继续由 `LoopRetryState` 的 typed bucket 处理。
- [ ] policy deny、审批等待、用户取消、content filter、context overflow 和 invalid request 保持原有分类，不被 H07 改写为“换工具试试”。
- [ ] conversation 与 `run_task` 使用同一 observation、episode 和 terminal 语义；展示格式可以不同。
- [ ] C 每个 episode 最多一次 H07 语义复盘，并设置每 turn 总上限；初版总上限冻结为 1，除非 M8 数据证明需要调整。
- [ ] reflection 失败时回到 B 的确定性行为，不重试 reflection，不吞掉原始工具结果。
- [ ] H07 提示、状态摘要和终止原因都计入 H03 最终输出预算；不能把 read/recall 的范围或恢复提示挤掉。
- [ ] H07 附加提示不能改变 H02/H03 的来源版本、可见范围、receipt、artifact 或恢复授权。
- [ ] 状态、文本、路径、episode 数和 metrics label 全部有界；不保存完整工具输出、完整参数、源码、绝对路径或凭据。
- [ ] semantic terminal 必须在 task、spawn recovery 和 lifecycle 分类中保持 `retryable=false`；不能因为输出里出现 `retry` 字样又自动执行一次。
- [ ] `arc/main.py` 的 failure signature、codegen/tools 切换、最佳状态恢复和 full-suite 停止逻辑原则上不改。
- [ ] H07 不放宽文件权限、mutation guard、并发锁、工具 schema、官方测试或预算。

## 3. 最小数据与状态约定

优先扩展 `LoopDetector` 和现有执行返回值。只有当 observation 构造在两个真实入口重复时，才抽一个
小型内部模块；不要建立通用事件溯源框架、数据库或跨任务全局状态。

### 3.1 Observation

建议的内部语义：

```text
ProgressObservation
  operation_family   read | search | mutate | validate | execute | wait | other
  target_key         有界、规范化的目标身份
  execution_status   success | failed | blocked | timed_out | unknown
  typed_outcome      modified | no_change | no_match | ambiguous | ...
  state_digest       最终版本或权威状态摘要，可为空
  evidence_key       稳定错误/结果摘要，可为空
  validation_key     授权验证结果摘要，可为空
  wait_key           当前 live handle 身份，可为空
  confidence         typed | trusted_adapter | exact_text_fallback
```

分类至少能表达：

```text
validation_improved | state_changed | evidence_changed |
verified_wait | no_progress | regressed | unknown
```

- [ ] observation 在 `ToolResult`、`output_document` 和 `structured_metadata` 仍可用时构造，不在只剩显示文本后反向猜测。
- [ ] call ID 只用于关联本批工具结果；episode identity 使用规范化目标和 typed 事实，不依赖可能重复的 provider call ID。
- [ ] 对模型可见文本 fallback 只做 exact digest；任意日志的“去时间戳正则”不进入首版。
- [ ] typed producer 可以明确声明哪些字段是 volatile；只有该 producer 的已知字段允许忽略。
- [ ] equality 使用完整内部 key；日志只显示有界 label，不输出不可逆大对象或高基数 metrics label。

### 3.2 Episode 与 decision

建议的内部状态：

```text
EpisodeKey
  operation_family + target_key + typed_outcome/error_code + stable evidence

EpisodeState
  observations + hinted + switch_required + reflected + post_switch_probe + terminal

ProgressDecision
  continue | attach_hint | reject_before_execute |
  request_reflection | terminal_non_retryable
```

约定：

- [ ] episode 以当前 conversation/task run 为生命周期；除非有现成可靠持久状态，不跨用户 turn 猜测连续性。
- [ ] episode 表、每个 episode 的样本和显示文本均设置固定上限；M0 记录精确数值和淘汰规则。
- [ ] 淘汰旧 episode 只损失优化机会，不得导致误终止。
- [ ] 无关工具成功不清除当前 episode；强 validation improvement 才结束相关验证 episode。
- [ ] 新失败位置或 expected/actual 产生 `evidence_changed`，允许下一步，但不把旧问题直接宣告解决。
- [ ] `unknown` 不产生 semantic terminal；旧 exact/cycle 保护仍可独立工作。

### 3.3 初版升级语义

| 情况 | 初版行为 |
| --- | --- |
| 第一次 observation | 仅记录 |
| 第 2 个完全等价、确定性结果 | 附短提示；不新增 LLM 请求 |
| 提示后第 3 次完全相同调用 | 执行前拒绝；工具实际执行次数保持 2 |
| 参数变化但同 episode 连续 3 次无进展 | 标记 `switch_required`；B 给确定性提示，C 可请求一次 reflection |
| switch 后选择不同诊断动作 | 允许一个有界 probe |
| switch/reflection 后 observation 仍等价 | `terminal_non_retryable` |
| live async handle 的相同状态 | `verified_wait`，走退避/等待上限，不套用上述同步阈值 |

这些数字是初版 contract，不是所有工具共享的永恒参数。M8 若显示误杀，只调整有证据的工具类别；
不得用提高一个全局阈值掩盖分类错误。

## 4. Milestone M0：冻结底座、调用图和基线反例

**目标：**在写实现前证明当前行为和所有自动重试出口。M0 不开启 H07。

- [x] 完成第 1.1 节，冻结 `MAIN_SHA`、依赖提交和 `A_SHA`。
- [x] 追踪 conversation：模型响应、terminal tool 检查、`record_doom`、cycle warning、工具执行、`record_result`、file/peer signal、convergence、最终 response。
- [x] 追踪 task：`run_task_inner`、工具执行、verifier、budget/max-token continuation 和 `TaskResult` 返回；证明当前没有同等 pre-call hard guard 和 signal 消费。
- [x] 追踪 spawn/MCP：`TaskResult.success=false` 怎样触发 M8.9 单次恢复、lifecycle retryable 分类和上层再次派发。
- [x] 追踪 `ToolResult` 的 success、`file_modified`、`output_document`、structured metadata、清洗、截断、H03 envelope 和最终模型消息。
- [x] 追踪 H05 `modified/no_change/no_match/ambiguous` 的真实字段及 H05 off 时缺字段行为。
- [x] 追踪 peer/background 工具的 handle、live/terminal 状态和轮询调用；不能只按工具名假设异步。
- [x] 证明当前普通 conversation 在第 3 次 exact call 执行前终止，因此看不到第 3 个 result-aware soft hint。
- [x] 证明当前 task 可执行 conversation 已经会拦截的第 3 次 exact call。
- [x] 证明成功 `no_change` 会被当前 success+path 逻辑计入 file churn。
- [x] 证明重复长 read 或附带 no-progress hint 的文本可能被 `is_productive_tool_message` 视为 productive。
- [x] 证明 provider retry bucket 与 task observation 的真实边界，并记录 verifier 豁免路径。
- [x] 用 fake provider/计数工具建立可重放反例，不调用付费模型，不把预期失败测试留在绿色分支中。
- [x] 冻结 observation/episode/hint 的容量、文本字节、阈值和 metrics label 集合；记录选择依据。
- [x] 创建 `h07/h07-m0-baseline.md` 或等价证据，列出命令、结果、SHA 和未覆盖入口。

**完成条件：**A 可重放；所有执行前检查、结果后判断、模型复盘和自动重试出口都有所有者；B/C 的唯一变量已冻结。

## 5. Milestone M1：bounded `ProgressObservation` 与 typed 提取

**依赖：**M0。**目标：**先建立事实，不改变生产决策。

- [x] 在最靠近工具执行结果的共享边界构造 observation；保留 `ToolResult` 的 typed 事实后再做字符串渲染。
- [x] 通过 call ID 将并行/串行 batch 的 observation 与原 tool call 稳定关联；去重、限制和 blocked placeholder 不得错配。
- [x] operation family 和 target 提取只覆盖实际工具；未知工具进入 `other`，不靠工具名子串猜类别。
- [x] H05 mutation 优先读取 `ToolResult.file_modified` 与 typed metadata；字段冲突时标记 unknown 并计诊断，不任取一个“成功”值。
- [x] H03 read/recall 优先读取 source/view/version/range identity；没有可信 source 时只保留最终模型可见 exact digest。
- [x] typed tool error 使用已有 `HarnessError`/error code；不得在上层解析 `"Error:"` 文本恢复类型。
- [x] 为未来授权 validator 预留可选 `validation_key`，但本阶段没有 typed producer 时保持空值，不解析 shell 测试输出。
- [x] 所有路径、detail 和列表按 M0 上限截断；episode key 不保存原始源码和完整命令。
- [x] 增加纯单元测试：typed、缺字段、冲突字段、Unicode、长路径、长错误、未知工具、重复 call ID 和多 call batch。
- [x] H07 off 时 observation 可以不构造或只做无副作用观测；模型消息、工具结果、metrics 和请求数与 A 等价。
- [x] 本地提交并记录代码 SHA、测试命令和 M1 证据。

M1 代码提交 `38c607cd0a54482e95bec2a3a9e13871d97379fe`；命令、结果与未覆盖入口见 [M1 证据](./h07-m1-evidence.md)。

**完成条件：**给定同一个工具结果，conversation/task 可得到相同、有界、可解释的 observation；尚未改变提示、拒绝或终止。

## 6. Milestone M2：exact 重复顺序与两个 loop 一致

**依赖：**M1。**目标：**先修复最明确、无需模型判断的重复调用。

- [ ] 将 exact 同步调用的结果历史与 pre-call 检查统一：第 2 个等价结果附提示，第 3 次相同调用执行前拒绝。
- [ ] 更新旧注释、常量和测试，不能继续声称“第 3 次软提示、第 4 次硬停”。
- [ ] conversation 与 `run_task` 调用同一 `before_call`/`after_result` 语义；不得只复制一段 if 到第二个 loop。
- [ ] exact 拒绝必须保留合法 tool call/result 配对或在写入 assistant tool-call 历史前终止；不能留下协议残缺消息。
- [ ] 多工具 batch 中命中拒绝时保持当前批处理安全语义，并明确其他 call 是否执行；测试不能只覆盖单 call。
- [ ] 保留 cycle length 2/3 的现有两阶段 warning/terminal 行为，除非 M3 用更强 typed key 明确接管。
- [ ] 保留 shell spiral 的既有恢复优先级、verifier 明确豁免和 peer async 特例；任何变化必须有专项测试。
- [ ] exact hint 经过 H03 最终预算，仍保留 read/recall 的范围、版本和恢复参数。
- [ ] H07 off 时旧 threshold、消息和工具执行次数与 A 一致。
- [ ] fake provider 测试同时断言 LLM 请求数、工具实际执行数、最终消息和 token 计量。
- [ ] 本地提交并记录 M2 证据。

**完成条件：**B 下两个 loop 的 exact 同步重复都只执行两次；提示先于拒绝到达模型，旧循环和特殊路径无回归。

## 7. Milestone M3：等价 key、bounded episode 与策略状态

**依赖：**M1-M2。**目标：**识别“参数在变，但目标和结果没变”的循环。

- [ ] 实现第 3.2 节的 bounded episode；复用 `LoopDetector` 生命周期，不新建全局 singleton。
- [ ] known typed producer 只使用稳定字段构造 key；忽略字段列表由 producer/adapter 明确提供。
- [ ] H05 no-match/ambiguous 使用 path、error code、matcher、候选位置/计数等稳定事实；变化的调用 JSON 不自动创建新 episode。
- [ ] HarnessError 使用 variant、recovery、稳定位置/原因；不把 backoff 次数或 provider request ID 算新证据。
- [ ] unknown/text fallback 保留原 exact digest 语义，不做激进模糊归一化。
- [ ] 同 failure location 但 expected/actual 改变时记 evidence change；仅耗时、时间戳、随机 ID 变化时保持同 episode。
- [ ] episode 到第 2 次附定向提示；到语义阈值设置 `switch_required`，但 B 不产生额外模型请求。
- [ ] switch 后允许一个不同 observation probe；同 key 继续出现时返回 typed terminal decision。
- [ ] eviction、hash collision 防护、计数饱和和极长 task 均有测试；淘汰不能触发 terminal。
- [ ] metrics label 只使用固定 enum，如 family/decision/confidence；path、tool args、error text 和 digest 不作 label。
- [ ] 本地提交并记录 M3 证据。

**完成条件：**改空白、limit、无关参数或 request ID 不能绕过已知 typed episode；真正的新错误证据仍允许继续。

## 8. Milestone M4：H05 文件事实、read 证据和 productive grace

**依赖：**M3，开发时需有 H05 typed metadata。**目标：**不把“成功调用”误当成“真实进展”。

- [ ] `outcome=no_change` 或 `file_modified=false` 记 no-progress，不增加 file churn。
- [ ] `file_modified=true` 且最终确认版本变化时记 state change；同一路径相同最终版本不重复计数。
- [ ] `final_state=unconfirmed` 或 typed 字段冲突时保持 unknown，不宣称 modified/no-progress。
- [ ] formatter 改变内容时以 `final_version` 为准；`changed_range` 只作证据，不代表 validation improvement。
- [ ] 真正连续版本变化可以触发现有 churn checkpoint，但 churn 本身不产生 semantic terminal。
- [ ] 相同 read source/version/range 和相同可见 digest 可以记 no-progress；新页、新范围、新版本或新搜索命中记 evidence change。
- [ ] H03 恢复页引用同一 source 但范围前进时不能误判为重复读取。
- [ ] typed no-progress 不调用 `record_productive_tool_call`，不能获得 budget grace。
- [ ] typed state/evidence change 可以记录 productive；旧无 typed 工具保留现有文本 heuristic 兼容路径。
- [ ] 重复长输出、`Exit code: 0` 但无新 typed 证据、附 H07 hint 后长度超过 128 字节均有反例测试。
- [ ] 回归 H02 receipt、H03 output envelope/recall 和 H05 M2-M6 测试。
- [ ] 本地提交并记录 M4 证据。

**完成条件：**文件进展来自最终实际状态；no-op 不再抬高 churn 或 grace，正常分页与多次有效编辑不被误杀。

## 9. Milestone M5：verified wait、retry 隔离与不可重试终止

**依赖：**M3-M4。**目标：**把“正在等”“基础设施重试”和“任务卡住”彻底分开。

- [ ] 为声明 async 的工具提取当前 live handle；只有运行时确认存活才返回 `verified_wait`。
- [ ] 同 handle 状态未变时采用现有 bounded wait/退避；不 busy-wait，不因一次 observation timeout 重启任务。
- [ ] handle 终止、缺失或状态不可确认时不再标记 verified wait；根据真实结果进入 completed/failed/unknown。
- [ ] 保留 peer changed-result、unchanged-result reflection 和最终结果测试；不要用通用 exact guard 覆盖它们。
- [ ] provider rate limit/network/stream/context retry 不增加 task episode，不因任意成功 read 清空 retry bucket。
- [ ] policy deny、approval pending、cancel 和 verifier 结果保持各自状态，不重复发 H07 提示。
- [ ] 为 `terminal_non_retryable` 定义稳定内部 code 和 `retryable=false`；用户文本只显示短原因和已观察事实。
- [ ] conversation 收到 terminal 后结束当前 turn，不再调用模型或工具。
- [ ] task 收到 terminal 后返回 `success=false` 和机器可识别的非重试身份；不得只靠英文关键词分类。
- [ ] `run_task_with_m8_9_recovery` 遇到 H07 terminal 不发起那一次自动恢复；普通可恢复失败仍保持原行为。
- [ ] child lifecycle 将 H07 terminal 分类为 `TerminalFailed`；输出中即使含有 “retry” 也不能变成 `RetryableFailed`。
- [ ] 若必须扩展 `TaskResult` ABI，按现有版本规则增加 optional 字段、更新所有构造者/serde/消费者和兼容测试；不得私自改 schema version。
- [ ] 本地提交并记录 M5 证据。

**完成条件：**合法等待不会被当作死循环；基础设施 retry 不污染 H07；semantic terminal 在 task/spawn 全链路只终止一次。

## 10. Milestone M6：B/C 共用策略梯子与一次复盘

**依赖：**M2-M5。**目标：**同一实现同时支持零额外复盘的 B 和条件复盘的 C。

- [ ] B/C 只使用一个 policy/state machine 和一个 `BC_SHA`；reflection 开关只改变 `request_reflection` 的处理。
- [ ] B 在 `switch_required` 时把短而具体的策略提示附到现有结果，下一次正常 action call 就是换策略机会。
- [ ] C 在相同状态下复用 `ConvergenceController` 和现有 tools-disabled 调用，不引入 verifier 或第二套 summary prompt。
- [ ] 提取最小共享 checkpoint helper，使 conversation/task 都能执行同一 H07 semantic reflection；task 不因此开启普通周期性 checkpoint。
- [ ] reflection prompt 只携带用户目标、episode 类别、有界证据和“选择不同可验证动作”；不复制完整工具输出。
- [ ] 每个 episode 最多一次 H07 reflection，每 turn 最多一次；其他 episode 退回 B 的确定性提示。
- [ ] H07 forced reason 与已有 periodic/file churn/peer reason 同时到期时合并为一次调用，不丢高优先级 typed 证据。
- [ ] reflection 的 input/output/cache/reasoning token 计入真实 turn/task usage，但不推进 action-call threshold。
- [ ] budget grace iteration 不用于 reflection；接近硬预算时直接使用 B 行为。
- [ ] reflection 文本作为 transient background context，不能持久化成用户可见 assistant final，也不能自己标记任务 complete。
- [ ] host 不解析 reflection 自述来重置 episode；后续工具 observation 才能证明策略变化或进展。
- [ ] reflection 失败或空输出时不重试，记录失败后继续 B；复盘后同 episode 再现则 terminal。
- [ ] verifier-configured Agent 不重复支付 verifier + H07 reflection；M0 选定并测试唯一所有者。
- [ ] 本地提交；同一 commit/branch 冻结 B/C 代码，配置差异单独记录。

**完成条件：**B 零新增模型请求；C 对一个停滞 turn 最多新增一次请求；两者除 reflection 开关外完全等价。

## 11. Milestone M7：真实入口、观测、回归和 `BC_SHA` 冻结

### 11.1 最小观测

- [ ] 记录固定枚举：operation family、progress class、decision、confidence、reflection requested/completed/failed。
- [ ] 记录 episode count、实际工具执行数、pre-call reject、hint、switch、terminal 和 H07 reflection token。
- [ ] observation/decision 指标失败不改变 Agent 结果；日志不包含源码、完整命令、完整结果、凭据或绝对路径。
- [ ] provider retry 指标继续使用原有命名；H07 task stall 使用独立 metric/event，不混入 `octos_loop_retry_total`。
- [ ] 如复用 harness progress/failure event，extra 字段有 schema/大小验证，terminal 明确 `retryable=false`。

### 11.2 必须覆盖的 24 项验收矩阵

| ID | 场景 | 判定点 |
| --- | --- | --- |
| T01 | H07 off | 与 A 的请求、工具执行和终止行为等价 |
| T02 | conversation exact 同步重复 | 第 2 次提示，第 3 次执行前拒绝，只执行 2 次 |
| T03 | task exact 同步重复 | 与 T02 相同语义，无无限 task loop |
| T04 | cycle 2/3 与 shell spiral | 旧两阶段恢复和优先级不回归 |
| T05 | H05 `no_change` | no-progress；不计 churn/grace |
| T06 | H05 不同最终版本 | state changed；不会仅因编辑次数终止 |
| T07 | final state unconfirmed/metadata 冲突 | unknown；不伪造进展 |
| T08 | no-match/ambiguous 参数抖动 | 聚合到同 typed episode |
| T09 | 只变化 known volatile 字段 | 不重置 episode |
| T10 | error location 或 expected/actual 变化 | evidence changed，允许继续 |
| T11 | read 同页与新页 | 同页可判 no-progress；范围前进算新证据 |
| T12 | trusted validation 改善/回退 | improvement 结束相关 episode；regression 不冒充进展 |
| T13 | 普通输出打印“tests passed” | 不创建 validation improvement |
| T14 | 无关成功 read | 不清除 mutate/validate stall |
| T15 | live peer/job poll | verified wait；变化和最终结果可观察 |
| T16 | provider retry/overflow/auth/policy | 走原 bucket，不进入 H07 episode |
| T17 | approval、cancel、steer、verifier | 原 lifecycle 保持，H07 不重复处理 |
| T18 | C semantic reflection | 每 episode/turn 至多一次，usage 完整 |
| T19 | reflection 空输出/失败/撞 periodic | 不重试、不重复调用、不丢正常 action |
| T20 | switch 后同 episode 再现 | bounded terminal，不再执行同类工具 |
| T21 | task terminal 经过 spawn | 不触发 M8.9 recovery，lifecycle 为 terminal |
| T22 | 并行/混合 tool batch | observation 按 call ID 对齐，消息协议完整 |
| T23 | 长路径、Unicode、长结果、episode 淘汰 | 状态与提示有界，无敏感正文 |
| T24 | ARC outer acceptance | failure signature、策略切换、最佳状态恢复不变 |

- [ ] T01-T24 均有自动化测试或有证据的“不适用”；T02、T03、T05、T08、T15、T18、T21 不能标不适用。
- [ ] 至少用真实 `process_message`、真实 `run_task` 和 spawn recovery 测试，而不是只测纯 detector。
- [ ] 增加真实 stdio + fake provider 场景，捕获最终 messages/tools、请求数、工具执行数和 reflection tool choice。
- [ ] 回归 `loop_retry_state`、convergence、peer polling、H02 receipt、H03 output/recall、H05 mutation 和 spawn lifecycle。
- [ ] 回归 ARC `failure_signature`、identical failure gate、no-improvement stop 和 best-state restore。
- [ ] 检查 H07 off 与 A 的兼容 diff；审查 `A_SHA..HEAD` 不含 H06/H08/H09、官方输入或无关重构。
- [ ] 本地提交并冻结唯一 `BC_SHA`、二进制 SHA-256、两个开关、精确阈值、schema/固定输入增量和测试证据。

**完成条件：**T01-T24 通过；B/C 共用 `BC_SHA`；H07 off 可回到 A；真实入口没有重复执行 terminal episode。

## 12. Milestone M8：固定官方任务 A/B/C 对照

### 12.1 开跑条件

- [ ] M7 完成，用户确认可以运行真实模型实验。
- [ ] 执行 `source ~/.zshrc`，确认 `ARCBENCH_API_KEY`、provider endpoint、`OCTOS_BIN`、二进制哈希、端口和隔离目录。
- [ ] A 使用 `A_SHA`；B/C 使用同一 `BC_SHA`。额外运行一次 `BC_SHA + H07 off` parity smoke，证明开关关闭不漂移。
- [ ] A/B/C 固定相同需求、测试、模板、模型、reasoning、工具、H01-H06 配置、预算、修复轮数和超时。
- [ ] 现有周期 convergence、verifier、file churn 和 H05 模式固定；C 只改变 H07 reflection 开关。
- [ ] 每个 task×variant 使用独立 workspace/data/session；固定重复次数，建议至少 3 次并交错运行顺序。
- [ ] 包含会触发 H07 的重复 read/no-op/等价失败任务，也包含正常多步编辑、错误逐步变化和异步等待反误杀任务。

### 12.2 每次运行记录

- [ ] `MAIN_SHA/A_SHA/BC_SHA`、实际运行 SHA、git dirty、二进制路径和 SHA-256。
- [ ] task、输入/测试/模板哈希、模型、reasoning、重复序号、运行顺序和全部有效开关。
- [ ] 最终官方逐例结果、首轮通过数、回归、重复稳定性和 previously-passing 行为损坏。
- [ ] provider input/output/cache/reasoning token、请求数、重试和 reflection token；unknown 不记零。
- [ ] 工具实际执行、pre-call reject、hint、switch、reflection、terminal、verified wait 和 episode eviction。
- [ ] no-change、相同 read、等价 failure、真实 state/evidence/validation change 及误判来源。
- [ ] 被 H07 提前终止后，外层是否增加了额外 repair；不能只统计当前 turn 节省。

### 12.3 采用规则

- [ ] 先比较最终正确率、回归和稳定性；正确率不下降后才比较全任务 token。
- [ ] B 对 A 下降则不采用，并先定位 observation、episode、terminal 或入口差异；不能用 token 节省解释。
- [ ] B 与 A 正确率相同且总 token 更低，可采用 B；B 提高正确率时可接受小幅 token 增量，但要逐任务报告。
- [ ] C 对 B 下降则关闭 reflection；保留 B，不通过提高全局阈值掩盖。
- [ ] C 提高最终正确率时，报告每个新增通过对应的额外 reflection/token，再决定默认或条件启用。
- [ ] C 与 B 正确率相同时，只有 C 降低全任务总 token 且重复运行稳定才采用；否则默认 B。
- [ ] 某任务没有触发 H07 或 C reflection，只能说明该任务无覆盖，不能作为等价证据。
- [ ] 任何合法等待误杀、真实进展误终止、terminal 被自动重试或 metrics 泄露敏感内容都直接阻止采用。
- [ ] 不用单次最好结果、少执行几个工具或某次 reflection 很短代替全任务累计结果。

**完成条件：**A/B/C 所有有效 run 可追溯；明确选择 A、B 或 C，或明确证据不足，不提前宣布收益。

## 13. Milestone M9：采用、最新主线集成与回滚

- [ ] 根据 M8 选择：拒绝 H07、采用 B，或采用 C；未采用模式不能残留为默认行为。
- [ ] 重新拉取最新 `origin/main`，从最新主线创建集成分支并移入选中实现，记录 `INTEGRATION_SHA`。
- [ ] 与最终 H05 S、H06 修复、H08 预算、H09 工具集合以及最新 task/spawn consumer 做组合审查。
- [ ] 若集成改变工具 metadata、convergence、TaskResult ABI、预算或自动恢复，重新跑对应对照；旧实验不能自动证明新组合。
- [ ] 提供独立回滚：关闭 reflection 回到 B；关闭 H07 core 回到 A 的现有 loop 行为；均不关闭 retry bucket、H02/H03/H05 保护。
- [ ] 删除未采用且无维护价值的实验死代码、死开关和重复 prompt；保留实验记录和拒绝原因。
- [ ] 更新优化总表和已有行为文档中的真实默认值、支持入口和实测结论，不创建无必要的平行说明。
- [ ] 运行受影响 crates、Rust fmt/Clippy、ARC Python tests 和官方 smoke；基线失败与新增失败分开。
- [ ] 代码与分析证据分别本地提交，记录 SHA；远程推送继续等待用户明确指令。

**完成条件：**选中方案在最新主线组合下仍满足正确率、终止安全和 token 门槛；两个开关可独立回滚。

## 14. 测试、提交和交接要求

### 14.1 候选验证命令

先用 `-- --list` 或测试清单确认过滤器确实命中；零测试不能算通过。下面是候选命令，
不是已经执行的记录：

```bash
cargo test -p octos-agent --lib loop_detect
cargo test -p octos-agent --lib convergence
cargo test -p octos-agent --lib loop_runner_tests
cargo test -p octos-agent --test loop_retry_state
cargo test -p octos-agent --test h07_progress_detection
cargo test -p octos-agent --test h07_loop_entrypoints
cargo test -p octos-agent --test h07_terminal_propagation
cargo test -p octos-agent --test h05_m2_typed_recovery
cargo test -p octos-agent --test h05_m3_mutation_results
cargo test -p octos-agent --test h05_m6_observability
cargo test -p octos-agent --test h03_m1_output
cargo test -p octos-agent --test h03_m3_file_pages
cargo test -p octos-agent --test h03_m7_search
cargo test -p octos-agent
cargo test -p octos-cli --test mcp_serve_integration
cd arc
python3 -m unittest tests.test_acceptance tests.test_identical_failure_gate tests.test_main_helpers
cd ..
cargo fmt --all -- --check
cargo clippy -p octos-agent -p octos-cli -p octos-core --all-targets -- -D warnings
git diff --check
```

新增测试文件名可按仓库惯例调整，调整后必须把真实命令写回验证证据。若修改 `TaskResult`
或 harness ABI，增加 `octos-core` serde/版本兼容测试和所有消费者编译检查。若修改 stdio、
MCP 或 spawn 注册，增加对应真实入口测试，不能只用 detector 单测替代。

已知环境问题必须重新核实：Python 3.9 不支持 `tarfile.extract(filter=...)`；严格 Clippy
可能遇到主线遗留告警。只有在 `A_SHA` 可复现时才能标为基线问题，不能预先忽略。

### 14.2 推荐提交顺序

1. `test(h07): pin no-progress entrypoint gaps`
2. `feat(h07): derive bounded progress observations`
3. `fix(h07): align exact repeat guards across agent loops`
4. `feat(h07): track equivalent no-progress episodes`
5. `fix(h07): classify real file progress and budget grace`
6. `fix(h07): separate waits retries and terminal stalls`
7. `feat(h07): gate one semantic convergence reflection`
8. `test(h07): freeze merged b-c behavior across real entrypoints`
9. `docs(h07): record fixed three-arm experiment results`

一个 Milestone 过大时可以拆成更小的绿色提交；不得把 M1-M6 压成一次大改。

### 14.3 每个 Milestone 的 coding guidelines

- [ ] 修改前重新读取当前 caller、tests 和配置来源；本文路径不是跳过现状核验的授权。
- [ ] 先写或定位能反证目标行为的测试，再做最小实现；A 的反例写入证据，功能提交保持绿色。
- [ ] 一个 commit 只完成一个可验证 Milestone 或保持绿色所需的小切片。
- [ ] 优先扩展 `LoopDetector`、现有 execution 返回值、`ConvergenceController` 和 task terminal 路径；不新建重复 scheduler/verifier。
- [ ] 新抽象必须至少服务 conversation/task 两个真实 caller，或保护一个明确跨层不变量。
- [ ] 不顺手重构旧 loop、改英文文案、格式化无关文件或修复 H06/H08/H09。
- [ ] 对 public/跨 crate 类型写清 owner、生命周期、有界值、兼容默认和 fail-safe；内部类型保持最小可见性。
- [ ] 提交前检查 intended path list、`git diff --check`、`git status --short` 和相关测试。
- [ ] 保留用户与并行 agent 的改动；遇到重叠修改时重新读取并协作合并，不 reset 或 checkout 覆盖。
- [ ] 每步本地提交，不推送；commit message/body 写行为变化、未改变边界和准确测试结果。
- [ ] 若源码推翻本文假设，先更新 M0 证据与本清单，再实现等价安全方案；不能静默放宽 typed、bounded、single-reflection 或 non-retryable 约束。

### 14.4 每个 Milestone 的交接格式

- [ ] 用通俗中文列出完成行为、未完成项和明确未做范围。
- [ ] 列出修改文件、关键入口、`MAIN_SHA/A_SHA/BC_SHA`、功能开关及实际默认值。
- [ ] 列出准确命令、通过/失败/跳过数量和退出码；基线失败与新增失败分开。
- [ ] 列出 LLM 请求、工具执行、reflection 和 token 变化；未运行付费实验时明确写“未运行”。
- [ ] 列出证据路径、代码 commit、分析 commit、工作树状态和下一 Milestone 起点。
- [ ] 没有自动化证据的项目不勾选；仅有代码、日志或模型自述都不算完成。

最终交付不是“多了一个循环计数器”，而是可以被自动化反证的这条 contract：

> Octos 只根据可信且有界的状态、证据和验证结果判断进展；同步等价重复先规则止损，语义停滞最多复盘一次，复盘后仍无进展则在所有入口不可自动重试地终止。
