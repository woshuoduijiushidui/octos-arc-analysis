# H05 M0：共同底座、局部编辑调用链与基线反例

- 状态：M0 已完成；H05 运行时行为尚未开启。
- 日期：2026-09-21（本机时区）。
- 代码分支：`feat/local-edit`。
- `MAIN_SHA`：`27d057c206c0f8250b60309905737f7e26ee0ba9`。
- `A_SHA`：`4c542e534e957d69a5ee05d24ffb7e166beb78bb`。
- M0 测试提交：`01f7480e0426fa341e2cd2d3d0e06ad35d11c352`。
- 本阶段未运行付费模型或官方做题实验。

## 1. 分支与共同底座

执行 `source ~/.zshrc` 后拉取两个仓库的最新 `origin/main`。代码主线仍为
`27d057c2`，分析主线为 `f32ac07e`。两个仓库均从各自主线创建
`feat/local-edit`。分析分支随后以 `--ff-only` 接入已冻结的
`feat/output-recovery@611facb`，使 H05 引用的 H03 文档和证据可直接复核。开工时：

- `octos-arc` 位于已冻结的 H03 分支，工作树干净；
- `octos-arc-analysis` 的 `h05/` 是用户已有的未跟踪目录；
- 没有清理、覆盖或改写上述分支和文件。

最新代码主线不含 H02/H03。H03 完整 B 是从同一个 `MAIN_SHA` 线性演进的
15 个原始提交，已经包含 H02 B，因此 H05 分支直接 `--ff-only` 快进到
`4c542e53`。这种方式保留原提交 SHA，没有重新 cherry-pick 出一套副本。

| 依赖 | 主线状态 | M0 处理 |
| --- | --- | --- |
| H02 强版本、读取凭据和写保护 | 未包含 | 原样保留到 `9d65681c` |
| H03 8 KiB 最终输出、恢复和搜索 | 未包含 | 原样保留到 `4c542e53` |
| H04 MCP task-loop 压缩 | 无有效实现 | 条件性“不适用”；H05 不顺手修改 |

H04 的判断来自真实调用：MCP 在 `commands/mcp_serve.rs:612-730` 构造
`CompactionRunner` 后调用 `Agent::run_task`；普通对话循环在
`agent/loop_runner.rs:1317-1354` 调用 preflight/turn compaction，而
`run_task_inner` 的请求前路径（约 2648-2673）只有 tier-1 和
ContextManager，没有对应两次调用。因此不能把“runner 已挂载”记为 H04 已完成。

`A_SHA` 是 H05 的共同运行底座。`01f7480e` 只新增 M0 测试和离线夹具，
不改变生产行为。

## 2. 变体与开关

M0 冻结后续唯一变量：

| 变体 | `OCTOS_LOCAL_EDIT` | `OCTOS_LOCAL_EDIT_STRICT_MATCH` | `OCTOS_ARC_CODEGEN_PATCH` |
| --- | --- | --- | --- |
| A | off | off | off |
| B | on | off | off |
| C | on | on | off |
| D | 与 M8 选中的 S 相同 | 与 S 相同 | on |

三个 H05 变量在 A 中尚未实现，等价于 off。M1 起应在 profile/进程组装时解析一次；
未知值关闭并输出有界诊断。关闭 B 时必须保持本记录中的 schema、文本和磁盘行为。

H05 对照固定启用已有 H03：

```text
OCTOS_FILE_READ_DEDUP=1
OCTOS_FILE_READ_RETAINED_RECEIPTS=0
OCTOS_OUTPUT_RECOVERY=1
OCTOS_OUP_SEMANTIC_CONTEXT_MODE=on
OCTOS_READ_WINDOW=1
OCTOS_DANGER_FULL_ACCESS=0
```

H01 保持共同底座现状；H04 保持未接通状态。依赖收益不得算作 H05 收益。

## 3. 三种编辑工具的真实调用链

共同入口如下：

```text
Profile/stdio allow-list
  -> ToolRegistry::specs（排序后的 ToolSpec）
  -> Agent::handle_tool_use（人工审批策略）
  -> Agent::execute_tools（批次分类、写前 snapshot）
  -> spawn_tool_task（ToolContext、hook、超时）
  -> ToolRegistry::execute_with_context
  -> edit_file / diff_edit / write_file
  -> mutation_guard（路径锁、当前 bytes、版本、写入）
  -> 可选 formatter
  -> receipt/cache 失效和 workspace git snapshot
  -> ToolResult.output -> Tool Message -> 下一轮 provider
```

关键事实：

1. `ToolRegistry::specs` 在 `tools/registry.rs:700` 生成并按名称稳定排序的 schema；
   `execute_with_context` 在约 1118 行做 policy、参数大小、panic 和 timeout 边界。
2. `edit_file`、`diff_edit`、`write_file` 都返回 `Exclusive`。`execute_tools`
   在 `agent/execution.rs:2553` 先按并发类别分批，写工具按模型调用顺序串行；
   一个失败会取消后续 exclusive sibling。
3. 人工审批规则在 `loop_runner::handle_tool_use` 执行前拦截。批准后的调用走
   `Agent::execute_approved_tool`，仍建立完整 `ToolContext`、写前 snapshot、
   hook 和 H03 最终输出投影，不走一套简化写入。
4. `edit_file` 在 `edit_file.rs:122-280` 完成参数和权限检查后，把 matcher
   放入 `mutation_guard::rewrite_existing` 的锁内 transform。
5. `diff_edit` 在锁外解析完整 diff，在锁内对当前文本应用全部 hunk；只有生成完整
   新 bytes 后才进入一次写盘，因此匹配或解析失败不会留下前半份修改。
6. `write_file` 区分已有文件与新文件：已有文件走 `rewrite_existing`，新文件走
   `create_new`/`O_CREAT|O_EXCL`；H02 window、版本、scope 和 write-grant 均先检查。
7. `rewrite_existing` 在 `mutation_guard.rs:346` 获取每路径锁，读取当前 bytes 和强版本，
   执行 transform，再次校验描述符，随后 `seek(0)`、`set_len(0)`、`write_all`、`flush`。
8. 成功写后才运行可选 formatter、撤销旧 receipt/cache，并创建工具级 workspace git
   snapshot。Agent 的可选撤销快照则在整个 mutating batch 执行前创建。

### 3.1 当前 matcher

`replacer.rs:62-108` 固定六级顺序，**第一个产生候选的阶段立即决定结果**：

1. `exact`：逐字节 substring。
2. `line_trimmed`：逐行 `trim()` 后相等。
3. `whitespace_normalized`：每行所有空白 run 合并为一个空格。
4. `indentation_flexible`：去掉 needle 边界空行，双方按各自公共缩进比较。
5. `escape_normalized`：解释 `\n`、`\t`、`\r`、`\\`、引号转义后精确搜索。
6. `block_anchor`：首尾 trim 后精确锚定，中间行 Levenshtein 平均相似度至少 0.65。

该阶段 1 个候选即写入，多个候选返回 ambiguity；不会让更模糊的后级覆盖前级歧义。
fuzzy 命中还受行数和字节放大保护，但“唯一且比例合理”不等于语义正确。

### 3.2 当前 diff

`diff_edit.rs:320-405` 的行为已冻结：

- 目标行先转为 0-based，只搜索 `+-3` 行；
- 比较时仅忽略 trailing whitespace；
- 同一窗口有多个候选即歧义；
- hunk 按旧行号降序应用，避免前面修改移动后面行号；
- hunk 重叠、无 context、任一匹配失败时，transform 整体失败，磁盘不写。

### 3.3 no-op 与 formatter

当前 `rewrite_existing` 没有比较 `new_bytes == current_bytes`。相同内容仍 truncate/write，
并被上层当作成功修改：`success=true`、`file_modified=Some(path)`，版本 claim 和读取凭据
被消费，`file_mutation`/`tool_completed` 事件照常产生，formatter 和两类 snapshot
也可能运行。

M3 的目标语义冻结为：

- no-op 使用 `success=true`，避免 exclusive 批次把后续合法写入级联取消；
- `file_modified=None`，不运行 formatter，不创建写前或写后 snapshot，不消费当前版本；
- metadata 使用 `outcome="no_change"` 机器识别；真正失败统一使用现有
  `error_code`，不再新增同义 `code`。

写前 snapshot 目前只按工具名判断，发生在工具获知 no-op 之前。这是 M3 必须解决的真实
结构约束，不能只在 `rewrite_existing` 提前 return 就声称“无 snapshot”。

## 4. 结果投影

当前通道不是一份对象贯穿到底：

| 消费方 | 实际得到的内容 | 是否占模型 token |
| --- | --- | --- |
| `ProgressEvent::ToolCompleted` / AppUI `tool/completed` | success、200 字节 output preview、耗时 | 否 |
| `file_modified` 事件 | 路径和 modify 事实 | 否 |
| `ConversationResponse.tool_results` | `(tool_call_id, structured_metadata)` | 否 |
| SessionActor 完成事件 | 当前只专门提取 `node_costs` | 否 |
| ContextManager 持久记录 | `ToolOutputEnvelope` 的正文、hash、view、artifact ref；不含任意 structured metadata | 最终投影正文占 |
| 下一轮 provider | 清洗、预算处理后的 `MessageRole::Tool.content` | 是 |
| direct skill action RPC | output、file_modified、artifact、structured_metadata | 不进入 Agent 模型轮 |

因此 H05 不能只填 `structured_metadata` 就认为模型能看见失败原因；模型需要的一行原因、
版本和补救动作必须进入有界 `ToolResult.output`。UI/审计所需完整 diff 应走 metadata 或
现有 diff preview，不重复塞入模型正文。

现有 typed stale metadata 使用 `error_code`；仓库中的 `code` 属于 RPC、provider 或其他
协议。H05 rejection 统一沿用 `error_code`。

## 5. 入口范围

| 入口 | M1-M7 要求 |
| --- | --- |
| ARC `serve --stdio --solo` / 普通 coding 对话 | 必须完整支持；这是主要实验入口 |
| MCP `run_octos_session` | 必须支持同 invocation 的编辑语义；每次调用保持 owner 隔离 |
| 同步和后台 spawn worker | 必须支持；子 Agent 复用工具实现，版本 ledger 可共享，receipt/owner 独立 |
| pipeline worker | 公共工具和 `ToolContext` 行为保持一致 |
| gateway 批准后继续 | 必须支持，不能绕过 metadata、输出预算或 no-op 语义 |
| legacy `Tool::execute()` | 只要求兼容；它转入 `execute_with_context(ToolContext::zero())`，不承诺会话级状态 |
| Python/Rust 无工具 codegen | A/B/C 不改；M9 的 D 才单独实验 existing patch 协议 |

## 6. 基线反例

`h05_m0_baseline.rs` 提供 8 个绿色 characterization tests；
`local_edit_baseline.py` 使用真实 `octos serve --stdio --solo` 和 loopback fake provider，
共完成 7 次请求，不连接付费模型。

| 反例/合同 | A 的结果 |
| --- | --- |
| 无匹配后重读 | 第一次只返回提交的旧文本，没有当前候选；模型必须再调用 `read_file` |
| 精确歧义 | 返回 occurrence count，文件不变 |
| 错误 fuzzy 自动写 | `is_admin` 对 `is_guest` 的唯一 block-anchor 候选被自动覆盖 |
| 行号漂移 | 全文件唯一 context 偏移 4 行时，`diff_edit` 因超过 `+-3` 拒绝 |
| no-op | 同 bytes 仍 success、`file_modified`、消费版本并产生 mutation 事件 |
| formatter 扩大 diff | 单点替换后 rustfmt 同时格式化未直接编辑的相邻函数 |
| trailing whitespace | diff context 忽略行尾空白后可应用 |
| 多 hunk 原子匹配 | 降序应用；任一 hunk 失败时磁盘保持原样 |

六级 matcher 的独立单元测试共 27 项；三种写工具和 mutation guard 另有
98 项聚焦回归。所有基线测试固定当前事实，不要求主分支保持红色。

## 7. 工具面与二进制

真实 stdio 请求在 H03 开启时携带 13 个工具：

```text
ask_user_question, check, diff_edit, edit_file, glob, grep, list_dir,
read_file, recall, shell, tool_search, update_plan, write_file
```

默认 ARC proxy 裁剪后为 9 个：

```text
diff_edit, edit_file, glob, grep, list_dir, read_file, recall, shell, write_file
```

两者都不含 `apply_patch`。

| 项目 | 值 |
| --- | --- |
| provider 工具 schema | 9,286 字节；排序 compact JSON SHA-256 `79f97b61...2acdafa` |
| proxy 后 schema | 6,654 字节；排序 compact JSON SHA-256 `50918794...159dc1` |
| 二进制 | `octos-arc/target/debug/octos` |
| 二进制 SHA-256 | `2c6d3dd0af281bc240587ebada37a71bc4c0aa4162abb202095b1236f938e60c` |
| Rust/Cargo | 1.96.1 |
| Python | 3.9.6 |
| Node | v26.0.0 |
| 系统 | macOS 26.6.2 arm64 |

二进制由 `A_SHA` 加测试资产构建；测试文件和 Python 脚本不进入运行时二进制。
后续冻结 B/C/D 时必须重新构建并记录新 hash。

## 8. 固定官方实验

M8 使用四题，覆盖不触发局部编辑的小任务、逐步增长的中型和大型应用：

| task | requirements SHA-256 | tests tree SHA-256 |
| --- | --- | --- |
| `smoke--counter` | `a6e82f80...b412fa3e` | `ee116ba3...9d1d638` |
| `arc-bench-web--keep` | `0ee5e976...f90ea0e` | `68e3c93a...b59b646` |
| `arc-bench-web--stackoverflow` | `a12bfe39...2dde2ce` | `c67c8327...978f7a4` |
| `arc-bench-web--12306` | `961f0c49...86f4510d` | `ffbf345b...10fd275` |

哈希算法见 `manifest.json`；四题均不使用外部 template。固定参数：

- 模型 `deepseek-v4-flash`，endpoint `https://api.arc-bench.com/v1`；
- reasoning `auto`，session scope `turn`，默认 workspace-write 权限；
- implement/large/repair/codegen 请求上限 `20/0/10/3`，max iterations `500`；
- 普通/大树/codegen/final 修复轮数 `5/3/2/2`；
- 每个 task×variant 重复 3 次，顺序交错
  `A-B-C / B-C-A / C-A-B`；
- policy SHA-256 `0a070809...ee883`，prompt tree SHA-256 `f812cbb9...4b806`。

当前 `ARCBENCH_API_KEY` 缺失，`OCTOS_BIN` 未设置；M8 真实实验尚未获用户确认，
因此未运行，unknown 未记为 0。执行 M8 前必须先 `source ~/.zshrc`，再补
`ARCBENCH_API_KEY` 并把 `OCTOS_BIN` 指向对应冻结二进制。

## 9. 验证

完整机器可读结果见 [manifest.json](./m0-evidence/manifest.json)，真实请求与事件见
[m0-evidence](./m0-evidence/)。

| 验证 | 结果 |
| --- | --- |
| H05 M0 新测试 | 8 passed |
| matcher / edit / diff / write / mutation guard | 27 / 37 / 11 / 48 / 2 passed |
| H02/H03/compaction 依赖 | 37 passed |
| stdio profile | 1 passed |
| MCP integration | 18 passed |
| spawn | 94 passed、1 ignored |
| pipeline parity | 6 passed |
| 真实 stdio fake provider | 7 requests，全部断言通过 |
| `cargo check --workspace --tests` | 通过 |
| `cargo fmt --all -- --check`、`git diff --check` | 通过 |

严格 Clippy 只报未修改的 `crates/octos-cli/src/commands/serve.rs:878`
`clippy::nonminimal_bool`；加既有单项豁免后通过。

ARC Python 外层共运行 408 项：399 passed、8 skipped、1 error。唯一错误仍是系统
Python 3.9 不支持 `tarfile.extract(..., filter="data")`，位置为未修改的
`arc/main.py:562`。没有为通过测试修改生产代码、测试或 Python 环境。

M0 至此满足：A 可重放，调用链和状态所有者已明确，A/B/C/D 唯一变量已冻结，
至少六个基线反例有自动化证据。M1 才开始增加局部编辑选择规则。
