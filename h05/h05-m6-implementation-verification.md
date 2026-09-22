# H05 M6：B 方案验收、观测与冻结

- 状态：M6 已完成，B 已冻结。
- 共同底座：`A_SHA=4c542e534e957d69a5ee05d24ffb7e166beb78bb`。
- M5 代码：`a1829e4d374e538f356a4e99956ba4f3415516a4`。
- 冻结版本：`B_SHA=8287e8f8ae63a27a58ab5898ecb2753b9b946c45`。
- 分支：`feat/local-edit`。
- 最终二进制 SHA-256：
  `99494dd7d1b56df47ab3dfce51ee835d8e6f2f44266c94c0c021943ba14375be`。

M6 没有修改生产匹配、写入、schema 或 codegen 行为。代码提交只增加验收脚本和测试，
并为现有原子创建、部分写入报告、formatter 后最终重读补齐回归。

## 1. 最小观测

Agent 侧夹具从真实 `ToolResult` 与 `ConversationResponse.tool_results` 记录：

```text
tool
success / result code
matcher
candidate count
replacement count / hunk count
changed lines before / after
formatter status / formatter expanded
argument bytes
result text bytes
structured metadata bytes
```

10 次确定性调用共记录 88 bytes 整写参数、600 bytes 局部编辑参数、1,262 bytes 结果
文本和 8,691 bytes structured metadata；实际改动范围合计 before 5 行、after 6 行。
记录只保存标签、计数和字节数，不保存源码正文、完整参数或凭据。观测发生在工具返回后，
不参与匹配和写入，无法改变工具结果。

真实 stdio 夹具另记录结果 code、matcher、候选数、参数/结果字节，以及失败后下一次编辑
是否成功和是否额外读取。此次两次恢复均成功：一次直接使用候选重试，一次先
`read_file` 再重试。fixture 内 stale 次数为 0，stale 安全由共享 mutation guard 的
并发测试覆盖，未把未发生事件误记为未知或非零。

## 2. T01-T16

16 个场景全部有自动化证据，没有“不适用”项。完整逐项映射见
[acceptance-matrix.json](./m6-evidence/acceptance-matrix.json)。

新增的关键边界：

- 两个并发 `create_new` 竞争同一路径时恰好一个成功，失败方返回
  `stale_file_version`，胜者内容不被覆盖；
- 可能已经发生部分 I/O 写入的错误必须设置 `file_modified`；
- 工具写入后磁盘内容再次变化时，未运行 formatter 的报告标记
  `final_state=unconfirmed` 且不伪造 diff；formatter 已运行时按最终磁盘 bytes
  计算版本与 diff。

T04、T08、T11、T15 均在真实 `serve --stdio --solo` 与 loopback fake provider 的
最终 messages/tools 上验证。15 次工具调用产生 16 次 provider 请求；6 条 typed
失败结果合计 6,909 bytes，接近但不超过 8 KiB。所有失败和 no-op 路径零写入，仅
7 次真实修改产生 mutation 事件。

## 3. 固定输入与字节

| 项目 | B |
| --- | ---: |
| 关闭态工具 schema | 9,286 bytes |
| 开启态工具 schema | 9,555 bytes |
| 新增 schema | 269 bytes |
| 新增 system prompt | 410 bytes |
| 固定输入增量 | 679 bytes |
| stdio 整写参数 | 44 bytes |
| stdio 局部编辑参数 | 2,749 bytes |
| stdio 模型可见工具结果 | 9,408 bytes |
| Agent structured metadata | 8,691 bytes |

关闭态 schema SHA-256 仍为 A 的
`79f97b610f4178e8820be561ce5fac943e6d43d04cb07e0147ac31aec2acdafa`。
默认工具列表保持不变且不含 `apply_patch`。

## 4. 范围审查

`A_SHA..B_SHA` 共 7 个提交，按顺序对应 M0-M6。生产改动只位于
`octos-agent` 的 prompt 组装、三个写工具、matcher、共享 mutation guard/report 和
registry；其余变化是 H05 自动化夹具。

审查确认没有：

- `OCTOS_LOCAL_EDIT_STRICT_MATCH` 或 strict matcher 行为；
- existing codegen patch 协议；
- Python/Rust codegen 生产改动；
- 官方需求、测试或输入变化；
- 默认 profile 变化；
- 将 `apply_patch` 加回默认工具列表；
- 与 H05 无关的生产重构。

机器可读结果见 [scope-audit.json](./m6-evidence/scope-audit.json)。

## 5. 验证

| 验证 | 结果 |
| --- | --- |
| M6 Agent 观测 | 1 passed |
| mutation guard / mutation report | 7 / 4 passed |
| edit / replacer / diff / write / formatter | 60 / 30 / 25 / 54 / 35 passed |
| 隐藏 `apply_patch` 回归 | 49 passed |
| H02/H03 与 M2-M6 集成 | 43 passed |
| M0 关闭态 | 8 passed |
| AppUI prompt / diff preview / file mutation | 1 / 5 / 8 passed |
| MCP、spawn/worker | 18 / 94 passed，1 ignored |
| `octos-arc` | 130 lib passed，2 ignored；1 integration passed |
| Python codegen | 71 passed |
| `cargo check --workspace --tests` | 通过 |
| 三 crate、all-targets 严格 Clippy | 通过 |
| `cargo fmt --all -- --check`、`git diff --check` | 通过 |
| 真实 stdio B 验收 | 16 requests、15 tool calls，全部断言通过 |
| 真实 stdio M0-M5 重放 | 全部通过 |

完整命令和结果见 [checks.json](./m6-evidence/checks.json)，聚合数据见
[summary.json](./m6-evidence/summary.json)，Agent metadata 记录见
[agent-observability.json](./m6-evidence/agent-observability.json)，真实请求和事件见
[stdio](./m6-evidence/stdio/)。

测试与构建前均执行 `source ~/.zshrc`，并补充 Homebrew rustup 路径。Rust/Cargo 为
1.98.1，Python 为 3.9.6，Node 为 v26.0.0。macOS 链接器仍只有已知的
`__eh_frame section too large` 性能提示。

首次 `octos-arc` 测试的全部测试均通过，但用户级 Git 提交钩子尝试写入沙箱外的
`~/.bytesec/commit_hook/commit_result.json`，使命令退出 1；使用隔离 Git 配置复跑后
退出 0。

本阶段未运行官方付费任务：当前环境缺少 `ARCBENCH_API_KEY`，固定 A/B/C 对照按计划在
M8 执行。M7 可以从上述 `B_SHA` 开始，只改变 fuzzy 自动写边界。
