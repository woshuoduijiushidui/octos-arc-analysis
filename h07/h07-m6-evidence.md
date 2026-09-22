# H07 M6：B/C 共用策略梯子与一次复盘证据

日期：2026-09-23。继续使用 M0 建立的两个 `feat/no-progress` 独立工作树。共同底座 `MAIN_SHA=27d057c206c0f8250b60309905737f7e26ee0ba9`、`A_SHA=8287e8f8ae63a27a58ab5898ecb2753b9b946c45`；M5 代码提交为 `66f5506100bd5eee5dfec638f141cfe77a34cd1c`。M6 的 B/C 共用代码提交与冻结点为 `BC_SHA=549e2e880893354bbf8c83a7a53502bad4427ce5`，分支仍为 `feat/no-progress`。

## B/C 配置与共用状态机

M6 没有复制第二套 episode、verifier 或 summary 状态机。`EpisodeTracker` 在第三次同 scope、同稳定 evidence 的 observation 上继续产生已有 `SwitchRequired` 与短提示，同时携带一个有类型的 `request_reflection`。episode 内部的 `reflection_requested` 保证该 episode 最多请求一次，turn-local `LoopDetector` latch 保证同一个 turn 最多接受一个；同一批或后续其他 episode 仍只得到 B 的确定性提示。

唯一配置差异如下。两组都使用相同分支和 `BC_SHA`：

| 策略 | `OCTOS_NO_PROGRESS` | `OCTOS_NO_PROGRESS_REFLECTION` | 行为 |
| --- | --- | --- | --- |
| B | `true` | unset 或 `false` | 消费并丢弃 `request_reflection`，保留附在现有工具结果上的 `SWITCH REQUIRED`；零额外模型请求 |
| C | `true` | `true` | 将同一个 `request_reflection` 转为 `SemanticNoProgress` forced reason，最多执行一次私有复盘 |

`no_progress_reflection` 默认关闭；`no_progress=false` 时不会产生 semantic reflection signal。配置开关只位于 conversation/task 对 `take_semantic_reflection_signal()` 的处理边界，不改变 observation、episode key、提示、terminal 或正常 action call。

真实 loop 测试让 B 和 C 都经历三次 typed no-match。B 的下一次模型请求直接看见原工具结果上的 `SWITCH REQUIRED`，改用 `check` 诊断工具后完成，共 5 次正常请求且 `tool_choice=None` 为 0。C 在同一位置多一次 tools-disabled 请求，随后正常 action request 看见 transient reflection 并改用同一诊断工具，共 5 次正常请求加 1 次 reflection。另一个测试在复盘后重放相同 episode：第四次工具 observation 直接得到 M5 的 non-retryable terminal，第六个 scripted model response 未被请求。

## 共用 checkpoint 路径

conversation 与 task 都调用 `Agent::run_convergence_checkpoint`。helper 统一派生 action config、设置 `tool_choice=None`、限制非 reasoning 输出、调用 silent LLM、记录 token/cost、完成 `ConvergenceController` 并决定继续下一 iteration 或在失败时执行本 iteration 的正常 action。C 没有引入 verifier，也没有第二套 summary prompt。

conversation 继续使用环境配置的 periodic convergence controller。task 使用 `ConvergenceController::semantic_only`，call/token/time 阈值均不参与调度；测试即使给 Agent 设置 2-call/1000-token/10-second convergence intervals，task 仍只有 H07 semantic signal 触发的一次 reflection。成功 reflection 作为既有 typed User-role `convergence_checkpoint` background envelope 注入下一 action request；每轮开头先移除旧 envelope，因此它不会进入持久化 output log、`ConversationResponse.messages`、`TaskResult.output` 或 assistant final，也不具备完成任务的权限。

H07 prompt 请求只发送稳定 system row 和一条有界 User prompt。User goal 最多 800 bytes；episode category、最多 96-byte target label，以及由 status/outcome/error/evidence digest 组成的最多 320-byte typed evidence 明确列出；提示只要求选择一个不同且可验证的动作及其新 observation。请求不复制 conversation/tool-result history。C 测试检查 reflection request 只有两条 message、含 goal/category/typed error、不含工具可见正文。

## 合并、预算与失败边界

`ConvergenceController::force` 不再覆盖前一个 forced reason，而是去重、按 `SemanticNoProgress`、file churn、verified wait、peer polling、periodic 的优先级排序并最多保留 8 个原因。`due()` 会把同轮 pending forced reasons 与已到期的一个 periodic axis 合并成单一 `Combined` reason。单元测试让 semantic、file churn、peer polling 与三次 action-call threshold 同时到期，得到一次四原因 checkpoint，且 typed semantic evidence 位于首位。相关 reason 写入 semantic prompt 前也限制为 320 bytes。

reflection 的 input、output、reasoning、cache-read、cache-write 和 attributed cost 都通过正常 `LoopTurnState` 记账。成功 C 测试分别断言五类 token；controller 另行记录 reflection active-token delta，使真实预算包含费用而 periodic action-token threshold 不把它当 action。失败或空 response 的已消耗 usage 同样由 LLM 边界写入 turn，再从 action threshold 中扣除。

H07 reflection 只有在 iteration 与 token 使用量都低于硬上限的 80% 时调度；到达该边界保留 pending signal 并执行 B 的正常 action。budget grace iteration 无条件跳过 checkpoint。`max_iterations=4` 的回归在第三次失败后证明第四次也是最后一次请求仍用于正常回答，未产生 tools-disabled 请求。

silent checkpoint 调用在局部 `LlmCallPolicy::FailFast` 作用域中执行，因此 agent retry、non-streaming fallback、provider failover 和 hedge 都不会发出第二次请求。空 reflection 测试证明只消费一次 tools-disabled request、usage 仍计入 turn、下一正常 action 继续看见 B 提示。失败只记录 warning，不把失败文字写入 transient context。host 从不解析 reflection 内容或用其重置 episode；episode 只接受后续工具 observation。

带 `AgentVerifierConfig` 的 Agent 在 signal 消费边界明确把 verifier 保留为 M0 选定的唯一复盘所有者。回归中三批 typed failure 各触发 verifier，但 planner 侧 4 次请求全部为正常 action request，没有 H07 `tool_choice=None` 请求。

## WSL 串行验证

所有最终命令均在 `h07-arc` 工作树的 WSL 中串行运行。每条 Cargo 测试或检查前都先执行 `pgrep -a -x cargo` 与 `pgrep -a -x rustc`；检测为空后才开始。本轮没有终止、重启或接管任何 WSL 会话。`octos-agent` 测试继续使用 M5 已验证的低内存 test profile，仅为该 package 设置 `debug=0` 与 `incremental=false`，没有修改仓库 profile、测试逻辑或优化级别。

| WSL 验证（`h07-arc` 工作树） | 实际结果 |
| --- | --- |
| `cargo --config "profile.test.package.octos-agent.debug=0" --config "profile.test.package.octos-agent.incremental=false" test -j 1 -p octos-agent --lib h07_m6 -- --nocapture` | M6 专项 10 通过、0 失败 |
| 同一 profile：`cargo test ... --lib h07_m -- --nocapture` | M0-M6 共 61 通过、0 失败 |
| 同一 profile：`cargo test ... --lib agent::convergence::tests -- --nocapture` | 11 通过、0 失败 |
| 同一 profile：`cargo test ... --lib loop_detect::tests -- --nocapture` | 30 通过、0 失败 |
| 同一 profile：`cargo test ... --lib agent::loop_runner::tests -- --nocapture` | 165 通过、1 个既有 ignored、0 失败 |
| 同一 profile：`cargo test ... --lib agent::llm_call::tests -- --nocapture` | 11 通过、0 失败 |
| `cargo check -j 1 -p octos-agent -p octos-cli` | 编译通过，退出码 0 |
| `cargo fmt --all -- --check` | 无格式差异，退出码 0 |
| `git diff --check` 与 `git show --check BC_SHA` | 无空白错误，退出码 0 |

首次按 package 名称过滤测试时，Cargo 仍串行重建了全部 integration test 可执行文件，耗时 24 分 20 秒；只读进程检查确认 rustc/rust-lld 一直在推进，因此保留原会话等待自然结束。该轮 9 个当时的 M6 测试中 8 个通过，唯一失败是 verifier fixture 预期 4 次、实际按设计调用 3 次的测试断言；修正断言后所有上述最终验证通过，未修改实现来迁就测试。

## 完成结论

B 的额外模型请求为 0；C 对一个 semantic-stalled turn 最多增加 1 次请求。两者共用 observation、episode、hint、terminal、checkpoint helper、代码提交和分支，唯一差异是 `no_progress_reflection` 是否消费 `request_reflection`。M6 不运行正式 A/B/C 付费模型实验；正式矩阵、指标与成本统计仍由后续里程碑执行。
