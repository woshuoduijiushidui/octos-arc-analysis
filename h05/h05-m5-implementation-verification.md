# H05 M5：exact-only `replace_all` 验证

- 状态：M5 已完成。
- 共同底座：`A_SHA=4c542e534e957d69a5ee05d24ffb7e166beb78bb`。
- M4 代码：`3fe3fce4c155f3e9ba8c762a2fc7bd3aa33daf3d`。
- M5 代码：`a1829e4d374e538f356a4e99956ba4f3415516a4`。
- 分支：`feat/local-edit`。
- 最终二进制 SHA-256：
  `9c936cc71743669d8fc1690fd61148c3b84235269cf6e8ce43d4d203ef0ac853`。

## 1. 开关与调用合同

`OCTOS_LOCAL_EDIT=1` 时，`edit_file` schema 增加可选布尔参数
`replace_all`，默认值为 `false`。只有显式传入 `true` 才进入批量路径；
省略或传入 `false` 时仍要求旧文本唯一，多个匹配继续返回
`edit_ambiguous`。

关闭开关时 schema、prompt 和原有调用行为保持兼容，传入新增参数会按未知参数拒绝。
开关开启但三个编辑工具未全部可见时，不注入工具选择说明，也不改工具描述；若
`edit_file` 本身可见，仍会暴露 `replace_all`。

## 2. 匹配与写入

批量路径只收集不重叠的 exact 或 CRLF/LF 等价匹配，不使用
`line_trimmed`、空白合并、缩进变换、转义或 block similarity 自动写入。没有安全
匹配时可返回 fuzzy 候选作为重试证据，但文件保持不变。

匹配、结果计算和一次性写入都在共享 `mutation_guard` 的同一目标锁内完成。guard
在 transform 前后重新读取并校验文件版本；并发替换目标时返回
`stale_file_version`，不会写入旧对象或返回过期候选。

批量替换保留未命中区域的原始 bytes，并根据命中位置保持 LF/CRLF 风格。相邻匹配
全部替换，重叠匹配按稳定的从左到右非重叠规则处理。限制如下：

```text
最多 1,000 个匹配
最终文件最多 10,000,000 bytes
最多返回前 20 个位置
```

超过匹配数或结果大小限制时返回 `invalid_edit_input`，并建议使用结构化生成器或明确
脚本，不会只替换前 N 个。

## 3. 结果与副作用

成功 metadata 包含 `replace_all`、真实 `replacement_count`、
`replacement_locations` 和 `replacement_locations_truncated`。模型可见摘要包含
matcher、总替换数和稳定行号；位置列表截断时仍保留总数。

formatter 继续复用 M3 的最终磁盘报告：`final_version`、`changed_range` 和
`diff_preview` 均基于 formatter 后的实际内容。`old_string == new_string` 返回
`no_change`；空旧文本、零匹配、超限、歧义和 stale 都不会触发 formatter、snapshot、
receipt/cache 失效或文件 mutation 事件。

## 4. 真实 stdio

最终二进制通过 `serve --stdio --solo` 连接 loopback fake provider，共 7 次请求：

1. 显式 exact `replace_all` 替换 3 处；
2. LF 参数匹配 CRLF 文件并替换 2 处，原文件仍为 CRLF；
3. 只有 fuzzy 候选时返回 typed no-match；
4. 1,001 个匹配超过上限，返回 typed limit；
5. 未传 `replace_all` 的重复 exact 仍返回 typed ambiguous；
6. 相同 old/new 返回 no-op；
7. provider 返回最终答案。

三条失败结果经 H03 投影后合计 3,447 bytes，均不可恢复且不生成后续完整读取。失败与
no-op 文件内容、mtime 和 snapshot 状态不变；事件流只记录 `batch.txt` 与
`crlf.txt` 两次真实修改。

机器可读摘要见 [summary.json](./m5-evidence/summary.json)，完整 provider 请求和事件见
[m5-evidence](./m5-evidence/)。

## 5. 验证

| 验证 | 结果 |
| --- | --- |
| `edit_file`：默认、批量、typed 限制、CRLF/Unicode、formatter | 60 passed |
| local-edit 汇总、registry、mutation guard | 50 / 57 / 5 passed |
| M4 `diff_edit`、`apply_patch` 回归 | 25 / 49 passed |
| H02/H03 与 M2-M5 agent 集成 | 42 passed |
| M0 关闭态 | 8 passed |
| stdio profile、MCP、spawn/worker | 1 / 18 / 94 passed，1 ignored |
| Python codegen | 71 passed |
| `cargo check --workspace --tests` | 通过 |
| `cargo clippy -p octos-agent --lib --tests -- -D warnings` | 通过 |
| `cargo fmt --all -- --check`、`git diff --check` | 通过 |
| 真实 stdio M5 | 5 次替换、3 次 typed 拒绝、1 次 no-op，全部通过 |
| 真实 stdio M0-M4 重放 | 全部通过 |

完整命令和结果见 [checks.json](./m5-evidence/checks.json)。构建与验证前均执行
`source ~/.zshrc`，并补充 Homebrew rustup 路径。最终链接只有 macOS
`__eh_frame section too large` 性能提示，不影响构建或测试。

本阶段未运行官方付费任务：当前环境缺少 `ARCBENCH_API_KEY`，固定任务 A/B/C 对照仍按
计划留到 M8。
