# H02 M6：B 变体观测、回归与冻结

- 日期：2026-09-20
- 状态：完成，B 变体已冻结
- 分支：`feat/safe-file-cache`
- A 基线：`6aacc9fb1a1599ae10f8368921ccf3e3afb7f87e`
- B 冻结提交：`73f5b1bf695af37167fcb47541726bcb24807102`
- M6 代码提交：`73f5b1bf695af37167fcb47541726bcb24807102`
- 远程状态：未推送

## 1. 冻结行为

1. 每次 `read_file` 都记录结果、稳定原因、读取范围、源文件和响应字节数及耗时。
   命中时另外记录来源证据、短版本号、投影策略、凭据代次和存活时间。
2. task、session、branch 和目标文件只写入 12 位 SHA-256 短标识。日志不记录文件
   正文、原始 owner、任意 shell 参数或绝对目标路径。
3. 文件内容 SHA-256 记录处理字节数与耗时。稳定读取在文件并发变化时最多重试
   一次，并区分 `retry`、`recovered` 和 `exhausted`。
4. 凭据 miss 使用固定枚举，不依赖自由文本。来源消失、裁剪、策略变化、版本变化、
   淘汰和生命周期清理都会留下有界原因，供下一次相关读取解释。
5. `OCTOS_FILE_READ_DEDUP=0|false|off` 会关闭 `[FILE_UNCHANGED]` 和新凭据登记，
   但强版本账本、写入新鲜度检查及 stale mutation 防护继续工作。
6. B 继续采用破坏性 frame 变化时全量清理当前 branch 凭据的保守策略。本提交不含
   retained-item 选择性保留，也不含热点文件自动回灌；这两项不属于 B。

## 2. 观测契约

| 类别 | 指标或日志 |
| --- | --- |
| 读取结果 | `octos_file_read_results_total{outcome,reason,view}` |
| 响应与源文件大小 | `octos_file_read_response_bytes{outcome}`、`octos_file_read_source_bytes{outcome}` |
| 读取耗时与可见性重读 | `octos_file_read_duration_seconds`、`octos_file_read_visibility_rereads_total{reason}` |
| 文件哈希 | `octos_file_version_hash_bytes_total`、`octos_file_version_hash_duration_seconds` |
| 版本拒绝 | `octos_file_read_version_rejects_total{reason}` |
| 稳定读取重试 | `octos_file_read_stability_retries_total{outcome}` |
| 凭据失效 | `octos_model_read_receipt_invalidations_total{reason}` |
| 生命周期与修改撤销 | `octos_model_read_receipt_lifecycle_clears_total`、`octos_model_read_receipt_entries_cleared_total`、`octos_model_read_receipt_target_revocations_total` |
| stale 写入 | `octos_stale_mutations_total{tool,reason}` |
| 调试日志 | target `octos::file_read`，只含哈希后的 owner/target、短版本、来源标识、范围、字节数、代次和年龄 |

稳定的命中/未命中原因如下：

```text
receipt_match
feature_disabled
missing_state
no_receipt
owner_mismatch
source_not_visible
source_truncated
view_not_covered
projection_changed
metadata_changed
digest_changed
receipt_evicted
lifecycle_cleared
```

读取参数、路径或 I/O 本身失败时使用 `invalid_request`、`invalid_range`、
`path_rejected`、`too_large`、`out_of_range`、`permission_denied`、
`unstable_observation` 或 `read_error`。指标和日志调用没有进入读取结果的错误路径，
因此观测后端异常不会改变正文、stub 或错误结果。

## 3. 18 个确定性场景

| 场景 | 自动化证据与结果 |
| --- | --- |
| 1. 同 owner、版本、范围且来源仍可见 | `successful_provider_dispatch_enables_next_matching_read_stub`、OUP/MCP 真实入口测试通过 |
| 2. compaction/trim 删除来源 | `prompt_replacement_clears_receipts_before_the_next_read` 及 compaction 测试证明下一次返回正文 |
| 3. B 的破坏性 frame 变化 | loop、tiered、PromptContext 和 OUP replacement 测试均执行全量清理 |
| 4. 100KB/50KB/8KiB/context pressure 裁剪 | `read_file_internal_100kb_truncation_does_not_stage_a_candidate`、`execution_50kb_truncation_does_not_activate_a_receipt`、`eight_kib_projection_does_not_activate_a_receipt`、`context_pressure_source_drop_does_not_activate_a_receipt` 通过 |
| 5. 投影策略或可见 bytes 变化 | sanitizer、after-tool hook、输出变更和 `changed_projection_policy_revokes_active_receipt` 测试通过 |
| 6. 同大小并恢复 mtime | `same_size_rewrite_with_restored_mtime_changes_strong_version` 通过，SHA-256 变化导致 miss |
| 7. 外部进程修改文件 | M1 强版本重读与 M4 外部修改测试通过，下一次读取不会复用旧版本 |
| 8. 内置修改后撤销旧凭据 | `write_file`、`edit_file`、`diff_edit`、`apply_patch` 成功路径及 targeted revoke 测试通过 |
| 9. task/session/workspace 隔离 | `task_session_branch_and_workspace_stores_do_not_share_receipts` 与 workspace owner 测试通过 |
| 10. parent/child 隔离 | M3 双向隔离和 `child_workers_share_ledger_but_mint_independent_receipts` 通过 |
| 11. rewind/fork/resume/task switch | lifecycle owner/store 重建测试通过，保留 ledger 时首次读取仍返回正文 |
| 12. 淘汰或状态丢失 | candidate/receipt LRU、锁中毒和 store 重建测试通过，结果均为保守 miss |
| 13. 同版本并发修改 | `concurrent_overwrites_cannot_consume_the_same_observed_version_twice` 通过，只有一个写入成功 |
| 14. patch context 唯一性 | edit/diff/patch 的唯一成功、0 次和多次匹配测试通过，无部分写入 |
| 15. stdio 与 MCP 真实入口 | `h02_m5_stdio_open_and_two_turns_reuse_verified_read_receipt`、`repeated_read_through_mcp_dispatch_uses_verified_receipt` 和跨调用隔离测试通过 |
| 16. 命中信息完整 | `miss_reason_labels_are_stable`、详细 lookup 和缺 owner 测试通过；无法说明 owner/version/view/source 时返回正文 |
| 17. 读取或写入中途替换 | bounded stable-read 与 mutation guard 测试通过，只会稳定重读或返回 typed concurrent/stale |
| 18. symlink/canonical alias | canonical alias、祖先 symlink、计划后 symlink swap 测试通过，不能绕过版本或写入保护 |

以上测试没有观察到错误的 `[FILE_UNCHANGED]`，并发与过期写入测试没有观察到 stale
mutation 漏放行。

## 4. 验证结果

运行前执行：

```text
source ~/.zshrc
export PATH="$HOME/.rustup/toolchains/1.96.1-aarch64-apple-darwin/bin:$PATH"
```

直接和跨层验证通过：

| 命令 | 结果 |
| --- | --- |
| `cargo test -p octos-agent model_read_receipts::tests` | 17 passed |
| `cargo test -p octos-agent tools::read_file::tests` | 55 passed |
| `cargo test -p octos-agent --test h02_m1_file_versions --test h02_m2_read_receipts --test h02_m3_receipt_lifecycle` | 19 passed |
| `cargo test -p octos-agent --lib tools::write_file::tests` | 48 passed |
| `cargo test -p octos-agent --lib tools::edit_file::tests` | 37 passed |
| `cargo test -p octos-agent --lib tools::diff_edit::tests` | 11 passed |
| `cargo test -p octos-agent --lib tools::apply_patch::tests` | 49 passed |
| `cargo test -p octos-agent --lib tools::mutation_guard::tests` | 2 passed |
| `cargo test -p octos-agent --lib tools::nofollow_tests` | 19 passed |
| `cargo test -p octos-agent --lib tools::read_window::tests` | 16 passed |
| `cargo test -p octos-agent --lib tools::spawn::tests` | 94 passed，1 ignored |
| `cargo test -p octos-agent --test m8_integration_tool_context` | 4 passed |
| `cargo test -p octos-cli --test mcp_serve_integration` | 14 passed |
| `cargo test -p octos-cli h02_m5 --lib` | 2 passed |
| `cargo test -p octos-pipeline --test m8_parity` | 6 passed |
| `cargo check -p octos-agent -p octos-pipeline -p octos-cli --tests` | 通过 |
| `cargo clippy -p octos-agent --all-targets -- -D warnings` | 通过 |
| `cargo clippy --workspace --all-targets -- -D warnings -A clippy::nonminimal-bool` | 通过 |
| `cargo fmt --all -- --check` | 通过 |
| `git diff --check` | 通过 |

提交后再次执行 `cargo fmt --all -- --check`、`git diff --check`、17 个 receipt 测试
和 55 个 `read_file` 测试，退出码均为 0。

## 5. 环境限制

1. `cd arc && python3 -m unittest discover -s tests` 共运行 408 项：399 passed、
   8 skipped、1 error。唯一错误来自当前 Python 3.9 不支持
   `tarfile.extract(..., filter="data")`，与 H02 文件状态改动无关。
2. UI Protocol 广泛回归共运行 950 项：943 passed、3 ignored、4 failed。4 项均为
   skill/plugin 安装用例，受 macOS 严格沙箱禁止写入
   `~/.octos/cache/verified/...` 影响；H02 stdio、context 与生命周期用例通过。
3. 不带例外的全工作区 Clippy 只报告既有
   `crates/octos-cli/src/commands/serve.rs:878` 的 `clippy::nonminimal_bool`。
   该文件不在 H02 差异中；仅放行此项后全工作区 Clippy 通过。

这些环境限制都没有被计作通过，也没有通过修改无关代码规避。

## 6. Git 冻结证据

```text
A_SHA=6aacc9fb1a1599ae10f8368921ccf3e3afb7f87e
B_SHA=73f5b1bf695af37167fcb47541726bcb24807102
git diff --stat A_SHA...B_SHA
40 files changed, 7435 insertions(+), 1255 deletions(-)
git status --porcelain
<empty>
```

M6 自身只修改 `file_state_cache.rs`、`model_read_receipts.rs`、`tools/mod.rs` 和
`tools/read_file.rs`，共 834 insertions、52 deletions。A 到 B 的 40 个文件是
M1-M6 的完整实现范围。

因此 B 已满足 18 个确定性场景、关闭开关兼容、错误 stub 为 0 和 stale mutation
漏放行为 0 的冻结条件。M7 必须从上述 `B_SHA` 新建独立分支。
