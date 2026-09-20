# H02 M7：选择性保留读取凭据验证

- 日期：2026-09-20
- 状态：完成，可进入 M8
- 分支：`feat/retained-read-receipts`
- B 基线：`73f5b1bf695af37167fcb47541726bcb24807102`
- C 冻结提交：`7eaa136ef086a2f9728794d17d8f150482df03d1`
- 远程状态：未推送

## 1. 本次完成的行为

1. 新增实验开关 `OCTOS_FILE_READ_RETAINED_RECEIPTS`，默认关闭。只有值为
   `1`、`true` 或 `on` 时开启；关闭时继续执行 B 的破坏性 frame 全清行为。
2. ContextManager 为最终 prompt 中的每条消息保留内存态 transcript item 来源。
   只有真实 item、未裁剪、未修复且未合成的 `read_file` call/output 才能生成
   retained source proof。
3. legacy/MCP compaction 没有 transcript item ID 时，使用 M2 已验证的最终消息
   proof：规范化 call ID、参数 SHA-256、输出 SHA-256 和 occurrence。
4. frame 变化时先清空所有尚未确认的 read candidate，再将 active receipt 与最终
   proof 求交集。只保留投影策略相同且 proof 完全匹配的 receipt。
5. 保留的 receipt 继续绑定原 `FileVersion`。下一次 `read_file` 仍会读取当前磁盘
   并比较强版本；测试证明压缩后未修改文件可返回 stub，文件变化后返回新正文。
6. 新增选择性 reconcile 次数和保留条目数指标。M6 的删除、生命周期、版本拒绝和
   读取结果指标继续生效。

## 2. 失败关闭规则

以下任一情况都会退回 B 的全清或保守 miss：

- 功能开关关闭。
- PromptContextManager 没有提供 provenance。
- 消息与 item 来源数量不一致、来源为空或 item ID 重复。
- ContextManager 对消息做过修复、合成或 tool output 裁剪。
- source proof 已从最终 frame 删除，或只在 summary、路径文字、artifact ref 中出现。
- call 参数、可见输出哈希、occurrence 或 projection policy 不一致。
- 旧来源只有 `[FILE_UNCHANGED]` stub，没有原始正文。
- 当前磁盘强版本与 receipt 中的版本不同。

rewind、resume、fork、task switch、owner 隔离和 mutation revoke 逻辑没有改变。
本里程碑没有加入热点文件回灌，也没有修改 prompt 文案、实验预算或文件写入保护。

## 3. 自动化覆盖

| 场景 | 结果 |
| --- | --- |
| 开关关闭 | 与 B 一样全清 receipt |
| ContextManager 保留完整 call/output item | 保留精确 receipt |
| legacy compaction 保留完整最终消息 | 保留精确 receipt |
| 压缩后再次读取未修改文件 | 返回 `[FILE_UNCHANGED]` |
| 压缩后文件发生变化 | 强版本不匹配，返回新正文 |
| 原 call/output 被删除 | receipt 被清除 |
| context-pressure 或 8KiB 裁剪 | provenance 无效，退回全清 |
| projection policy 改变 | 退回全清 |
| 重复 call ID | 由参数、输出和 occurrence 区分 |
| 重复 item ID 或重复 proof | 视为无效 provenance，全清 |
| summary 只提到文件路径 | 不生成 read source proof |
| stub 出现在最终 frame | 不替代原正文 proof，不形成续命链 |
| staged candidate 跨 frame 变化 | 始终清除，不能延迟激活 |

## 4. 验证结果

运行前执行：

```text
source ~/.zshrc
export PATH="$HOME/.rustup/toolchains/1.96.1-aarch64-apple-darwin/bin:$PATH"
```

通过的命令：

| 命令 | 结果 |
| --- | --- |
| `cargo test -p octos-agent --lib h02_m7` | 4 passed |
| `cargo test -p octos-agent --lib model_read_receipts::tests` | 21 passed |
| `cargo test -p octos-agent --lib agent::compaction::tests` | 6 passed |
| `cargo test -p octos-agent --lib agent::loop_compaction::tests` | 6 passed |
| `cargo test -p octos-agent --lib agent::llm_call::tests` | 11 passed |
| `cargo test -p octos-agent --test h02_m1_file_versions --test h02_m2_read_receipts --test h02_m3_receipt_lifecycle` | 19 passed |
| `cargo test -p octos-agent --lib tools::read_file::tests` | 55 passed |
| `cargo test -p octos-agent --lib tools::write_file::tests` | 48 passed |
| `cargo test -p octos-agent --lib tools::edit_file::tests` | 37 passed |
| `cargo test -p octos-agent --lib tools::diff_edit::tests` | 11 passed |
| `cargo test -p octos-agent --lib tools::apply_patch::tests` | 49 passed |
| `cargo test -p octos-agent --lib tools::mutation_guard::tests` | 2 passed |
| `cargo test -p octos-agent --lib tools::nofollow_tests` | 19 passed |
| `cargo test -p octos-agent --lib tools::read_window::tests` | 16 passed |
| `cargo test -p octos-agent --lib tools::spawn::tests` | 94 passed，1 ignored |
| `cargo test -p octos-agent --test m8_integration_cache_handoff --test m8_integration_tool_context --test m8_end_to_end_gate` | 8 passed |
| `cargo test -p octos-cli --lib h02_m7` | 3 passed |
| `cargo test -p octos-cli --lib context_manager::tests` | 98 passed |
| `cargo test -p octos-cli --lib session_actor_prompt_context_bridge` | 3 passed |
| `cargo test -p octos-cli --lib h02_m5` | 2 passed |
| `cargo test -p octos-cli --test mcp_serve_integration` | 14 passed |
| `cargo test -p octos-pipeline --test m8_parity` | 6 passed |
| `cargo clippy -p octos-agent --all-targets -- -D warnings` | 通过 |
| `cargo clippy --workspace --all-targets -- -D warnings -A clippy::nonminimal-bool` | 通过 |
| `cargo fmt --all -- --check` | 通过 |
| `git diff --check` | 通过 |

`cd arc && python3 -m unittest discover -s tests` 共运行 408 项：399 passed、
8 skipped、1 error。唯一错误仍是本机 Python 3.9 不支持
`tarfile.extract(..., filter="data")`，与 M7 Rust 改动无关。

不带例外的 `octos-agent + octos-cli` 严格 Clippy 仍只报告基线文件
`crates/octos-cli/src/commands/serve.rs:878` 的 `clippy::nonminimal_bool`。该文件
不在 C 相对 B 的差异中。

## 5. Git 冻结证据

```text
B_SHA=73f5b1bf695af37167fcb47541726bcb24807102
C_SHA=7eaa136ef086a2f9728794d17d8f150482df03d1
git diff --stat B_SHA...C_SHA
12 files changed, 828 insertions(+), 29 deletions(-)
git status --porcelain
<empty>
```

C 相对 B 只包含 retained source proof、frame 生命周期交集保留、开关、观测和测试。
没有修改强版本算法、mutation guard、stdio/MCP owner、prompt 文案、实验预算，
也没有加入热点文件自动回灌。

因此 M7 完成条件已满足：开关关闭时行为与 B 一致；开启时只有最终 frame 仍能证明
含有原始正文的 receipt 可以跨 compaction 保留，所有不确定情况都保守返回正文。
