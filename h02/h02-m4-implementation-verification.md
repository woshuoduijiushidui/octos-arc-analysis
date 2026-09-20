# H02 M4：文件修改时的陈旧版本保护验证

- 日期：2026-09-20
- 状态：完成，可进入 M5
- 分支：`feat/safe-file-cache`
- 主线基线：`main@6aacc9fb1a1599ae10f8368921ccf3e3afb7f87e`
- M4 代码提交：`1dc0f7e5d5385155c9e890c240de0524d1b67a15`
- 远程状态：未推送

## 1. 本次完成的行为

1. 新增共享的本地文件修改保护层。它按规范化工作区和目标文件串行处理同一
   文件的修改，并在同一个已打开文件句柄上执行“读取、SHA-256 校验、再次核对、
   截断写入”。
2. `write_file` 覆盖现有文件时，如果任务已启用版本账本，必须取得最近一次
   稳定读取产生的版本。文件内容、大小、mtime 被伪造回原值但 SHA-256 不同时，
   写入仍会被拒绝。
3. 同一读取版本只能被一个并发修改领取。两个并发整文件覆盖最多一个成功，
   另一个返回 `stale_file_version`。
4. `edit_file` 和 `diff_edit` 不复用调用开始时的旧内存快照，而是在受保护的当前
   文件句柄上重新寻找上下文。唯一匹配才写入；找不到或有多个匹配均不落盘。
5. `apply_patch` 在计划阶段保存现有文件的强版本和原文，执行阶段重新核对。
   新增文件使用排他创建，更新和删除使用计划时版本，计划后替换文件会失败。
6. 工作区内的最终打开复用逐级 `openat + O_NOFOLLOW`，可阻止中途把父目录或
   文件换成 symlink。受写入白名单保护的路径继续使用同一套 confined open。
7. 原有 `read_window` 的完整、部分、脱敏、格式转换和 epoch 判定仍是
   `write_file` 的前置条件；强版本校验没有替代这套授权。
8. 陈旧写入返回稳定错误码 `stale_file_version`、expected/current 的
   SHA-256 与大小摘要，以及“重新读取、检查、再修改”的恢复指引。绝对路径只显示
   文件名，不返回正文。
9. 四个内置修改工具成功后都会失效磁盘版本，并精确撤销当前模型分支中该目标的
   staged/active receipt。写入成功文本本身不会创建新 receipt。
10. 修改失败不会登记新文件版本。上下文不匹配和普通 I/O/权限错误保持各自错误
    类型，不伪装成 stale，也没有自动重试旧修改意图。

## 2. 工具行为

| 工具 | 最终写入前的检查 |
| --- | --- |
| `write_file` | 已有文件核对账本中的完整强版本；新文件使用排他创建 |
| `edit_file` | 在当前句柄上重新做 exact/fuzzy 唯一匹配，再次核对后回写 |
| `diff_edit` | 在当前句柄上重新应用 hunk；目标范围内 0 次或多次匹配均拒绝 |
| `apply_patch` | 计划时保存版本/原文，执行时重新核对；Add/Delete/Update/Move 均使用受保护操作 |

局部编辑允许文件发生不冲突的外部变化：只要当前磁盘上的旧文本或 patch context
仍然唯一，就对当前内容应用修改。整文件覆盖没有旧文本可重新定位，因此要求之前
读取得到的完整强版本。

## 3. 场景覆盖

| Research 场景 | M4 证据 |
| --- | --- |
| 6：同大小且恢复 mtime | `write_file` 测试把内容从 `AAAA` 改为 `BBBB` 并恢复 mtime，SHA-256 不同使覆盖失败 |
| 7：外部修改 | `edit_file` 在外部增加不冲突内容后重新唯一匹配并成功；整文件旧版本覆盖失败 |
| 8：成功后撤销 receipt | targeted revoke 测试保留其他文件 receipt，只删除被修改目标及写入前 pending |
| 13：同一版本并发修改 | 两个并发 `write_file` 请求恰好一个成功，另一个得到 typed stale |
| 14：唯一 patch context | `edit_file`、`diff_edit`、`apply_patch` 均覆盖唯一成功、0 次失败和多次匹配失败 |
| 17：读取/修改中途替换 | 共享 guard 测试在匹配后、截断前替换 inode，返回 typed stale 且保留替换文件 |
| 18：symlink/alias | M1 canonical alias 测试继续通过；M4 在计划后和截断前换成 symlink 时均拒绝写入 |

## 4. 验证结果

运行前执行：

```text
source ~/.zshrc
export PATH="$HOME/.rustup/toolchains/1.96.1-aarch64-apple-darwin/bin:$PATH"
```

通过的命令：

| 命令 | 结果 |
| --- | --- |
| `cargo test -p octos-agent --lib tools::write_file::tests` | 48 passed |
| `cargo test -p octos-agent --lib tools::edit_file::tests` | 37 passed |
| `cargo test -p octos-agent --lib tools::diff_edit::tests` | 11 passed |
| `cargo test -p octos-agent --lib tools::apply_patch::tests` | 49 passed |
| `cargo test -p octos-agent --lib tools::mutation_guard::tests` | 2 passed |
| `cargo test -p octos-agent --lib tools::write_grant::tests` | 15 passed |
| `cargo test -p octos-agent --lib tools::nofollow_tests` | 19 passed |
| `cargo test -p octos-agent --lib tools::read_window::tests` | 16 passed |
| `cargo test -p octos-agent --lib file_state_cache::tests` | 14 passed |
| `cargo test -p octos-agent --lib model_read_receipts::tests` | 14 passed |
| `cargo test -p octos-agent --test h02_m1_file_versions --test h02_m2_read_receipts --test h02_m3_receipt_lifecycle` | 18 passed |
| `cargo check -p octos-agent --all-targets` | 通过 |
| `cargo clippy -p octos-agent --all-targets -- -D warnings` | 通过 |
| `cargo clippy --workspace --all-targets -- -D warnings -A clippy::nonminimal-bool` | 通过 |
| `cargo fmt --all -- --check` | 通过 |
| `git diff --check` | 通过 |

严格的全工作区 Clippy 仍只被基线文件
`crates/octos-cli/src/commands/serve.rs:878` 的
`clippy::nonminimal_bool` 阻断；该文件不在 M4 diff 中。

没有重复运行已知会受 macOS sandbox、后台进程和 send-file 环境影响的
`cargo test -p octos-agent --lib` 全量套件。M4 直接修改和依赖的确定性测试均已
单独完整退出并通过。

未调用真实模型。

## 5. 完成判断

整文件覆盖不能再凭旧 mtime、旧 size 或过期读取直接写入；局部修改只能在当前
磁盘内容中找到唯一上下文后落盘。文件在计划、审批或匹配后被替换时，工具会在
截断前停止，并返回可机器识别且可操作的重读提示。成功修改会立即撤销当前分支的
旧读取凭据，失败不会制造新版本或新凭据。

因此 M4 的 stale mutation 失败关闭条件已满足，可以进入 M5。
