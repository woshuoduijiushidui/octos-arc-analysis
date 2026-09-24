# H07 M5：verified wait、retry 隔离与不可重试终止证据

日期：2026-09-23。继续使用 M0 建立的两个 `feat/no-progress` 独立工作树。共同底座 `MAIN_SHA=27d057c206c0f8250b60309905737f7e26ee0ba9`、`A_SHA=8287e8f8ae63a27a58ab5898ecb2753b9b946c45`；M4 代码提交为 `ba39ec5a2973dcf1ab4ed0bfd52615c33091415a`，M5 代码提交为 `66f5506100bd5eee5dfec638f141cfe77a34cd1c`。

## verified wait

共享执行聚合边界只从两个已声明的异步表面提取 handle：`spawn_only` 工具返回的受控 JSON envelope，以及 `read_task_output.task_handle`。两者都必须再由 `TaskSupervisor` 确认状态为 `Spawned` 或 `Running`，才构造 `VerifiedWait` observation。completed、failed、cancelled、parked、缺失和不可解析的 handle 不获得例外，继续使用各自真实工具结果形成 completed、failed 或 unknown observation。

运行时确认存活的 handle 使用 handle 与 supervisor 状态组成有界 wait key，工具可见结果组成 evidence。相同 handle、相同状态与相同结果连续三次时复用 convergence 的 tools-disabled checkpoint，提示模型停止 busy-wait、做独立工作或采用 bounded wait；状态或结果变化记新证据。conversation/task 的通用 exact pre-call guard 会跳过当前仍存活的 handle，结果后也不会建立同步 exact terminal 历史，因此一次读取超时或未变化 observation 不会停止或重启原任务。task 没有普通 convergence 调用，仍受既有 task iteration/budget 上限约束。真实 `process_message` 测试确认三次 unchanged read 只触发一次 reflection，后台任务保持 `running`，随后仍由模型给出最终结果。

peer polling 保持独立已有路径；完整 loop runner 回归继续覆盖 changed third result、unchanged snapshot reflection、变化后阈值重置和最终模型结果。H07 不用一个通用 exact 特例替换 peer 语义。

## retry 与 lifecycle 隔离

provider 的 rate limit、network、stream 和 context 失败仍在 `LoopRetryState`/LLM 调用层计数；H07 episode 只消费工具 observation。`record_productive_tool_call` 只增加 budget grace 资格，不修改任何 provider retry counter。回归测试在记录 rate-limit 后插入成功 read，确认 bucket 计数不变；完整 retry-state 测试覆盖既有 provider/context 决策。

policy deny、session limit/cancel placeholder 和非可信结果保持 blocked/unknown，不进入 semantic episode。approval pending 与 approval policy error 在共享工具处理函数中提前返回，不创建 H07 hint；semantic terminal 在 conversation/task 中均先于 verifier 调用返回。相同结果同时满足 exact 与 semantic 检查时只追加一个 hint。完整 loop runner 回归覆盖 approval、verifier、peer、budget 和既有终止路径。

`terminal_non_retryable` 现在通过内部 `H07Terminal` 单向传播，稳定失败码为 `h07_terminal_non_retryable`。用户只看到有界短文本，包含 operation family、目标标签、策略变化后仍无新证据这三个已观察事实。conversation 在收到 terminal 后直接结束当前 turn，不再调用 verifier、模型或工具；测试以四个语义等价但参数变化的 no-match 结果触发 terminal，并证明第五个 scripted response 未被请求。

task 返回 `success=false`，并携带 `TaskFailure { code, retryable: false }`。`TaskResult` v1 只增加 `#[serde(default, skip_serializing_if = "Option::is_none")]` 的 optional `failure` 字段，没有修改 `TASK_RESULT_SCHEMA_VERSION`；所有 Rust 构造者、re-export、架构/ABI 文档和旧 payload 兼容测试均已更新。M8.9 recovery 仅对 error、无 typed identity 的旧失败或显式 `retryable=true` 失败执行一次恢复；H07 terminal 原样返回。child lifecycle 优先读取 typed failure，`retryable=false` 即使输出正文含 `retry` 也稳定分类为 `TerminalFailed`，不再依赖英文关键词覆盖 typed 事实。

## 验证

所有最终通过命令均在 WSL 中串行运行。`octos-agent` 单元测试 crate 较大，为避免已经观察到的并行 rustc OOM，最终 agent 测试固定 `-j 1`，并仅通过 Cargo `--config` 为 `profile.test.package.octos-agent` 设置 `debug=0`、`incremental=false`；没有修改仓库 profile、测试逻辑或优化级别。

| WSL 验证（`h07-arc` 工作树） | 实际结果 |
| --- | --- |
| `cargo --config "profile.test.package.octos-agent.debug=0" --config "profile.test.package.octos-agent.incremental=false" test -j 1 -p octos-agent --lib h07_m5 -- --nocapture` | M5 专项 11 通过、0 失败 |
| 同一 profile：`cargo test ... --lib h07_m --quiet` | M0-M5 共 51 通过、0 失败 |
| 同一 profile：`cargo test ... --lib loop_detect::tests --quiet` | 29 通过、0 失败 |
| 同一 profile：`cargo test ... --lib agent::loop_runner::tests --quiet` | 158 通过、1 个既有 ignored、0 失败 |
| 同一 profile：`cargo test ... --lib agent::loop_state::tests --quiet` | 20 通过、0 失败 |
| 同一 profile：`cargo test ... --lib tools::spawn::tests --quiet` | 96 通过、1 个既有 ignored、0 失败 |
| 同一 profile：`cargo test ... --lib run_task_with_m8_9_recovery --quiet` | 2 通过、0 失败 |
| 同一 profile：`cargo test ... --lib classify_child_session --quiet` | 1 通过、0 失败；M5 typed terminal 正例另计入专项 11 项 |
| `cargo test -j 1 -p octos-core --lib task::tests --quiet` | 21 通过、0 失败 |
| `CARGO_INCREMENTAL=0 cargo check -j 1 -p octos-agent --lib` | 编译通过，退出码 0 |
| `CARGO_INCREMENTAL=0 cargo check -j 1 -p octos-cli --bin octos --quiet` | 编译通过，退出码 0 |
| `cargo fmt --all -- --check` | 无格式差异，退出码 0 |
| `git diff --check`（代码提交前） | 无空白错误，退出码 0 |

测试开始阶段多次发现另一条 `cargo build -p octos-cli --bin octos` 在同一 WSL 中运行，并确认其结束发行版时会使等待中的 bash 返回 `Input/output error`。本次没有终止、重启或接管该会话；停止自己的 Cargo，等待外部构建自然结束并观察持续空闲后才完成上述串行验证。

## 后续边界

M5 只接通已存在的 M3 typed terminal，并把合法 runtime wait、provider retry 和任务停滞分开。M6 的 B/C 共用策略梯子、每 episode/turn 至多一次 semantic reflection 以及 task reflection 共享仍未实现；本文件不声称已运行正式 H07 A/B/C 或付费模型实验。
