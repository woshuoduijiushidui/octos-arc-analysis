# H07 M4：文件事实、read 证据与 productive grace 证据

日期：2026-09-23。继续使用 M0 建立的两个 `feat/no-progress` 独立工作树。共同底座 `MAIN_SHA=27d057c206c0f8250b60309905737f7e26ee0ba9`、`A_SHA=8287e8f8ae63a27a58ab5898ecb2753b9b946c45`；M3 代码提交为 `41729c6431669f2d6902875ba187665484ff5838`。

## 设计与行为

H05 mutation observation 现在只在 typed 字段一致、`final_state=confirmed` 且 `final_version.content_sha256` 有效时进入语义进展判断。`outcome=no_change` 或成功结果中的 `file_modified=false` 归类为 `NoProgress`；`outcome=modified` 且确认的最终版本发生变化归类为 `StateChanged`。同一路径、同一 outcome 和同一最终版本使用相同键，不因 `write_version`、formatter 中间结果或 `changed_range` 变化重复计数。`changed_range` 保留为工具报告中的辅助事实，不会创建 validation improvement。未确认最终状态、无效最终版本和 typed 字段冲突均返回 `Unknown`，不产生 churn 或 productive grace。

既有 file churn checkpoint 仍由 `LoopDetector` 所有，但 H07 开启时只消费 `StateChanged`；no-op、重复最终版本和 unknown 不增加计数。确认的连续不同最终版本仍可触发原 checkpoint，checkpoint 不改变 semantic episode 的 terminal 状态。H07 关闭时继续使用原来的成功 mutation 计数路径，保持 A 行为。

可信 read adapter 使用文件 source target、完整 SHA-256 版本和可见范围构造稳定键。`read_file` 与 H03 `recall` 即使调用参数不同，只要引用同一文件版本和同一范围就归入同一 episode；范围前进或文件版本变化记 `EvidenceChanged`。H03 recall search 使用已知 JSON producer 的 output ID、stream、query 摘要、搜索范围、命中起止坐标和完成状态；snippet、limit、耗时及控制字段不参与相等判断。新搜索页或新命中坐标是新证据，相同坐标的展示文本变化不会伪造进展。search adapter 只在 `recall` 的成功 search 调用上解析固定 producer schema，不把任意工具正文当成状态。

共享 `handle_tool_use` 保存每个 call ID 的 `ProgressClass`，同一个判定同时驱动 churn 和 budget grace。H07 开启且 observation 具有 typed 或可信 adapter 事实时，只有 `StateChanged` 与 `EvidenceChanged` 调用 `record_productive_tool_call`；`NoProgress` 和 `Unknown` 不会因为长输出、`Exit code: 0` 或追加 H07 hint 后超过 128 字节获得 grace。没有 authoritative observation 的旧工具继续走原文本 heuristic。conversation 的真实预算测试证明 no-change 在两次 action call 后停止，而两个不同最终版本获得一次现有 grace 并正常消费第三个 EndTurn；没有新增模型请求类型。

## 验证

代码提交为 `ba39ec5a2973dcf1ab4ed0bfd52615c33091415a`。

| WSL 验证（`h07-arc` 工作树） | 实际结果 |
| --- | --- |
| `cargo test -p octos-agent --lib h07_m4 --quiet` | M4 专项 9 通过、0 失败 |
| `cargo test -p octos-agent --lib h07_m --quiet` | M0-M4 共 40 通过、0 失败 |
| `cargo test -p octos-agent --lib loop_detect::tests --quiet` | 27 通过、0 失败 |
| `cargo test -p octos-agent --lib agent::loop_runner::tests --quiet` | 155 通过、1 个既有 ignored、0 失败 |
| H02 M1-M3、H03 M1/M2/M3/M7、H05 M2-M6 的 12 个 integration targets | 合计 45 通过、0 失败 |
| `cargo fmt --all -- --check` | 无格式差异，退出码 0 |
| `cargo check -p octos-cli --quiet` | 编译通过，退出码 0 |
| `git diff --check`（代码提交前） | 无空白错误，退出码 0 |

专项测试覆盖：no-change、仅 `file_modified=false`、相同最终版本、formatter 后不同最终版本、未确认状态、typed 冲突、read 同页/下一页/新版本、H03 recall 跨入口同源分页、search 相同坐标与新命中、churn 只消费不同确认版本，以及 typed 结果覆盖文本 productive heuristic。真实 `process_message` 用例同时覆盖长成功正文、`Exit code: 0`、追加 H07 hint 后的长度反例与有效 state change 的 grace 正例。

所有 WSL 命令均串行执行。开测前发现另一项 H06 `cargo test` 和 `rustc` 正在占用 WSL，本次没有终止它们或结束会话；等待进程自然退出后才开始 M4 格式化、测试和编译检查。

## 后续边界

M4 只负责文件/read/search 的进展事实以及 churn/grace 消费。typed terminal 的 conversation/task/spawn 传播、verified wait 和 provider retry 隔离仍由 M5 完成；本文件不声称已运行正式 H07 A/B/C 或付费模型实验。
