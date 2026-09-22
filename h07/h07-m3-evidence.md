# H07 M3：等价 episode 与策略状态证据

日期：2026-09-23。继续使用 M0 建立的两个 `feat/no-progress` 独立工作树。共同底座 `MAIN_SHA=27d057c206c0f8250b60309905737f7e26ee0ba9`、`A_SHA=8287e8f8ae63a27a58ab5898ecb2753b9b946c45`；M2 代码提交为 `c658ad0a6544c49c231143708bac3ae09cfd284d`。

## 设计与行为

`LoopDetector` 拥有每个 conversation/task run 的 `EpisodeTracker`，不共享全局状态。最多保存 32 个 episode，按最近使用顺序淘汰最久未活跃项；每个 episode 最多保存 4 个摘要样本，观察次数用饱和计数。内部比较完整 SHA-256 摘要及 family/target/status/outcome/error 字段，不使用展示标签或摘要前缀作相等判定。目标展示最多 96 UTF-8 字节，error kind 最多 128 字节，提示最多 320 字节；episode 不保存源码、完整参数、完整输出或绝对路径。淘汰只删除历史，不生成终止决定。

H05 `edit_file`/`diff_edit` 的 `no_match` 与 `ambiguous` 使用 call path、error code、matcher、reason、hunk/expected line、候选行位置及计数、当前文件版本构造稳定事实；adapter 明确忽略尝试文本或 context digest、候选 score/excerpt、limit、耗时与 request ID。只有 matcher 和有效当前版本都存在时才参与语义升级；缺字段和冲突结果降级。已分类的工具 `HarnessError` 使用 variant、recovery、调用目标和可信 `std::io::ErrorKind`；没有稳定 reason 的错误保留精确文本 fallback。provider 错误位于工具观察之前，仍由既有 retry bucket 处理。

同 key 首次只记录；第二次附定向提示；第三次即使调用参数变化也设置 `switch_required` 并附确定性切换提示，不增发模型请求。切换后的不同 observation 记录为一次 probe；原 key 再出现会返回 typed `TerminalNonRetryable` 决定。新位置、当前版本或 expected/actual 改变时返回 `EvidenceChanged`，新 key 可以继续；旧 episode 仍保留，不把旧问题宣告已解决。未知文本只用模型可见文本的精确摘要，不做时间戳清洗或模糊归一化，也不触发语义 terminal。M3 的 terminal 是内部 typed decision；task/spawn 的不可重试传播和实际终止接线由 M5 完成。

共享 `handle_tool_use` 在同步且 call ID 唯一的结果上先按 M2 更新 exact 历史，再消费 typed episode；若两种提示同时到期，使用更具体的语义提示。H03 已登记的结果仍按 M2 通过独立提示行保留原始来源/范围/恢复 envelope。`octos_no_progress_observation_total` 的 label 只包含固定枚举 `family`、`progress_class`、`decision`、`confidence`，不包含路径、参数、错误正文或摘要。

## 验证

代码提交为 `41729c6431669f2d6902875ba187665484ff5838`。

| WSL 验证（`h07-arc` 工作树） | 实际结果 |
| --- | --- |
| `cargo test -p octos-agent --lib h07_m --quiet` | M0-M3 共 31 通过、0 失败 |
| 编译后的 `octos_agent-* loop_detect::tests --quiet` | 26 通过、0 失败 |
| 编译后的 `octos_agent-* agent::loop_runner::tests --quiet` | 152 通过、1 个既有 ignored、0 失败 |
| `cargo test -p octos-agent --test h03_m1_output --test h05_m3_mutation_results --test loop_retry_state --quiet` | 13 + 1 + 10 = 24 通过、0 失败 |
| `cargo check -p octos-cli --no-default-features --features api` | 编译通过，退出码 0 |
| `rustfmt --edition 2024 --config skip_children=true --check`（6 个改动文件） | 无格式差异，退出码 0 |
| `git diff --cached --check`（代码提交前） | 无空白错误，退出码 0 |

定向 fake provider 的 conversation/task 用例各执行 3 次不同参数的 `diff_edit`，实际工具执行 3 次，随后正常 EndTurn；模型请求总数均为 4，累计 input token 为 4，没有 H07 附加请求。第三个请求收到第二次等价结果的定向提示，第四个请求收到 `switch_required` 提示。纯状态测试另覆盖了 typed terminal decision、expected/actual evidence change、候选排序、volatile 字段、完整摘要区分、32 项 LRU 淘汰、4 样本上限、饱和计数及 50,000 次长运行。

所有 WSL 测试均按串行约定执行。发现 H06 测试占用时，先中止尚未完成的本轮 H07 编译并保留会话工作，等待空闲后重新执行；上述表格只记录最终代码上的完整通过结果。

## 后续边界

M4 校准文件变化、read 和 productive grace；M5 接入 live wait、provider retry 隔离和跨 task/spawn 的不可重试终止；M6 引入可选一次复盘。正式 H07 A/B/C 和付费模型实验未运行，本文件不声称官方任务正确率或 token 收益。
