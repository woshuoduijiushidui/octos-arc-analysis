# H01 M5：B 变体行为、观测与冻结记录

- 日期：2026-09-19
- 分支：`feat/h01-evidence-capsule`
- 冻结提交：`B_SHA=6d7d1559b72c3b0a34789909d3056527fdc9d42d`
- 状态：已冻结，未推送远端

## B 变体行为

B 包含 H01a-d，不包含 H01e：

- ARC 为当前 requirement、source state 和真实 acceptance 结果维护
  `octos.task-evidence.v1` capsule。
- stdio `turn/start` 以 typed input 传输 capsule；缺少 capsule 时 payload
  保持原来的 text-only 形状。
- ContextManager 只保留最新 capsule，并在压缩后按独立预算重新注入。
- 确定性摘要按任务契约、失败、验证、source/change、next action 的优先级
  保留证据。
- 长工具输出沿用现有 context ledger 和 `recall`；acceptance 失败详情写入
  `.arc/evidence/`，模型仅在显式 `read_file` 时读取。
- B 不实现 structured LLM checkpoint，不增加 H01e provider request。

## 配置示例

```bash
export OCTOS_H01_VARIANT=B
export OCTOS_DRIVER=stdio
export OCTOS_SESSION_SCOPE=node
export OCTOS_OUP_SEMANTIC_CONTEXT_MODE=on
export OCTOS_CONTEXT_COMPACT_THRESHOLD_TOKENS=12000
export OCTOS_CONTEXT_COMPACT_TARGET_TOKENS=8000
```

`OCTOS_H01_VARIANT` 只标记实验变体，不切换代码实现。A/B/C 必须继续使用各自
冻结的 Git SHA。上面的 compaction threshold/target 只是示例；正式实验必须在看
结果前写入 manifest，并对三个变体使用同一值。

ARC 的 `octos serve --stdio --solo` 默认不传 `--llm-compaction`，因此 B 的
compaction 使用 `extractive`。不要在 B 实验中手工启用 LLM compaction。

## 观测契约

H01 观测复用 `.arc/runner-events.jsonl`，记录 `type=h01_observation`。字段经过
固定 allowlist，不写入 prompt、message、命令、工具参数、输出正文或密钥。

| kind | 关键字段 |
| --- | --- |
| `run` | `variant`、`compaction_count=0`、`typed_input_enabled`、`h01e_extra_requests=0`、`h01e_extra_tokens=0` |
| `capsule` | `status`、`schema`、`bytes`、`estimated_tokens` |
| `compaction` | 累计次数、前后 token、`summarizer_kind`、candidate decision/reason |
| `artifact` | write/replay/recall、状态、ref、SHA-256、字节数、枚举化失败原因 |

`context/compaction_completed` 新增的 additive 字段为：

- `summarizer_kind`: `none|extractive|llm|extractive_fallback`
- `candidate_decision`: `accepted|rejected`
- `candidate_reason`: 固定枚举，例如 `accepted_within_budget`、
  `rejected_over_budget`、`rejected_not_smaller`、`rejected_persistence`

`.arc/octos-events.jsonl` 保留结构化生命周期和计数，但会删除
`arguments/command/prompt/message/text/output/output_preview/error` 等正文，仅记录
对应字节数。精确 provider token 仍以 `.arc/llm-usage.jsonl` 为准。

## 已知限制

- `OCTOS_DRIVER=chat` 不支持 typed task evidence，`typed_input_enabled=false`；
  B 的正式实验应使用默认 stdio driver。
- 默认 `OCTOS_SESSION_SCOPE=turn` 很少积累到压缩阈值；需要研究压缩行为时应使用
  固定的 `node` scope，并在 A/B/C 中保持一致。
- capsule token 数是 UTF-8 bytes/4 的确定性估算，不是 provider tokenizer 精确值。
- acceptance artifact 当前无自动 GC；capsule 只引用最新 verification。
- 旧 Octos 二进制没有新增 compaction 观测字段时，Python 记录
  `summarizer_kind=unknown` 和 legacy candidate reason。
- H01e 计数在 B 固定为零；M6 必须在独立分支接入真实 usage 计数。

## 验证结果

聚焦测试：

- Python H01 reducer/transport/observability：25 passed。
- `cargo test -p octos-core --lib ui_protocol`：165 passed。
- `cargo test -p octos-cli --lib context_manager::tests`：101 passed。
- ARC stdio compaction integration：3 passed。
- CLI compaction observation：2 passed。
- `cargo test -p octos-agent --lib compaction`：66 passed。
- `cargo test -p octos-agent --lib tools::read_file::tests`：51 passed。
- `cargo fmt --all -- --check` 和 `git diff --check`：通过。
- 受影响 crates 的 Clippy 在忽略一个既有
  `commands/serve.rs:878` `clippy::nonminimal-bool` 后通过；H01 新增代码无告警。

全量测试：

- Python 共运行 205 项；唯一错误仍为 Python 3.9 不支持
  `tarfile.TarFile.extract(..., filter="data")`，另有 5 skipped。
- `cargo test --workspace` 已实际启动并运行约 15 分钟。H01 相关用例通过，但
  `octos-agent` 的既有 macOS sandbox、shell 子进程、build-cache 和 background
  task 测试在当前受限执行环境中出现超时/进程清理失败，套件未能干净结束。
  代表性失败包括
  `test_macos_sandbox_restricts_read_paths`、
  `exec_session_completes_even_when_a_descendant_keeps_stdout_open` 和
  `background_child_retains_build_cache_claim`；本次未修改这些实现。

## 冻结核验

- `git status --short`：代码提交后为空。
- 搜索 `structured_checkpoint|llm_structured|H01e`：只有 B 的
  `h01e_extra_requests=0`、`h01e_extra_tokens=0` 观测字段。
- 未修改官方 requirement 或 acceptance spec。
