# H05 M1：局部编辑选择规则验证

- 状态：M1 已完成。
- 共同底座：`A_SHA=4c542e534e957d69a5ee05d24ffb7e166beb78bb`。
- M0 测试：`01f7480e0426fa341e2cd2d3d0e06ad35d11c352`。
- M1 代码：`f15f3a6c50bb2833a2c8475ffd7efd78c52f4fa1`。
- 分支：`feat/local-edit`。
- 最终二进制 SHA-256：
  `0996d664918bf8453b29cd5bb9cc65dbffd2b70f0efe1547d612d1468bf44bac`。

## 1. 实现范围

M1 只实现 H05a，没有改变工具执行、matcher、失败结果、写入保护、codegen、预算或
默认工具集合。

新增 `local_edit.rs` 作为唯一配置和文案来源：

- `OCTOS_LOCAL_EDIT` 在进程内由 `OnceLock` 解析一次；
- `1/true/on` 开启，未设置及 `0/false/off` 关闭；
- 未知值关闭，并输出不回显原值的固定长度诊断；
- `ToolRegistry` 构造时保存解析后的 policy，snapshot/rebind 沿用同一值。

公共 `compose_system_prompt` 只在开关开启且 `write_file`、`edit_file`、
`diff_edit` 三者都对模型可见时追加一次：

```text
## File editing

Choose before generating arguments:
- New file: `write_file`.
- One contiguous change in an existing file: `edit_file`.
- Multiple separated changes in one existing file: one multi-hunk `diff_edit`.
Use `write_file` on an existing file only when its complete current contents
are visible and a whole-file rewrite is necessary. Edit multiple files with
separate calls; mutations run serially.
```

使用同一个 `ToolRegistry` 判定同步替换三个最终 ToolSpec description：

- `write_file`：新文件，或在完整当前内容可见且确需整体重建时整写；
- `edit_file`：已有文件的一个连续、唯一局部；
- `diff_edit`：同一已有文件的多个分散修改，使用一次 multi-hunk diff。

受限 profile 若缺少任一编辑工具，不注入引用不可用工具的系统规则，也不改剩余工具描述。
这保留了 slides 等窄工具面的既有契约。

## 2. 入口一致性

普通对话由 `process_message`、MCP 和 spawn/worker 由 `run_task` 构造初始消息；
两者都调用同一个 `compose_system_prompt`。因此 stdio/solo、普通 coding profile、
MCP 和 worker 不各自复制提示文案，也不会随入口产生不同版本。

本阶段没有修改 `arc/prompts/`：

- 工具模式已经通过共享 system prompt 获得规则，不需要再向 ARC user prompt 重复；
- codegen 模式没有这些工具，保持完整文件协议，留到 M9 单独实验；
- provider-specific 工具排序、注册数量和 `apply_patch` 可见性均保持不变。

## 3. 关闭兼容与固定成本

真实 `serve --stdio --solo` 使用三个独立进程测试 `0`、`1` 和未知值。每个进程连接
loopback fake provider，不调用付费模型。结果：

| 项目 | A / off | M1 / on | 增量 |
| --- | ---: | ---: | ---: |
| provider 工具数 | 13 | 13 | 0 |
| provider 工具 schema | 9,286 bytes | 9,379 bytes | 93 bytes |
| system prompt | 归一化后与 M0 相同 | 增加一段 | 410 bytes |
| 每次请求固定输入 | - | - | 503 bytes |
| ARC proxy 裁剪后固定输入 | - | - | 503 bytes |

off 的 schema SHA-256 仍为 M0 的
`79f97b610f4178e8820be561ce5fac943e6d43d04cb07e0147ac31aec2acdafa`。
on 只改变 `diff_edit`、`edit_file`、`write_file` 的 description，参数 schema、
工具名和顺序完全相同；system prompt 中标题只出现一次。未知值与 off 的 schema 和
H05 提示一致，并在 stderr 输出：

```text
warning: unknown OCTOS_LOCAL_EDIT value; local-edit guidance disabled
```

关闭态还用最终 M1 二进制重放了 M0 的真实 stdio 工具序列：无匹配后重读、歧义、
block-anchor 自动写、超过三行的 diff 漂移和 no-op 写入全部保持 A 行为。

## 4. 验证

机器可读结果见 [checks.json](./m1-evidence/checks.json)，三组最终请求及 stderr 见
[m1-evidence](./m1-evidence/)。

| 验证 | 结果 |
| --- | --- |
| policy、单次提示注入、受限工具面、schema 差异 | 6 passed |
| coding profile | 9 passed |
| ToolRegistry | 56 passed |
| H03 最终输出 + H05 M0 反例 | 21 passed |
| stdio profile | 1 passed |
| MCP | 18 passed |
| spawn/worker | 94 passed、1 ignored |
| workspace `cargo check --tests` | 通过 |
| fmt、diff check | 通过 |
| Clippy（沿用一项主线豁免） | 通过 |
| 真实 stdio M1 开关 | off/on/未知值全部通过 |
| 真实 stdio M0 行为重放 | 7 requests，全部通过 |

严格 Clippy 仍只报未修改的
`crates/octos-cli/src/commands/serve.rs:878 clippy::nonminimal_bool`；加入既有单项
豁免后通过。全量 `octos-agent --lib` 未作为门槛：该宿主上的既有 sandbox、
后台进程和 build-cache 时序用例会失败或长时间阻塞，已改用本次影响范围的定向套件。

本阶段未运行官方付费任务，正确率与 token 收益仍留到 M8。M2 可在当前短规则之上增加
typed 失败和有界当前候选；不得改变这里冻结的工具选择或 off 兼容行为。
