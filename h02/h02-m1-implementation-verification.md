# H02 M1：强文件版本与稳定读取验证

- 日期：2026-09-20
- 状态：完成，可进入 M2
- 分支：`feat/safe-file-cache`
- 当前主线基线：`main@6aacc9fb1a1599ae10f8368921ccf3e3afb7f87e`
- 初始调研基线：`c599d18c5acd2b846f049ffea2be84e72fe60fac`
- M0 提交：`0e236311`（rebase 前为 `7d4f81e6`）
- M1 提交：`463f9dbd9eeea6132814421b671680b2c82fd49d`（rebase 前为 `756528ee`）
- 远程状态：未推送

M0、M1 已从初始调研基线重放到最新 `origin/main`。`git range-diff`
显示两个提交的补丁均完全等价，且 rebase 无冲突。

## 1. 本次完成的行为

M1 只建立可信的磁盘版本，不启用重复读取省略：

1. `FileTarget` 使用工作区 owner 和 canonical target 共同标识文件，避免不同工作区互相混淆。
2. `FileVersion` 保存可选 provider revision、原始文件字节的 SHA-256、大小和 metadata hint。旧 FNV 和仅比较 mtime 的命中逻辑已移除。
3. 本地读取在同一个 no-follow 文件描述符上执行 `stat-before -> bounded read/hash -> stat-after`，再核对路径当前仍指向同一文件。发现变化后只重试一次，再失败时返回 `concurrent_file_change`。
4. 正文和版本来自同一次稳定读取。PDF 的版本按磁盘原始字节计算，展示正文仍使用提取后的文本。
5. canonical target 无法建立时仍返回正文，但不登记无法证明归属的版本。
6. `read_file` 的行模式和字节模式都会登记版本；重复读取无论版本是否相同都继续返回正文，不产生 `[FILE_UNCHANGED]`。
7. `write_file`、`edit_file`、`diff_edit` 和 `apply_patch` 统一调用 `invalidate_path`。删除类 patch 在文件消失前失效，避免删除后无法 canonicalize。
8. resume 中的历史摘要/hash 不再被当作当前磁盘版本。恢复后的第一次读取必须重新观察当前文件。
9. LRU 条目数和总字节上限继续保留；淘汰、锁中毒或版本 key 建立失败只会丢失优化状态，不会制造旧版本命中。

## 2. 明确未做的内容

- 没有创建 `ModelReadReceipt`，也没有在最终 provider 请求后确认模型可见性；这是 M2。
- 没有启用正文省略或 token 优化。M1 的所有成功读取仍返回实际正文。
- mutation 目前只统一主动失效版本记录；真正写入临界区内的 expected-version 校验仍属于 M4。
- 没有改变 stdio、MCP 和 spawn 的模型分支 receipt 生命周期。

## 3. 自动化覆盖

新增或更新的测试覆盖：

- 相同内容重复读取产生相同强版本，但两次都返回正文。
- 同大小改写并恢复原 mtime 后，SHA-256 仍能识别内容变化。
- 相同 target 在不同 workspace owner 下保持隔离。
- 普通文件、ancestor symlink alias、leaf symlink 拒绝和路径替换。
- 读取期间连续两次替换时返回 typed concurrent-change。
- 文件不存在、版本 key 无法建立、LRU 条目/字节淘汰和锁中毒。
- 四个内置 mutation 工具的统一版本失效。
- resume、tier-3 compatibility、Agent ToolContext、ContextManager 投影、MCP 和 pipeline 原有接线回归。

## 4. 验证结果

运行前执行了：

```text
source ~/.zshrc
export PATH="$HOME/.rustup/toolchains/1.96.1-aarch64-apple-darwin/bin:$PATH"
```

以下命令均在 rebase 后的 `main@6aacc9fb` 基线上重新通过：

| 命令 | 结果 |
| --- | --- |
| `cargo fmt --all -- --check` | 通过 |
| `cargo test -p octos-agent --test h02_m1_file_versions` | 3 passed |
| `cargo test -p octos-agent file_state_cache` | 15 passed |
| `cargo test -p octos-agent --lib tools::read_file::tests` | 52 passed |
| `cargo test -p octos-agent --lib tools::nofollow_tests` | 19 passed |
| `cargo test -p octos-agent --lib tools::write_file::tests` | 46 passed |
| `cargo test -p octos-agent --lib tools::edit_file::tests` | 36 passed |
| `cargo test -p octos-agent --lib tools::diff_edit::tests` | 10 passed |
| `cargo test -p octos-agent --lib tools::apply_patch::tests` | 46 passed |
| `cargo test -p octos-agent --test m8_integration_cache_handoff` | 2 passed |
| `cargo test -p octos-agent --test m8_integration_tool_context` | 4 passed |
| `cargo test -p octos-agent --test m8_end_to_end_gate` | 2 passed |
| `cargo test -p octos-cli --lib context_manager::tests` | 96 passed |
| `cargo test -p octos-cli --lib h02_m0_characterization_oup_and_mcp_agents_omit_file_cache_wiring` | 1 passed |
| `cargo test -p octos-cli --test mcp_serve_integration` | 12 passed |
| `cargo test -p octos-pipeline --test m8_parity` | 6 passed |
| `cargo clippy -p octos-agent -p octos-cli -p octos-pipeline --all-targets -- -D warnings -A clippy::nonminimal_bool` | 通过 |
| `git diff --check` | 通过 |

严格 Clippy：

```text
cargo clippy -p octos-agent -p octos-cli -p octos-pipeline --all-targets -- -D warnings
```

严格模式只被基线文件 `crates/octos-cli/src/commands/serve.rs:878` 的
`clippy::nonminimal_bool` 阻断。该文件不在 M1 diff 中，因此没有顺手修改。

早期还试跑过 `cargo test -p octos-agent` 全量测试。部分依赖本机
send-file、build-cache、sandbox/shell 环境的用例失败或超时，随后手动停止；
该次运行不计为通过证据。上表列出的 M1 相关确定性测试均完整退出并通过。

未调用真实模型。

## 5. 完成判断

当前每次 `read_file` 都从本次稳定读取的原始字节生成强版本。旧 mtime、
旧 hash、resume artifact 或遗漏主动失效都不能让 M1 省略正文。版本相同只会
更新磁盘事实，不会声称模型已经看过内容。

因此 M1 的完成条件已满足；M2 可以在此基础上新增独立的模型可见读取凭据。
