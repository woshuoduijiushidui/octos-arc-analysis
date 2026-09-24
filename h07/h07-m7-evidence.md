# H07 M7：真实入口、观测、回归和 BC_SHA 冻结证据

日期：2026-09-23。继续使用 M0 建立的两个 `feat/no-progress` 独立工作树。共同底座为 `MAIN_SHA=27d057c206c0f8250b60309905737f7e26ee0ba9`、`A_SHA=8287e8f8ae63a27a58ab5898ecb2753b9b946c45`；M6 代码提交为 `549e2e880893354bbf8c83a7a53502bad4427ce5`。M7 冻结后的 B/C 共用代码提交为 `BC_SHA=e8d5af2d064cb36f13ab95a814ce44202533d2ac`，分支仍为 `feat/no-progress`。

## 最小观测与安全边界

H07 使用独立、固定且低基数的 metrics。调用者只传静态枚举值；指标层由 `catch_unwind` 隔离，recorder panic 不改变 Agent 结果。任何指标均不接收工具参数、路径、命令、源码、provider 输出或凭据。故障注入测试刻意让 recorder 闭包 panic，panic 被吸收且控制流继续；测试输出会显示 panic hook 文本，但测试本身通过。

| 指标 | 固定 label/value |
| --- | --- |
| `octos_no_progress_observation_total` | `family={read,search,mutate,validate,execute,wait,other}`、`progress_class={validation_improved,state_changed,no_progress,evidence_changed,verified_wait,regressed,unknown}`、`decision={continue,hint,switch_required,terminal_non_retryable}`、`confidence={typed,trusted_adapter,exact_text_fallback}`、`reflection_status={requested,not_requested}` |
| `octos_h07_episode_total` | 无 label；只在新 episode/baseline 建立时增加 |
| `octos_h07_tool_execution_total` | 无 label；在 approval、policy 与 hook 通过后、实际调用 registry 前增加；pre-call reject 不计执行 |
| `octos_h07_decision_total` | `decision={pre_call_reject,hint,switch,terminal}` |
| `octos_h07_reflection_total` | `status={requested,completed,failed}` |
| `octos_h07_reflection_tokens_total` | `kind={input,output,reasoning,cache_read,cache_write}` |
| `octos_h07_terminal_total` | `mode={conversation,task}`、`retryable=false` |

provider retry 继续使用既有 `octos_loop_retry_total`；schema 测试明确断言 H07 terminal metric 与该名称不同。H07 没有扩展或复用 harness progress event。task terminal 继续使用 `TaskResult` v1 的 optional `failure={code:"h07_terminal_non_retryable",retryable:false}`，未修改 schema version；conversation terminal 直接结束当前 turn。

`check` 工具新增 additive `structured_metadata.validation`，仅实际运行且退出成功或产生可解析 diagnostic 时给出：`schema="octos.validation.v1"`、`adapter="check"`、`ran=true`、整数 `errors/warnings`。H07 只信任该 producer/schema，不解析普通输出中的 “tests passed”。同一 target 的 `(errors,warnings)` 按错误数优先、警告数次之比较；改善结束相关 validation episode 并建立新 baseline，回退建立新 baseline 但不记 productive。无关成功 read 不会清除已有 validation stall。

## 冻结开关、阈值与输入

| 项目 | 冻结值 |
| --- | --- |
| B | `OCTOS_NO_PROGRESS=true`；`OCTOS_NO_PROGRESS_REFLECTION` unset/`false` |
| C | `OCTOS_NO_PROGRESS=true`；`OCTOS_NO_PROGRESS_REFLECTION=true` |
| A/off | `OCTOS_NO_PROGRESS` unset/`false`；reflection 开关单独开启也不会建立 H07 episode |
| exact 同步重复 | 第 2 个相同实际结果附 hint；第 3 个相同调用在执行前拒绝；实际执行数为 2 |
| typed semantic episode | 第 1 次建立 baseline，第 2 次 hint，第 3 次 switch；switch 后同 episode 再现即 non-retryable terminal |
| 状态上限 | 32 个 episode；每个 episode 4 个 sample；hint/evidence 320 bytes；target label 96 bytes |
| reflection 上限 | 每 episode 1 次、每 turn 1 次；goal 800 bytes；related reason 320 bytes；最多合并 8 个 reason |
| reflection 预算 | iteration 与 input+output+cache token 均严格低于硬上限 80%；grace iteration 不运行 reflection |
| loop window | 12；旧 cycle 2/3 与 shell spiral 仍先走原有恢复路径 |
| task ABI | `TASK_RESULT_SCHEMA_VERSION=1`；terminal code `h07_terminal_non_retryable`；`retryable=false` |
| validation producer | `octos.validation.v1` / `adapter=check` / `ran=true` / unsigned `errors,warnings` |

M0 冻结的五个官方任务及公开测试未改动；`A_SHA..BC_SHA` 没有 `arc/tasks/`、`arc/public-tests/` 或 manifest diff。因此继续使用 M0 记录的十个 tree OID，`arc/public-tests/manifest.json` 仍为 `d5bc5cafe260c34687b7d213613e8551562861bb`。本里程碑未运行付费模型或正式 A/B/C 实验。

构建命令为 `cargo build -j1 -p octos-cli --no-default-features --features api --bin octos`。冻结二进制为 `h07-arc/target/debug/octos`，大小 `1,118,898,544` bytes，SHA-256 为 `7990d3c22aa806728b374da75e15ffea400a712ace89dcd05335c10ea5b5ad1c`。

## T01-T24 验收矩阵

以下 24 项均有自动化覆盖，没有把必测项标为不适用。

| ID | 自动化证据与结果 |
| --- | --- |
| T01 | `h07_m0_task_loop_executes_third_exact_call_without_conversation_guard` 固定 off 行为；配置默认测试和 `A_SHA..BC_SHA` 审计确认 observation/terminal 分支受开关控制，off 时保持 A 的请求、执行和结束路径。 |
| T02 | `h07_m2_conversation_hints_then_rejects_whole_batch_before_execution` 通过：真实 `process_message` 第 2 次提示、第 3 次 pre-call reject、工具仅执行 2 次。 |
| T03 | `h07_m2_task_uses_same_hint_and_pre_call_guard` 通过：真实 `run_task` 与 conversation 同语义并有界结束。 |
| T04 | `h07_m2_alternating_cycle_keeps_two_stage_recovery`、`h07_m2_shell_spiral_recovery_precedes_exact_rejection` 通过。 |
| T05 | `h07_m4_final_version_owns_mutation_progress_and_no_change_stalls`、`h07_m4_no_change_long_success_gets_no_budget_grace` 通过。 |
| T06 | `h07_m4_distinct_final_versions_remain_productive` 与 churn distinct-version 测试通过。 |
| T07 | `h07_m4_unconfirmed_and_conflicting_mutations_stay_unknown` 通过；冲突仅记录计数诊断。 |
| T08 | `h07_m3_typed_episode_ignores_volatile_attempts_and_switches_once` 通过：参数抖动聚合为同一 typed episode。 |
| T09 | 同一 M3 测试改变 request ID、duration、excerpt、candidate score 等 volatile 字段，episode 不重置。 |
| T10 | `h07_m3_expected_actual_change_is_new_evidence_at_same_location` 与 candidate ranking 测试通过。 |
| T11 | `h07_m4_read_pages_use_source_range_and_version_evidence` 和 H03 rendered-view/recall 回归通过。 |
| T12 | `h07_m7_trusted_validation_improvement_and_regression_are_directional` 通过；改善 productive，回退不 productive。 |
| T13 | `h07_m7_plain_tests_passed_text_is_not_trusted_validation_progress` 通过。 |
| T14 | `h07_m7_unrelated_successful_read_does_not_clear_validation_stall` 通过：插入可信 read 后第三次相同 validation 仍进入 switch。 |
| T15 | `h07_m5_live_handle_uses_bounded_wait_reflection_without_restarting_task`、peer changed/unchanged 测试通过。 |
| T16 | `agent::llm_call::tests` 11/11、`loop_retry_state` 及 policy 回归通过；H07 metric 与 provider retry metric 分离。 |
| T17 | 完整 loop runner 165 通过、1 个既有 ignored；另有 `spawn_only_interrupt_cancellation` 2/2，通过 approval、cancel、steer、verifier 生命周期。 |
| T18 | M6 C conversation/task 测试与真实 stdio fixture 通过；每 episode/turn 一次，五类 usage 入账。 |
| T19 | M6 empty reflection、near-limit、combined periodic/convergence、FailFast 测试通过；失败不重试且正常 action 继续。 |
| T20 | `h07_m6_same_episode_is_terminal_after_its_single_reflection` 通过；未请求预置的后续模型响应。 |
| T21 | M5 task terminal、typed child terminal、M8.9 recovery 及 spawn lifecycle 回归通过；typed non-retryable 不恢复。 |
| T22 | M1 parallel duplicate ID、serial failure+blocked sibling、limited batch positional alignment 测试通过。 |
| T23 | UTF-8 bounded label、32-entry LRU、长 run 测试通过；真实 stdio 使用 118-byte Unicode target，捕获文件仅存消息哈希与固定 shape。 |
| T24 | ARC Python `test_acceptance`、`test_identical_failure_gate`、`test_main_helpers` 共 227 通过、7 跳过；覆盖 failure signature、identical gate、换策略、no-improvement stop 与 best-state restore。 |

真实入口覆盖不是 detector-only：T02/T18 使用 `process_message`，T03/T18/T20 使用 `run_task`，T21 使用真实 spawn recovery 与 child lifecycle。H02 receipt、H03 output/recall、H05 mutation、peer polling、convergence、provider retry 和 spawn 入口均在本轮重新回归。

## 真实 stdio + fake provider

新增 `arc/integration/no_progress_m7.py`，通过真实 `octos serve --stdio --solo` 和 `OctosStdioSession` 运行，provider 是本机 loopback OpenAI-compatible fake，usage 字段为合成值，不读取用户密钥且不会计费。runtime/data 使用 WSL `/tmp`，测试 workspace/evidence 位于工作树的 ignored `target/h07-m7-stdio-evidence/`。

fixture 对 118-byte Unicode 相对路径发出三次 typed edit no-match，随后 C 执行一次 tools-disabled reflection，再由下一次正常 action 改用 `read_file` 并结束。最终断言和证据为：

- provider 请求 6 次，其中正常 action 5 次、reflection 1 次；reflection 位于请求索引 3，`tool_choice="none"`。
- reflection 请求只有 system+user 两行，保留工具 schema，包含有界 `mutate/no_progress` 事实。
- 实际工具执行 4 次：3 次 edit、1 次 diagnostic read；四个 tool call ID 均唯一，目标文件保持不变。
- 最终请求捕获 11 个 message role、13 个可用工具名、4 个 tool result；没有 `turn/error` 或 terminal 重复执行。
- 请求捕获文件只保存 message SHA-256、role、tool 名和 choice，不保存完整消息、参数、源码或绝对路径；同目录 workspace 仅含合成 fixture 文本。
- 最终输出：`PASS: real stdio emitted one tools-disabled reflection, executed four tools, and completed after a strategy switch.`

## WSL 串行验证

所有 WSL 命令均串行执行；每项 Cargo 测试、构建或检查前均先运行 `pgrep -a -x cargo` 与 `pgrep -a -x rustc`，确认为空后开始。本轮没有终止、重启或接管其他 WSL 会话。

| 验证 | 实际结果 |
| --- | --- |
| `cargo ... test -j1 -p octos-agent --lib h07_m7 -- --nocapture` | M7 专项 5 通过、0 失败；故障注入的 panic hook 文本为预期 |
| `cargo ... test -j1 -p octos-agent --lib h07_m -- --nocapture` | M0-M7 共 66 通过、0 失败 |
| `cargo ... test -j1 -p octos-agent --lib agent::convergence::tests -- --nocapture` | 11 通过、0 失败 |
| `cargo ... test -j1 -p octos-agent --lib loop_detect::tests -- --nocapture` | 30 通过、0 失败 |
| `cargo ... test -j1 -p octos-agent --lib agent::loop_runner::tests -- --nocapture` | 165 通过、1 个既有 ignored、0 失败 |
| `cargo ... test -j1 -p octos-agent --lib agent::llm_call::tests --quiet` | 11 通过、0 失败 |
| `cargo ... test -j1 -p octos-agent --lib should_run_fake_checker_and_render_diagnostics -- --nocapture` | 1 通过、0 失败；断言 validation schema/adapter/count |
| `loop_retry_state`、H02 M2/M3、H03 output/recall、H05 mutation/observability、spawn envelope/recovery 共 9 个 integration targets | 合计 45 通过、0 失败 |
| `cargo test -j1 -p octos-agent --test spawn_only_interrupt_cancellation --quiet` | 2 通过、0 失败 |
| `cd arc && python3 -m unittest tests.test_acceptance tests.test_identical_failure_gate tests.test_main_helpers` | 227 通过、7 跳过、0 失败；仅有既有 ResourceWarning |
| `cargo check -j1 -p octos-agent -p octos-cli` | 编译通过，退出码 0 |
| `cargo fmt --all -- --check` | 无格式差异，退出码 0 |
| `cargo build -j1 -p octos-cli --no-default-features --features api --bin octos` | 构建通过；二进制哈希见上文 |
| 真实 stdio fixture | 通过；6 请求、4 次实际工具执行、1 次 reflection |
| `git diff --check`、`git diff --cached --check`、`git show --check BC_SHA` | 无空白错误，退出码 0 |

额外运行 `cargo test -j1 -p octos-arc --lib --quiet` 得到 129 通过、2 个既有 ignored、1 个失败。唯一失败是 `codegen::tests::should_build_the_compact_prompt_with_size_rule_and_port_clause`：Windows worktree 将 `arc/prompts/codegen-prompt.md` 检出为 CRLF，而测试固定断言模板以 LF 开头。临时只把该文件转成 LF 后，原失败用例 1/1 通过；随后恢复文件且未提交行尾变化。H07/ARC Python 回归均无新增失败。

开发中还修正了三项测试基础设施问题：将 `h07_metrics` 可见性调整到 agent crate、把实际匹配 0 个测试的 checker 过滤器改为精确测试名、将 stdio runtime 从不支持 Unix socket 的 `/mnt/d` 移到 WSL `/tmp`。最终表格只记录确实命中且通过的运行。

## 兼容与范围审查

`A_SHA..BC_SHA` 只包含 `octos-agent` 的 H07 observation/loop/convergence/execution、spawn terminal 消费，`octos-core` 的 M5 additive optional failure ABI，两份既有 ABI/architecture 文档，以及 M7 离线 stdio fixture。没有 H06/H08/H09、官方 task/test/manifest 或无关 ARC 生产路径。M7 自身新增的 `check` metadata 为 additive producer fact；H07 off 时不消费它来改变请求、工具执行或终止行为。

B/C 使用同一 `BC_SHA`，唯一差异仍为 reflection 开关。B 不增加模型请求；C 对一个停滞 turn 最多增加一次 tools-disabled 请求。关闭 `OCTOS_NO_PROGRESS` 后回到 A 的既有 exact/cycle/shell 行为，且不关闭 provider retry、H02、H03 或 H05 保护。M7 不宣布正式模型收益，A/B/C 付费对照仍留给 M8。
