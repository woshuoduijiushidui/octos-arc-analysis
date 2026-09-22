# H05 M7：C 的 fuzzy 只提示验证

- 状态：M7 已完成，C 已冻结。
- B 基线：`B_SHA=8287e8f8ae63a27a58ab5898ecb2753b9b946c45`。
- C 版本：`C_SHA=bb53c733ff6a40b477e5b6502dcb512a28be32ca`。
- 分支：`feat/local-edit`。
- 最终二进制 SHA-256：
  `4bf5952b52c50ba73b20f6abade9539beac1c54a5209b2d5a85a243585146d8b`。

## 1. 独立开关

新增 `OCTOS_LOCAL_EDIT_STRICT_MATCH`，默认关闭，并且只有
`OCTOS_LOCAL_EDIT=1` 时才生效：

```text
OCTOS_LOCAL_EDIT=0 + strict 任意值 -> A 行为
OCTOS_LOCAL_EDIT=1 + strict=0/未设置 -> B 行为
OCTOS_LOCAL_EDIT=1 + strict=1 -> C 行为
```

两个开关都在进程内解析一次，由同一个 `LocalEditPolicy` 保存，再通过 registry 的
task-local 执行上下文传给工具。未知 strict 值按关闭处理并输出有界 warning。

## 2. C 的匹配边界

`edit_file` 在 C 中按以下顺序决定是否写入：

1. exact 匹配优先，保持 B 的唯一性规则；
2. 没有 exact 时允许唯一的 CRLF/LF 等价匹配；
3. `line_trimmed`、`whitespace_normalized`、`indentation_flexible`、
   `escape_normalized` 和 `block_anchor` 只生成当前版本候选；
4. 多个 exact 或行尾等价匹配仍返回 ambiguous，绝不选择第一处。

`replace_all=true` 本来就只允许 exact/行尾等价，因此 C 不改变它。

`diff_edit` 在 C 中只接受逐行 exact；行尾编码由现有行索引处理，所以 CRLF/LF 等价
仍可写入。局部窗口的 trailing-whitespace 宽松匹配只作为 suggestion；全文件 fallback
仍要求唯一 exact。多 hunk 继续先全部定位，任一 hunk 只有 fuzzy 候选时整体零写入。

## 3. 候选与说明

strict 拒绝复用 B 已有的 typed 结果、当前强版本、候选范围、matcher、score、excerpt、
sanitizer 和 H03 预算。`file_modified` 保持为空，失败目录不产生 snapshot 或 mutation
事件。

候选排序在重复调用间稳定。block-anchor 继续保留 score，其他 matcher 保留准确类型和
行范围。

B 与 C 的 system prompt、工具名称和 input schema 完全相同。只有 `edit_file` 和
`diff_edit` 的工具描述改为说明“近似匹配只作为 suggestion”；`write_file` 及其他工具
描述不变。完整 tool spec 因文案缩短 21 bytes。

## 4. 真实 stdio 对照

最终 C 二进制通过 `serve --stdio --solo` 分别启动 B 和 C 两个独立进程，每个变体
15 次 provider 请求，使用相同 fixture、调用顺序、模型和预算：

- 8 个 fuzzy 场景：Python 缩进、Markdown 双空格、字符串字面量空格、模板文本、
  indentation-flexible、转义字符串、block-anchor 和 diff trailing whitespace；
- 4 个安全写入：exact、CRLF/LF 等价、远距离 exact diff、exact `replace_all`；
- 2 个共享非写入：exact 歧义和 no-op。

结果：

| 指标 | B | C |
| --- | ---: | ---: |
| fuzzy 自动写入 | 8 | 0 |
| fuzzy suggestion | 0 | 8 |
| 安全写入 | 4 | 4 |
| 总 mutation 事件 | 12 | 4 |

C 的 8 条 fuzzy 失败文本合计 4,615 bytes，低于 8 KiB；对应文件全部保持原 bytes。
exact、CRLF、全文件 exact diff 和 `replace_all` 的结果均正确。普通 stderr 未出现源码
正文、调用参数或凭据。

机器可读汇总见 [summary.json](./m7-evidence/summary.json)，完整 B/C provider 请求和
事件见 [m7-evidence](./m7-evidence/)。

## 5. T01-T16 与范围

C 重新通过 T01-T16；T04 的判定按计划改为“返回 suggestion 且零写入”，其余合同不变。
逐项证据见 [acceptance-matrix.json](./m7-evidence/acceptance-matrix.json)。

`B_SHA..C_SHA` 只有一个提交和 6 个文件：

- strict 真实 stdio 夹具；
- policy、registry task-local 与工具描述；
- `edit_file` 和 `diff_edit` 的 strict 分支；
- 相邻单元/profile 测试。

没有修改 `write_file`、mutation guard/report、codegen、官方输入、模型、预算、system
prompt、input schema 或默认 profile，也没有把 `apply_patch` 加回默认工具面。机器可读
审查见 [scope-audit.json](./m7-evidence/scope-audit.json)。

## 6. 验证

| 验证 | 结果 |
| --- | --- |
| strict 专项 | 8 passed |
| edit / diff / replacer | 63 / 29 / 30 passed |
| registry / profile / local-edit 汇总 | 57 / 10 / 50 passed |
| mutation guard / write / formatter / apply_patch | 7 / 54 / 35 / 49 passed |
| B 的 H02/H03 与 M2-M6 集成 | 43 passed |
| H05 off 且 strict=1 | 8 passed，strict 不生效 |
| AppUI prompt / diff preview / file mutation | 1 / 5 / 8 passed |
| MCP、spawn/worker | 18 / 94 passed，1 ignored |
| `octos-arc` | 130 lib passed，2 ignored；1 integration passed |
| Python codegen | 71 passed |
| `cargo check --workspace --tests` | 通过 |
| 三 crate、all-targets 严格 Clippy | 通过 |
| `cargo fmt --all -- --check`、`git diff --check` | 通过 |
| 真实 stdio B/C | 每组 15 requests，全部断言通过 |
| 最终 C 二进制重放 M0-M6 的 B 路径 | 全部通过 |

完整命令见 [checks.json](./m7-evidence/checks.json)。测试与构建前均执行
`source ~/.zshrc`，并补充 Homebrew rustup 路径。macOS 链接器仍只有已知的
`__eh_frame section too large` 性能提示。

本阶段未运行官方付费任务：当前环境缺少 `ARCBENCH_API_KEY`。B/C 的真实模型正确率与
token 对照必须留到 M8，不能仅凭 deterministic 结果提前选择方案。
