# H05 M4：diff_edit 全文件唯一 fallback 验证

- 状态：M4 已完成。
- 共同底座：`A_SHA=4c542e534e957d69a5ee05d24ffb7e166beb78bb`。
- M3 代码：`384e327999c0099fcc2b236f96e0a63dab606a40`。
- M4 代码：`3fe3fce4c155f3e9ba8c762a2fc7bd3aa33daf3d`。
- 分支：`feat/local-edit`。
- 最终二进制 SHA-256：
  `777a307097cd29e0a9431fe4a50c9da8dad19f7682f3b74b9ae17113a39c4566`。

## 1. 匹配顺序

`OCTOS_LOCAL_EDIT=1` 时，`diff_edit` 对每个 hunk 按以下顺序定位：

1. 保留原有目标行附近 `+-3` 搜索和 trailing-whitespace 兼容行为；
2. 局部窗口完全没有候选时，才扫描全文件；
3. 全文件扫描只比较逐行文本，忽略 `CRLF` 与 `LF` 分隔符差异，但不 trim
   行尾空格，不使用空白合并、缩进变换、转义或相似度匹配；
4. 全文件恰好一个候选才应用，多个或零个候选均拒绝。

关闭开关时仍调用原有 `apply_hunks`，错误文本、`+-3` 范围、trailing-whitespace
匹配和 LF 写回行为保持不变。

全文件 fallback 设有三重上限：

```text
10,000,000 bytes
100,000 lines
1,000,000 line comparisons
```

超过任一上限返回 `diff_context_no_match`，reason 为 `global_scan_limit`，不会继续做
高成本扫描。

## 2. typed 失败证据

全文件重复返回 `diff_context_ambiguous`，零匹配返回
`diff_context_no_match`，空 context 与实际位置重叠返回
`invalid_edit_input`。

metadata 包含：

```text
path
current_version
searched_context_digest
reason
hunk_index
expected_line
matcher
occurrence_count
candidates
full_file_scanned
scan_limits
remedy
file_modified=false
```

候选按行号稳定排序，最多 3 个；每段 excerpt 最多 512 bytes，单个失败文本最多
3,072 bytes。候选来自 `mutation_guard` 锁内的当前 bytes，并经过现有 sanitizer。
零匹配时返回目标行附近的当前片段。结果使用不可恢复 `OutputDocument`，不会生成完整
文件读取 receipt；若生成证据期间文件变化，仍由共享 guard 优先返回 stale。

## 3. 多 hunk 与行尾

开启路径先在同一份不可变内容上定位所有 hunk，再验证实际范围不重叠，最后按实际位置
从后向前写入内存副本。后一个 hunk 新增或删除的文本不会改变前一个 hunk 的候选集合；
任一 hunk 失败时 transform 整体拒绝，磁盘不发生写入。

成功 metadata 新增 `hunk_matches`，逐项记录输入序号、声明行、实际行和 matcher；
`full_file_fallback_count` 汇总全文件 fallback 数量。模型摘要使用
`positions=声明行->实际行`，不回显 diff 全文。

开启路径按原文件 byte span 替换，只重建命中的 hunk：

- 未修改区域逐字节保留；
- context 行沿用磁盘中的原文本和行尾；
- 新增行沿用命中位置的 `CRLF` 或 `LF`；
- 文件原本无末尾换行时不新增末尾换行；
- 全文件匹配不会忽略 Markdown 双空格等有语义的尾随内容。

## 4. 真实 stdio

最终二进制通过 `serve --stdio --solo` 连接 loopback fake provider，共 5 次请求：

1. 声明第 1 行、实际第 5 行的唯一 hunk 成功；
2. 两个全文件候选返回 typed ambiguous；
3. 零候选返回 typed no-match 和目标位置附近片段；
4. 两个 hunk 在原始内容上预定位后成功反向应用；
5. provider 返回最终答案。

两条失败结果经 H03 投影后合计 1,307 bytes，均标记 `recoverable=false`。失败文件内容和
mtime 不变，失败目录未创建 snapshot；事件流只记录 `unique.txt` 和 `multi.txt` 两次
真实修改。

机器可读摘要见 [summary.json](./m4-evidence/summary.json)，完整 provider 请求和事件见
[m4-evidence](./m4-evidence/)。

## 5. 验证

| 验证 | 结果 |
| --- | --- |
| `diff_edit`：局部、全文件、typed 失败、多 hunk、行尾和扫描上限 | 25 passed |
| M4 agent fake provider | 1 passed |
| local-edit、`apply_patch`、mutation guard | 39 / 49 / 5 passed |
| H02 文件版本 | 3 passed |
| H03 输出 + M2/M3/M4 集成 | 16 passed |
| M0 关闭态 | 8 passed |
| MCP、spawn/worker | 18 / 94 passed，1 ignored |
| Python codegen | 71 passed |
| `cargo check --workspace --tests` | 通过 |
| `cargo clippy -p octos-agent --lib --tests -- -D warnings` | 通过 |
| `cargo fmt --all -- --check`、`git diff --check` | 通过 |
| 真实 stdio M4 | 2 次成功、2 次 typed 拒绝，全部通过 |
| 真实 stdio M0-M3 重放 | 全部通过 |

完整命令和结果见 [checks.json](./m4-evidence/checks.json)。构建与验证前均执行
`source ~/.zshrc`，并补充 Homebrew rustup 路径。最终链接只有 macOS
`__eh_frame section too large` 性能提示，不影响构建或测试。

本阶段未运行官方付费任务：当前环境缺少 `ARCBENCH_API_KEY`，固定任务 A/B/C 对照仍按
计划留到 M8。
