# H07 M2：exact 重复顺序与双入口证据

日期：2026-09-23。代码与分析继续使用 M0 建立的 `feat/no-progress` 独立工作树。共同底座 `MAIN_SHA=27d057c206c0f8250b60309905737f7e26ee0ba9`、`A_SHA=8287e8f8ae63a27a58ab5898ecb2753b9b946c45`；M1 代码提交为 `38c607cd0a54482e95bec2a3a9e13871d97379fe`，M2 代码提交为 `c658ad0a6544c49c231143708bac3ae09cfd284d`。

## 行为与边界

`AgentConfig::default` 在构造时解析一次 `OCTOS_NO_PROGRESS`：仅 `1`/`true` 开启；未设置、`0`/`false` 或未知值均关闭，未知值只记录固定诊断，不记录原值。测试通过构造 `AgentConfig { no_progress: true, .. }` 注入，不修改全局环境。`OCTOS_NO_PROGRESS_REFLECTION` 尚未接入；M6 才引入可选复盘。

conversation 和 `run_task` 共用 `LoopDetector::before_call` / `after_result`。H07 开启时，第一个同步结果仅记录；同工具、同参数、同结果的第二次结果发送短提示；第三次同调用在执行前拒绝。一般结果比较最终可见文本的精确摘要；H03 文件 read 的可信 source/version/range 摘要用于避开每次不同的 envelope ID。只有成功结果或 H05 明确给出 `no_match/ambiguous` 的确定性失败能建立这段 exact 历史；普通 `success=false`、blocked、timeout、歧义 call ID 和异步等待不能建立同步拒绝证据。参数相同但结果变化不会触发 exact guard。H07 关闭时，conversation 保留原来的第三次参数相同调用前 doom 拦截、旧第三结果提示和 cycle 1/2/3；task 保留 M0 固定的旧行为。

conversation 的拒绝发生在写入本轮 assistant tool-call 行之前，多工具批次全部不执行；此前已写入的 assistant/tool 行保持一一配对。task 在同一拒绝点返回 `success=false`、准确累计 usage 和有界说明，也不写入未配对的本轮工具行。spawn 对 task 失败的自动恢复和 typed `retryable=false` 属于 M5，M2 不声称已解决。

H07 开启时，cycle 1 由结果判断接管，原 cycle 2/3 的两阶段 warning/terminal 仍使用现有路径；纯同参数但持续变化的输出不会被误认成 cycle 2/3。conversation 原 shell spiral 恢复在 exact 终止前执行，verifier-configured Agent 仍豁免 exact 硬拦截，peer/background 同步阈值豁免。H03 已登记的 read/recall 结果不改写 envelope，短提示作为单独模型提示计入最终 H03 输入预算；范围、版本和 `read_file_next` 参数仍由 H03 渲染。普通工具正文在预算内附提示，超出时也使用单独提示。未新增模型复盘请求。

## 验证

| WSL 验证（`h07-arc` 工作树） | 实际结果 |
| --- | --- |
| `cargo test -p octos-agent --lib h07_m -- --nocapture` | M0–M2 共 24 通过、0 失败，退出码 0（最终代码） |
| `./target/debug/deps/octos_agent-10bd1ddb90ba50f4 loop_detect::tests --quiet` | 26 通过、0 失败，退出码 0 |
| `./target/debug/deps/octos_agent-10bd1ddb90ba50f4 agent::loop_runner::tests --quiet` | 150 通过、1 忽略、0 失败，退出码 0（最终代码） |
| `cargo test -p octos-agent --test h03_m1_output --test h05_m3_mutation_results --test loop_retry_state --quiet` | 13 + 1 + 10 = 24 通过、0 失败，退出码 0 |
| `cargo check -p octos-cli --no-default-features --features api` | 编译通过，退出码 0 |
| `rustfmt --edition 2024 --config skip_children=true --check`（4 个改动文件） | 无格式差异，退出码 0 |
| `git diff --cached --check`（代码提交前） | 无空白错误，退出码 0 |

首次 M2 聚焦运行 9 项时有 8 项通过，H03 新测试错误地要求未配置 recall 存储的夹具也必须出现 `recall` 字段；修正为检查实际可用的 `read_file_next` 及 `source_sha256` 后通过。新增 shell 专项的首版测试错误地假设旧 spiral 恢复一定会再请求模型总结；实际该夹具走既有直接终止恢复分支，改为断言恢复优先级、累计 usage 和实际工具次数后通过。最终另加 `success=false` 的策略拒绝反误拦截用例，24 项 M0–M2 均通过。H03/H05/retry 集成测试及 CLI 编译先于最后一处失败结果资格收紧运行；最终 24 项聚焦测试、26 项 detector 和 150 项主循环通过后完成代码提交。该收紧仅在 H07 开启时消费失败结果，不改 H07-off 路径。

真实官方 A/B/C 与付费模型实验未运行；正确率和真实任务 token 收益尚未测量。fake provider 的 conversation 和 task exact 用例均为 3 次模型请求、2 次真实工具执行、累计 3 input + 3 output token；M0 的 H07-off task 反例为 4 次模型请求、3 次执行、累计 4 input + 4 output token。shell 恢复用例为 5 次模型请求、4 次工具执行、累计 5 input + 5 output token；策略拒绝用例为 4 次模型请求、3 次工具执行、累计 4 input + 4 output token。H07 reflection 请求数为 0（功能尚未接入）。

## 后续边界

M3 才引入等价 episode 和策略状态；M4 校准 H05 文件事实、read 证据及 productive grace；M5 处理 live wait、provider retry 隔离和跨 spawn 不可自动重试；M6 才加入 B/C 共用策略梯子与一次语义复盘。M2 的离线结果不能当作官方正确率收益。
