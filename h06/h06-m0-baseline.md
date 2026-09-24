# H06 M0：共同底座、调用边界与 A 反例

## 版本和范围

- 代码仓库：`feat/verification-repair`；分析仓库：`feat/verification-repair`。开工时两仓库均为干净的 `main`，分别跟踪 `origin/main`，没有未跟踪文件。两次 `git fetch origin main` 后均无主线更新。
- `MAIN_SHA=27d057c206c0f8250b60309905737f7e26ee0ba9`；分析仓库起点 `9c4a9cbf5c43fd11fc2c93c1176c2a033c5ad55d`。
- H02/H03/H05 的已验证 B 依赖来自 `origin/feat/local-edit-strict-match` 中 `origin/main..8287e8f8ae63a27a58ab5898ecb2753b9b946c45` 的 22 个原始提交。该 SHA 是 `origin/main` 的直系后代，代码分支快进到此提交，无重写或冲突。H05 C 的 `bb53c733` strict-match 实验未纳入。H02 状态的末提交为 `9d65681c`，H03 输出恢复末提交为 `4c542e53`，H05 文件修改事实提交为 `384e3279`，H05 B 验证提交为 `8287e8f8`。
- `A_SHA=8287e8f8ae63a27a58ab5898ecb2753b9b946c45`。A 没有 H06 代码或 `OCTOS_VERIFICATION_REPAIR` 开关；验证失败仍直接终止。H03、H05 各自的实验开关仍按其现有默认关闭。M0 新增测试只固定 A，不改变生产路径。
- M0 测试提交为 `25617a27`，只包含两处 Rust 测试文件；A 的生产代码与 `A_SHA` 相同。
- 本机：Windows，Python 3.13.2，Node 24.21.0，工作区内安装的 Rust/Cargo 1.96.1，GNU host `x86_64-pc-windows-gnu`。MCP 反例使用内存中的 `RealSessionDispatch`、`ScriptedLlmProvider`、`SandboxMode::None`、未设置 tool deny policy，`max_iterations=4`；不涉及 HTTP/stdio wire transport。生产 MCP 默认为 Auto sandbox、workspace-write + `ApprovalPolicy::Never`，无 sandbox backend 时拒绝工具运行。实际本机测试二进制为 `D:\projects\arc-bench\octos-arc\target\debug\octos.exe`，`--version` 报告 `octos 2.0.3-rc.11 (8287e8f8)`，SHA-256 为 `10da26218b8a5be87f1bfe40bf0581d16c290a8860f670857c196f93a0c5eedb`。这只是 A 的本机构建，不是 M7 官方实验的最终 B 二进制。

依赖选择依据：H03 的 `OutputPolicy`、有界页和 invocation-local output owner 需要 H02 的消息/文件读取状态；H05 B 提供 typed edit/mutation 结果与真实 `file_modified`。这条依赖链已在 H05 的 M7 记录中通过专项和联合回归；本机仍需对当前 A 重新验证。
H01 的 `TaskEvidenceCapsule` 不在这条 A 分支（源码搜索无此类型），H04 没有独立实施目录；H06 首版不得声称已得到 H01 压缩后契约恢复能力。H02、H03、H05 均在依赖链中，H05 C 的 strict-match 不在其中。

## 实际调用图

```text
MCP tools/call (mcp_server.rs:608)
  -> register TaskSupervisor + SupervisorObserver
  -> RealSessionDispatch::run_session (mcp_serve.rs:492)
     -> Running
     -> parse_arc_agent_task_input (arc_task.rs:171)
        native: 校验 schema、workspace_root、expected_artifact；失败时 provider 请求为零
        legacy: arc_task 缺席时使用 prompt / expected_artifact
     -> factory.build_provider + per-call memory, sandbox, tool policy, Agent
     -> native: system_prompt + Custom arc.agent-task.v1 / execution_params
        legacy: prompt 进 working_memory + Custom(contract, input)
     -> Agent::run_task (loop_runner.rs:2537)
        -> build_initial_messages (memory.rs:249)
        -> loop / provider / tool results
        -> EndTurn: opt-in verifier -> project-root completion validators
           -> workspace contract inspector -> TaskCompleted -> TaskResult
     -> success=false: 直接 Failed，不跑 MCP completion validators / artifact 检查
     -> Verifying -> session-root completion validators (mcp_serve.rs:918)
     -> resolve artifact: expected > policy entry > files_to_send (mcp_serve.rs:953)
     -> required gate -> existence -> native canonical location
        -> <=64 KiB UTF-8 read -> native JSON/schema -> Ready/Failed
  -> dispatch_run_octos_session 最终调用 supervisor.mark_completed/mark_failed
     -> MCP outcome / cost / validator_results / artifact 字段
```

关键区别：native `arc_task` 在 provider/Agent 构造前由 `arc_task.rs:171-230` 验证；legacy prompt 可在 `mcp_serve.rs:503-726` 按旧路径构造。native 需要 workspace-relative `expected_artifact`，且已存在 artifact 必须 canonicalize 到工作区内；legacy 的显式路径可为绝对路径。两条路径都先检查 `TaskResult.success`，再做 MCP 的 completion gate。MCP 的 `validator_results` 来自本次 session-root validator；失败时 artifact 字段为空，正常响应 token cost 从这次 `TaskResult.token_usage` 投影。

`run_task_inner` 在每次调用开始时重新创建 `messages`、`files_modified`、`files_to_send`、`LoopTurnState`、loop detector 和 turn ledger（`loop_runner.rs:2581-2600`）。初始消息由当前 Agent 的系统 prompt、Task working memory、可选 episodic recall、TaskKind 文本组成（`memory.rs:249-318`）。同一个 Agent 的 provider、registry、配置、可选 H02 读取凭据/文件状态、H03 output owner、可选 snapshot manager 与物理工作区可以存活；只有显式配置的 persistent retry state 会跨 `run_task` 合并。首次调用期间的 assistant/tool 消息、累计 usage、iteration 和 `files_to_send` 不会成为第二次 `run_task` 的初始消息。因而第二次调用不满足 H06 的 same-run continuation。

task loop 在 provider 返回后先以 `turn.record_llm_usage` 累计本轮 usage（`loop_runner.rs:2707`）。`EndTurn` 分支没有将此次 assistant response 压入 `messages`；只有 `ToolUse` 的 `handle_tool_use` 会添加 assistant/tool 行（`loop_runner.rs:3152`）。opt-in LLM verifier 在 `loop_runner.rs:2753` 先判定是否允许结束；随后 core 的 project-root validators 与 workspace contract 在 `2842-2854` 执行。`TaskCompleted` 在 `2856` 发出，之后才构造并可能 demote `TaskResult`。MCP session-root completion validators、artifact resolve/location/schema 在 `run_task` 返回之后才运行。于是 A 中 MCP validator/schema 失败时，内部 `TaskCompleted(success=true)` 已经发生；MCP observer 随后给出 `Failed`。B 必须把最终 TaskCompleted 推迟到最终 gate 结果，且不得对每张 RepairTicket 再运行一次 opt-in verifier。

H06 on 的顺序冻结为：一次候选 EndTurn → 现有 opt-in verifier → core project-root validators/contract → MCP completion validator/artifact/schema → typed decision。若 core contract 失败，也要在同一次 task loop 里作 gate decision，不能先构造失败 TaskResult 再重启。H06 off 保持上述 A 顺序和外部 outcome。B 期间只保留外部 `Running`，中间 gate 结果发内部事件；最终确定后外部一次 `Verifying` 和一次 terminal `Ready`/`Failed`/`Cancelled`。`TaskSupervisor::mark_running` 可以覆盖非终态 `VerifyingOutputs`，但终态有保护；MCP 的 `SupervisorObserver` 对 Ready/Failed 不直接提交，最终由 `dispatch_run_octos_session` 提交（`mcp_server.rs:608-660,774-800`）。

## Gate、产物和候选边界

- Core `run_project_root_validators` 枚举 session 下的 policy-managed slides/sites project，在各 project root 运行 completion phase，写入该 root 的 `.octos/validator_outcomes.jsonl`，供 workspace contract inspector 使用（`workspace_contract.rs:680-805`）。MCP `run_completion_validators` 只读 MCP cwd 的 policy，在 cwd 运行 completion phase，repo label 为 `mcp-serve/{contract}`，不挂 ledger（`mcp_serve.rs:918-951`）。通常 root 不同；B 仍须以 canonical workspace root + phase + validator ID/policy 判重，避免同一命令被两层重复执行。两者都可能有命令/工具副作用，不能把旧 ledger pass 当成本次候选通过。
- Artifact 选择顺序为显式 `expected_artifact`、仅当文件已经存在的 policy artifact 直接路径、首个已存在的 `files_to_send`；policy glob 不由 MCP resolve 扩展。只有显式 expected 可返回一个尚未存在的路径并进入 `artifact_missing`；否则无法定位时是 `contract_failed`。`files_to_send` 是 tool 结果收集的路径，不证明文件存在、内容合格或用户可交付。小文本读取上限 65,536 bytes；大文件或无效 UTF-8 返回 `None`，native schema-required 路径失败为 `artifact_schema_invalid`。native 先检查 canonical location，再读 JSON/schema；required validator 失败先于 artifact 检查。
- `SnapshotManager` 默认未附加到 MCP Agent（`agent/mod.rs:581,690,782`；`mcp_serve.rs` 无 `with_snapshot_manager`）。它使用独立 Git object store，因此无 Git 的工作区可以创建快照，且不触碰用户 `.git`；但 `.gitignore` 文件及其 artifact 不被快照/恢复，nested repo 被记录成 gitlink 而非文件，`index.lock` 并发竞争可使快照失败（`snapshot.rs:18-43,324-360`）。restore 先创建 pre-restore 快照，再 checkout/逐文件删除新增非忽略文件；删除错误只记录 warning，不能证明原子恢复（`snapshot.rs:435-555`）。结论：现有 manager 不能保护所有合法 H06 目标。M5 不能据此默认开启 B 或声称“保留最佳候选”；需单独设计完整候选版本机制，或明确限制到可证明隔离的 disposable workspace。
- `TaskResult` 是 durable ABI（`octos-core/src/task.rs`）。M3 优先采用 `run_task_with_completion_gate -> { TaskResult, final_receipt }` 的 invocation-local typed wrapper，返回值同时携带任务结果、候选版本和最终 gate receipt。另一种最小方案是 invocation-local handle：MCP 创建唯一 handle，Agent 写入 receipt，MCP 取回；但它需要生命周期管理，并须防止取消、并发或重试时误读旧 receipt。wrapper 更直接地把 receipt 与返回的候选绑定，不需进程全局/Agent mutable slot。M0 不修改 `TaskResult` schema。H06 on/off 的行为差异留到 M1-M4 实现和测试。

RepairTicket 冻结预算：单张模型可见 UTF-8 总字节不超过 **4,096**，少于 H03 单结果页的 8,192 bytes（`output_recovery.rs:13`）；最多内联 **4** 个失败，单个 stderr tail 最多 **256** bytes，单个 reason 最多 **256** bytes，路径与 evidence ref 各最多 **256** bytes。固定字段（错误码、gate ID、round/max、允许动作、pass 摘要、证据引用）先保留，再按 UTF-8 边界裁剪不可信正文。第 5 个及以后失败只给数量与稳定 ID 摘要；完整证据必须有 invocation-local 可达引用，否则 ticket 明示证据不可用。H03 目前存储的是工具输出，validator evidence 路径尚未自动进入 H03；M1/M4 需要证明引用可达，不能仅在文字中填假引用。

## A 反例与可重放夹具

`crates/octos-cli/tests/mcp_serve_integration.rs` 增加五个 `h06_m0_*` 场景，使用同一个真实 `RealSessionDispatch` 入口和 `ScriptedLlmProvider`。每个有效 EndTurn 的 fake usage 为 input 42 / output 17，只用于检查投影，不能算真实模型 token。五项均实际通过，结果矩阵如下。

| 场景 | provider 请求 | observer | 最终 prefix | validator_results | artifact | cost |
| --- | ---: | --- | --- | --- | --- | --- |
| required FileExists Fail | 1 | Running → Verifying → Failed | `contract_failed:` | `m0-gate=Fail` | 两字段空 | 42 / 17 |
| native artifact missing | 1 | Running → Verifying → Failed | `artifact_missing:` | 空 | 两字段空 | 42 / 17 |
| native schema invalid | 1 | Running → Verifying → Failed | `artifact_schema_invalid:` | 空 | 两字段空 | 42 / 17 |
| required validator Error（缺少 `${args.unavailable}`） | 1 | Running → Verifying → Failed | `contract_failed:` | `m0-gate=Error` | 两字段空 | 42 / 17 |
| 非法 native `expected_artifact=../outside.json` | 0 | Running → Failed | `InvalidParams`，无 outcome | 不适用 | 不适用 | 不适用 |

基线回归和构建记录：

| 命令 | 结果 |
| --- | --- |
| `cargo fmt --all -- --check` | 通过，退出码 0 |
| `git diff --check` | 通过，退出码 0 |
| 在 `arc/` 执行 `python -m unittest discover -s tests` | 231 tests：133 成功、2 失败、87 错误、9 跳过；退出码 1。多为 Windows 临时目录 `EPERM`、Unix 路径预期和本机环境差异。Python 代码与 A_SHA 相同，M0 只新增 Rust 测试，故不是 H06 引入的 Python 回归；不将其记成通过。 |
| `cargo test -p octos-cli --test mcp_serve_integration h06_m0 -- --list` | 列出五项；退出码 0 |
| `cargo test -p octos-cli --test mcp_serve_integration h06_m0` | 5 通过、0 失败，退出码 0；有效反例均为 1 次 provider 请求，非法输入为 0 次。 |
| `cargo test -p octos-agent --lib h06_m0_second_run_task_rebuilds_messages_and_usage` | 1 通过、0 失败，退出码 0；同一 Agent 第二次调用的初始消息不含首轮工具输出/答案，usage 从本次重新累计。 |
| `cargo test -p octos-agent --lib 'agent::loop_runner::tests::run_task_'` | 4 通过、1 忽略，退出码 0。 |
| `cargo test -p octos-cli --test mcp_serve_integration` | 21 通过、2 失败，退出码 1。失败为现有 H03 的 `mcp_output_recovery_is_callable_within_one_invocation` 和 `separate_mcp_invocations_do_not_share_output_recovery_owner`；`output_store.rs` 的 `#[cfg(not(unix))]` 分支明确返回 `RecoveryUnavailable`，本机 Windows 无法满足这两个 Unix 能力假设。生产代码未由 M0 修改；不将整组回归记成通过。 |
| `cargo test -p octos-agent --lib validators` | 70 通过、1 失败，退出码 101。现有 `command_args_interpolate_output_key` 调用 POSIX `test -f`；Windows PATH 无 `test` 时 `program not found`，加入 MSYS `test.exe` 后又因本机信号管道 Win32 error 5 而失败。生产代码未由 M0 修改；不将整组回归记成通过。 |

上述三项现有回归失败是 A 的 Windows 平台/运行环境基线，不由新增测试引起；主分支没有收到本次改动。任何未实际运行的项目保持未勾选；测试文件本身不算通过证据。

### WSL Ubuntu 复核（2026-09-22）

从同一 `feat/verification-repair` 工作树经 `/mnt/d/projects/arc-bench/octos-arc` 运行；Ubuntu WSL2、Rust/Cargo 1.96.1、Python 3.12.3、Node 18.19.1、npm 9.2.0。安装 `build-essential`、CMake、pkg-config、OpenSSL 开发库及 Node/npm 后，设置 `CARGO_TARGET_DIR=$HOME/.cache/arc-bench-h06-target`、`CARGO_PROFILE_TEST_DEBUG=0`、`CARGO_INCREMENTAL=0`，避免把 Linux 产物混入 Windows `target/`。测试前后代码仓库工作树均干净。

| 在 WSL 仓库目录运行的命令 | 结果 |
| --- | --- |
| `cargo test -p octos-cli --test mcp_serve_integration` | 23 通过、0 失败，退出码 0；包含全部五个 M0 反例，以及 Windows 上失败的两项 H03 输出恢复测试。 |
| `cargo test -p octos-agent --lib validators` | 73 通过、0 失败，退出码 0；包含 Windows 上失败的 POSIX `test -f` 场景；另有两个仅在 Unix 编译的测试。 |
| `cargo test -p octos-agent --lib h06_m0_second_run_task_rebuilds_messages_and_usage` | 1 通过、0 失败，退出码 0。 |
| 在 `arc/` 执行 `python3 -m unittest discover -s tests -q` | 408 项、8 跳过、0 失败、0 错误，退出码 0。首次运行缺少 `node` 时失败；安装 Node/npm 后重跑为上述通过结果。 |

因此当前 M0 的 MCP、Agent、validator 和 ARC Python 回归在 Linux 环境可重放通过。Windows 失败保留为平台基线记录，不据此修改 H06 生产路径。

## 官方实验输入冻结状态

预登记 `arc/tasks/arc-bench-web--{12306,bookstack,ctrip,keep,prestashop,stackoverflow}` 与 `ticket-booking--ticket-booking` 七个公开任务；每个 variant 各重复 3 次，交错顺序，独立 workspace/data/session。固定公开测试 476 个文件的树摘要：对按仓库相对路径排序的每个文件，将 UTF-8 路径、NUL、该文件 SHA-256 的 32 字节摘要依次拼入 SHA-256，结果 `29881181f005f16887ff587e8d89e7a92956aea8729a3e700acb6289cacc7939`；`arc/public-tests/manifest.json` SHA-256 为 `61c1e8538b3028de2c19862b9e9878c0bfe2ff348c4031e3abb93a10148c6eec`。

| 任务 | requirements.yaml SHA-256 |
| --- | --- |
| 12306 | `b88713c0be62f3689cae1f7745f44bf556d8f42302e9b259fde50ada7eb44ebf` |
| bookstack | `2fc773dc95d6a8f42203769401e1228539eb958e54e0dcf9522c1dbb43be12e3` |
| ctrip | `39c8b1453aa7fee0b8a969b4cf650cadd2862f8e1ae7d0ac8a6bc8f2d8239da4` |
| keep | `a618ebd4dd96e94996f8424aecf27c7f7ef145325c611ab0faa3f5a4683bba2d` |
| prestashop | `a8b89a68eb46886ecf60f0f688b0264bb2d680c97c7f4f4314482136f616cec1` |
| stackoverflow | `dcf802a82fc40d6d82fae901115be4401b275ce34858f388a9784f3a21b8e124` |
| ticket-booking | `b011cbccccb5ef9290e41cb1a3fb162b321195367eb192bc25e9d430ca05e7fd` |

当前官方 `arc/main.py` 使用 stdio/OUP 的 `turn/start`，并未调用本 M0 的 MCP `run_octos_session`，因此这些官方任务无法在现有入口直接测到 H06 的 MCP 开关。M7 必须先证明相同官方任务会经过 MCP 入口，或明确此项实验不可用于 H06 结论；不得把 Python acceptance loop 的修复收益算作 H06。H05 基线曾采用 `deepseek-v4-flash` 与 `https://api.arc-bench.com/v1`，但本次环境未配置实际模型名、endpoint、`ARCBENCH_API_KEY` 与最终 response schema 产物，也没有 H06 MCP 官方请求预算，因此尚不能把 H05 配置当成已冻结的 H06 实验条件。真实付费实验需在 M6 后另行确认。
