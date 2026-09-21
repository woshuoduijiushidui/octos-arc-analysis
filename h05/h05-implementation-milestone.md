# H05 实施 Milestone：已有代码优先局部编辑

- 状态：M0-M2 已完成，M3-M11 待实施
- 面向对象：后续 coding agent
- 设计依据：[H05 竞品调研](./h05-local-edit-competitor-research.md)
- 关联约束：[H02 实施清单](../h02/h02-implementation-milestone.md)、[H03 实施清单](../h03/h03-implementation-milestone.md)、[优化总表](../harness-optimization-table.md)
- M0 证据：[共同底座、调用链与基线反例](./h05-m0-baseline.md)
- M1 证据：[局部编辑选择规则验证](./h05-m1-implementation-verification.md)
- M2 证据：[typed 失败与有界当前候选验证](./h05-m2-implementation-verification.md)
- 编写日期：2026-09-21
- 调研时主线：`octos-arc origin/main@27d057c206c0f8250b60309905737f7e26ee0ba9`
- 可复核依赖：H02 文件保护 `7eaa136ef086a2f9728794d17d8f150482df03d1`；H03 完整 B `4c542e534e957d69a5ee05d24ffb7e166beb78bb`

本文是实施 todo list，不代表代码已经完成。只有同时具备代码、自动化验证和可追溯证据时，
才能把 `[ ]` 改成 `[x]`。类型名和文件位置可随最新主线调整，但安全边界、实验隔离和完成条件
不得静默弱化。

## 0. 后续 Agent 先读这一节

目标不是简单地“多用 patch”，而是让已有文件的修改满足以下规则：

```text
新文件可以完整写入
已有文件的局部变化优先唯一定位后局部修改
定位不唯一时不猜、不写，直接给下一次重试所需的少量当前证据
成功只返回短摘要，实际改动通过结构化元数据记录
```

评估顺序固定为：

1. 官方测试正确率、回归数和重复运行稳定性。
2. 错位置写入、过期覆盖、歧义放行和未报告的部分写入，目标均为零。
3. 全任务累计 token，包含失败调用、候选反馈、重读、重试和 fallback。
4. 请求数、工具调用数、I/O 和耗时只用于解释结果；耗时不计入成绩。

### 0.1 A/B/C/D 到底是什么

| 组别 | 内容 | 唯一要回答的问题 |
| --- | --- | --- |
| A | 最新共同底座，保持当前编辑行为 | 当前正确率、token 和误写基线是多少 |
| B | A + H05a-d、H05f；保留当前 fuzzy 自动写 | 工具选择、失败恢复、no-op、实际 diff、`replace_all` 和 `diff_edit` fallback 是否有效 |
| C | B + H05e；近似 fuzzy 只返回候选，不自动写 | 收紧匹配是否减少回归，以及增加多少重试/token |
| D | M8 选中的工具模式 + existing codegen patch；fresh/new file 仍完整输出 | 无工具 codegen 的补丁协议是否额外提高稳定性或降低总 token |

本文件的实验命名以此表为准：codegen patch 始终属于 D，不再复用 C 这个名字。
若 M8 最终选择 C，D 的对照底座就是 C；若选择 B，D 的对照底座就是 B。下文把这个已选底座
记为 `S`。D 只与 S 比较，不与 A 直接比较。

### 0.2 执行原则

1. 开工先 `git fetch origin main`，从当时最新 `origin/main` 创建 `feat/local-edit`；本文记录的 SHA 只用于查证，不能直接当成未来开工基线。
2. 当前 `feat/output-recovery` 有未推送的 H02/H03 提交，不得 reset、覆盖或改写。必要时使用独立 worktree 创建 H05 分支。
3. 若最新主线尚未包含 H02/H03，先把经验证且 H05 必需的依赖移到共同底座，单独提交并记录来源 SHA；依赖收益不得算作 H05 收益。
4. M1-M6 只形成 B；M7 单独形成 C；M9 才开始 D。不得在一个提交里同时改变工具反馈、matcher 和 codegen 协议。
5. 每个 Milestone 完成后本地提交；不推送远程，不创建 PR，除非用户另行明确要求。
6. 不修改官方需求、测试、判分器、模型、reasoning、请求预算、修复轮数或超时来“换取”通过。
7. 不把隐藏的 `apply_patch` 加回默认 coding/stdio 工具面，也不新增第二套文件版本、锁或 diff 状态系统。
8. 真实环境运行前执行 `source ~/.zshrc`。若配置或凭据缺失，明确写出缺少的名称和补充位置，不把 unknown 记成 0。

| Milestone | 主要产出 | 对应分组 |
| --- | --- | --- |
| M0 | 最新共同底座、真实调用图、开关和基线反例 | A |
| M1 | 新建/整写/局部编辑的短选择规则 | B |
| M2 | typed 失败、当前版本和有界候选证据 | B |
| M3 | no-op 与最终实际改动元数据 | B |
| M4 | `diff_edit` 全文件唯一 fallback | B |
| M5 | exact-only 显式 `replace_all` | B |
| M6 | B 的真实入口回归、观测和冻结 | B |
| M7 | fuzzy 只提示的独立开关、回归和冻结 | C |
| M8 | 固定官方任务 A/B/C 对照并选择 S | A/B/C |
| M9 | existing codegen patch 协议与确定性验证 | D |
| M10 | 固定官方任务 S/D 对照 | S/D |
| M11 | 采用、最新主线集成和独立回滚 | 选中方案 |

## 1. 分支、开关和共同底座

### 1.1 M0 必须冻结的版本

- [x] 检查 `octos-arc` 与 `octos-arc-analysis` 的分支、工作树、未跟踪文件和未推送提交；不自动清理用户改动。
- [x] 拉取最新 `origin/main`，记录 `MAIN_SHA`，从该 SHA 创建 `feat/local-edit` 或等价独立 worktree。
- [x] 核对最新主线是否已有 H02 强版本/写保护、H03 8 KiB 最终输出预算和 H04 的有效实现；逐项记录“已包含、需移植、不适用”。
- [x] 若需移植依赖，保持原提交可追溯并先跑依赖专项回归，冻结共同底座 `A_SHA`；H05 行为尚未开启。
- [x] 记录 A 的二进制路径、SHA-256、Rust/Python/Node 版本、默认工具列表、工具 schema 字节数和有效配置。
- [x] 固定官方实验任务、输入/测试哈希、模型、reasoning、session scope、工具权限、请求预算、修复轮数和重复次数。

建议开关语义如下；若最新主线已有统一配置入口，可调整名字，但必须保留三项独立能力：

| 开关 | 默认 | 用途 |
| --- | --- | --- |
| `OCTOS_LOCAL_EDIT` | off | M1-M6 的 B 总开关 |
| `OCTOS_LOCAL_EDIT_STRICT_MATCH` | off | M7 的 C matcher 开关；只有 B 开启时才生效 |
| `OCTOS_ARC_CODEGEN_PATCH` | off | M9 的 D 开关；不影响 fresh/new file |

- [x] `OCTOS_LOCAL_EDIT` 在进程内解析一次并由 `ToolRegistry` 保存，不在每次 matcher 调用里反复读取环境变量。
- [x] `OCTOS_LOCAL_EDIT=0` 时，工具 schema、结果文本和磁盘行为与 A 兼容。
- [ ] strict 开关关闭时必须与 B 等价；codegen patch 关闭时必须与 S 等价。
- [x] 已实现的 H05 开关遇到未知值时按 off 处理并留下有界诊断，不静默开启实验行为。

### 1.2 优先核对的真实代码路径

| 职责 | 优先阅读位置（相对 `octos-arc/`） |
| --- | --- |
| 单点替换与参数 | `crates/octos-agent/src/tools/edit_file.rs` |
| 六级 matcher | `crates/octos-agent/src/tools/replacer.rs` |
| unified diff 与 hunk 定位 | `crates/octos-agent/src/tools/diff_edit.rs` |
| 版本、锁、读取当前字节和写入 | `crates/octos-agent/src/tools/mutation_guard.rs` |
| 新建/整写与 H02 保护 | `crates/octos-agent/src/tools/write_file.rs` |
| formatter 后处理 | `crates/octos-agent/src/format.rs` |
| 模型文本与结构化结果 | `crates/octos-agent/src/tools/mod.rs::ToolResult`、`agent/execution.rs` |
| 默认 coding 工具面 | `crates/octos-agent/src/assets/profiles/coding.json`、`profile/mod.rs` |
| stdio/solo 注册与最终 prompt | `crates/octos-cli/src/runtime/profile.rs`、`api/ui_protocol_transport.rs` |
| diff UI/持久侧通道 | `crates/octos-agent/src/tools/apply_patch.rs`、`crates/octos-cli/src/contracts/diff.rs` |
| Python codegen | `arc/main.py`、`arc/codegen.py` |
| Rust codegen | `crates/octos-arc/src/flow.rs`、`codegen.rs`、`prompts.rs` |

## 2. 不可破坏的约束

- [x] 所有已有文件修改仍在 `mutation_guard` 的同一路径锁内读取当前 bytes、检查版本、定位和写入。
- [x] H02 的 stale/context/read receipt 规则保持失败关闭；候选片段不能冒充完整文件读取，也不能授权整文件覆盖。
- [ ] 新文件创建继续使用 `create_new`/`O_CREAT|O_EXCL` 等现有保护；目标并发出现时拒绝覆盖。
- [ ] no-match、ambiguous、no-change 和 parse failure 前后文件 hash 不变，不运行 formatter，不创建 workspace snapshot。
- [ ] 发生 I/O 部分写入时必须设置 `file_modified` 并明确提示重新读取；不得返回“未修改”。
- [x] 候选片段来自本次锁内读取的当前内容，经过现有清洗和最终投影；不从旧消息、旧 receipt 或旧缓存拼装。
- [x] 模型可见结果、候选、路径、版本和补救提示共同计入 H03 最终批次 8 KiB 预算；不得依赖下游盲切保持可解析性。
- [ ] 完整 `old_string`、`new_string` 和整文件不在成功文本中重复回显；它们已存在于工具调用参数或磁盘。
- [ ] formatter 运行后才计算“最终实际改动”。无法可靠重读或发生并发变化时，元数据明确标为不可确认，不能伪造精确范围。
- [ ] `write_file`、`edit_file`、`diff_edit`、隐藏 `apply_patch` 的权限、路径 confinement、symlink 和 write-grant 行为不放宽。
- [ ] 默认工具列表不增加 `apply_patch`；不同时提供第四种重叠编辑工具来增加固定 schema token。
- [ ] 不为 H05 顺手修改 H04 压缩、H06 修复轮、H07 循环检测、H08 预算或 H09 全工具 schema。

## 3. 结果约定

具体 Rust 类型优先扩展已有结构；只有在三个工具确有重复时才抽小型共享 helper，不新建平行
状态系统。

### 3.1 失败结果

建议至少能稳定区分：

```text
edit_no_match
edit_ambiguous
diff_context_no_match
diff_context_ambiguous
no_change
stale_file_version
invalid_edit_input
```

- [x] M0 已核对现有消费者并选定 `error_code` 为 rejection 的 canonical 字段；不得同时新增两套含义相同的字段。
- [x] structured metadata 至少包含 path、当前强版本、matcher、occurrence count、稳定行范围、补救动作和 `file_modified` 事实。
- [x] 文本结果只保留一行原因和下一步；绝对路径、完整源码、凭据和超长 `old_string` 不进入日志或模型文本。
- [x] 多候选按稳定顺序返回；每个候选只有必要上下文，标明 `suggestion=true`，不得暗示已经写入。
- [x] stale 优先返回 H02 的重读补救，不用 fuzzy 候选掩盖版本变化。

### 3.2 成功结果

- [ ] 模型文本包含 path、实际 matcher、替换次数或 hunk 数、最终短版本和 formatter 状态。
- [ ] structured metadata 记录最终实际改动范围、applied diff 摘要、最终版本和是否发生 formatter 扩大改动。
- [ ] UI/审计需要的 diff 复用现有 `structured_metadata`/diff preview 通道；模型文本不重复携带完整 diff。
- [ ] `file_modified` 只在磁盘确实可能变化时设置；typed no-op 不得伪装成成功写入。
- [x] no-op 的 `success` 冻结为 `true`，用 metadata `outcome=no_change` 机器识别，避免 exclusive-call 级联取消；同时必须无副作用。

## 4. Milestone M0：冻结底座、调用图和基线反例

**目标：**在写功能前确认真实入口、状态所有者和实验差异。M0 不开启 H05。

- [x] 完成第 1.1 节，记录 `MAIN_SHA`、依赖移植 SHA 和 `A_SHA`。
- [x] 追踪 `edit_file`、`diff_edit`、`write_file` 从 ToolSpec、参数解析、审批、exclusive 执行、`mutation_guard`、formatter、snapshot 到最终 provider message 的完整链路。
- [x] 分别追踪普通 stdio/solo、MCP `run_octos_session`、spawn/worker 和 legacy `execute()`；明确 H05 必须支持与只需保持兼容的入口。
- [x] 证明当前 `edit_file` 六级 matcher 的每级行为、歧义规则和首个阶段优先规则。
- [x] 证明当前 `diff_edit` 的 `+-3`、trailing-whitespace 比较、多 hunk 反向应用及失败时未写盘行为。
- [x] 证明当前 `rewrite_existing` 即使前后 bytes 相同也会 truncate/write，并确认 claim、receipt、formatter、snapshot 的副作用。
- [x] 核对 `ToolResult.structured_metadata` 到事件、AppUI、持久记录和下一轮模型消息的真实投影，确认哪些字段会占模型 token。
- [x] 核对 A 的默认 coding/stdio 工具列表不含 `apply_patch`，记录完整 schema 哈希或字节数。
- [x] 准备不调用付费模型的 fake provider/真实 stdio 夹具，复现：无匹配后重读、歧义、错误 fuzzy 自动写、行号漂移、no-op 仍写盘、formatter 扩大 diff。
- [x] 只新增能固定现状或目标 contract 的测试；不要把主分支永久留在红色状态。

**完成条件：**A 可重放，B/C/D 的唯一变量、开关、真实调用链和至少六个基线反例均有证据。

## 5. Milestone M1：增加短而统一的编辑选择规则

**依赖：**M0。**对应：**H05a。**目标：**让模型在生成长参数前先选对现有工具。

- [x] 在稳定 coding profile/system section 中加入一次短选择矩阵：新文件用 `write_file`；一个连续局部变化用 `edit_file`；同一文件多个分散变化用单次多 hunk `diff_edit`。
- [x] 已有文件只有在完整当前版本可见且确实需要整体重建时才用 `write_file`；不得写成“一律禁止整写”。
- [x] 多文件小改继续使用独立局部调用并保持 mutation 串行，不新增默认多文件 patch schema。
- [x] 同步收紧三个工具的 description，使其职责互补；避免在 system prompt、三个 schema 和 ARC user prompt 中重复长段规则。
- [x] stdio/solo 与普通 coding profile 获得相同核心规则；MCP/worker 复用公共 prompt 组装，不复制另一份易漂移文案。
- [x] ARC tool-mode 已由公共 system prompt 覆盖，因此未修改 ARC user prompt、codegen 协议或请求预算。
- [x] 保持 provider-specific tool order、默认工具数量和 `apply_patch` 可见性不变。
- [x] 测试 H05 off 时 schema 文本与 A 一致；H05 on 时规则短、无冲突、所有真实入口只注入一次。

**完成条件：**模型在最终工具 schema/system prompt 中能明确区分创建、整写、单点替换和单文件多 hunk，且固定输入增量已量化。

## 6. Milestone M2：typed 失败与有界当前候选

**依赖：**M1。**对应：**H05b。**目标：**常见编辑失败不再强迫模型先整文件重读。

- [x] 扩展 `replacer` 的结果，使 no-match/ambiguous 能返回 matcher、候选 range、稳定行号和可选 score，而不是只返回字符串/count。
- [x] exact 多匹配返回 occurrence count 和有限起始行；不自动选择第一处。
- [x] exact 为零时可以运行现有 fuzzy matcher寻找候选，但 B 仍保持当前自动写行为；本阶段只建立可复用的候选表达。
- [x] 把 transform 内的字符串错误升级为 typed rejection，贯穿 `mutation_guard` 到 `ToolResult`；不要在上层解析错误文本恢复类型。
- [x] structured metadata 带当前强版本和 searched-old digest；模型文本中的版本只显示短摘要。
- [x] 候选片段直接来自锁内当前 bytes，并记录实际行范围；文件在候选计算前后变化时走 stale，不返回旧候选。
- [x] 每个候选和总候选数有硬上限；先保留错误码、版本、范围和 remedy，再裁候选正文。
- [x] 候选结果经过现有 sanitize/final projection，且不会创建 H02 完整读取 receipt。
- [x] 覆盖 Unicode、CRLF、超长行、长路径、重复文本、无候选、多阶段候选和极小剩余预算。
- [x] 在最终 fake provider 请求中验证 typed 字段与文本一致，整体不超过 H03 的最终批次预算。

**完成条件：**no-match/ambiguous 后，模型可直接用返回的当前局部证据重试；失败前后文件 hash 不变，结果有界且不产生错误读取授权。

## 7. Milestone M3：no-op 与最终实际改动元数据

**依赖：**M2。**对应：**H05c。**目标：**不为“没有变化”制造写入，也不把调用意图冒充实际结果。

- [x] 在共享写入边界比较当前 bytes 与候选 bytes；相同时在 truncate/write 前返回 typed `no_change`。
- [x] no-op 释放 mutation claim，但不消费现有版本、不撤销 receipt、不 invalidate cache、不运行 formatter、不创建 snapshot。
- [x] `old_string == new_string`、diff 应用后 bytes 相同、已有文件整写内容相同都进入明确 no-op；新建空文件仍是真实创建。
- [x] no-op 不能绕过路径权限、write grant 或 stale 检查；无权写和版本过期仍返回原错误。
- [x] 记录 before version、工具写入后的版本和 formatter 后最终版本；无法确认最终版本时如实降级。
- [x] 成功 metadata 包含 matcher、replacement count/hunk count、实际行范围、formatter 状态和有界 diff preview。
- [x] formatter 改变内容时，以 formatter 后磁盘内容计算最终范围；不要只比较工具参数中的 `new_string`。
- [x] formatter 失败但文件已改时保持 `file_modified` 和真实成功/告警语义，避免模型重复应用同一修改。
- [x] 复用现有 AppUI diff metadata 约定；不得为 H05 新建第二个 diff 持久仓库。
- [x] 测试 inode/mtime 或写计数、formatter 调用计数、snapshot 数和 receipt/cache 状态，证明 no-op 确实没有副作用。

**完成条件：**三种文件工具都能区分“请求成功但没有变化”和“磁盘已变化”，成功摘要与 formatter 后最终内容一致。

## 8. Milestone M4：`diff_edit` 全文件唯一 fallback

**依赖：**M2-M3。**对应：**H05f。**目标：**行号漂移超过 3 行时，只要上下文在全文件唯一，仍可一次成功。

- [ ] 保留当前 hunk 目标位置和 `+-3` 搜索作为首选，避免无必要全文件扫描。
- [ ] 局部没有候选时，在当前锁内内容中搜索全文件唯一的 exact/行尾等价 block。
- [ ] 全文件恰好一个候选才应用；多个候选返回 typed ambiguous 和有界位置；零候选返回 typed no-match 和当前位置附近证据。
- [ ] 不把 `line_trimmed`、空白合并、缩进变换或 block similarity 用作全文件自动 fallback。
- [ ] 多 hunk 先在内存中全部定位、验证不重叠并计算最终内容，任一 hunk 失败时不写文件。
- [ ] 反向应用后仍报告原 hunk 与实际位置的映射；后一个 hunk 的变化不能让前一个 hunk 错配。
- [ ] 保留文件末尾换行和 CRLF/LF 策略；行尾等价不能吞掉 Markdown 双空格等有语义内容。
- [ ] 覆盖偏移 4 行、远距离唯一、全文件重复、hunk 重叠、空 context、多 hunk 一处失败和大文件扫描上限。

**完成条件：**超出 `+-3` 的唯一旧 block 可以安全应用；歧义和失败均零写入，并给出一次重试所需的证据。

## 9. Milestone M5：exact-only 显式 `replace_all`

**依赖：**M2-M3。**对应：**H05d。**目标：**明确的批量字面替换不需要模型重复调用。

- [ ] 为 `edit_file` 增加可选 `replace_all=false`，保持旧调用兼容并拒绝未知/错误类型。
- [ ] 只有模型显式传 `true` 才批量替换；harness 不在 ambiguous 后自动改成 `true`。
- [ ] 只允许 exact 或明确的行尾等价匹配；禁止 fuzzy replace-all。
- [ ] 在同一次锁内读取的当前版本上收集全部不重叠 occurrence，一次计算并一次写入。
- [ ] 返回真实 replacement count 和稳定行位置摘要；位置过多时截断列表但保留总数。
- [ ] `old_string` 为空、`old_string == new_string`、匹配数为零、结果超出既有限制时返回 typed 结果且不写。
- [ ] 大量匹配设置明确上限或使用已有 mutation/output policy；拒绝时建议结构化生成器或明确脚本，不静默只改前 N 个。
- [ ] exact 单点默认行为不变；`replace_all=false` 遇到多个匹配仍拒绝。
- [ ] 覆盖相邻/重叠文本、Unicode、CRLF、匹配上限、并发版本变化和 formatter 后实际 diff。

**完成条件：**批量替换的意图、匹配范围和结果可追溯；默认单点编辑不会因新增参数放宽歧义保护。

## 10. Milestone M6：B 的真实入口、回归、观测和冻结

**依赖：**M1-M5。**目标：**把 H05a-d、H05f 作为完整 B 验收，不提前混入 C 或 D。

### 10.1 最小观测

- [ ] 记录工具、结果 code、matcher、候选数、替换数/hunk 数、实际修改行数和 formatter 是否扩大改动。
- [ ] 记录 no-match/ambiguous/no-change/stale 次数，以及失败后下一次编辑是否成功、是否发生额外 read。
- [ ] 记录整文件写入参数字节、局部编辑参数字节、结果文本字节、structured metadata 字节和新增 schema 字节。
- [ ] 指标失败不改变工具结果；普通日志不包含源码正文、完整调用参数或凭据。

### 10.2 B 的确定性验收矩阵

| ID | 场景 | 判定点 |
| --- | --- | --- |
| T01 | 新文件创建；同名目标并发出现 | 首次成功；并发出现拒绝覆盖 |
| T02 | exact unique 单点编辑 | 只改目标范围 |
| T03 | exact 多匹配默认编辑 | 拒绝，返回总数和稳定位置 |
| T04 | no-match 与 fuzzy 候选 | B 保持当前自动写；失败候选来自当前版本 |
| T05 | `replace_all=true` | 只改全部 exact/行尾等价匹配，次数正确 |
| T06 | 三类 no-op | 无写入、formatter、snapshot 或 receipt/cache 失效 |
| T07 | CRLF、Unicode、超长行、Markdown 尾随空格 | 无乱码、无意外语义归一化 |
| T08 | `diff_edit` 偏移超过 3 行且全文件唯一 | 成功并报告实际位置 |
| T09 | `diff_edit` 全文件多候选 | 拒绝且零写入 |
| T10 | 多 hunk 中一个失败 | 整个文件不写 |
| T11 | 候选和结果接近 8 KiB | 最终请求有界且 metadata/text 一致 |
| T12 | 匹配前、写入前、formatter 前后并发变化 | 无 stale overwrite；元数据不撒谎 |
| T13 | formatter 扩大/不改变/失败 | 最终 diff 与 `file_modified` 真实 |
| T14 | H02 receipt 与 compaction | 候选不授权整写；旧 receipt 不放宽 |
| T15 | stdio/solo、MCP、spawn/legacy | 支持入口同合同；其他入口保持兼容 |
| T16 | H05 off 与默认工具面 | A 行为恢复；`apply_patch` 仍不在默认列表 |

- [ ] T01-T16 均有自动化测试或有证据的“不适用”；stdio/solo 核心场景不能标不适用。
- [ ] T04/T08/T11/T15 至少在真实 stdio + fake provider 的最终 messages/tools 上验证。
- [ ] 回归 H02 mutation、H03 输出预算/压缩/恢复和受影响的 AppUI diff 路径。
- [ ] 审查 `A_SHA..HEAD`，不含 strict matcher、codegen patch、官方输入变化或无关重构。
- [ ] 本地提交并记录 `B_SHA`、二进制 SHA-256、有效开关、工具 schema 大小和测试证据。

**完成条件：**B 通过 T01-T16，H05 off 与 A 兼容，所有失败路径有界且无错误写入；此时才能进入 C。

## 11. Milestone M7：C 的 fuzzy 只提示实验

**依赖：**M6。**对应：**H05e。**目标：**只改变自动匹配边界，测清 fuzzy 自动写的真实价值和风险。

- [ ] 从 `B_SHA` 继续或创建可追溯实验分支，开启独立 strict matcher 开关；不修改 B 的其他反馈和 metadata。
- [ ] `edit_file` 自动写入只允许 exact 和行尾等价；`line_trimmed`、whitespace、indentation、escape、block-anchor 只返回候选。
- [ ] `diff_edit` 在 strict 下也只用 exact/行尾等价自动定位；trailing-whitespace 宽松匹配只能作为 suggestion。
- [ ] fuzzy 候选保持稳定排序、matcher、score/范围和有界片段，但 `file_modified=None`。
- [ ] 工具 description 与实际 strict 行为一致；除此之外保持 schema、prompt、模型和预算不变。
- [ ] strict 关闭时逐项与 B 等价，不能因重构悄悄改变 B matcher 顺序。
- [ ] 测试 Python 缩进、Markdown 双空格、字符串字面量空格、模板文本、转义字符串和 block-anchor 误写反例。
- [ ] 回归 T01-T16；T04 的判定改为“返回 suggestion 且零写入”，其余合同不变。
- [ ] 本地提交并冻结 `C_SHA`，记录 B/C 唯一 diff、二进制哈希和确定性测试证据。

**完成条件：**C 除 fuzzy 自动落盘外与 B 等价；所有近似匹配只提示且不写，exact/行尾等价成功率不回归。

## 12. Milestone M8：固定官方任务 A/B/C 对照

### 12.1 开跑条件

- [ ] B、C 均通过确定性门槛，且用户确认可以运行真实模型实验。
- [ ] 执行 `source ~/.zshrc`，确认 provider endpoint/key、`OCTOS_BIN`、二进制哈希、端口和隔离目录。
- [ ] A/B/C 使用相同需求、测试、模板、模型、reasoning、session scope、工具权限、请求预算、修复轮数、超时和 H01-H04 配置。
- [ ] 每个 task×variant 使用独立 workspace/data/session；固定重复次数，建议至少 3 次并交错顺序。
- [ ] 无 H05 触发的任务仍计入总体正确率/token，但不能用于推断 matcher 的局部收益。

### 12.2 每次运行记录

- [ ] `MAIN_SHA/A_SHA/B_SHA/C_SHA`、实际运行 SHA、git dirty、二进制路径和 SHA-256。
- [ ] task、输入/测试/模板哈希、模型、reasoning、重复序号、运行顺序和全部有效开关。
- [ ] 最终官方逐例结果、首轮通过数、回归数、重复稳定性和 previously-passing 行为损坏数。
- [ ] provider input/output/cache/reasoning token、请求数、重试；unknown 不记零。
- [ ] 全文写入、局部参数、候选结果、unchanged rewrite 字节和 schema 固定成本。
- [ ] no-match/ambiguous/no-change/stale、各 matcher 触发、失败后成功率、额外 read/LLM 请求。
- [ ] 错位置写入、歧义误放行、stale overwrite 和未报告部分写入，目标为零。

### 12.3 选择 S

- [ ] 先比较官方最终通过数、全通过率、回归和稳定性；正确率不下降后才比较全任务 token。
- [ ] 若 C 更稳定但 token 略增，可按“正确率优先”选择 C。
- [ ] 若 C 只增加重试且没有减少误写，选择 B；必要时另测只降级 `block_anchor`，不得事后挑选样本。
- [ ] 不用单个任务、单次最好结果或“patch 文本更短”代替全任务累计数据。
- [ ] 冻结选中的工具模式为 `S_SHA`，明确 S 是 B 还是 C；证据不足时结论为未确定，不进入 D 的收益结论。

**完成条件：**A/B/C 的全部有效 run 可追溯且结论遵守正确率优先；得到明确 S 或明确停止理由。

## 13. Milestone M9：D 的 existing codegen patch 协议

**依赖：**M8 已冻结 S。**对应：**H05h。**目标：**只在无工具的 existing implement/repair
路径实验 patch，不改变 fresh app 和新文件完整生成。

- [ ] 从 `S_SHA` 创建独立 D 实验提交/分支；工具模式代码、matcher 和结果格式不再变化。
- [ ] 明确 eligibility：existing app 的 implement/repair、相关当前源文件完整可见、未超上下文预算时才允许 patch。
- [ ] fresh app、新文件、tiny 新页面和明确整体重建继续使用现有完整 `<<<FILE>>>` 协议。
- [ ] 为 Python 与 Rust 定义同一 patch grammar、路径规则、换行规则、重复文件规则和错误码；不要两边各自“近似实现”。
- [ ] patch 只引用本轮完整可见的当前版本，并带可校验版本/digest；文件变化后拒绝，不在近似位置猜测。
- [ ] 一次回复的所有 patch 先完成解析、路径 confinement、版本、唯一定位、重叠和 no-op 验证，再开始落盘。
- [ ] 任一 hunk 不确定时本轮零写入；写入阶段 I/O 仍可能部分失败时必须回滚或精确报告受影响文件，不能宣称事务成功。
- [ ] 新文件仍走完整 file block；若允许一轮混合新文件和 patch，先冻结全部计划并验证，失败不能留下未报告的半套结果。
- [ ] 解析/匹配失败只允许一次有界 fallback，计入请求和 token；fallback 使用现有完整文件或工具模式，不无限切换协议。
- [ ] 保留 `drop_unseen_rewrites`/`sources_fit` 的安全门槛；patch 不能成为绕过“未见源文件禁止覆盖”的后门。
- [ ] no-op、formatter/确定性 repair、manifest 写入、protected path、path traversal 和重复 block 继续遵守现有规则。
- [ ] Python `arc/tests/test_codegen.py` 与 Rust `octos-arc` 使用同一组 golden cases，验证成功、失败和磁盘结果一致。
- [ ] 记录 patch 输出字节、完整文件 fallback 字节、解析失败、重试和最终实际 diff；不只统计 patch 自身长度。
- [ ] 本地提交并冻结 `D_SHA`、二进制哈希和协议版本；D 尚未通过官方实验前默认关闭。

**完成条件：**D 在 eligible existing 场景可确定性应用，所有不确定情况失败关闭；fresh/new file 与 S 等价，Python/Rust 行为一致。

## 14. Milestone M10：固定官方任务 S/D 对照

- [ ] 复用 M8 的固定任务、模型、预算、重复次数和隔离方式；唯一变量是 existing codegen patch。
- [ ] 只用 `S_SHA` 与 `D_SHA` 比较，不用 A 作为 D 的直接对照。
- [ ] 同时覆盖 fresh、existing implement、existing repair、未完整引用源码、patch 解析失败和 fallback 场景。
- [ ] 记录最终正确率、回归、稳定性、总 token、codegen 输出字节、fallback 请求和跨节点旧功能损坏。
- [ ] 验证 fresh/new file 没有因 D 改变协议或增加固定输入。
- [ ] 任何错误位置应用、未报告部分写入、绕过完整可见门槛或 Python/Rust 分歧都直接否决 D。
- [ ] 只有最终通过表现不下降且全任务 token 更低，才采用 D；仅 patch 文本更短不构成采用依据。
- [ ] 保存逐 run manifest、原始官方报告和聚合结果；失败样本不得删除或改记为基础设施故障。

**完成条件：**S/D 结论可追溯；明确采用 D、保留 S，或因证据不足继续保持 D 默认关闭。

## 15. Milestone M11：采用、最新主线集成与回滚

- [ ] 汇总最终采用项：B 或 C；D 独立决定。未采用实验不能作为默认行为残留。
- [ ] 重新拉取最新 `origin/main`，在不改写冻结 SHA 的前提下集成选中实现，记录 `INTEGRATION_SHA`。
- [ ] 核对与最新 H01-H04、H06/H07、tool policy、formatter、AppUI diff 和 codegen 双入口的组合。
- [ ] 若集成改变 matcher、prompt、schema、预算或 codegen eligibility，重跑对应对照；旧实验不能自动证明新组合。
- [ ] 提供独立回滚：关闭 strict 只退回 B，关闭 codegen patch 只退回 S，关闭 H05 core 退回 A；均不关闭 H02 写保护。
- [ ] 删除未采用且无维护价值的实验死代码；保留实验记录和失败原因。
- [ ] 更新已有优化总表/行为文档中的实际默认值和结论，不创建无必要的平行说明。
- [ ] 跑受影响全量测试、格式、Clippy、Python tests 和官方 smoke，区分基线失败与新增失败。
- [ ] 每个 Milestone 的代码和分析证据分别本地提交，记录 SHA；远程推送仍等待用户指令。

**完成条件：**选中方案在最新主线上满足正确率、安全和 token 门槛；各层开关能独立回滚，且不会撤销 H02/H03 的既有保护。

## 16. 测试、提交和交接要求

### 16.1 候选验证命令

先用 `-- --list` 或测试文件清单确认过滤器确实命中；零测试不能算通过。

```bash
cargo test -p octos-agent --lib edit_file
cargo test -p octos-agent --lib replacer
cargo test -p octos-agent --lib diff_edit
cargo test -p octos-agent --lib mutation_guard
cargo test -p octos-agent --lib write_file
cargo test -p octos-agent --lib format
cargo test -p octos-agent --test h02_m1_file_versions
cargo test -p octos-agent --test h02_m2_read_receipts
cargo test -p octos-agent --test h02_m3_receipt_lifecycle
cargo test -p octos-agent --test h03_m1_output
cargo test -p octos-agent --test h03_m3_file_pages
cargo test -p octos-cli --lib appui_prompt_context_bridge
cargo test -p octos-cli --test mcp_serve_integration
cargo test -p octos-arc
cd arc
python3 -m unittest discover -s tests -p 'test_codegen.py'
cd ..
cargo fmt --all -- --check
cargo clippy -p octos-agent -p octos-cli -p octos-arc --all-targets -- -D warnings
git diff --check
```

新增 H05 的真实 stdio + fake provider 测试必须写入证据，不能用工具单测代替。若修改
spawn/fleet、MCP 或 UI metadata，再增加对应 crate 的专项回归。全量测试遇到 macOS 沙箱、
文件锁或 TTY 时序问题时，先在 `A_SHA` 复现；能复现才可标为基线波动。

### 16.2 每个 Milestone 的本地提交

- [ ] 一个 commit 只完成一个可验证 Milestone，或一个为保持绿色所需的更小切片。
- [ ] 提交信息写实际行为，例如“为编辑失败返回当前候选位置”“避免无变化编辑写盘”“支持偏移后的唯一 diff 上下文”，不只写内部编号。
- [ ] 提交前运行相关专项测试、`cargo fmt --all -- --check` 和 `git diff --check`。
- [ ] 不提交真实凭据、大模型原始密钥、临时工作区、无界日志或与 H05 无关的格式化变化。
- [ ] 分析仓库中的验证记录与代码仓库提交分开；不推送远程。

### 16.3 每个 Milestone 的交接格式

- [ ] 用通俗中文列出完成行为、未完成项和没有做的范围。
- [ ] 列出修改文件、关键入口、依赖 SHA、功能开关及实际默认值。
- [ ] 列出准确命令、通过/失败/跳过数量和退出码；基线失败与新增失败分开。
- [ ] 列出证据路径、代码 commit、分析 commit、工作树状态和下一 Milestone 起点。
- [ ] 没有自动化证据的项目不勾选；发现设计假设错误时先更新本清单，再实施等价安全方案。

后续 agent 不应为了赶进度把 M1-M7 压成一次大改。B、C、D 的价值只有在变量隔离后才能判断；
正确率没有守住时，token 更低也不能采用。
