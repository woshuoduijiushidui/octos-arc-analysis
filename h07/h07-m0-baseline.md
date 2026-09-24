# H07 M0：共同底座、调用链与离线反例

日期：2026-09-22。此文件冻结实施前的事实和后续 A/B/C 的共同输入；M0 不启用 H07。代码仓库与分析仓库都从各自最新的 `origin/main` 建了 `feat/no-progress` 独立工作树。原 `feat/verification-repair` 工作树及其未提交文件未改动。

## 版本与依赖

| 项 | 固定值 |
| --- | --- |
| 代码 `MAIN_SHA` | `27d057c206c0f8250b60309905737f7e26ee0ba9`；`git -c http.sslBackend=openssl fetch origin main` 后核对 |
| 分析 `origin/main` | `9c4a9cbf5c43fd11fc2c93c1176c2a033c5ad55d` |
| 代码工作树 | `D:/projects/arc-bench/h07-arc` |
| 分析工作树 | `D:/projects/arc-bench/h07-analysis` |
| 暂定共同底座 `A_SHA` | `8287e8f8ae63a27a58ab5898ecb2753b9b946c45`，从 `MAIN_SHA` 快进，保留 22 个原有 H02/H03/H05 B 提交；不把这些依赖算作 H07 收益 |
| M0 代码测试提交 | `10240be04dc634a9463551a40672595c2b49e2e5`，只新增 3 个离线反例测试，生产代码等同 `A_SHA` |
| M0 `OCTOS_BIN` | `/mnt/d/projects/arc-bench/h07-arc/target/debug/octos`；从 M0 代码提交在该 WSL 工作树执行 `cargo build -p octos-cli --no-default-features --features api --bin octos` 构建，退出码 0 |
| M0 binary SHA-256 | `d31122d7141ae53592a5f6887110d88a809de1f98bd74c96eecab9c72fc2c86e`；WSL `sha256sum` 实测 |
| H05 C 候选 | `bb53c733ff6a40b477e5b6502dcb512a28be32ca`；H05 的最终 S 尚未选定，正式 A/B/C 不可开跑 |

`A_SHA` 的 `loop_detect.rs`、`loop_runner.rs`、`convergence.rs`、`loop_state.rs` 与 `MAIN_SHA` 分别具有相同 Git blob ID；H02/H03 的附加接线在相邻执行和配置模块。H07 的 typed observation、episode、两个 H07 开关均不存在。H02 的文件版本与 receipt、H03 的来源/范围/恢复、H05 B 的 `modified/no_change/no_match/ambiguous` 事实已经在 `A_SHA`；H01 证据胶囊不在此提交链中，仓库无 H04 实施目录。H07 M0 无需移植 H01/H04。H05 C 的 strict match 是独立候选，后续若 S 选择 C，必须先更新共同底座并重验，不沿用本文件的 A 结果。

开工时原代码检出为 `feat/verification-repair`，相对 `origin/main` 超前 23 个未推送提交，`crates/octos-agent/src/lib.rs` 有修改，`completion_gate.rs` 与 `completion_gate_tests.rs` 未跟踪；原分析检出为同名分支，超前 2 个未推送提交、工作树干净。两处原检出均保持原状，H07 的文件只写入上述两个新工作树。

## 真实调用图与责任边界

| 路径 | 当前顺序与边界 |
| --- | --- |
| conversation | `loop_runner.rs` 的 `process_message_inner` 建 `LoopDetector(12)` 与 `ConvergenceController`；调用模型后，`StopReason::ToolUse` 先看 terminal tool，再调用 `record_doom` 和 `record`，检查 shell spiral recovery，才进入 `handle_tool_use`；结果经 `execute_tools` 和 `merge_tool_messages_in_order`，再 `record_result`、`record_file_mutation`、productive 判断。peer/file 信号仅在此入口被取出并强制 convergence；下轮的 `due` 可发 tools-disabled checkpoint。最终响应、max-token continuation、预算和 verifier 各自保留原出口。关键位置：`loop_runner.rs:1076,1095,1392-1490,1733-1846,2071-2128,2441`。 |
| task | `run_task_inner` 建独立 `LoopDetector(12)` 和持久 `LoopRetryState`；`StopReason::ToolUse` 直接进入共享 `handle_tool_use`，再跑 verifier。没有 conversation 同等的 pre-call `record_doom`、`record` 硬拦截，也未消费 peer/file 信号或周期 convergence。EndTurn 可能被 verifier/contract gate 拒绝；MaxTokens 在有界次数内续写；预算结束返回 `TaskResult.success=false`。位置：`loop_runner.rs:2556,2599,2748-2951`。 |
| spawn / MCP | `tools/spawn.rs:2299-2341` 的 `run_task_with_m8_9_recovery` 对 `Err` 或任意 `success=false` 都重新运行一次 task；`classify_child_session_lifecycle_kind` 在 `:665-695` 靠输出字符串是否含 `retry` 等词分类。`session_actor.rs` 也有 M8.9 恢复 prompt 和 spawn-only 失败路径。H07 terminal 将来必须以 typed non-retryable 穿过这些消费者，不能仅写一段可能含 `retry` 的说明。 |
| 工具结果 | `ToolResult` 在 `tools/mod.rs:591` 有 `success`、`file_modified`、`output_document`、`structured_metadata`。`execution.rs:2254-2344` 仍持有这些 typed 事实；`:2454-2513` 才经 H03 envelope 或常规截断、sanitize、hook 反馈形成模型可见消息，并以 call ID 携出 metadata。`handle_tool_use` 当前把 `ToolResult.success` 按 call ID 传入，但 `record_result` 只看最终文本，`record_file_mutation` 只看成功位和参数中的路径；它们没有消费 `file_modified` 或 H05 metadata。 |
| H05 | `mutation_report.rs:160-204` 的 `modified` 包含确认的 `final_version`、变更范围、`file_modified=true`；`no_change` 包含相同最终版本、空修改路径、`file_modified=false`。`edit_file.rs` 和 `diff_edit.rs` 的 no-match/ambiguous 返回 `error_code` 与有限候选事实；`write_file.rs` 也返回 no-change metadata。H05 缺字段的旧工具在 H07 中只能为 unknown，不能由成功文本推断已修改。 |
| 等待 | `peer_gather`/`peer_list` 读 peer blackboard，返回文本快照；`check_background_tasks` 查询 session supervisor，输出 task id/status/active_count，但当前 `ToolResult` 未单独带 live handle。`LoopDetector::record_doom` 对 peer 两工具豁免，`record_result` 对三次同快照发 peer 提示；这不等于证明 handle 仍存活。未来 verified wait 应查询当前 owner 的活句柄。 |
| provider 重试 | LLM 请求或工具执行失败由 `handle_loop_error_with_dispatch` 交给 typed `LoopRetryState`；这是观察工具结果之前的失败桶。`is_productive_tool_message` 影响预算 grace。verifier 配置使 conversation `record_doom` 豁免，但 cycle 和 verifier ledger 仍运行。H07 不能把 provider 失败算任务无进展。 |

## 可重放的 A 反例

1. conversation：现有 `doom_loop_does_not_execute_the_tripping_call` 使用 fake provider 和计数工具，3 次相同模型调用只实际执行 2 次。`record_result` 的 soft hint 阈值为第 3 个**执行后的**同结果，因此该同步路径在 hard guard 提前结束，看不到所宣称的第 3 次 soft hint。`loop_detect.rs:168,264`。
2. task：新增 `h07_m0_task_loop_executes_third_exact_call_without_conversation_guard` 用三次相同工具调用加 EndTurn，断言实际执行 3 次、模型使用量 4 input/4 output；它固定 task 与 conversation 的现状差距。
3. H05 `no_change`：`edit_file.rs:928-955` 的成功结果有 `file_modified=None`、metadata `outcome=no_change`；共享 `handle_tool_use` 却只把 `success=true` 喂给 `LoopDetector::record_file_mutation`。`loop_detect.rs:117-145` 按 path 计数，故 5 次成功 no-op 能触发默认 churn。新增 `h07_m0_successful_no_change_is_counted_as_file_churn` 用 typed no-change fixture 固定当前 detector API 的缺口；M4 须用真实工具补完整回归。
4. 长 read：`is_productive_tool_message` 在 `loop_runner.rs:3589` 对正文至少 128 字节、且不含已知错误词的结果返回 true；追加 `[NO PROGRESS]` 提示后仍满足。新增 `h07_m0_long_repeated_read_with_hint_is_marked_productive` 固定这一缺口。
5. `LoopDetector` 原有测试还覆盖 exact、cycle 2/3、peer 同快照、file churn；`loop_retry_state` 和 `convergence` 各有独立测试。它们是 A 的旧保护，不是 H07 的收益。

## 固定的后续实验输入

候选官方任务固定为本仓库五个公开需求副本及其公开测试：`smoke--counter`、`smoke--dice`、`smoke-evolution--counter`、`smoke-evolution--dice`、`ticket-booking--ticket-booking`。以下是 `A_SHA` 上按此顺序得到的 Git tree OID（需求、测试各一个）；`arc/public-tests/manifest.json` 为 `d5bc5cafe260c34687b7d213613e8551562861bb`。

| 任务 | 需求 tree | 测试 tree |
| --- | --- | --- |
| smoke--counter | `84781bbe2692b130dd3f5090185d04c398ed560d` | `31642fe98dc12a172e061f29f03d9d29311a24e1` |
| smoke--dice | `8e3760b31503308bd45f1fcb046cda492b33f1d9` | `cabfebc0ad384fa206678d353a32c39777259ca2` |
| smoke-evolution--counter | `fb02baa155b53f46c397b33e2f317d24ad6fbbfb` | `d86fb6b46dec67180414c42a676d50928ad09434` |
| smoke-evolution--dice | `eef8d47d223bd81c8603538098c894b63fbbee2c` | `67791f918a1e07c319ee4739a5dc86996cfcada6` |
| ticket-booking--ticket-booking | `ea998d98b53c1e9af2144a351d6cf06fb16cd34c` | `8cf406d85a786b295aa2f54e46ae3a1db89fde08` |

M8 的三个组使用同一 task/test tree、`coding` profile（SHA-256 `89462B8A914B9BA519A3D82AA5AB13CCA731B1A76DFB36DF7675A8FF5771B7B0`，工具名单见 `crates/octos-agent/src/assets/profiles/coding.json`）、单模型 `deepseek-v4-flash`、OpenAI 兼容 provider、endpoint `https://api.arc-bench.com/v1`、`OCTOS_ARC_REASONING=auto`、model routes 关闭、session scope `turn`，每题每组 3 次并交错顺序。共同开关固定为 `OCTOS_LOCAL_EDIT=1`（H05 B）、`OCTOS_OUTPUT_RECOVERY=1`（H03）、`OCTOS_READ_WINDOW=1`（H02）、`OCTOS_FILE_READ_DEDUP=1`、`OCTOS_FILE_CHURN_THRESHOLD=5`、convergence 20 calls / 100,000 active tokens / 300 s；verifier 保持默认配置。预算固定为 `OCTOS_TIME_BUDGET=3600`、`OCTOS_NODE_TIME_BUDGET=3000`、`OCTOS_NODE_TIMEOUT=1200`、`OCTOS_DESIGN_TIMEOUT=420`、`OCTOS_REPAIR_ROUNDS=5`、`OCTOS_MIN_REPAIR_SECONDS=300`、`OCTOS_ARC_MAX_TOTAL_TOKENS_ABS=0`。stdio driver 的瞬时失败重试保持 3 次。另加合成 repeated-read/no-op/equivalent-failure/verified-wait 任务作为反例覆盖，不混入官方通过数。M8 启动前必须再核对平台实际模型、expanded tool schema、官方输入与 H05 S；任何差异另建冻结记录并重跑 A。当前未调用付费模型。

WSL 已运行 `source ~/.zshrc`。工具链：Rust `1.96.1`、Cargo `1.96.1`、Python `3.12.3`、Node `18.19.1`。用户随后说明模型配置在 `~/.bashrc`；非交互 `bash -lc` 不加载其中的 export，交互 `bash -ic` 已核实 `MODEL=OCTOS_MODEL=deepseek-v4-flash`、`OCTOS_ARC_REASONING=auto`、`OPENAI_BASE_URL=https://api.arc-bench.com/v1`，`ARCBENCH_API_KEY` 与 `OPENAI_API_KEY` 均存在，未读取或记录密钥值。此前非交互 shell 的 `OCTOS_BIN`、`OCTOS_PROVIDER`、三项 `OCTOS_CONVERGENCE_*`、`OCTOS_FILE_CHURN_THRESHOLD`、`OCTOS_SESSION_SCOPE`、`OCTOS_LOCAL_EDIT`、`OCTOS_OUTPUT_RECOVERY`、`OCTOS_READ_WINDOW`、`OCTOS_FILE_READ_DEDUP` 均未设置；故这次离线测试中 H03 output recovery、H05 local-edit guidance/typed rejection 为 off，H02 read dedup 为默认 on。H05 的成功修改/no-change metadata 仍可由工具产生，不能仅凭环境开关判断字段存在。正式实验必须以交互 shell 加载凭据，并显式设置上述共同开关。旧 exact hard 阈值 3、cycle 窗口 12；旧 retry bucket 保持 `LoopRetryLimits::default()`。H07 两个建议开关尚不存在，行为为 off。M0 构建产物的路径与 SHA-256 已冻结于上表；未来正式模型实验必须再次记录实际运行的 binary，不能用另一个工作树的 binary 代替。

## M1-M6 的预定边界

初版 episode 只活在当前 conversation/task run，最多 32 个 key，按最旧未活跃项淘汰；每 key 最多保留 4 个有界 observation；内部 key 使用完整稳定 digest，不存源码、完整命令或完整工具输出。展示 target 最多 96 UTF-8 字节，evidence 摘要最多 128，单条提示最多 320；过长时按字符边界截断并携完整 digest 作比较。指标 label 仅固定枚举 `family`、`progress_class`、`decision`、`confidence`、`reflection_status`，不含路径、参数或文本。exact 第 2 次结果提示、第 3 次相同调用前拒绝；等价 episode 第 3 次要求切换；切换后允许 1 次不同 probe；每 episode 和每 turn 各最多 1 次语义复盘。eviction 仅损失优化机会，不允许触发 terminal；unknown 只保留旧 exact/cycle。以上是待实现的数值 contract，M0 没有修改生产行为。

32 个 episode 保留一个 turn 内多个目标的局部历史而不随工具调用数增长；4 个样本恰好容纳首次观察、两次等价结果和切换后的 probe。96/128/320 字节分别约束目标标签、证据摘要和追加提示，避免挤占 H03 的模型可见输出；比较仍用完整 digest，显示截断不参与相等判定。阈值与第 3 次调用前现有 hard guard 对齐，并把 C 的新请求上限限定为每 turn 一次。

枚举值也冻结：`family={read,search,mutate,validate,execute,wait,other}`；`progress_class={validation_improved,state_changed,evidence_changed,verified_wait,no_progress,regressed,unknown}`；`decision={continue,hint,reject,switch_required,reflect,terminal_non_retryable}`；`confidence={typed,trusted_adapter,exact_text_fallback}`；`reflection_status={not_requested,requested,completed,failed}`。生产指标不得添加来自工具文本的值。

## 验证记录

首次 `cargo test -p octos-agent --lib task_loop_executes_third_exact_call_without_conversation_guard -- --exact --nocapture` 使用了不含模块路径的 exact 过滤器，结果为 **0 tests**，退出码 0；此结果不算通过。改用 `cargo test -p octos-agent --lib h07_m0_ -- --list` 确认命中 3 项，退出码 0。等待其他 agent 的 WSL Cargo 运行结束后，在本工作树执行已编译的 `./target/debug/deps/octos_agent-10bd1ddb90ba50f4 h07_m0_ --nocapture`，3 通过、0 失败、退出码 0。

| WSL 命令（均在 `h07-arc`） | 实际结果 |
| --- | --- |
| `./target/debug/deps/octos_agent-10bd1ddb90ba50f4 loop_detect::tests --quiet` | 22 通过，0 失败，退出码 0 |
| `./target/debug/deps/octos_agent-10bd1ddb90ba50f4 convergence::tests --quiet` | 9 通过，0 失败，退出码 0 |
| `./target/debug/deps/octos_agent-10bd1ddb90ba50f4 doom_loop_does_not_execute_the_tripping_call --quiet` | 1 通过，0 失败，退出码 0 |
| `cd arc && python3 -m unittest tests.test_acceptance tests.test_identical_failure_gate tests.test_main_helpers` | 运行 227 项，7 跳过，0 失败，退出码 0；已有 ResourceWarning，不影响结论 |
| `cargo test -p octos-agent --test loop_retry_state --test h05_m3_mutation_results --test h03_m1_output --quiet` | 三个文件依次运行 13、1、10 项，24 通过、0 失败，退出码 0 |
| `rustfmt --edition 2024 --check crates/octos-agent/src/loop_detect.rs crates/octos-agent/src/agent/loop_runner_tests.rs` | 无格式差异，退出码 0 |
| `git diff --check`（代码与分析工作树） | 无空白错误，退出码 0 |
| `cargo build -p octos-cli --no-default-features --features api --bin octos` | WSL 本工作树构建成功，退出码 0；产物及 SHA-256 见上表 |

额外的离线 `octos --version` 检查未执行：自动审批服务返回登录 refresh token 已撤销，无法完成审批。构建和上述测试在此之前均已成功；该命令未作为通过证据。M0 代码仅新增三个用于固定旧行为的离线反例测试；生产逻辑未改。未运行官方任务、付费模型、H07 语义复盘；其请求数、token 变化与正确率变化均为未测量，不能记为零。

M0 尚未自动覆盖 spawn/MCP terminal 传播、真实 H05 编辑工具到 churn 的整条链、live peer/job handle 与 stdio fake-provider 协议；这些分别由 M4/M5/M7 的验收矩阵补上。本阶段的 spawn/MCP/peer 结论来自源码调用链及相邻旧测试，不能当作 H07 新行为的通过证明。
