# H07 M1：typed observation 证据

日期：2026-09-22。代码与分析工作树均为 `feat/no-progress`；共同底座及 M0 反例见 [h07-m0-baseline.md](./h07-m0-baseline.md)。M1 仅采集事实，不作提示、拒绝、复盘或终止决定。

## 接线与边界

`agent/execution.rs::spawn_tool_task` 在拆解 `ToolResult`、H03 渲染和字符串清洗前调用 `ObservationFacts::from_result`。工具抛错时沿既有 `HarnessError::classify_report` 取 variant；工具正常返回但 `success=false` 时优先取 H05 的 typed `error_code`。`finish` 只用最终模型可见文本计算 exact 摘要；若 H03 已登记当前、唯一且摘要一致的文件视图，则使用 `OutputSource::File` 的版本及实际 `visible_ranges` 形成证据。普通 read 还需匹配本次 `output_id`；recall 可复用历史 `output_id`，但相同 call ID/可见内容对应多个登记项时回退到 exact 摘要。失败结果不采用文件视图作强来源。

`execute_tools` 将 observation 与 `ToolCallResult` 一起按原调用顺序回收，包含并行、串行、超时、取消和 preflight 阻断。`handle_tool_use` 跨拆分批次按位置合并，按原始调用序列插入 session-limit 的 blocked observation。重复 call ID 不用哈希表重关联；若重复 ID 令 H03 read 来源有歧义，仅 read 来源降级为 exact。conversation 与 `run_task` 均走此共享入口。审批挂起尚未执行工具，M1 不伪造工具事实。

内部 `ProgressObservation` 只保存用于当前批次关联的临时 call ID、固定枚举、目标和证据的 SHA-256、最多 96 字节的 UTF-8 basename、最多 128 字节的错误类别，以及可选的已验证文件版本；不保存完整参数、源码、输出、绝对路径、候选列表或任意 detail。call ID 不写入后续 episode 状态。未知工具严格为 `other`。H05 `modified/no_change/no_match/ambiguous` 来自 `file_modified`、typed outcome 或 error code；字段互相冲突时 outcome/state 为 unknown，并按批次计数记入 debug 诊断。`validation_key` 和 `wait_key` 在 M1 恒空；普通 shell 文本不能生成验证事实或 live handle。

M1 observation 不进入模型消息、`ToolResult`、现有 loop/retry/convergence 决策或 metrics，也不产生额外 provider 请求。H07 总开关尚未接线，其关闭状态保持 M0 生产决策。M2-M6 才消费这些观察值；M7 将定义正式指标与真实入口验收。

## 验证

代码提交：`38c607cd0a54482e95bec2a3a9e13871d97379fe`。第一次编译测试文件时误用了不存在的辅助函数，编译失败；已改为现有 `session_limit_message` 并在最终测试中通过。最初 `cargo test -p octos-agent --lib h07_m1_ -- --list` 确认过滤器命中 8 项，之后新增 read/recall 两项真实登记测试；最终 `cargo test -p octos-agent --lib h07_m -- --nocapture` 运行 13 项（M0 3、M1 10），全部通过、退出码 0。

| WSL 验证（`h07-arc` 工作树） | 结果 |
| --- | --- |
| `cargo test -p octos-agent --lib h07_m -- --nocapture` | 13 通过、0 失败，退出码 0 |
| `cargo test -p octos-agent --test h03_m1_output --test h05_m3_mutation_results --test loop_retry_state --quiet` | 13 + 1 + 10 项，共 24 通过、0 失败，退出码 0 |
| `./target/debug/deps/octos_agent-10bd1ddb90ba50f4 agent::execution::tests --quiet` | 44 通过、0 失败，退出码 0 |
| `./target/debug/deps/octos_agent-10bd1ddb90ba50f4 agent::loop_runner::tests --quiet` | 143 通过、1 忽略、0 失败，退出码 0 |
| `rustfmt --edition 2024 --config skip_children=true --check`（6 个改动文件） | 无格式差异，退出码 0 |
| `git diff --cached --check` | 无空白错误，退出码 0 |

H03/H05/retry 与执行器/主循环回归先于最后一处只读 `lookup_unambiguous` 接线运行；最终 13 项 M0/M1 测试在该接线后重新编译并通过，其中包括 read 与 recall 真实登记入口及歧义降级。新增查找不改变 H03 原有的 `lookup`、渲染或恢复逻辑。

这些离线测试覆盖 H05 typed/缺字段/冲突字段，H03 read/recall source/view/range，错误代码与文本隔离，Unicode 和长标签，未知工具，重复 call ID、并行/串行批次和 blocked placeholder。没有运行付费模型或官方 A/B/C 实验；token、正确率与策略切换收益尚未测量。

## 尚未覆盖

审批挂起后的人工恢复工具执行不经过本次普通工具批处理；M1 不将其占位消息当作已执行工具观察。真实文件编辑后跨轮的版本去重、live peer/job handle、授权 validator、spawn/MCP terminal 传播、H07 off 的整轮 byte parity 与正式指标，分别由 M4-M7 的专项验收处理。本阶段只证明 observation 旁路和当前离线回归，不声称这些后续行为已经实现。
