# H02 M2：模型可见读取凭据验证

- 日期：2026-09-20
- 状态：完成，可进入 M3
- 分支：`feat/safe-file-cache`
- 主线基线：`main@6aacc9fb1a1599ae10f8368921ccf3e3afb7f87e`
- M2 提交：`9f763cf7d9b5ff9f64c72d04cbf11398f2059947`
- 远程状态：未推送

## 1. 本次完成的行为

M2 在 M1 的磁盘强版本之外，新增独立的 branch-local
`ModelReadReceiptStore`：

1. `read_file` 成功返回正文时暂存 typed candidate，记录 tool call ID、规范化参数哈希、canonical target、强文件版本、请求/返回范围和原始输出 SHA-256。
2. candidate 不写入模型可见正文，也不依赖 `ToolResult.structured_metadata` 或 ContextManager 持久化格式。
3. 最终 `call_llm_with_hooks_mode` 在 provider 请求前扫描实际发送的 `Message`，按规范化 call ID、参数 SHA-256、输出 SHA-256 和 occurrence 配对。
4. 最终消息缺失、正文被修改、截断、脱敏或附加 hook feedback 时，candidate 被消费但不能成为 receipt。
5. 匹配成功的 candidate 先成为当前调用局部的 pending receipt；只有非空、非重试型 provider 响应成功后才激活。
6. provider 失败、调用取消或 Before-LLM hook 拒绝时，pending receipt 随调用丢弃。silent checkpoint 不消费也不激活主模型分支的 candidate。
7. 每次普通 provider dispatch 都重新核对 active receipt 的 source proof 和投影策略 ID；source 消失、occurrence 改变或策略变化时立即失效。
8. `read_file` 只有在当前稳定 `FileVersion` 相同且 receipt 覆盖请求范围时返回 `[FILE_UNCHANGED]`。
9. partial line/byte receipt 只能覆盖相同坐标系中的子范围；行模式全文不能授权 raw byte 模式。
10. stub 携带 target、短版本标识、可见范围、candidate 和 occurrence，且 stub 本身不会创建新 candidate。

## 2. 安全边界

- `FileStateCache` 只保存磁盘事实，`ModelReadReceiptStore` 只保存模型可见事实，两者没有合并。
- 没有 receipt store、没有文件版本 ledger、没有稳定版本或没有 source proof 时都返回正文。
- 100KB 工具内截断不会暂存 candidate。
- 50KB 执行层截断、8KiB prompt 投影、context-pressure 丢弃、脱敏和 hook feedback 都会造成最终摘要不匹配，因此不激活 receipt。
- 同一批并行读取发生在下一次 provider dispatch 前，不能互相命中。
- 重复 provider call ID 使用参数、输出和 occurrence 区分；旧 occurrence 消失后不会被另一个同名调用替代。
- receipt 不持久化，也不会由 resume artifact 恢复。

## 3. 明确未做的内容

- stdio/OUP、MCP 和 spawn 的生产级 owner 创建与传播仍属于 M5。本里程碑通过显式 builder 验证核心链路。
- compaction、rewind、resume、fork 和 task switch 的统一清理原因与生命周期接线仍属于 M3。
- mutation 临界区内的 expected-version 校验和 eager receipt revoke 仍属于 M4。
- 没有修改 ContextManager 的持久 wire schema。

## 4. 验证结果

运行前执行：

```text
source ~/.zshrc
export PATH="$HOME/.rustup/toolchains/1.96.1-aarch64-apple-darwin/bin:$PATH"
```

通过的命令：

| 命令 | 结果 |
| --- | --- |
| `cargo test -p octos-agent --test h02_m2_read_receipts` | 11 passed |
| `cargo test -p octos-agent --lib model_read_receipts` | 8 passed |
| `cargo test -p octos-agent --lib agent::llm_call::tests` | 11 passed |
| `cargo test -p octos-agent --lib agent::execution::tests` | 41 passed |
| `cargo test -p octos-agent --lib tools::read_file::tests` | 52 passed |
| `cargo test -p octos-agent --lib tools::write_file::tests` | 46 passed |
| `cargo test -p octos-agent --lib tools::edit_file::tests` | 36 passed |
| `cargo test -p octos-agent --lib tools::diff_edit::tests` | 10 passed |
| `cargo test -p octos-agent --lib tools::apply_patch::tests` | 46 passed |
| `cargo test -p octos-agent --test h02_m1_file_versions --test m8_integration_cache_handoff --test m8_integration_tool_context --test m8_end_to_end_gate` | 11 passed |
| `cargo test -p octos-cli --lib context_manager::tests` | 96 passed |
| `cargo test -p octos-cli --test mcp_serve_integration` | 12 passed |
| `cargo test -p octos-pipeline --test m8_parity` | 6 passed |
| `cargo fmt --all -- --check` | 通过 |
| `cargo clippy -p octos-agent -p octos-cli -p octos-pipeline --all-targets -- -D warnings -A clippy::nonminimal_bool` | 通过 |
| `git diff --check` | 通过 |

严格 Clippy 仍只被基线文件 `crates/octos-cli/src/commands/serve.rs:878`
的 `clippy::nonminimal_bool` 阻断；该文件不在 H02 diff 中。

未调用真实模型。未把依赖本机 send-file、build-cache、sandbox/shell 环境的
`cargo test -p octos-agent` 全量套件记为 M2 通过条件。

## 5. 完成判断

每一个 `[FILE_UNCHANGED]` 都要求：

```text
当前稳定 FileVersion
+ 被 receipt 覆盖的请求范围
+ 当前最终 prompt 中仍存在的精确 source proof
+ 相同的投影策略
```

任何条件缺失都会返回当前正文。receipt 只会在对应 provider 请求成功后激活，
因此 M2 的最终可见性确认链已经闭合。
