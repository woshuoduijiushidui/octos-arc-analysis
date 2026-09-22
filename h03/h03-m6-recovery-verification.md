# H03 M6 实现与验证：恢复链观测和确定性回归

## 1. 结论

- 状态：M6 已完成。
- 代码提交：`fbcfd6b85214fa12316303f16599dbb3a97437ce`，仅本地提交，未推送。
- 观测策略：`output_recovery_v1`。
- 恢复行为、8 KiB 最终输出预算和 M5 入口范围不变；M6 只补充低基数指标、无正文
  调试事件和确定性回归。
- T01-T24 均有自动化测试或入口证据；没有把核心 stdio 场景标为不适用。

## 2. 恢复链观测

`OutputState` 统一记录以下事件：

| 观测 | 内容 |
| --- | --- |
| 通用事件 | `operation/layer/outcome/reason/policy` |
| 字节 | 捕获、实际保存、最终可见、同一坐标系下的已知遗漏量 |
| unknown | 来源总量未知或清洗改变坐标时显式记录，不伪造遗漏量 |
| 页恢复 | 请求类型、stream、请求/返回范围、严格前进、EOF、stale 和失败原因 |
| 命令 | 每个 output ID 只记录一次终态执行，含退出/超时/取消及 artifact 状态 |

新增指标：

- `octos_output_recovery_events_total`
- `octos_output_recovery_bytes_total`
- `octos_output_recovery_unknown_totals_total`
- `octos_output_recovery_recall_total`
- `octos_output_recovery_command_executions_total`

结构化调试日志 target 为 `octos.output_recovery`。字段只包含固定枚举、布尔值和数字范围，
不包含路径、owner、output ID、call ID、命令参数或正文。会话内事件、重复请求摘要和命令
终态去重各自最多保留 128 条；锁中毒按现有 fail-safe 方式恢复。指标和日志调用不参与工具
成功/失败分支，不改变工具结果。

命令捕获字节优先使用排空后的真实 stream total；文件捕获只统计本次选择范围。保存字节
使用持久 artifact 的实际范围，最终可见字节使用 `visible_ranges`。若清洗改变正文长度，
事件保留捕获量，但将后续坐标标为 unknown，已知遗漏量置零。

页恢复通过请求摘要判断重复调用。成功结果记录返回范围；仍有下一页且范围非空时记为
`strict_progress`，终页记为 `eof` 或 `selection_end`，错误保留
`invalid_cursor/stale_source/out_of_range/...` 等固定原因。恢复旧日志不会生成新的命令执行
事件，因此能和“又执行了一次命令”区分。

H02 不新增状态账本，继续复用：

- `octos_model_read_receipt_target_revocations_total`
- `octos_model_read_receipt_entries_revoked_total`
- `octos_model_read_receipt_lifecycle_clears_total`
- `octos_model_read_receipt_entries_cleared_total`
- `octos_model_read_receipt_invalidations_total`

这些指标已有 `source_not_visible/source_truncated/projection_changed/lifecycle_cleared` 等原因，
M6 回归确认重渲染、来源消失和生命周期清理仍按原合同撤销凭据。

## 3. M6 新增确定性测试

`output_store_tests.rs` 新增 3 项：

1. `h03_m6_observes_bytes_recall_progress_and_repetition_without_payloads`
   验证捕获/保存/可见/遗漏、严格前进、重复恢复、返回范围及事件不含正文和标识。
2. `h03_m6_counts_one_terminal_command_and_bounds_observation_memory`
   验证同一命令终态只计一次、超时与 artifact 状态、stale 原因和 128 条内存上限。
3. `h03_m6_transformed_coordinates_report_unknown_instead_of_false_omission`
   验证清洗后使用 unknown，不把安全文本长度误报成原文遗漏量，也不泄漏密钥。

已有冷恢复测试增加明确断言：恢复文件页必须是 historical，且
`document.file_read=None`，不能把历史文本转成当前文件读取凭据。

## 4. T01-T24 验收矩阵

| ID | 自动化测试或证据 |
| --- | --- |
| T01 | `file_and_log_share_total_budget_including_all_metadata`、`metadata_over_budget_and_unknown_config_fail_closed` |
| T02 | `final_provider_pages_cover_lines_long_line_and_eof_without_gaps`、`h03_m2_hot_and_cold_unicode_ranges_reconstruct_exact_hash` |
| T03 | `bounded_byte_pages_stop_at_the_requested_utf8_boundary`、`h03_m2_duplicate_call_ids_and_fixed_legacy_pages_do_not_skip_gaps` |
| T04 | `final_provider_pages_cover_lines_long_line_and_eof_without_gaps`、M2 Unicode 哈希重组 |
| T05 | `empty_crlf_bom_and_no_newline_have_exact_source_ranges`、`h03_m2_invalid_cursor_eof_empty_and_argument_validation` |
| T06 | `batch_allocation_is_repeatable_and_bounded`、`smaller_projection_restarts_from_source_and_updates_proof`、bridge failure |
| T07 | `sanitization_and_hook_text_are_budgeted_without_source_coverage`、`bridge_failure_never_sends_a_cut_range_declaration` |
| T08 | `only_the_final_visible_file_range_activates_h02_receipts`、`transformed_file_page_never_claims_raw_continuation_or_h02_coverage` |
| T09 | `a_same_size_same_mtime_replacement_rejects_the_old_continuation` |
| T10 | `real_file_and_shell_reach_final_provider_with_typed_ranges_and_status`、`h03_m4_command_preview_marks_head_tail_gap_and_recall_restores_each_stream` |
| T11 | `command_aliases_preserve_nonzero_exit_and_both_streams`、M4 timeout/cancel 专项 |
| T12 | `h03_m4_repeated_recall_does_not_execute_the_command_again`、stdio `command_executions=1` |
| T13 | `h03_m4_command_store_failure_preserves_output_and_exit_status_without_false_reference`、容量/running/spool failure 专项 |
| T14 | M2 corrupt/missing/schema、unpublished、publish failure 专项 |
| T15 | `h03_m2_duplicate_call_ids_and_fixed_legacy_pages_do_not_skip_gaps` |
| T16 | `h03_m2_owner_task_branch_and_workspace_must_all_match`、MCP invocation 隔离、H02 owner 隔离 |
| T17 | M2 热/冷哈希重组、ContextManager 压缩恢复、真实 stdio 热/冷恢复 |
| T18 | `h03_m2_repeated_cursor_is_stable_and_never_writes_an_artifact`、M2 Agent recall、M6 重复恢复 |
| T19 | M2 historical/no-file-read 凭据断言与 M3 强版本 stale 测试组合 |
| T20 | `h03_m2_long_secrets_across_blocks_and_pages_use_one_safe_view`、command capture 损坏 UTF-8 测试 |
| T21 | M2 running/published、lease、session/index/capture limit 专项 |
| T22 | 真实 stdio 恢复与受限模式、MCP 全局/provider deny |
| T23 | MCP 18 项集成：同 invocation 支持、跨 invocation 明确隔离 |
| T24 | `recovery_off_preserves_file_output`、`h03_page_is_identical_across_read_window_and_dedup_switches`、真实受限模式 |

T02、T04 和 T10 均在最终 provider 请求上验证。完整保存 fixture 使用范围连续性和 SHA-256
重组比较；partial capture 只验证已保存范围和明确缺口，不要求重建未保存字节。

## 5. 回归结果

环境为 macOS 26.6.2 arm64，`rustc/cargo 1.96.1`。真实运行前执行了
`source ~/.zshrc`，并显式加入项目固定工具链：

```bash
export PATH="$HOME/.rustup/toolchains/1.96.1-aarch64-apple-darwin/bin:$PATH"
```

| 验证 | 结果 |
| --- | --- |
| H03 存储、命令与 M6 观测 | 26 passed |
| M0-M3 最终 provider 链 | 22 passed |
| H02 M1-M3 | 19 passed |
| ContextManager | 101 passed |
| OUP | 47 passed |
| shell | 44 passed、1 ignored |
| command capture / 旧 recall | 4 / 3 passed |
| 压缩 policy 与恢复占位符 | 16 passed |
| MCP 完整集成 | 18 passed |
| read_file / read_window | 57 / 16 passed |
| model receipts / file state | 17 / 14 passed |
| workspace check / Clippy / fmt / diff | 全部退出码 0 |

OUP 过滤器与 ContextManager 集合存在少量重叠，因此不把各行机械相加为总数。准确命令、
命中数量和退出码见 [checks.json](./m6-evidence/checks.json)。Clippy 仅沿用已有
`serve.rs` 的 `nonminimal_bool` 基线豁免，没有新增豁免。

## 6. 真实 stdio 与提交

最终源码构建的 `target/debug/octos` SHA-256：
`69a29e0f6765076bfaa953f526a1cc12cc89fe7c5803520dc4cdc81d76b8d863`。

真实 stdio 使用 loopback fake provider，结果为：

- 6 次成功 provider 请求，含 1 次按脚本注入的 HTTP 重试；
- 2 个并行工具结果均到达 provider；
- 1 次审批事件，批准后继续；
- 同进程与跨进程冷恢复均成功；
- 含副作用命令只执行 1 次；
- 受限模式最终只有 `read_file`，输出明确
  `recoverable=false/recovery_tool_unavailable`。

摘要见 [summary.json](./m6-evidence/summary.json)，请求、事件和持久索引位于
[m6-evidence](./m6-evidence/)。脚本打印 PASS 并以 0 退出后，宿主沙箱额外打印一次
进程启动提示；该提示没有改变脚本断言、摘要或退出码。

代码提交钩子在提交对象创建后因沙箱拒绝写
`~/.bytesec/commit_hook/commit_result.json` 返回非零；提交
`fbcfd6b85214fa12316303f16599dbb3a97437ce` 已核对存在，代码工作树干净。未禁用钩子，
未推送远程。

本阶段没有运行付费模型或官方 ARC A/B，不对正确率和 token 收益作结论。M7 从该提交继续
补充有界搜索，完整 B 仍需 M7 联合验收后冻结。
