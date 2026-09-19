# H01 M6：C 变体结构化 LLM Checkpoint

- 日期：2026-09-19
- 分支：`exp/h01e-llm-checkpoint`
- 基线：`B_SHA=6d7d1559b72c3b0a34789909d3056527fdc9d42d`
- 冻结提交：`C_SHA=804e42a8d42b5e570a5d1d2cb78b01d0a73059d7`
- 状态：已完成，未推送远端

## 行为

C 在 AppUI/stdio 的真实 ContextManager 压缩路径增加
`llm_structured_checkpoint`。该 summarizer 只接收将被丢弃的历史前缀；
当前用户请求、最新 typed task-evidence capsule、开放工具交互和保留尾部仍由
B 的 ContextManager 规则固定，不交给模型改写。

模型只允许返回以下 JSON 字段：

- `historical_decisions`
- `completed_work`
- `unresolved_investigation`
- `next_suggested_action`
- `critical_file_references`

接受边界会检查严格 schema、非空字段、自然结束、无工具调用、无图片内容、
token 预算、相对被替换区域确实变小，以及相对文件引用和可选 `#Lx-Ly`
格式。task-evidence 标记、绝对路径、父目录跳转、图片引用、截断结果和额外
字段都会被拒绝。

每次 compaction 最多调用 provider 一次，不重试。空输出、malformed JSON、
缺字段、超长、未缩小、timeout 或 provider error 均返回原 B
`PromptFrame::compact_summary` 的确定性结果；最终安装仍经过 ContextManager
原有的预算、原子替换和持久化校验。

## 配置

正式 C 运行：

```bash
export OCTOS_H01_VARIANT=C
export OCTOS_H01E_LLM_CHECKPOINT=1
export OCTOS_DRIVER=stdio
export OCTOS_SESSION_SCOPE=node
```

`OCTOS_H01_VARIANT=C` 未显式设置 checkpoint 开关时默认启用。
`OCTOS_H01E_LLM_CHECKPOINT=0` 可关闭 H01e，此时不传
`--llm-compaction`，行为与 B 相同。A/B 变体拒绝显式启用 H01e，防止实验串组。

H01e 要求 HTTP provider endpoint，以便 ARC 代理记录精确请求 usage。代理以
OpenAI `response_format.json_schema.name=h01e_structured_checkpoint` 识别请求：

- `.arc/llm-usage.jsonl` 增加 `request_kind=h01e_compaction`；
- 有 usage 时保留 prompt、completion、reasoning 和 cache token；
- provider error 即使没有 usage 也记录请求，标记 `usage_available=false`；
- `.arc/runner-events.jsonl` 的最终 `kind=run` 记录
  `h01e_extra_requests` 和 prompt + completion token 总数；
- H01e 请求计入 run-wide provider 总量，但不消耗普通 agent turn request cap。

## 测试

新增 mock provider 用例覆盖有效结果、空结果、malformed JSON、字段缺失、
截断、超长、图片、非法引用、未缩小、timeout、provider error、提示注入隔离、
单次调用和 fallback 字节等价性。

验证结果：

- `cargo test -p octos-agent --test h01e_structured_checkpoint`：6 passed。
- `cargo test -p octos-agent --lib compaction`：66 passed。
- compaction policy/wiring/session-summary 集成测试：28 passed。
- `cargo test -p octos-cli --lib compaction`：47 passed。
- `cargo test -p octos-cli --lib context_manager::tests`：101 passed。
- ARC stdio compaction 集成测试：3 passed。
- `cargo test -p octos-core --lib ui_protocol`：165 passed。
- Python H01/usage 聚焦测试：24 passed。
- Python 全量：208 项中 202 passed、5 skipped、1 个既知错误；错误仍是
  Python 3.9 不支持 `tarfile.TarFile.extract(..., filter="data")`。
- `cargo fmt --all -- --check`：通过。
- `cargo clippy -p octos-agent --all-targets -- -D warnings`：通过。
- CLI all-target Clippy：通过；仅允许既有的
  `clippy::nonminimal-bool` lint。
- `git diff --check`：通过。

未重复运行 `cargo test --workspace`：M5 已确认当前受限 macOS 环境中的既有
sandbox、shell 子进程和 background-task 测试会超时或失败；M6 未修改这些路径。

## 差异核验

`git diff B_SHA...C_SHA` 仅包含：

- H01e structured checkpoint 的 schema、prompt、校验和 mock 测试；
- AppUI compaction 的 H01e 选择与 `summarizer_kind`；
- ARC C 变体开关和 usage 分类/汇总；
- 对应 Rust/Python 测试及 CLI 帮助文本。

未修改 H01a-d reducer、typed capsule 契约、ARC 任务 prompt、官方 requirement、
官方 acceptance spec 或实验 token/时间预算。
