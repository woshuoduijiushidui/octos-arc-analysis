# H05 M3：no-op 与最终实际改动元数据验证

- 状态：M3 已完成。
- 共同底座：`A_SHA=4c542e534e957d69a5ee05d24ffb7e166beb78bb`。
- M2 代码：`7f892c66`。
- M3 代码：`384e327999c0099fcc2b236f96e0a63dab606a40`。
- 分支：`feat/local-edit`。
- 最终二进制 SHA-256：
  `bafcff96ac90003c1e5fba8cb62c29854b1e6bdec0eb44ff387f4d4c0be40636`。

## 1. no-op 写入边界

`edit_file`、`diff_edit` 和已有文件上的 `write_file` 在
`OCTOS_LOCAL_EDIT=1` 时共用 `mutation_guard` 的 no-op 判定。判定发生在路径锁内，
并且排在权限、write grant、read-window epoch、文件版本和二次稳定读取之后，但排在
`seek`、`set_len`、`write_all` 之前。

候选 bytes 与锁内当前 bytes 相同时返回：

```text
success=true
file_modified=None
structured_metadata.outcome=no_change
```

此路径只释放 mutation claim，不标记写入成功，因此不会消费文件版本、撤销 H02 receipt、
invalidate cache、运行 formatter 或创建 workspace snapshot。测试同时固定了 bytes、
mtime、inode 和 ctime。相同内容仍不能绕过只读权限、create-only write grant、过期
`FileVersion` 或已失效的 read-window descriptor epoch。

三个入口均已覆盖：

- `edit_file` 的 `old_string == new_string`，即使该字符串不在文件中也明确 no-op；
- `diff_edit` 应用后 bytes 不变；
- `write_file` 覆盖已有文件时内容不变；
- 新建空文件不属于 no-op，仍创建文件并报告真实修改。

## 2. 最终实际改动

真实写入由共享 `MutationReport` 记录三段状态：

```text
before_version
write_version
final_version
```

报告还包含 `matcher`、`replacement_count` 或 `hunk_count`、工具写入范围、
formatter 后最终范围、formatter 状态、`formatter_expanded_change`、最多 2,048 bytes
的 unified diff preview，以及 AppUI 已使用的 `codex_tool`、`diff_preview` 和
`modified_paths` 字段。

formatter 执行后会重新读取稳定的磁盘内容，再计算最终 SHA、行范围和 diff。rustfmt
测试证明 formatter 扩大改动时 `write_version != final_version`，最终 SHA 与磁盘内容
一致。formatter 失败或超时不会把已经落盘的修改说成未修改；结果保持成功并带
`file_modified` 与失败状态。

写入完成后还会从同一 descriptor 回读并核对候选 bytes。若 truncate/write 后发生
descriptor 替换或回读不一致，错误会标记为“可能已经修改”，不会再返回容易误导模型的
普通 stale 结果。

## 3. 真实 stdio

最终二进制通过 `serve --stdio --solo` 连接 loopback fake provider，共 7 次请求：

1. `edit_file` 相同参数 no-op；
2. `read_file` 建立整写所需的当前版本；
3. `write_file` 相同内容 no-op；
4. `diff_edit` 相同 diff no-op；
5. `write_file` 创建空文件；
6. `edit_file` 执行真实修改；
7. provider 返回最终答案。

三个 no-op 模型可见文本分别为 80、88、83 bytes。两个真实修改摘要分别为 96、98
bytes，均包含最终 SHA。三个原文件 mtime 和内容保持不变，嵌套站点未创建 Git
snapshot；事件流只出现 `empty.txt` 和 `actual.txt` 两个真实修改。

机器可读摘要见 [summary.json](./m3-evidence/summary.json)，完整 provider 请求和事件见
[m3-evidence](./m3-evidence/)。

## 4. 验证

| 验证 | 结果 |
| --- | --- |
| 共享报告、写入边界、`edit_file`、`diff_edit`、`write_file` | 3 / 5 / 50 / 13 / 54 passed |
| `apply_patch` 共享写入边界回归 | 49 passed |
| local-edit、profile、ToolRegistry | 28 / 9 / 57 passed |
| H03 输出、M2 typed 失败、M3 fake provider | 15 passed |
| M0 关闭态 | 8 passed |
| H02 receipt 生命周期 | 16 passed |
| stdio profile、MCP、spawn/worker | 1 / 18 / 94 passed，1 ignored |
| `cargo check --workspace --tests` | 通过 |
| `cargo clippy -p octos-agent --lib --tests -- -D warnings` | 通过 |
| `cargo fmt --all -- --check`、`git diff --check` | 通过 |
| 真实 stdio M3 | 3 no-op，2 个真实修改，全部通过 |
| 真实 stdio M2、M1、M0 重放 | 全部通过 |

完整命令和结果见 [checks.json](./m3-evidence/checks.json)。构建与验证前均执行
`source ~/.zshrc`，并补充 Homebrew rustup 路径。最终链接只有 macOS
`__eh_frame section too large` 性能提示，不影响构建或测试。

本阶段未运行官方付费任务：当前环境缺少 `ARCBENCH_API_KEY`，固定任务 A/B/C 对照仍按
计划留到 M8。
