# H03 M1：来源、范围与预算内展示

- 日期：2026-09-21。
- 分支：两个仓库均为 `feat/output-recovery`，继续 M0 的冻结底座。
- `MAIN_SHA=27d057c206c0f8250b60309905737f7e26ee0ba9`。
- `A_SHA=9d65681c3ef0c2b699e2fc68bbaac1d8b0d71cf1`；M0 代码提交 `b69c0a1e323a87dd45075ffba428e4d433079bba`。
- 状态：M1 已完成；代码本地提交 `0f69ad4e83f84cebc1fee65d1ece2c7640b5709a`，未推送。

## 1. 本阶段完成的行为

文件读取和前台 `shell`、`bash`、`exec_command` 现在使用同一套预算内展示：
每份结果最多 **8,192 UTF-8 字节**，状态头、行号、通道标签、附加说明都包含在内。
文件展示连续范围；命令分别展示 stdout/stderr 的范围，不声称两个通道具有全局时间顺序。
命令的非零退出不会因截断而变成成功。

结果在执行时获得独立 ID，不依赖 provider 的 call ID 或正文哈希。
同一个 call ID 多次出现时，运行时以规范化 call ID、已知视图摘要及参数摘要关联来源。
正文中的 JSON 仅供模型理解，代码不从正文反解析 ID 来建立授权。
来源通过 `ToolResult.output_document → OutputState → ToolOutputEnvelope.output_view`
传递；原来的 `structured_metadata` 仍用于成本、UI 和执行控制。

M1 **没有实现原文恢复**。所有新视图均明确写出 `recoverable=false`、
`recovery_error=recovery_tool_unavailable`；持久字段中 `availability=missing`、
`stored_ranges=[]`、`stored_bytes=0`、`stored_sha256=null`。
内存中暂存来源供缩页使用，不等于已发布、可恢复的持久原文。
`next` 目前表示实际展示末端；M2/M3 才实现按来源 ID 恢复和版本校验的续读入口。

## 2. 配置和预算

`OutputPolicy::from_env()` 使用 `OnceLock` 在进程内解析一次：

| `OCTOS_OUTPUT_RECOVERY` | 结果 |
| --- | --- |
| 未设置、`0/false/off` | 关闭；保持共同底座路径 |
| `1/true/on`，忽略外侧空格及英文大小写 | 开启 |
| 其他值 | 关闭，并写诊断日志 |

Agent 持有已解析 policy，工具、最终发送和两个 CLI bridge 共用同一个 `OutputState`。
文件 schema 读取同一缓存 policy；打开 H03 即提供字节参数，不要求同时打开
`OCTOS_READ_WINDOW`。不改全局环境变量，不关闭 H02 写保护。

- 单结果：`min(工具限制, 8192, 当前分配额度)`；最多 2,000 个完整文件行。
- 整批：先扣非工具消息、工具定义和旧工具结果所占空间；按调用顺序均分余量，
  余数从前向后分配。某工具额度较小，不把余额重新分给后续工具。
- CLI 使用已有 prompt token 上限估算字节空间；最终 Agent 发送再按 provider
  context window 的既有安全比例核对。它是有界输出分配，不是精确 tokenizer。
- 缩页从源文本重新渲染，不切已有状态头；更新实际范围、`view_digest`、`source_proof`。
  已收紧的额度不能被后面的较宽限制放大。
- 少于 512 字节，或实际完整状态头与一个可见码点仍装不下，返回
  `insufficient_output_budget`。CLI 可先执行既有压缩；最后一道发送检查不能忽略失败。
- 来源暂存最多 256 条、64 MiB 文本，单条最多 16 MiB，单视图元数据上限 16 KiB。
  达到容量上限采用有界淘汰；失去运行时来源后明确降级，不重新执行工具。
  M0 中的磁盘总量、stream 采集内存、TTL、索引发布规则仍属 M2/M4。

## 3. 字段生产、消费和缺失行为

以下字段位于 `crates/octos-agent/src/output_recovery.rs`；上层 envelope 的
`output_view` 是可选字段。旧 envelope 缺字段时为 `None`，不凭旧 raw artifact 补全来源。

| 字段 | 生产者 | 消费者 | 缺失或不能证明时 |
| --- | --- | --- | --- |
| `schema_version` / `policy_version` | 共享渲染器，当前均为 1 | envelope 序列化、视图校验/证明 | 旧 envelope 没有 view；新字段不能代替运行时登记；冷恢复解析留 M2 |
| `output_id` | 普通执行、批准后执行，各次分配 UUID | 来源暂存、最终关联、持久 envelope | 无运行时匹配即 `source_incomplete`，不按同名/同内容猜测 |
| `owner` | H02 分支 owner；无宿主状态时由 Agent 创建独立 owner | 分支独立的 OutputState、持久 envelope | 新 Agent/child 默认独立；未实现从磁盘重建授权 |
| `call_id` / `arguments_digest` | 执行侧规范化 call ID、实际参数 | 最终按出现顺序配对工具调用/结果 | 参数或正文改变后不沿用来源；正文 ID 不能授权 |
| `source` | 文件稳定读取的目标和 SHA-256；命令执行 ID | 重渲染、来源证明、envelope | `unspecified`，明确不可恢复 |
| `capture` / `captured_ranges` / `source_totals` | 文件所选范围、现有命令捕获结果 | 范围核算、状态头、后续存储接口 | 未知总量保留 `null`；complete 仅指捕获的选定范围 |
| `loss_reason` | 缺元数据、超时、容量/渲染失败 | 状态头和持久记录 | 没有已知丢失原因为 `null`，不反推全文完整 |
| `availability` / `stored_ranges` / `stored_bytes` / `stored_sha256` | M1 明确填 missing / 空 / 0 / null | 持久 envelope、恢复状态消费者 | 不借现有 artifact 存在声称新原文已保存 |
| `visible_ranges` / `transformed` | 来源清洗、行/字节渲染 | 模型状态头、最终消息校验、持久 envelope | 无法映射则标 safe-text 坐标；不授予原文件覆盖 |
| `view_digest` / `source_proof` | 每次完整渲染后计算 SHA-256 | Message 来源关联、最终刷新、持久视图 | 无匹配即明确降级；这两个字段不是 H02 已读凭据 |
| `continuation` | 实际末端、捕获状态、已知总量 | 模型状态头、后续分页接口 | 区分 next / selection_end / eof / pending / unavailable |
| `execution` | `ExitStatus` 的 code/signal，或真实 timeout 分支 | 状态头、envelope | 未知保持 unknown；后台/特殊分支不猜测成功 |
| `success` | 原 ToolResult | 模型、宿主原控制流 | 渲染失败仍保留业务执行结果，不改成另一种执行结果 |
| `recoverable` | 当前固定 false | 模型和 envelope | M2 发布原文且读取入口合法可达后才可能变 true |

行是 1-based、两端包含；字节是 0-based、右端不包含。
完整文件行保留 CRLF、BOM、无末尾换行，格式化行号不计源范围。
第一页装不下超长行时使用 UTF-8 字节页；空文件不构造 `1–0` 范围。
附加说明使用独立 display 范围，不影响文件/命令源的 EOF 判定。
清洗在分页前进行；lossy 解码或清洗改变正文时，清除原始行映射并明确 safe-text 坐标。

## 4. 实际接线与边界

| 位置 | M1 行为 |
| --- | --- |
| `tools/read_file.rs` | 复用 no-follow 稳定读取与强版本；生成源范围；H03 off 保留旧路径 |
| `tools/shell.rs`、`tools/coding_tools.rs` | 从前台真实 `Output` 取得两个 stream 和退出状态；保留 hook、变更收据、沙箱提示 |
| `agent/execution.rs` | 普通与审批后执行共同登记结果；兼容工具仍走原裁剪逻辑 |
| `agent/llm_call.rs` | 真正 provider 请求前重新分配预算和核对来源，覆盖无 bridge / 失败 bridge |
| `api/context_manager.rs` | typed 页不盲切；envelope 带 view；刷新 active 与 canonical ledger 的最终视图 |
| `api/ui_protocol_transport.rs` | 每 turn Agent 继承当前 session 的输出状态；最终发送前同步 scratch/canonical 并持久化 |
| `session_actor.rs` | 使用同一状态和持久视图刷新接口 |
| `tools/mod.rs`、`octos-pipeline/src/tool.rs` | 新可选字段及默认值；公共构造兼容 |

H03 文件路径保留强版本记录和写保护，但 **M1 不生成新页的 H02 缓存命中凭据**。
精确的最终页凭据、丢页撤销、历史页与当前文件权限分离在 M3 完成。
本阶段也未改 `wait_with_output` 的完整缓冲方式；有界流式采集、超时已捕获内容保存、
tty/yield/后台历史输出、持久 recall、冷启动及搜索均未完成。

已持久的 view 是来源/展示记录，不证明模型调用成功，不重建正文读取权限。
MCP 目前只继承公共 Agent 的预算检查；不能据此宣称同 invocation 恢复已接通。
M5 仍需验证工具注册、allow/deny、代理裁剪、跨 turn 生命周期与条件性入口。

## 5. 验证记录

所有 Rust 套件先执行对应 `-- --list`，确认非零命中，再使用
`-- --test-threads=1` 运行。回归环境固定 `OCTOS_OUTPUT_RECOVERY=0`；
新增 M1 Rust 测试显式注入开/关 policy，真实 stdio 脚本显式开启。

| 验证 | 结果 |
| --- | --- |
| `h03_m1_output` | 13 passed；覆盖文件/日志共同预算、Unicode、空文件、缩页、来源隔离、真实 Agent 和批准后执行 |
| CLI 新增 `h03_m1_*` | 2 passed；也包含在下面 101 项 ContextManager 回归中，不重复计数 |
| `h03_m0_dispatch` | 2 passed；开关关闭时的原 metadata/bridge 合同 |
| file_state_cache / model_read_receipts / task_file_state | 15 / 21 / 3 passed |
| read_file / read_window / mutation_guard / nofollow | 55 / 16 / 2 / 19 passed |
| spawn | 94 passed、1 ignored |
| compaction / loop_compaction / llm_call | 2 / 6 / 11 passed |
| shell，串行 | 55 passed、1 ignored |
| coding_tools，串行 | 84 passed、1 failed；下述未修改基线可复现 |
| H02 M1–M3 与三个 M8 集成套件 | 合计 27 passed |
| ContextManager / AppUI bridge / H02 OUP 接线 / SessionActor bridge | 101 / 1 / 2 / 3 passed |
| MCP integration / pipeline m8_parity | 14 / 6 passed |
| `cargo fmt --all -- --check` | 退出码 0 |
| `cargo check --workspace --tests` | 退出码 0 |

不重复累计复跑，Rust 聚焦回归合计 **552 passed、1 failed、2 ignored**。
这不是整个 workspace 的全量测试。准确命令、测试列表、数量和退出码见
[checks.json](./m1-evidence/checks.json)；最终代码的复核见
[final-checks.json](./m1-evidence/final-checks.json)。

`coding_tools::tests::exec_session_captures_all_output_when_process_exits_at_deadline`
的 40 次尝试都没有在 5ms yield 窗口内观察到 completed，报
`no trial reached the completed path — test is vacuous`。
当前分支关闭 H03 后单独复跑仍失败；再在独立、干净的
`b69c0a1e` worktree 上执行同一个测试，得到同样的断言失败与退出码 101。
测试源码及 `spawn_session` 分支均未修改；本次没有放大 yield、删断言或关闭沙箱。
基线 worktree 验证后移除，原工作树不变。此项是有证据的基线限制，不计为通过。

最终严格 Clippy：
`cargo clippy -p octos-agent -p octos-cli --all-targets -- -D warnings`
退出码 101，唯一剩余诊断为未修改的 `serve.rs:878`
`clippy::nonminimal_bool`。仅追加 `-A clippy::nonminimal-bool` 后退出码 0。
首轮发现并修复了两个新增问题：测试使用高于 MSRV 的字符边界 API；
新增 view 内联导致 enum 过大。分别改为兼容的 UTF-8 边界循环和
`Option<Box<OutputView>>`，保留相同持久 JSON 格式；原始失败日志也已保存。

真实 stdio 使用最终构建的独立副本 `target/h03-m1-final-octos`，
SHA-256 为 `8e9ff7d821da119da184374fef45f25dda59fd963eba8e8c86d1696a2476331f`。
后续构建可能覆盖 `target/debug/octos`，证据绑定的是此哈希。

| stdio 场景 | 最终 provider 与磁盘结果 |
| --- | --- |
| H03 on，`read_window=0` | 共 5 个本机假模型请求，四次工具均使用 `call_reused`，生成 4 个独立 output ID |
| 文件请求 30–3029 行 | 实际正文 30–223 行、源字节 `[948,7474)`，整份结果 8,178 字节；next 为实际末端 7474 |
| 大 stdout + 短 stderr，真实 exit=7 | shell 为 3,258 字节，bash/exec_command 各 3,273 字节；保留唯一 stderr 失败标记、各通道范围与失败状态 |
| 执行次数 | 计数文件严格为 shell/bash/exec_command 各一次 |
| 持久 envelope | 4 个最终 view 的范围及 digest 与最终 provider 正文一致，均为 missing / recoverable=false |
| H03 off | M0 原脚本的 3 个场景、7 个请求全部通过；仍精确复现旧 8,204 字节结果、旧窗口/footer 丢失和旧 shell 保存缺口 |

on/off 脚本退出码均为 0，全程 `OCTOS_DANGER_FULL_ACCESS=0`。
本次 stdio 未触发审批（事件数 0）；批准后执行由 Rust 专项测试覆盖，
不把它当成 stdio 交互审批验证。测试专用 `ProtocolSession` 继承 M0 的
`session_id` 修正，生产 `octos_stdio.py` 的已知缺口未在 M1 顺手修改。

重放命令（代码仓库根目录；证据目录须为新的目录）：

```bash
source ~/.zshrc
export PATH="$HOME/.rustup/toolchains/1.96.1-aarch64-apple-darwin/bin:$PATH"
cargo build --locked -p octos-cli --bin octos
python3 arc/integration/output_recovery_contract.py target/debug/octos ../octos-arc-analysis/test-temp/h03/m1-replay-on
python3 arc/integration/output_recovery_baseline.py target/debug/octos ../octos-arc-analysis/test-temp/h03/m1-replay-off
```

完整请求、事件、提取的持久 view、日志和哈希见 [m1-evidence](./m1-evidence/)。
只归档本地合成夹具；日志清理行尾空白，JSON 保留原字符串。
没有改 ARC 运行逻辑，本轮只对新增 Python 脚本做编译及真实协议验证；
M0 已记录的 Python 3.9 `tarfile.extract(filter=...)` 失败未重复运行或修复。
没有运行真实模型或官方任务对照，不对正确率或 token 收益作结论。

## 6. 提交与后续

代码提交 `0f69ad4e`，共 19 个文件；`git diff --check`、暂存路径核对均通过，
提交后代码工作树干净。提交钩子报告硬编码扫描超过 2 秒，但提交实际成功、退出码 0；
没有禁用钩子或重复提交。
分析文档、清单和证据在分析仓库单独本地提交。两个仓库均不推送。
M2 从本次来源/视图合同继续，首先实现有界持久原文、版本化索引和按范围读取；
不能把 M1 的内存来源重渲染或 envelope 序列化算成原文恢复。
