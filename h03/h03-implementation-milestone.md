# H03 实施 Milestone：可靠分页与工具原文恢复

- 状态：M0–M7 已完成；M8–M9 待实施
- 面向对象：后续 coding agent
- 设计依据：[H03 竞品调研](./h03-output-pagination-recovery-competitor-research.md)
- 关联约束：[H02 实施清单](../h02/h02-implementation-milestone.md)、[H02 M7 验证](../h02/h02-m7-implementation-verification.md)、[优化总表](../harness-optimization-table.md)
- 编写日期：2026-09-20
- 本次复核主线：`octos-arc origin/main@27d057c206c0f8250b60309905737f7e26ee0ba9`
- H02 参考：B `73f5b1bf695af37167fcb47541726bcb24807102`；C `7eaa136ef086a2f9728794d17d8f150482df03d1`
- M0 证据：[共同底座、输出边界与离线反例](./h03-m0-state-boundary.md)；共同底座 `A_SHA=9d65681c3ef0c2b699e2fc68bbaac1d8b0d71cf1`，分支 `feat/output-recovery`。
- M1 证据：[来源、范围与预算内展示](./h03-m1-implementation-verification.md)；代码提交 `0f69ad4e`，仅本地提交，原文恢复仍待 M2。
- M2 证据：[有界原文存储与按范围恢复](./h03-m2-implementation-verification.md)；代码提交 `d6f8198e`，仅本地提交，stdio 全入口接线仍待 M5。
- M3 证据：[文件分页与最终读取凭据](./h03-m3-implementation-verification.md)；代码提交 `2ced3def`，仅本地提交，命令流式采集仍待 M4。
- M4 证据：[命令输出在首次截断前保存](./h03-m4-implementation-verification.md)；代码提交 `d7931fbc`，仅本地提交，stdio 的 `recall` 注册和冷启动恢复仍待 M5。
- M5 证据：[真实入口、压缩和冷启动恢复](./h03-m5-implementation-verification.md)；代码提交 `d85bd227`，仅本地提交，恢复链观测仍待 M6。
- M6 证据：[恢复链观测和确定性回归](./h03-m6-recovery-verification.md)；代码提交 `fbcfd6b8`，仅本地提交，完整 B 仍待 M7 输出内搜索。
- M7 证据：[有界输出搜索与完整 B 冻结](./h03-m7-b-variant-freeze.md)；`B_SHA=4c542e53`，仅本地提交，官方任务 A/B 留待 M8。

本文同时记录开发计划与已完成验证；`[x]` 表示已有代码和证据，`[ ]` 表示后续待办。
类型名可按仓库惯例调整，范围、完整性、隔离和验收语义不得弱化。源码位置以 M0 的
当前代码为准，不照抄旧行号。

## 0. 后续 Agent 先读这一节

目标是让模型收到**完整的一页和可执行的恢复说明**，必要时取回同一版本文件或同一次命令的缺失内容。通过率与稳定性优先，其次是全任务 token；耗时只作诊断，不计入成绩。

最终必须证明：

```text
本次声明的可见范围 = 最终模型请求中实际存在的正文范围
静态来源的非终止正文页严格前进，且不跳过缺失内容
可恢复引用指向同一来源，恢复不重新执行原命令
历史结果恢复不自动授权当前文件的缓存命中或写入
```

执行原则：

1. 只做 A/B 两组：A 为共同底座，B 完成 H03a–e 与 H03f 中的输出内有界搜索，作为一套完整方案评估。
2. B 的主交付入口是 `octos serve --stdio --solo` 工具模式；公共代码和已受影响入口必须回归。MCP 支持范围在 M0 明确，不能默认它共用 stdio ContextManager。
3. 复用 `read_window`、`ToolOutputEnvelope`、artifact、`recall`、H02 版本与凭据。先证明现有对象怎样传递，再补最小字段和接口。
4. 文件返回连续页；日志首版可以返回标明缺口的首尾片段。智能挑选失败片段、自动调页大小、新摘要模型调用均不进入 B。
5. 输出内搜索是 B 的必做项，在恢复链完成后实现；不设独立 C 分支或 C 开关。更大页、压缩阈值和推理预算不在本轮一起调整。
6. 每个 Milestone 完成后本地提交。保持当前用户改动，不推送、不创建远程 PR；是否运行真实模型实验服从届时用户给出的执行范围。

| Milestone | 主要产出 | 前置条件 |
| --- | --- | --- |
| M0 | 共同底座、真实调用图、预算和反例 | 开工核验 |
| M1 | 来源/范围类型与预算内渲染约定 | M0 |
| M2 | 有界存储、范围恢复和持久索引 | M1 |
| M3 | 文件页完整到达模型、H02 凭据联动 | M1–M2 |
| M4 | 首次截断前保存 shell 输出 | M2–M3 |
| M5 | stdio、压缩、冷恢复与条件性入口接线 | M2–M4 |
| M6 | 24 项恢复场景回归与阶段提交 | M0–M5 |
| M7 | 输出内搜索、联合回归与完整 B 冻结 | M6 |
| M8 | 全量官方任务 A/B 对照 | 完整 B 通过 |
| M9 | 采用结论、最新主线集成与回滚 | M8 |

## 1. 分支、依赖和实验底座

### 1.1 基线处理

本指南与调研属于同一 H03 文档任务。后续修改 **`octos-arc` 代码**时，重新拉取其最新 `origin/main` 并创建新分支，不能直接在当前 H02 C 分支继续写。

- [x] 检查两个仓库的工作树、当前分支和未提交内容；不覆盖、不自动清理用户改动。
- [x] `git fetch origin main` 后记录 `MAIN_SHA`，从该 SHA 创建代码分支 `feat/output-recovery`。
- [x] 核实 H02 未合入最新主线，将 H02 B 的必要文件版本、凭据、写保护与接线改动移植到最新主线，验证后冻结共同底座 `A_SHA`。
- [x] H02 依赖移植使用可审查的小提交，不合入 H02 分支上与此无关的打包、实验产物或历史主线差异；原/新 SHA 已记录。
- [x] 核实当前主线不含 H02 C，本次不移植 C，显式记录 retained-receipts 关闭配置。
- [x] 固定 H01 实现/开关与 H02 dedup、retained-receipts、写保护配置；不得把依赖修复的收益算到 H03。
- [x] `A_SHA` 已完成底座回归，基线问题单列；尚未开始 H03 行为变更。中途主线更新不漂移实验基线；最终集成在 M9 重新同步。

| 变体 | 起点 | 改动 | 冻结时机 |
| --- | --- | --- | --- |
| A | 最新主线加已验证的共同依赖 `A_SHA` | 当前输出行为 | M0 |
| B | 从 `A_SHA` 开始，代码分支建议 `feat/output-recovery` | H03a–e + 输出内有界搜索，固定页预算 | M7 记录 `B_SHA` |

`A_SHA` 可能不同于本文写作时的 `27d057c2`，也不同于 H02 原实验的 A。必须在证据中说明，不能拿不同底座直接比较。

这两组回答“完整优化方案是否值得采用”。恢复和搜索仍分阶段开发、分别做确定性测试，但不单独安排第三组官方任务实验，因此不能将 B 的整体收益归因于搜索一项。上文的 H02 B/C 是既有依赖版本，不是本次 H03 的实验分组。

### 1.2 功能开关与兼容

- [x] B 开发期使用一个总开关 `OCTOS_OUTPUT_RECOVERY`，默认关闭；进程内解析一次，共享 policy 注入工具与 prompt 构建。
- [x] 启用值为 `1/true/on`；未知值关闭并写诊断。M1 stdio manifest 记录有效配置，正式实验 manifest 留 M8。
- [x] 开关开启时，`read_file` 使用 H03 的有效页预算，不要求同时开启 `OCTOS_READ_WINDOW`。
- [x] `OCTOS_READ_WINDOW` 现有整文件覆盖保护和 H02 mutation guard 独立保持；未修改全局环境变量或关闭写保护。
- [x] H03 关闭应恢复共同底座的输出行为。H03 已产生的持久引用仍应有兼容读取或明确的不支持状态，不能用旧逻辑错误解释。
- [x] 输出内搜索与恢复共用 H03 总开关；开启后提供搜索能力，由模型按需调用，不要求每次恢复前都搜索。

## 2. 范围与不可破坏的约束

### 2.1 各层负责什么

| 层 | 负责的事实 | 禁止替代的事实 |
| --- | --- | --- |
| 文件 provider / H02 | 同一次稳定读取的版本、字节和路径身份 | “文件没变”不证明正文仍在模型上下文 |
| 进程采集 | 已捕获 stdout/stderr、真实退出/超时/取消状态 | “保存了日志”不证明测试通过 |
| 输出存储 | 来源、已保存范围、校验值、容量与可用性 | artifact 存在不代表源输出完整 |
| 页渲染 | 正文、装饰、实际范围、缺口、恢复参数 | 请求的范围不等于实际可见范围 |
| 最终 prompt 构建 | 当前模型分支实际收到的结果及预算 | UI 预览、历史账本不能替代最终请求 |
| H02 dispatch | 根据最终来源确认或撤销读取凭据 | `recall` 历史正文不能自动变成当前文件凭据 |
| 官方 runner | 应用测试结果和成绩 | 模型自述、工具 success、退出码 0 均不能替代官方验收 |

### 2.2 必须保持的不变量

- [x] 正文、行号、状态、截断标记、路径/ID、恢复提示全部计入可见预算；不采用“正文正好装满，再往后追加 footer”。
- [x] 后续层要减量时，从来源及范围重新生成视图，或保留完整恢复状态；不能再盲切一段已格式化结果。
- [x] 整批工具输出共享当前 prompt 的可用空间；多个并行调用不能各自占满同一份剩余预算。
- [x] 小于一个最小完整状态头的预算不得产生残缺 JSON、无效调用参数或无进展页；优先走已有压缩，仍不足则明确返回预算错误。
- [x] 文件分页必须单调前进；不能把超长行截短后跳到下一行，也不能从 `requested_offset + requested_limit` 推断缺失部分已读。
- [x] 运行中输出没有新内容时返回明确的 pending/no-new-output，保持读取位置，不伪造正文进展或 EOF；不自动连续轮询，后续检查沿用已有任务等待策略。
- [x] 文件版本变化后旧游标失败为 `stale`，不混合不同版本；恢复旧快照时明确标注历史版本。
- [x] stdout/stderr 的通道和范围分开保留；若只知道各通道顺序，不虚构二者的全局时间顺序。
- [x] 成功、非零退出、超时、取消和采集失败分别保留真实状态；退出状态未知时保持未知，不能写成成功。
- [x] 保存完成且可由合法读取入口访问后，才声明 `recoverable=true`；保存失败或达到容量上限必须如实降级。
- [x] 恢复不再次生成另一份同样内容的 artifact，不再次触发原命令，也不引入无界重试。
- [x] 历史压缩可以删除正文，但仍被保留的恢复提示必须完整有效；不能单独删除 tool call 或伪造其结果。
- [x] owner、授权和内容完整性从运行时元数据判断，不解析模型或工具打印的伪造 “output_id/complete” 文本来授予能力。
- [x] 清洗/脱敏在恢复路径继续生效。分块和翻页不能使原本会被识别的内容绕过规则；无法准确映射的变换不得计入原文件全文覆盖。
- [x] 缺失、损坏、过期、未知旧格式或越权引用都明确报错；不自动选择“最新同名输出”替代。
- [x] 文件、内存、句柄、存储容量和索引均有上限；读取一页不把完整大日志重新加载到内存，也不在 ContextManager 全局锁内读大文件。

### 2.3 本轮不扩展的任务

- 不修改官方需求、测试、模板、判分器或测试预算。
- 不修改 Tiny/codegen 的文件输出协议、档位选择或外层修复次数。
- 不实施 H04 的 MCP 通用压缩策略、H05 的工具选择策略、H07 的通用循环检测或 H08 的任务预算调整。
- 不新增远端对象存储、语义向量检索、自动摘要模型、通用插件框架或跨题记忆。
- 不把现有后台 shell 的输出丢弃行为直接改造成新任务系统。M0 列明捕获能力；未捕获的历史内容必须标记不可恢复。

## 3. 最小数据与接口约定

这是字段语义约束，不要求逐字实现新的大结构。优先扩展已有对象，并在真正共享的位置定义小类型。

| 信息 | 必需语义 |
| --- | --- |
| `output_id` | 一次结果的不可变身份，区别于可能重复的 provider call ID；多个恢复页引用同一个 ID |
| `owner` | workspace/task/logical session/model branch 或现有等价所有权；运行期对象身份不能代替持久身份 |
| `source` | 文件目标及强版本，或命令运行 ID 与 stream；保存的是源全文、选定范围还是变换后的文本 |
| `capture_state` | `running / complete / partial`，完成状态与丢失原因分开 |
| `availability` | `available / missing / expired / store_failed / corrupt`；完整捕获和当前可读不能混成一个布尔值 |
| `stored_ranges` | 已保存范围、已知遗漏量或 unknown、保存字节及校验值；禁止把未知总量记成 0 |
| `visible_view` | 实际连续行/字节范围或片段列表、变换标志、view digest、展示策略版本 |
| `continuation` | 来源 ID/版本、单位、下一位置；显式区分选定范围结束、EOF、仍运行和不可恢复 |
| `execution_status` | 可信 exit code、signal、timeout/cancel 状态，不从尾部文本反向猜测 |

范围约定：

- 行：1-based，首末行均包含；空结果单独表示，不构造 `1–0` 假范围。
- 字节：0-based、右端不包含 `[start, end)`，位置明确属于源字节还是变换后的文本。
- UTF-8 字符不能被页边界拆开；不因只有 1 字节正文预算就无限返回同一页。
- 同时传入行参数与字节参数、负数、溢出、相互冲突的 cursor/offset，必须验证并拒绝歧义。
- 无换行、CRLF、BOM、空文件与 EOF 行为在 M1 固定；格式化行号不参与源字节哈希或覆盖。
- `complete` 必须带来源范围：完整保存 1–100 行，不表示保存了整个文件。

候选错误码可复用项目已有枚举；新增时至少能区别：

```text
invalid_cursor | stale_source | ambiguous_call_id | out_of_range |
output_missing | output_expired | output_corrupt | owner_mismatch |
storage_limit | storage_failed | source_incomplete |
insufficient_output_budget | recovery_tool_unavailable
```

接口纪律：

- [x] `structured_metadata` 保留原成本/UI 路径；M1 验证 `output_document → OutputState → output_view` 的 typed 通道到最终请求和持久 envelope。
- [x] `ToolResult/ToolContext` 增加可选来源/状态字段，使用有界任务状态；不解析正文 JSON 建立来源和授权。
- [x] `octos-agent` 不依赖 `octos-cli`；上层注入共享状态，MCP 不引入 AppUI。持久原文服务留 M2。
- [x] 新版恢复读取返回“范围 + 内容 + 状态”，不要继续要求 `fetch()` 先返回整份大字符串再分页。
- [x] 新版主要使用来源 ID 和绝对位置。旧 `recall(tool_call_id, page)` 只在唯一解析、分页策略固定时兼容；有歧义或旧策略不可判定就报错。
- [x] 持久化新增字段有明确版本和旧格式读取规则；旧 artifact 的 complete/recoverable 不能因缺字段被默认设成 true。

## 4. Milestone M0：固定底座、入口和验证条件

**目标：**把谁保存原文、谁截断、谁最终发给模型查清楚，并冻结 A。M0 不开启 H03 行为。

- [x] 完成第 1.1 节的最新主线、H02 依赖和 `A_SHA` 冻结；1.2 的 H03 功能实现仍待后续阶段。
- [x] 追踪 ARC 的 `main.py → octos_stdio.py → serve --stdio --solo → session/open/turn/start → request_agent → provider`；记录实际工具名单与 `OCTOS_SESSION_SCOPE`。
- [x] 分开记录未开启/开启 `OCTOS_READ_WINDOW` 的读取路径，以及文件内限制、execution、sanitize/hook、8 KiB、context pressure 的顺序。
- [x] 追踪 `ToolResult` 到 Message、事件、持久 ledger 和 prompt 的元数据流；确认普通执行、审批后继续、并行结果、重试、回放是否经过同一处理点。
- [x] 查清 `recall` 的注册、白名单、权限、原始数据来源、冷启动索引和重复 call ID 行为。
- [x] 查清 shell 的 stdout/stderr 捕获、超时、取消、子进程退出及后台模式；列明哪些原文早于 ContextManager 已经丢失。
- [x] 确认 `PromptContextManager::prepare_prompt` 失败时继续使用当前可变向量、不会自动回滚；通过最终请求测试验证。
- [x] 选择能力范围：stdio 完整支持；MCP 因共享执行改动纳入同 invocation 内恢复，不宣称跨 invocation 冷恢复。
- [x] 固定首版预算：stdio 总结果 8,192 字节，包含全部展示文字；最多 2,000 行；各层共享解析后的 policy。
- [x] 固定有限的每输出存储、每 session 总量、索引条目、运行中输出保留和清理参数；数值和依据已写入 M0 证据第 6 节。
- [x] 准备不调用付费模型的 fake provider，捕获最终 messages/tools；用确定性夹具展示二次截断、续读跳空、晚保存、不可达 recall 和冷恢复缺口。
- [x] 记录 Rust/Python/Node、准确测试命令与基线失败；新增测试绿色复现基线缺口，没有提交破坏现有 CI 的红色测试。

M0 实测修正：最终 stdio schema 有 15 工具，默认代理纯函数裁剪后为 9 工具，并非始终等于 12 工具常量；`bash/exec_command` 有独立采集路径。M1/M4/M5 必须覆盖实际前台命令入口。gateway 批准后执行与普通路径分开；数据通道选择和基线测试详见 M0 证据。

优先阅读位置（相对 `octos-arc/`）：

| 职责 | 文件/对象 |
| --- | --- |
| 读取、窗口、版本 | `crates/octos-agent/src/tools/read_file.rs`、`tools/read_window.rs`、`file_state_cache.rs` |
| 工具结果/上下文 | `crates/octos-agent/src/tools/mod.rs::ToolResult/ToolContext` |
| 输出执行与清洗 | `crates/octos-agent/src/agent/execution.rs`、`sanitize.rs`、`crates/octos-core/src/utils.rs` |
| shell 与恢复工具 | `crates/octos-agent/src/tools/shell.rs`、`tools/coding_tools.rs`（bash/exec_command）、`tools/recall.rs` |
| H02 最终确认 | `crates/octos-agent/src/model_read_receipts.rs`、`agent/llm_call.rs::call_llm_with_hooks_mode` |
| 跨层 prompt 接口 | `crates/octos-agent/src/prompt_context.rs::PromptContextManager` |
| ledger 与最终视图 | `crates/octos-cli/src/api/context_manager.rs` |
| stdio bridge / 每轮 Agent | `crates/octos-cli/src/api/ui_protocol_transport.rs::AppUiPromptContextBridge` |
| 创建状态与白名单 | `crates/octos-cli/src/runtime/session.rs`、`runtime/profile.rs` |
| 另一会话入口 | `crates/octos-cli/src/session_actor.rs` |
| MCP / 子 Agent | `crates/octos-cli/src/commands/mcp_serve.rs`、`crates/octos-agent/src/tools/spawn.rs` |
| 外层限制与用量 | `arc/octos_stdio.py`、`arc/llm_proxy.py`、`arc/metrics.py`，先只读 |

**完成条件：**已冻结实际调用图、数据通道方案、有限预算与能力范围，并有可重放的基线反例。证据见 [h03-m0-state-boundary.md](./h03-m0-state-boundary.md)；新增功能留在 M1–M9。

## 5. Milestone M1：来源、视图和预算共同约定

**依赖：**M0。**目标：**建立足以支持文件与 shell 两个真实调用者的小型共享约定。

- [x] 实现第 3 节必要字段，贯穿结果传递、来源关联和持久 envelope；生产者、消费者和缺失时行为见 M1 证据表。
- [x] 执行侧分配独立结果 ID，关联 call occurrence；重复 call ID、相同正文仍有独立来源与权限。
- [x] 统一预算内渲染入口，完整状态头和附加文字均占预算；长路径只保存在 typed 来源中。
- [x] 文件连续页与 stdout/stderr 片段共用预算，保留各自源范围。
- [x] 单结果限制与最终额度分开，按固定调用顺序均分并取较小值。
- [x] 缩页从来源重渲染；最终 active/canonical envelope 的 digest、范围和来源证明同步更新。
- [x] 保留工具 success、真实 code/signal/timeout；渲染失败不改写业务执行结果。
- [x] 旧工具保留兼容路径；支持工具缺关键来源时显式降级，所有 M1 新输出明确不可恢复。
- [x] 聚焦覆盖小预算、长路径、Unicode、多工具、metadata 超预算及开关关闭；新增 15 项测试及真实 stdio on/off 验证通过。

**完成条件：**同一组预算测试同时约束文件页和日志视图；结果完整可解析，总字节预算计算包括所有附加文字。typed 数据能到达实际消费方，不能只有未被调用的结构定义。

M1 已完成，见 [验证记录](./h03-m1-implementation-verification.md)。聚焦回归合计
552 passed、1 个在干净 M0 复现的基线失败、2 ignored；Clippy 仅豁免已验证的
既有告警后通过。M1 提交本身不实现持久 payload/recall，也不激活 H03 新页的 H02 读取凭据；
M3–M9 及第 2 节面向完整恢复链的不变量仍按后续阶段验收，不提前勾选。

## 6. Milestone M2：可恢复存储与按范围 `recall`

**依赖：**M1。**目标：**先让“已保存的原文”真正可以找回，供后续文件和 shell 使用。

- [x] 演进现有 artifact/ledger，提供有界写入、范围读取和状态查询；优先保留现有目录与内容寻址机制，不新建平行的 ContextManager。
- [x] 写入使用临时文件与现有原子发布机制；发布 manifest/index 之前完成对应数据持久化。崩溃留下半文件时不能返回 complete。
- [x] 运行中输出只能读取已发布字节上界；最终结束后冻结来源与校验值，处理未完成源和最终输出的状态转换。
- [x] 超容量后保存规则固定并报告 partial/缺口；不要仅停止读 pipe 导致子进程阻塞，也不要为了落盘失败重新执行原命令。
- [x] 限制索引、内存与磁盘容量，清理不删正在写入或仍被合法引用的活跃对象；被淘汰的引用返回 expired/missing。
- [x] 范围读取只加载请求范围，核对身份、完整性及必要校验；避免持有会话全局锁做磁盘 I/O。
- [x] `recall` 支持不可变结果 ID + 绝对位置/游标，返回预算内的一页和精确 next；固定来源、发布上界和预算下重复读取结果一致，EOF 与越界明确区分。
- [x] 运行中来源的游标绑定已发布上界；新一轮查询才观察后续增长。没有新字节时返回 pending，不能把同一位置包装成可立即继续的新页。
- [x] 旧 call ID 唯一时允许兼容；重复时拒绝歧义。旧 page 依固定旧分段解释，不能按每次变化的预算重新计算页号。
- [x] 为遗留大 page 的内部缺口返回新式续读游标；不保留“超大 page 下标自动返回最后一页”的静默钳位。
- [x] 恢复结果仍指向原 artifact，不重复落盘正文，不形成 recall→spill→recall 链。
- [x] 冷启动从持久索引重建可读关系；旧快照不能确认来源时明确降级，不使用空 map 却宣称恢复成功。
- [x] 验证 owner、权限、工作区身份和 no-follow 路径规则。新的 task/child 默认无权读别人的输出；同逻辑会话恢复通过持久身份校验后才重建权限。
- [x] 采用统一、可分页的模型安全文本视图。跨采集块/页边界的清洗要与完整视图策略一致；原始审计字节不直接通过 `recall` 暴露。
- [x] 测试：保存成功/失败、部分写入、容量耗尽、校验损坏、旧 schema、重启、重复 ID、越权、游标溢出、连续恢复不重复保存。

**完成条件：**给定一个大于上下文预算的固定文本，在内存和冷启动两条路径都能按合法游标找齐已声明保存的范围；无法恢复时返回真实原因。原始命令无需参与此测试。

M2 已完成，见 [验证记录](./h03-m2-implementation-verification.md)。16 项存储/恢复测试和
1 项真实 Agent 调用链测试通过；相关回归共 173 passed、0 failed、0 ignored。
本阶段只发布统一清洗后的安全文本，运行中内容在最终冻结前返回 pending；stdio 工具策略、
文件凭据和命令流式采集仍按 M3–M5 的边界实施。

## 7. Milestone M3：文件页完整到达模型，并与 H02 对齐

**依赖：**M1–M2。**目标：**关闭文件工具到最终模型请求之间的二次截断缺口。

- [x] 复用现有稳定读取与窗口算法，将 H03 有效页预算作为显式参数；保留已有 `path/offset/limit/start_line/end_line` 的合法调用方式。
- [x] 无范围大文件先返回有用的第一页。显式范围超过当前页预算时给出实际子范围与续读位置，不要求模型猜一个新的 limit。
- [x] 为文件来源保留强版本和请求范围；下次读当前文件时验证版本，变化返回 stale。历史快照通过历史入口读取并标清来源。
- [x] 长行使用已有 byte mode，并从真实字节位置继续；UTF-8 边界修正必须体现在实际范围中，不能跳字节。
- [x] 改掉通用恢复建议依赖 `start + limit` 的路径；以本次最终已见末端为 next，显式范围结束与 EOF 分开。
- [x] execution、sanitize/hook、ContextManager 和 pressure 投影都识别 typed 页。更小预算时重新渲染；不再次无差别裁剪正文+footer。
- [x] hook 新增文本也占预算；若改变源码正文且无法映射，取消相关 H02 候选，保留真实变换状态。
- [x] page、output ID、digest、候选范围及最终消息 provenance 同步更新。首版无法证明重渲染后的范围时保守失效，不伪造完整 source proof。
- [x] H02 只在真实主模型请求成功后确认最终页；取消、provider 失败、内部摘要请求和直接调用工具不激活凭据。
- [x] 完整可见的部分页最多支持相同/子范围的缓存命中；历史 `recall`、summary、路径提及及 stub 不登记为当前文件读取。
- [x] 页后来从 prompt 删除或被压缩时沿用 H02 的失效逻辑；不要将过去累计读过的页当作当前仍可见。
- [x] 给 bridge 失败/fallback、legacy 无 bridge 和 provider 路由变化做明确降级：不发送旧范围声明配新残缺正文。
- [x] 在最终 fake provider 请求中核对可见正文、范围、next 和预算。按照游标重组文件范围后与固定版本原文比对。
- [x] 回归 `OCTOS_READ_WINDOW` 开/关与 H02 dedup 开/关组合，证明整文件写保护、强版本、symlink 防护和保守 miss 保持。

**完成条件：**大文件中间、末尾和超长行都可达；最终 provider messages 中不存在“声明整页但只剩开头”的结果；H02 不产生错误 stub 或放宽写入授权。

M3 已完成，见 [验证记录](./h03-m3-implementation-verification.md)。6 项最终 provider
分页测试和 57 项 `read_file` 测试通过；聚焦回归共 357 passed、0 failed、0 ignored。
真实 stdio 的文件页已包含实际范围、强版本和精确 next，持久 `recall` 的 stdio 工具注册
仍按 M5 实施。

## 8. Milestone M4：shell 在首次截断前保留输出

**依赖：**M2；最终展示复用 M3 接通的路径。**目标：**命令输出的保存早于工具内和 execution 层的有损处理。

- [x] 在当前前台 shell 的捕获层接入有界流式落盘，避免 `wait_with_output()` 完整缓冲后才处理大日志。复用现有进程与取消管理，不重写执行框架。
- [x] 覆盖 M0 实测同样对模型可见的前台 `bash` 与 `exec_command` 采集路径；tty/yield 和后台分支仅声明实际保存范围，不承诺未捕获的历史全文。
- [x] 并发排空 stdout/stderr，分别保存 stream 范围；内存仅保留有界展示片段和必要状态。
- [x] 稳定 UTF-8 解码处理跨块字符；无效编码标记变换，不能把 lossy 解码字节当作原始字节范围。
- [x] 显式记录完整捕获、部分捕获、仍运行、终止原因与未知状态；stdout/stderr 各自达到上限时能解释缺口。
- [x] 非零退出也保存输出，不能仅在 success=true 时提供恢复路径。状态来源为进程结果，不靠清洗后的尾部文本。
- [x] 超时/取消保存已捕获输出并标注是否终止；保持现有进程处置、usage claim 释放和审批语义，不擅自改为后台任务。
- [x] 存储满或写入失败后继续安全排空或按既有约定终止采集，保持有界内存和可解释状态；不让管道写满造成新死锁。
- [x] 首版仅给确定性的首尾预览、stream 标签、真实执行状态和恢复引用。没有可靠结构化信息时不猜测失败测试字段。
- [x] 首尾片段的缺口明确显示；退出状态与恢复引用位于保留区域，整体仍受统一预算约束。
- [x] 现有后台或特殊执行分支未捕获的输出明确不可恢复；不要错误复用前台路径或承诺历史全文。
- [x] 测试故意制造大量 stdout、短 stderr 中的唯一失败、非零退出、超时、取消、无效编码与磁盘写失败。
- [x] 用一次写入计数器的命令证明多次 `recall` 不会增加实际执行次数。

**完成条件：**源输出在容量内时，任意位置可从同次运行恢复；超限/失败时状态真实；日志恢复不会导致命令重跑、进程泄漏或丢失退出状态。

M4 已完成，见 [验证记录](./h03-m4-implementation-verification.md)。前台命令在首次裁剪前
并发排空并保存，超限时继续排空且明确 partial；真实 stdio 已验证三种命令的 stdout
首尾范围、短 stderr 和退出码到达最终 provider。stdio 注册持久 `recall` 仍按 M5 实施。

## 9. Milestone M5：真实入口、压缩和冷启动接通

**依赖：**M2–M4。**目标：**完成实际接线，证明模型确实能使用恢复能力。

- [x] `SessionRuntime` 为逻辑 session 创建正确 owner 的输出服务，并向每 turn 的 OUP `request_agent` 显式传递；不只接 bootstrap Agent。
- [x] stdio 注册 `recall`，核对 lean 白名单、工具合同、显式 allow/deny、provider policy、外层代理裁剪和最终 tools schema。
- [x] 显式禁用恢复工具时仍尊重用户政策；标明当前模型不能用该引用恢复，不建议调用一个被裁掉的工具。
- [x] 默认 `turn` scope 下不跨 session 自动共享。相同 `node/run` session 的结果可在其合法寿命内恢复；不强迫改变 session scope。
- [x] 压缩/trim 替代工具结果时保留短、完整的来源和恢复参数；latest request 和 call/result 配对沿用既有保护，不新增自由文本摘要模型。
- [x] 同时验证同进程压缩恢复和进程退出后持久恢复；确认只持久正文而未持久索引的情况不能算完成。
- [x] session_actor 路径复用同一恢复语义，避免保留另一套 50KB 页而再次被截断。
- [x] MCP 按 M0 冻结范围处理：支持时创建 invocation-local 服务，尊重工具政策并完成同调用内恢复；不引入 AppUI 依赖或扩展为 H04。
- [x] 不支持 MCP 跨 invocation 冷恢复时明确记录边界；不能因某个 stdio 快照测试成功而宣称 MCP resume 已覆盖。
- [x] spawn/pipeline 的公共构造点保持编译与行为兼容；每个 child 默认使用自己的输出权限，不继承“看见过正文”的凭据或整个父级存储能力。
- [x] 严格沙箱下使用受控账本读取，不让模型绕到任意用户目录；缺权限时返回明确错误，不循环请求放开全盘访问。
- [x] 真实 stdio 协议测试使用 fake provider 完成“读大文件/执行大日志 → 获得 next/ref → 恢复 → 最终请求含目标片段”，同时覆盖错误与受限工具模式。
- [x] 覆盖审批后继续、并行结果、重试、桥接失败等 M0 找到的实际分支；共享代码未覆盖的入口保持原行为并明确能力缺失。

**完成条件：**stdio/solo 的真实 tools 与 messages 中恢复功能可调用、可达、范围真实；压缩与重启之后仍能定位同一结果。条件性入口的支持与不支持均有证据。

M5 已完成，见 [验证记录](./h03-m5-implementation-verification.md)。真实 stdio 已验证
同进程与冷启动恢复、审批后继续、并行结果、provider 重试和受限工具策略；MCP 仅支持
invocation-local 恢复，不支持跨 invocation resume。

## 10. Milestone M6：恢复链观测、确定性回归与阶段提交

### 10.1 最小观测

- [x] 记录捕获字节、保存字节、最终可见字节、已知遗漏量/unknown、每层渲染/裁剪原因及策略 ID。
- [x] 记录页请求、返回范围、严格前进/EOF/stale、恢复成功/失败原因、保存次数和重复恢复次数。
- [x] 记录真实命令执行次数、终止状态及 artifact 状态，能够区分“取回旧日志”和“又执行了一次测试”。
- [x] 记录 H02 因重渲染/失去来源撤销候选与凭据的原因，复用已有指标，不另建状态账本。
- [x] 指标失败不改变工具结果；普通日志不输出完整源码、密钥、任意命令参数或原文正文。

### 10.2 必须覆盖的验收矩阵

下表覆盖 B 的恢复链；M7 再补搜索场景并联合验收。已在前置 Milestone 完成的测试直接复用，不再重复写同样的单测。数字是清单 ID，不是应凑齐的测试函数数量。

| ID | 场景 | 判定点 |
| --- | --- | --- |
| T01 | 临界页：8,192 字节、execution 上限、长路径与完整 footer | 最终请求整体预算内，提示可解析 |
| T02 | 文件中间/末尾唯一标记 | 按 next 重组声明范围，无遗漏 |
| T03 | 请求范围大于页；起点不为 1 | next 来自实际末端，范围不越界 |
| T04 | 超长单行、emoji、中文、CRLF、无末尾换行 | 不拆 UTF-8；变换与源覆盖不混淆 |
| T05 | 空文件、EOF、非法/溢出/混合参数 | 结果或错误明确，不静默钳位 |
| T06 | 单页和整批 context pressure，最低预算不足 | 有界重渲染或明确错误，无坏 footer |
| T07 | hook/sanitize/bridge fallback 改变内容 | 来源同步或失效，无假凭据 |
| T08 | H02 相同/子范围、full 请求、页被压缩 | 只有当前有效范围可命中 |
| T09 | 文件在两页间替换，保留旧 mtime/size | 强版本发现 stale，不混页 |
| T10 | 大 stdout，stderr/日志中间有唯一失败 | 状态与失败证据均可找到 |
| T11 | 非零退出、超时、取消、未知 exit code | 真实终止状态可见，无假成功 |
| T12 | 多次恢复含副作用命令的输出 | 原命令执行一次 |
| T13 | store failure、配额耗尽、partial capture | 明确不可恢复范围，无死锁/无界内存 |
| T14 | 落盘/索引发布途中崩溃、损坏或未知 schema | 不返回伪完整结果 |
| T15 | 同一 call ID 跨 turn 重复 | output ID 精确，旧 ID 歧义报错 |
| T16 | 两 task/session、父子/兄弟 Agent | 权限隔离，哈希相同也不串读 |
| T17 | 压缩两次、同进程恢复、冷启动恢复 | 引用仍指向同一记录或明确过期 |
| T18 | 恢复大结果、重复同游标 | 固定上界/预算下结果一致且不重复 spill；有效 next 前进 |
| T19 | 当前文件已变后恢复历史文件页 | 只作历史证据，不授权当前写入 |
| T20 | 跨块/页边界触发清洗，损坏 UTF-8 | 不绕过清洗，无假原文映射 |
| T21 | 正在写入时读/清理，索引与内存上限 | 只读已发布范围；无新输出为 pending；不删活跃数据 |
| T22 | stdio/solo 协议、显式 allow/deny、外层代理 | 最终 schema/权限与恢复提示一致 |
| T23 | M0 选定的 MCP/其他入口范围 | 已支持合同通过，未支持行为明确 |
| T24 | H03 off，read-window/dedup 各组合 | 底座兼容，写保护仍生效 |

- [x] T01–T24 都有对应自动化测试或明确的“不适用”入口证据；核心 stdio 场景不能标不适用。
- [x] T02/T04/T10 至少在最终 provider 请求上验证，不以 `ReadFileTool.output` 或 UI preview 代替。
- [x] 对 fixture 声明“完整保存”的内容按范围拼接并比较哈希；对 partial 明确验证缺口，不要求重建从未保存的字节。
- [x] 记录准确测试名、数量、命令和结果，零测试命中的过滤器不算通过。
- [x] 受影响 crate、H02 专项、ContextManager、OUP、shell 和条件性 MCP 回归完成。
- [x] 只记录尚存的基线问题，修复新引入失败；不得通过关沙箱、弱化断言或增加任务预算让测试变绿。
- [x] 审查 `A_SHA..HEAD`，没有混入官方输入变化、较大页实验或无关重构。
- [x] 本地提交并记录阶段 `M6_SHA`，保存实际二进制哈希和有效策略参数；证据文件建议 `h03-m6-recovery-verification.md`。该 SHA 只用于开发回归定位，不作为独立实验组。

**完成条件：**无静默缺口、错误游标、错误完整性声明和 H02 错误授权；所有容量和失败路径有界。恢复链具备继续开发搜索的条件，完整 B 在 M7 之后才具备实验条件。

M6 已完成，见 [验证记录](./h03-m6-recovery-verification.md)。代码提交为
`fbcfd6b85214fa12316303f16599dbb3a97437ce`，观测策略为 `output_recovery_v1`；
T01-T24 全部有自动化证据，真实 stdio 的热/冷恢复和命令单次执行继续通过。

## 11. Milestone M7：输出内搜索、联合验收与 B 冻结

**依赖：**M6。**目标：**在同一 B 分支补齐有界搜索，再冻结完整优化方案。

- [x] 从 `M6_SHA` 继续同一 `feat/output-recovery` 分支，保留独立实现提交用于定位回归，不创建第三组实验分支。
- [x] 在同一受控输出服务上增加有界定位能力，优先扩展 `recall` 的可选 literal query/模式；不增加语义索引或新 agent。
- [x] 搜索只接受合法 output ID 和 owner，限制扫描量、匹配数、片段长度；返回位置，再按既有页读取。
- [x] 搜索未扫完整范围时明确 `search_complete=false` 和下一位置；不能把“当前已扫描无匹配”说成“整个输出无错误”。
- [x] 搜索在模型安全文本视图上运行，不借匹配片段泄漏 raw 审计内容。
- [x] page/执行/存储预算、压缩、H02、模型和外层流程保持 M6 的设定，只补搜索及其必要 schema。
- [x] 验证无匹配、多匹配、跨块匹配、超限续查、partial artifact、取消与越权。
- [x] 回归 T01–T24，并完成下面 T25–T28；无需因每个搜索小改动重复全部测试，但最终冻结必须覆盖完整组合。
- [x] H03 总开关关闭时恢复共同底座行为；开启时分页、恢复和搜索均可用，记录全部新增工具定义的输入 token 成本。
- [x] 审查 `A_SHA..HEAD`，本地提交并冻结完整 `B_SHA`，记录二进制哈希、配置、28 项场景证据与限制；证据文件建议 `h03-m7-b-variant-freeze.md`。

| ID | 搜索场景 | 判定点 |
| --- | --- | --- |
| T25 | 无匹配、多匹配、跨块匹配 | 位置正确；完整无匹配与部分未命中区别明确 |
| T26 | 扫描/匹配/片段预算、partial artifact、取消 | 有界执行；缺口和 next 可解释，不伪称全文已搜索 |
| T27 | 越权引用与清洗后的输出 | 与恢复共用权限和安全文本视图，不泄漏原始审计内容 |
| T28 | 真实入口搜索后按位置读取，H03 开/关 | 最终 schema 和 messages 一致；目标片段可达且原命令不重跑 |

**完成条件：**分页、原文恢复、输出内搜索作为完整 B 通过 T01–T28。更大页策略另立后续任务，不进入本轮；没有完成搜索不能把 M6 阶段版本冒充完整 B。

M7 已完成，见 [完整 B 冻结记录](./h03-m7-b-variant-freeze.md)。
`B_SHA=4c542e534e957d69a5ee05d24ffb7e166beb78bb`；T01-T28 和真实 stdio
均已验证。官方任务正确率与全任务 token 对照仍属于 M8，当前不作收益结论。

## 12. Milestone M8：固定官方任务的 A/B 对照

### 12.1 开跑条件

- [ ] M7 冻结的完整 B 通过全部确定性门槛。先确认当前执行范围允许真实模型实验。
- [ ] 运行前执行 `source ~/.zshrc`；确认模型配置、真实 `OCTOS_BIN`、二进制哈希、端口与隔离目录。
- [ ] 缺配置时具体报告名称及补充位置，例如 `OCTOS_BIN`、当前 provider 要求的 endpoint/key；不输出凭据值，不进入重复排障循环。
- [ ] 默认以固定的全量官方任务/测试集合做主对照，先列出完整清单及输入哈希。资源不足时标记尚未完成，不用少数 smoke 代替全量结论。
- [ ] A/B 的 requirements、测试、模板、模型、reasoning、生成档位、session scope、工具权限和请求/修复预算一致；差异仅限完整 H03 功能和必要恢复/搜索工具。
- [ ] 时间不作为评分指标；既有超时/墙钟截止仍会影响结果，两组保持相同设置并记录，不能只给 B 延长执行预算。
- [ ] 固定重复次数，建议每个 task×variant 至少 3 次，交错运行顺序；未完成的重复如实报告。
- [ ] 每 run 使用独立工作区/data/session，避免共享生成结果、artifact、receipt 或长期记忆；同 key 计量遵循项目既有串行要求。
- [ ] 观察实际是否进入 tool mode、产生大结果、执行恢复。未触发场景仍计入全任务正确率/总 token，但不用于推断恢复机制的触发收益。

### 12.2 每次运行记录

复用现有 experiment manifest/usage 管道；只增加必要字段，不另造平行计费器。

- [ ] `MAIN_SHA/A_SHA/B_SHA`、实际运行 SHA、git dirty、二进制路径与哈希。
- [ ] 任务 ID、官方输入/测试/模板哈希、模型及非敏感 endpoint 标识、repetition/run_order。
- [ ] H01/H02/H03 开关、有效页/存储/搜索/compaction policy、工具列表与权限、session scope。
- [ ] 所有已知 provider input/output/cache/reasoning 用量、请求数与重试；无用量记 unknown，不记零。
- [ ] 最终逐用例原始报告、生成产物版本、恢复指标、命令执行数、存储/内存和耗时诊断。
- [ ] 外部基础设施故障单列；由 H03 引起的 OOM、死锁、输出错乱、超时或保存错误是产品失败，不能排除后只报告成功样本。

### 12.3 采用顺序

| 优先级 | 指标 | 判定 |
| --- | --- | --- |
| 1 | 官方最终通过数、全通过率、回归和重复稳定性 | 不因少传正文而降低正确率 |
| 2 | 静默遗漏、错误游标、伪完整引用、越权恢复、错误 H02 授权 | 确定性门槛为零 |
| 3 | 全任务 token | 含失败、重试、恢复和新增 schema；按 provider 契约避免重复计入缓存/推理 |
| 4 | 重读/恢复请求、查到失败片段前的调用数、命令重跑 | 解释 token 变化，不能替代总量 |
| 5 | 时间、I/O、内存、磁盘 | 运行诊断，不算成绩 |

- [ ] 报告 B−A 的完整方案收益，包含分页、恢复、搜索及新增 schema 的成本；不将整体收益归因于某个单项，也不计入共同依赖移植的效果。
- [ ] 单页变短、缓存命中上升、请求减少均不能独立证明节省；比较整题累计 token。
- [ ] 不挑最优单次结果；逐任务列出重复结果、失败类型和离散程度。证据不足时结论为未确定。

**完成条件：**预注册的全部有效实验完成，用量可追溯、失败不漏报；结论遵守正确率优先。建议未来证据文件 `h03-experiment-results.md`。

## 13. Milestone M9：采用、集成与回滚

- [ ] 汇总完整 B 是否满足确定性与官方测试门槛，并与 A 比较；不达标或证据不足时保持 A，修正后重新冻结和评估，不因已写代码强行采用。
- [ ] 决定启用前重新拉取最新主线并集成选中实现，记录 `INTEGRATION_SHA`；不改写已冻结实验 SHA。
- [ ] 检查与当前 H01、H02、MCP、tool policy、持久 schema 的组合，重新跑受影响回归与官方 smoke。
- [ ] 若集成改变了关键执行语义，重跑对应对照；旧实验不能自动证明新组合的收益。
- [ ] 关闭 H03 后不关闭 H02 强版本/写保护，也不删除用户文件或破坏现有数据。
- [ ] 旧二进制/未知 schema 遇到新引用时有明确失败或兼容策略；不能把损坏/不支持记录当成完整原文。
- [ ] 更新实际采用的默认配置和行为文档，移除本分支未采用且无维护价值的实验死代码；保留实验结论。
- [ ] 完成每个 Milestone 的本地 Git 提交和证据记录；远程推送按届时用户指令执行。

**完成条件：**选中方案在最新主线组合下仍可验证，回滚不会破坏文件或撤销既有保护；文档准确区分支持入口、存储寿命和已测收益。

## 14. 测试、提交与交接要求

### 14.1 验证方式

每步运行与改动相关的测试；M6 汇总恢复链回归，M7 完成含搜索的联合验收。先用 `-- --list` 核对测试实际存在和过滤范围；下面是候选命令，不是已运行记录。

```bash
cargo test -p octos-agent --lib read_file
cargo test -p octos-agent --lib read_window
cargo test -p octos-agent --lib recall
cargo test -p octos-agent --lib shell
cargo test -p octos-agent --lib model_read_receipts
cargo test -p octos-agent --test h02_m1_file_versions --test h02_m2_read_receipts --test h02_m3_receipt_lifecycle
cargo test -p octos-cli --lib context_manager
cargo test -p octos-cli --lib appui_prompt_context_bridge
cargo test -p octos-cli --test mcp_serve_integration
cargo fmt --all -- --check
cargo clippy -p octos-agent -p octos-cli --all-targets -- -D warnings
git diff --check
```

后续新增 H03 集成测试命令必须写入证据，尤其是**真实 stdio + fake provider**测试。上面的模块过滤器不能替代它。更改 spawn/pipeline 构造时增加对应专项回归；跨层 API 变更完成时做必要的 workspace 编译检查。

涉及 ARC 外层或全量冻结验证时，按仓库可运行方式执行：

```bash
cd arc
python3 -m unittest discover -s tests
```

已知环境问题只作排查参考，必须重新核实：macOS 沙箱下部分全量测试可能被 `SIGKILL`；Python 3.9 不支持 `tarfile.extract(filter=...)`；旧基线 `serve.rs` 存在 Clippy 告警。不要预先忽略所有错误，也不要为本轮顺手修改无关基线代码。`octos_stdio.py` 的审批响应必须包含 `session_id`，真实测试若卡在审批应先核对协议证据。

### 14.2 每个 Milestone 的交接格式

- [ ] 本次完成的行为和仍待完成的清单项，使用通俗中文。
- [ ] 修改文件、关键入口、依赖 SHA、功能开关与实际默认值。
- [ ] 准确测试命令、通过/失败/跳过数量、退出码；基线失败与新增失败分开。
- [ ] 证据位置、限制和下一 Milestone 的起点；没有证据的项不勾选。
- [ ] `git diff --check`、预期路径检查、干净状态与本地提交 SHA。

建议提交按 M0→M7 逐步进行；一个 Milestone 过大时拆成保持绿色的小提交。提交信息写实际行为，如“保证文件页与续读提示完整进入模型”“保存并恢复同一次命令的输出”“按位置查找输出中的文本”。不把内部代号当成变更说明。

如果提交后钩子报错，先核实 commit 是否已经创建及工作树状态，不盲目重复提交或关闭钩子。若实际源码推翻某个假设，在对应证据里写清事实和等价方案，更新本清单后继续；不能静默放宽完整性、版本、权限或最终模型可见性要求。
