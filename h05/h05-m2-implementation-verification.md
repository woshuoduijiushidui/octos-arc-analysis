# H05 M2：typed 失败与有界当前候选验证

- 状态：M2 已完成。
- 共同底座：`A_SHA=4c542e534e957d69a5ee05d24ffb7e166beb78bb`。
- M1 代码：`f15f3a6c50bb2833a2c8475ffd7efd78c52f4fa1`。
- M2 代码：`7f892c66`。
- 分支：`feat/local-edit`。
- 最终二进制 SHA-256：
  `0ade1d5336656706f09ad42aad21656045736667729a5eadb0667d99560668c7`。

## 1. 实现范围

M2 只改变 `OCTOS_LOCAL_EDIT=1` 时 `edit_file` 的失败反馈，不改变成功匹配层级、
写入协议、默认工具集合、schema、codegen 或请求预算。关闭开关时，原有失败文本和磁盘
行为保持不变。

`replacer` 现在除原有结果外，还返回当前匹配证据：

- matcher 名称；
- 当前字节范围和 1-based 行范围；
- block-anchor 的可选 score；
- 完整 occurrence count；
- 最多 3 个、按稳定顺序排列的候选。

exact 为零时仍按原有六级链查找。B 变体继续自动写入唯一 fuzzy 匹配；只有歧义、无安全
匹配、过大 fuzzy 范围和无效输入返回 typed 拒绝。M7 才会单独实验“fuzzy 只提示”。

## 2. typed 拒绝链

transform 不再把 M2 失败压成普通字符串。`MutationTransformError` 携带有界
`MutationRejection`，经 `mutation_guard` 原样转成 `ToolResult`，canonical 字段仍是
`error_code`。

当前实现能返回：

```text
edit_ambiguous
edit_no_match
invalid_edit_input
stale_file_version
```

metadata 包含：

```text
path
current_version.content_sha256 / size
searched_old_digest
reason
matcher
occurrence_count
candidates[].byte_range / line_range / matcher / score / suggestion / excerpt
remedy
file_modified=false
```

模型文本只显示短版本。绝对路径只显示文件名；`old_string` 不回显。候选正文先经过现有
sanitize，再同时进入文本和 metadata。

## 3. 并发和 H02/H03 边界

候选定位、行号和正文均来自 `mutation_guard` 锁内读取的同一份当前 bytes。transform
拒绝后，guard 会再次读取并比较版本；候选计算期间若文件变化，返回
`stale_file_version`，不会泄露旧候选。

每个候选正文最多 512 bytes，总候选最多 3 个，单个 typed 失败文本最多 3,072 bytes。
文本按以下优先级排列：

```text
error code -> path -> occurrence count -> short current version -> remedy
-> candidate ranges -> candidate bodies
```

因此 H03 预算不足时先裁候选正文。512-byte 极小投影仍保留错误码、短版本、补救动作和
首个候选行号。

候选使用 `OutputDocument` 进入 H03 最终投影，但 `file_read=None`。最终 header 为
`recoverable=false`，没有 `read_file_next`，不能生成 H02 完整文件读取 receipt，也不能
授权整文件覆盖。

## 4. 验证

| 验证 | 结果 |
| --- | --- |
| `edit_file`：Unicode、CRLF、长行、长/绝对路径、sanitize、无候选、多 matcher、空输入 | 45 passed |
| `replacer`：候选范围、行号、score、排序和原有六级行为 | 30 passed |
| `mutation_guard`：写前替换、symlink 替换、typed 拒绝期间变化 | 3 passed |
| `ToolRegistry`：开关传递、快照/过滤/超时等回归 | 57 passed |
| H03 最终输出 + H05 M0 + M2 fake provider | 22 passed |
| `cargo check --workspace --tests` | 通过 |
| `cargo clippy -p octos-agent --lib --tests -- -D warnings` | 通过 |
| `cargo fmt --all -- --check`、`git diff --check` | 通过 |
| 真实 stdio M2 | 5 requests，typed 结果合计 1,953 bytes |
| 真实 stdio M1 开关与 M0 关闭态重放 | 全部通过 |

真实 stdio 使用 `serve --stdio --solo` 和 loopback fake provider，不调用付费模型。
机器可读结果见 [summary.json](./m2-evidence/summary.json)，完整 provider 请求和事件见
[m2-evidence](./m2-evidence/)。

构建前已执行 `source ~/.zshrc`。当前 `~/.zshrc` 未加入 Homebrew rustup 路径，验证时
额外加入 `/opt/homebrew/Cellar/rustup/1.29.0_2/bin`。最终链接只有 macOS
`__eh_frame section too large` 性能提示，不影响构建结果。

本阶段未运行官方付费任务：当前环境缺少 `ARCBENCH_API_KEY`，应配置在 shell 环境后由 M8
执行固定任务 A/B/C 对照。M3 可在当前 typed 失败基础上实现 no-op 和 formatter 后的实际
改动元数据；不得把本阶段候选当成完整文件读取授权。
