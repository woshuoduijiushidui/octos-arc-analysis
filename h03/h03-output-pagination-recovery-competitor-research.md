# H03 竞品调研：统一分页、截断与原文恢复

- 调研日期：2026-09-20
- 优化表原分析基线：`c599d18c5acd2b846f049ffea2be84e72fe60fac`
- 本次拉取并复核的 Octos 主线：`27d057c206c0f8250b60309905737f7e26ee0ba9`
- H02 实现复核：B 冻结 `73f5b1bf695af37167fcb47541726bcb24807102`；当前 C 分支 `feat/safe-file-cache-retained-receipts`，提交 `7eaa136ef086a2f9728794d17d8f150482df03d1`
- 调研对象：Anthropic Claude Code、OpenAI Codex、DeepSeek Harness
- 范围：只做源码与官方文档调研；未修改运行代码，未运行付费模型或官方任务实验。本文沿用 [H01 调研](../h01/h01-context-evidence-competitor-research.md) 的组织方式。

## 结论先行

H03 建议**调整后采用**。核心不是把文件页调大或调小，而是建立一个贯穿工具执行到模型请求的约定：

> **返回的范围必须等于模型实际看到的范围；省略的内容必须有明确、可用的恢复方式，无法恢复时必须如实说明。**

适合 Octos 的组合是：

1. 借鉴 **Codex 的统一预算与元数据预留**：正文、行号、退出状态、截断说明和恢复参数共同占用预算，历史层不能再盲切已经生成的页。
2. 借鉴 **Claude Code 的部分视图提示与日志文件引用**：明确告知模型拿到的只是文件的一部分；大日志先保存，再返回短视图。但不能照搬其失败日志不一定附带文件路径的行为。
3. 借鉴 **DeepSeek 的实际范围续读、预留恢复提示空间、读取结果避免再次外置**：同时补足它的单行截断缺少字节续读、部分原文存储有上限等边界。
4. 复用 Octos 已有的 `read_window`、`ToolOutputEnvelope`、artifact、`recall` 和 H02 读取凭据，不另建一套无关系统。

首要落点是 **stdio 工具模式的端到端输出链路**。先让一页完整到达模型，再让文件中间、日志尾部和旧工具结果都能按需找回。无需为此新增模型摘要调用，也不改变“固定需求 → 按节点生成或修改 → 官方测试 → 修复”的外层流程。

目前没有找到三家在相同 ARC 任务、模型、预算下独立验证 H03 收益的公开对照数据。下文的通过率与 token 收益均为待测假设；**最终通过数与稳定性优先，总 token 次之，耗时不计入成绩**。

## 1. H03 到底解决什么问题

H03 处理的是：**文件或工具结果很长，模型只收到一部分时，怎样知道缺了什么，以及怎样拿到缺失部分。**

需要区分三种操作：

| 操作 | 含义 | 恢复要求 |
| --- | --- | --- |
| 分页 | 本次有意只给一个连续范围 | 下一次从实际返回范围之后继续，不能漏读 |
| 截断 | 某层删除了部分正文，例如只留首尾 | 标出缺口；不能把两端拼接后称为连续全文 |
| 历史压缩 | 已经进入过模型上下文的结果被短文本替换 | 保留能定位原结果的引用；恢复结果还要满足分页预算 |

边界如下：

- H01 负责压缩后保留需求、失败和进展；它不能重新创造早已被丢弃的日志。
- H02 负责文件版本、模型可见凭据和写入保护；它不能单靠“禁止错误缓存命中”让模型看见缺失正文。
- H05 负责已有代码的局部修改策略；H03 提供可靠的读取材料，不要求所有修改前都把整个文件翻完。
- H08 负责任务与模型输出预算；模型生成代码时输出被截断，不属于本次工具结果分页的直接范围。
- 官方需求、测试内容和判分规则保持固定。不能通过隐藏失败日志、跳过测试或缩短官方测试来制造收益。

相邻的 `agentic-requirement-compiler` 展示需求编译思想，hackathon 仓库提供课程和实验背景；它们不是本次替换的运行内核。Octos 当前 Python Flow 经 `octos serve --stdio --solo` 驱动工具模式，默认 `OCTOS_SESSION_SCOPE=turn`。因此 H03 首先影响一个工具 turn 内的调查和修复，不应直接推断所有 Tiny/codegen 请求都会获益。流程背景见 [仓库导读](../repository-walkthrough-zh.md) 与 [优化范围说明](../harness-optimization-zh.md)。

## 2. Octos 当前已经有什么

### 2.1 先区分旧分析、最新主线与 H02 分支

本次同时读取了最新 `origin/main` 和当前 H02 C 分支。下列关键文件在旧基线 `c599d18c` 与最新主线 `27d057c2` **内容相同**：`read_window.rs`、`recall.rs`、`utils.rs`、`context_manager.rs`、`shell.rs`、`runtime/profile.rs`。因此优化表提出的主要 H03 问题仍成立。

H02 分支已经实现强版本检查、最终 prompt 凭据确认、任务/分支隔离，以及可选的压缩后凭据保留。不能再把这些写成尚未开发的 H03 功能。它们还未因此自动成为最新主线的能力。

尤其是 H02 会在输出被改写、来源消失或投影不匹配时拒绝激活/保留凭据，见 [凭据确认逻辑][o-receipts] 和 [M7 验证记录](../h02/h02-m7-implementation-verification.md)。这能阻止“未看全却命中全文缓存”，但**仍可能导致模型反复读取同一份被截断的正文**；H03 正是补后半段。

### 2.2 文件页只适配了执行层，尚未适配最终模型视图

已有 `read_window` 能按行分页，也能对超长单行按字节读取：

- `OCTOS_READ_WINDOW=1` 开启，默认关闭；
- 单页正文最多 2,000 行、48 KiB 格式化字节；
- 额外预留 400 字节放实际范围和续读说明；
- 已有测试确保 `48 KiB + 400 ≤ read_file` 的 50,000 字节执行层上限。

这些是可复用基础，见 [窗口约定和常量][o-window]。但它只证明页能穿过 50,000 字节上限，没证明它能完整进入 stdio 的 8 KiB 模型视图。

| 层级 | 当前行为 | H03 的问题 |
| --- | --- | --- |
| `read_file` 未开启窗口 | 不带范围且文件超过约 50,000 字节时，先返回缩小范围提示；显式范围仍可能走 100,000 字节首部截断 | 不能笼统写成“所有大文件都返回 100KB”；范围读取仍有丢内容风险 |
| `read_file` 开启窗口 | 48 KiB 格式化正文 + footer，实际行/字节范围可续读 | 页大于后续模型可见限制 |
| 通用执行层 | `read_file` 50,000；`shell` 30,000；默认工具 50,000 字节，首尾裁剪后可能追加恢复提示 | 追加提示并未统一计入后续层预算 |
| stdio `ContextManager` | 默认取前 8 KiB，再追加 `[truncated]` | 页尾范围、续读参数、错误尾部可能全部消失 |
| prompt 压力处理 | 超过当前 prompt 预算时还可能进一步缩短工具消息 | 单工具页适配 8 KiB，也不能忽略整批结果和上下文压力 |

依据：[无界读取提示与范围输出][o-read]、[执行层上限][o-limits]、[执行层裁剪][o-execution]、[ContextManager 记录结果][o-envelope]、[压力裁剪][o-pressure]。

这里的 8 KiB、50,000 字节都是实现中的字节预算，不是 tokenizer 测出的 token 数；`[truncated]` 等追加文字还会使最终字符串略超对应正文阈值。UI 的 512 字节预览也不是模型实际输入，不能拿 UI 展开效果证明模型已经看全。

一个静态反例：开启窗口后，工具返回一页接近 48 KiB 的文件内容，并在页尾给出续读参数；ContextManager 仅保留约 8 KiB 开头。模型没有看到这一页的大部分内容，页尾说明也没到达。这是由上述裁剪顺序推导的反例，不是本次新跑出的 ARC 失败记录。

### 2.3 续读位置有时来自请求范围，而非实际可见范围

窗口路径在工具内部用 `included_end + 1` 产生续读位置，这个方向正确。但通用 `truncation_recovery` 在同时拿到 `offset` 和 `limit` 时，建议从 `start + limit` 继续，见 [恢复提示实现][o-read-recovery]。

若请求 1–1,000 行，执行层只保留首尾，下一次直接从 1,001 行继续，就跳过了本次中间被删除的内容。即便这条建议在执行层成立，后续 8 KiB 裁剪也会使它失真。

因此不能只修提示文案：**下一页位置必须由最终可见范围计算，不能由请求参数推算。**

### 2.4 artifact 保存得太晚，不能证明持有原始输出

ContextManager 会计算 `raw_sha256`，并为过大输出保存内容寻址 artifact。这比直接丢掉整个工具结果好，但其中 `raw_output` 指的是**传到 ContextManager 的字符串**。

在这之前：

- `shell` 已把 stdout 和 stderr 组合后截到约 50,000 字节，再追加退出码；
- 通用执行层又会对 `shell` 做 30,000 字节首尾裁剪；
- 脱敏/清洗也可能改写正文；
- 文件范围输出也可能已经经历自己的截断。

见 [shell 输出处理][o-shell] 与 [执行层裁剪][o-execution]。因此一个 artifact 可以完整保存“执行层之后的结果”，却不包含原始进程日志的全部内容。**哈希只能证明保存了哪份内容，不能证明更早的内容没有丢失。**

退出码虽然在 shell 内部预留了空间，仍可能被后面的首部 8 KiB 裁剪去掉。对 ARC 来说，失败末尾的断言、堆栈和退出状态比大量成功日志更重要，不能只保证第一层没有切掉它们。

### 2.5 `recall` 已存在，但恢复链路还不完整

已有 `RecallTool(tool_call_id, page)`，按 UTF-8 边界和换行分页；默认按通用 50,000 字节上限减去 512 字节预留正文预算。它从账本找旧输出，不重新执行命令，见 [recall][o-recall]。

仍有四个缺口：

1. **入口**：`RecallTool` 的生产注册位于 `session_actor`；stdio/solo 的 12 工具白名单不包含它。不能因为某个交互入口可用，就声称 ARC 已有恢复工具，见 [注册位置][o-recall-register]、[stdio 白名单][o-profile]。OUP 的 per-turn Agent 独立接入 ContextManager bridge，见 [实际 bridge][o-bridge]。
2. **页大小**：`recall` 的约 50KB 页进入默认 ContextManager 后还会被截到约 8 KiB；单测里“页小于工具上限”不等于“恢复内容完整送到模型”。
3. **冷恢复**：同进程 `recall_index` 可跨压缩保留；但 `from_snapshot` 将 artifact map 和 `recall_index` 初始化为空，[快照恢复][o-snapshot]。`fetch` 先查 index，[账本读取][o-fetch]。仅凭 artifact 已写到磁盘，不能承诺重启后可恢复；在快照直接加载且没有重新登记结果的路径，甚至会查无此 ID，而不只是返回短视图。
4. **引用身份**：当前 index 对相同 call ID 使用最新记录覆盖。跨 turn 重复 ID 时，仅凭 call ID 不足以精确定位旧证据；应增加不可变结果身份，兼容旧参数但对歧义明确报错。

这些问题在 H03 内可以集中处理，无需重新设计需求编排或整个上下文系统。

## 3. 竞品版本与证据边界

| 竞品 | 固定版本 | 可审计范围 | 本次重点 |
| --- | --- | --- | --- |
| Claude Code | [`7974a707`](https://github.com/anthropics/claude-code/tree/7974a70773fa229e4cc65aa1b356cc21f5c216c4)，2026-09-20 | 官方文档、CHANGELOG、插件；CLI 核心未公开 | Read 部分视图、Bash 输出文件、不同失败路径 |
| OpenAI Codex | [`5c5308fc`](https://github.com/openai/codex/commit/5c5308fc9a9ee789049d646ef11e5400384b9c6f)，2026-09-20 | 公开 Rust 实现及测试 | 请求/策略预算协调、历史层避免二次截断、进程缓冲边界 |
| DeepSeek Harness | [`ddefc45f`](https://github.com/deepseek-ai/deepseek-harness/commit/ddefc45fbc7f8e46dd73185e68295696d1297887)，`0.1.6-alpha.2` | 公开 TypeScript 实现、默认组合及测试；developer preview | 文件窗口、流输出保存、通用 spill、历史裁剪 |

Claude Code 的 [README][cc-readme] 将该仓库定位为产品入口和插件集合，不能把文档行为写成已公开的内部算法。本文对 `code.claude.com` 的结论来自 2026-09-20 可见的滚动文档，不声称它与 GitHub commit 完全同步。

所有“默认”均限定在所查执行路径和配置上。CLI 文本结果、程序化工具返回、UI 展示和持久日志可能使用不同预算；下文不会把其中一条路径的保证扩展到全部入口。

## 4. 三家怎么做

### 4.1 Claude Code：部分视图可以继续读，日志恢复要区分成功与失败

**文件读取。** 官方 [Read 行为][cc-tools-read] 说明：

- 整文件读取超过 token 限制时，返回第一页和 `PARTIAL view` 提示，说明读到多少、怎样用 `offset/limit` 继续；
- 显式指定 `offset` 或 `limit` 后仍超过限制，则返回错误，要求缩小范围；
- 显式 `limit` 的范围已经大到不可能装下时，会提前停止，避免把剩余范围全装入内存；
- 空文件和越过 EOF 有不同提示；单行过长时建议搜索具体内容。

CHANGELOG 也记录了从“大文件硬错误”改为“返回带部分视图提示的第一页”，见 [变更记录][cc-partial]。这是很适合 Octos 的交互原则：默认先给有用内容，范围不足时说清楚。但文档没有承诺单行内部可无损逐字节翻页。

**命令输出。** 当前官方 [Bash 输出限制][cc-tools-bash] 比“长输出都会保存原文”更复杂：

| 情况 | 文档描述的行为 | 对 Octos 的含义 |
| --- | --- | --- |
| 命令运行中 | 输出流写入工作文件；超过 5 GB 会终止命令 | 支持较早捕获输出，但不是无限保留 |
| 认定为有效的结果 | 默认约 30,000 字符以内内联；更大时返回文件路径和最多约 2,000 字符预览，保存文件超过 64 MiB 会截断 | 可以按需读取/搜索；文件引用仍需标注是否完整 |
| 认定为失败的结果 | 约 10,000 字符以内内联；更大时从读回窗口取首尾，**不附文件路径** | 不适合直接用于 ARC 失败修复 |
| 后台任务 | 返回任务 ID 与输出文件路径，支持后续读取 | 应区分“读新输出”与“回看同次运行的旧输出” |

`BASH_MAX_OUTPUT_LENGTH` 控制读回窗口，`bashOutputMaxChars` 在支持版本中控制内联上限及读回窗口；两者不等同于原始输出保存量。退出码 1 是否算有效还依赖命令类型，例如 `grep` 无匹配可以算有效，不能拿这种分类代替官方测试的通过/失败。

通用工具结果的历史 CHANGELOG 确实写过“长结果落盘，提供文件引用”，后来又加入已保存结果的容量上限和截断提示，见 [落盘变更][cc-persist]、[保存上限变更][cc-storage-cap]。这些不能覆盖掉当前 Bash 文档的更具体限制。

**存储与寿命。** 官方目录文档列出 session JSONL 和 `projects/<project>/<session>/tool-results/`，并说明它们受默认 30 天的启动清理影响，见 [应用数据][cc-directory]。存盘是恢复基础，不是永久有效承诺。

**效果证据与迁移判断。** 可核实的是产品行为及相关修复，没有可比 ARC A/B 数据。采用“第一页 + 明确部分状态 + 文件引用”的原则；不复制字符阈值、失败日志不提供路径、跨项目目录与清理周期。

### 4.2 OpenAI Codex：同一个输出预算贯穿渲染与历史层

固定版本的 core tools 主要通过 shell 工具读取文件，见 [工具注册][cx-tools]。本次没有发现默认路径中的独立 `Read` 行分页器；`sed/rg` 等命令选取什么范围仍由调用决定，不能将它写成统一文件游标协议。

**预算协调是最值得迁移的实现。**

`ExecCommandToolOutput` 分开保存输出、退出码、进程 ID、原始 token 估算和采集阶段遗漏字节。模型可见输出按以下顺序生成，见 [输出渲染][cx-output]：

1. 取调用者 `max_output_tokens` 与模型/配置截断策略中较小的预算。
2. 先生成状态头：chunk、退出码或仍运行的 session ID、原始 token 估算。
3. 从历史层的序列化预算中扣掉状态头和分隔文字。
4. 从同一份采集结果重新生成有界正文；若标记和警告使它超限，继续减小正文预算。
5. 历史层使用对应预算处理完整结果，避免把已经截断过的正文再切一次。

这里有明确的源码注释说明“预留元数据、警告和截断标记，避免历史层二次截断”。[历史记录逻辑][cx-history] 还支持随结果保存历史截断预算覆盖值；[公共工具函数][cx-truncation] 中序列化余量当前为 20%。20% 是产品实现参数，不是 Octos 应直接采用的常数。

首尾裁剪按 UTF-8 边界进行，保留省略标记；token 估算以约 4 字节/token 换算，见 [字符串裁剪][cx-string]。这种换算不能当成真实 provider 用量，中文、压缩代码等应另行测量。

**恢复能力有明确上限。**

`exec_command`/`write_stdin` 支持分批读取仍运行的进程，默认请求输出预算 10,000 token。与此同时，采集缓冲 `HeadTailBuffer` 上限是 1 MiB，保留首尾并丢掉中间，见 [默认参数][cx-exec-defaults]、[缓冲实现][cx-buffer]。

`write_stdin` 读取的是会被取走的缓冲和后续新输出，见 [缓冲消费][cx-drain]。它不是对历史输出任意偏移的读取工具；重复轮询不能恢复之前已丢弃的中间部分。原始 token 数、chunk ID、甚至独立日志视图，也不能自动证明拥有可供模型恢复的完整原文。

**测试证据。** [策略上限测试][cx-budget-test] 让模型请求远大于 policy 的输出，并检查结果只有一次 token 截断标记；[大输出测试][cx-large-test] 检查首尾和采集遗漏标记仍可见。这是机制正确性证据，不是任务通过率收益证据。

**对 Octos 的价值。** 直接借鉴预算合并、元数据预留、从原始材料重新渲染和按入口区分日志/模型视图。不能仅复制首尾截断或轮询协议，就声称 H03 的原文恢复已经完成。

### 4.3 DeepSeek Harness：文件窗口与两类输出保存分工明确

默认 base 组合挂载文件工具、subprocess、shell、spill 和工具结果裁剪器，见 [默认组合][ds-base]。需要区分文件读取、进程输出和通用工具结果三条路径。

**文件读取：按实际末行继续，但长行仍有损失。**

`read(file_path, offset, limit)` 使用 1-based offset，默认/最大 2,000 行；默认单行最多 2,000 个 JS 字符单位，正文最多 50 KiB，见 [read][ds-read]、[窗口构建][ds-render]。

窗口返回带行号的行数组和总行数，footer 根据实际 `endLine + 1` 续读。文件达到 10 MiB 或大小未知时走流式读取，并限制单行缓冲；不过为获得精确总行数，窗口装满后仍扫描后续输入。这是有界内存设计，不等于只读取当前页的磁盘 I/O。

它有两个不适合照搬的边界：

- 单行超限会直接截掉尾部；`offset/limit` 只能跳到另一行，没有字节游标可以取回这一行的后半段。即便 footer 表示到了 EOF，也不代表每行字节完整。
- `maxBytes` 主要统计选中行的文本与换行，最终行号、路径标签和 footer 另行渲染。不能将 50 KiB 解释为整个模型可见结果的严格总上限。

[窗口测试][ds-read-tests] 覆盖范围、CRLF、超长行、字节上限、空文件、EOF 和流分块一致性。这证明其声明的窗口行为，不证明完整文件可无损恢复。

**进程输出：在采集层保存，比通用 spill 更早。**

本地 shell 执行器把 stdout/stderr 的采集预算交给 subprocess，每流内存默认 64,000 字节，并配置默认 64 MiB 的 spill 上限，见 [bash-local][ds-bash-local]。这是本地执行器默认值，实际组合可覆盖。

模型看到保留的输出尾部、退出状态，以及：

```text
[output truncated; full output: <path-or-(unavailable)>]
```

后台增量读取也会报告内存丢失与相应 stream 路径，见 [Bash 渲染][ds-bash-render]。因此 DeepSeek 并非只有工具返回后的通用保存器；进程层已有较早的保存能力。但存储上限、后端失败仍可能使完整路径不可用，不能把模板中的 “full output” 当成无条件保证。

**通用 spill：保存最终格式化结果，并将恢复提示算进预算。**

默认 base 的 `maxInlineBytes=50000`。普通纯文本工具结果超过阈值时：

1. 用 session owner、工具名和 call ID 保存完整的最终格式化文本；
2. 先按最大遗漏量估算恢复提示的字节数，为路径、提示和分隔符留空间；
3. 用余下预算生成首尾预览；
4. 只有整个替代结果不超预算时才安装；保存失败或提示本身装不下，则保留原内联结果。

见 [spill 实现][ds-spill]。此策略只缩短模型视图，不改程序化结果；混合图片等非纯文本结果、部分替换决策和嵌套调用另有处理。

特别值得借鉴的是：**模型侧 `read` 结果跳过通用 spill，避免“读外置文件 → 结果又被外置 → 再读”的循环。** 文件工具自己承担窗口限制。这不是无限豁免所有后续预算，尤其不能把它理解为会阻止历史压缩。

通用 spill 只能保存它收到的最终文本。更早被 provider 删除的正文，以及文件工具已经截掉的长行，不能在这里补回。这个边界在 [spill README][ds-spill-doc] 中明确说明；不能与 shell 的采集层保存混为一谈。

**历史压力：进一步裁剪，但不等于完整恢复协议。**

后续 pruner 默认对超过 8,192 Unicode code points 的工具文本保留头部 4,096、尾部 1,024 和标记，并以新事件替换模型视图、引用旧事件，见 [pruner][ds-pruner]。append-only log 能保留该阶段的旧内容，但旧内容可能已经是窗口或 spill 预览；也不能保证任意长度的恢复提示都能留在尾部 1,024 字符内。

本地 spill 返回路径，默认目录在临时区域，普通 `read/grep` 必须能访问。其文档明确保留了“工作区限制怎样允许访问外部 spill 路径”的适配问题，见 [存储边界][ds-local]。Octos 本机严格沙箱曾经影响读取与执行，不能假设给模型一个 `/tmp` 路径就能找回内容。

**效果证据与迁移判断。** [spill 预算及读取豁免测试][ds-spill-tests] 与 [保存失败测试][ds-spill-failure-tests] 覆盖预算内替代、`read` 豁免、保存失败与小预算降级；没有可比 ARC 收益数据。采用实际范围、提示预留、早期输出保存和分层职责；不采用有损长行截断作为无损读取方案，也不复制插件框架与固定阈值。

## 5. 横向对比

| 问题 | Claude Code | Codex | DeepSeek Harness | Octos 建议 |
| --- | --- | --- | --- | --- |
| 大文件首次读取 | 部分页 + `PARTIAL view`；显式范围超限报错 | 默认主要靠 shell 选取范围 | 行窗口 + 实际末行续读 | 自动返回预算内的有用页，标明真实范围 |
| 超长单行 | 过大范围报错并建议搜索，未见无损字节游标承诺 | 依赖命令；输出仍会截断 | 每行截短，行分页无法找回尾部 | 复用 Octos 已有 UTF-8 字节分页 |
| 多层输出预算 | 文档区分内联、读回、存储；核心算法未知 | 模型/配置取较小值，预留状态头，协调历史预算 | 文件自分页；spill 为提示预留预算；pruner 再缩短历史 | 同一预算协议贯穿当前页与最终 prompt |
| 日志中间与末尾 | 有效大结果可找文件；失败结果不一定有路径 | 首尾缓冲有损；轮询不等于历史恢复 | 进程流可保存，通用结果也可 spill | 第一次有损裁剪前保存，成功/失败都适用 |
| 恢复提示怎样保留 | 部分视图、路径和格式提示 | 状态头独立预留；不提供通用原文游标 | spill notice 计入预算，`read` 避免再次 spill | typed 元数据，任何缩短都保留可用引用 |
| 原文是否永久完整 | 否，工具/存储有上限且有清理 | 否，采集层有中间遗漏 | 否，长行/stream cap/存储失败均有限制 | 明确 complete、partial、missing、expired 等状态 |
| 再读是否重复执行命令 | 可从文件读；依路径可用性 | `write_stdin` 继续同一进程；不能回溯已消费输出 | 文件读取或 job 增量读取 | 历史 artifact 恢复不触发命令重跑 |
| 迁移结论 | 调整后采用部分视图与文件引用 | 采用预算协调，不照搬有损缓冲作恢复 | 调整后采用窗口/spill 分工 | 组合机制，服从已有 ARC 流程 |

共同启示是：**存储预算、单次可见预算和历史上下文预算是三件事。** 只有三者之间的范围、状态和引用能够接上，减少正文才可能减少无效重读。

## 6. 适合 Octos 的目标设计

以下是调研建议，不是已经实现的协议或本次新增的实施计划。

```mermaid
flowchart LR
    A[文件稳定版本 / 进程输出流] --> B[保留可恢复原文及完整性状态]
    B --> C[按实际入口预算选择连续页或日志片段]
    C --> D[正文 + 状态 + 实际范围 + 恢复参数]
    D --> E[最终 prompt 校验]
    E --> F[模型]
    E --> G[H02 可见凭据确认]
    F -->|下一页或定位失败片段| H[读取同一版本或同一次输出]
    H --> C
    E -->|预算变化| C
```

### 6.1 统一“原文、当前视图、恢复方式”的描述

建议扩展已有 `ToolOutputEnvelope`，让三类信息各有明确归属：

| 信息 | 最小内容 | 用途 |
| --- | --- | --- |
| 原文身份 | task/session/branch owner、不可变 output ID、源类型、哈希或文件版本 | 找到同一次输出，避免重复 call ID 串记录 |
| 当前视图 | 连续范围或片段列表、单位、是否变换、是否完整、实际可见字节 | 说明模型究竟收到了什么 |
| 恢复方式 | artifact 引用或带版本的文件游标、下一位置、恢复状态 | 找回缺失内容，或明确解释不能恢复 |
| 运行状态 | exit code、signal、timeout、仍在运行标记 | 不让日志截断改变对执行结果的判断 |

建议固定行号为 1-based、包含末行；字节范围为 0-based、右端不包含。正文中的行号和省略标记不计入源文件覆盖，但计入传输预算。空文件、选定范围读完和整个文件读完必须分开。

无需让模型每次看全部内部字段。模型可以只看到短头部，例如“本次为部分视图，文件版本 X，第 81–140 行，下次从 141 继续”；完整 provenance 留在运行记录中。内部字段应来自工具运行时，不从日志里碰巧出现的同名文字推断。

### 6.2 从下游预算反推页大小

每页预算需要满足：

```text
格式化正文 + 状态 + 范围 + 恢复提示
    <= min(工具执行层上限, 入口单结果上限, 当前 prompt 分配给该结果的额度)
```

其中：

- 字节限制检查最终 UTF-8 文本；token 限制使用项目选定估算器，并在 provider 请求口观测实际用量。
- 多个并行工具不能各自占满“当前剩余预算”；prompt builder 需要考虑整批结果。
- 先为不可缺少的元数据预留空间，再选择正文。路径过长时用短 ID，不让提示文字反过来挤爆预算。
- 下游需要进一步减量时，从原文和范围元数据重新生成更小视图；不要对已有页字符串再调用一次无差别首部/首尾截断。
- 如果最低限度的状态和恢复引用都放不下，应先触发已有压缩，或返回明确预算不足状态；不能反复返回同一个没有进展的游标。

这不要求首版做复杂的自动调参。可以先固定 stdio 的有效单页预算，完成真正端到端的保证，再校准大页策略。单纯把 48 KiB 改成 8 KiB 仍不够，因为还有行号、提示、清洗和上下文压力。

### 6.3 文件使用连续页，日志可以使用有标记的片段

**文件。** 优先接受模型指定的相关行范围；无范围且文件大时给有用的第一页。续读位置来自最终返回末行。单行超预算时转入已有字节模式，保持 UTF-8 边界和严格前进，不能把一行截短后直接跳到下一行。

文件在页间发生变化时，旧游标应得到 `stale`，重新定位或读取新版本。若需要回看旧版本，则明确读旧快照，不能把不同版本的页拼成“完整文件”。CRLF 归一化、行号装饰、脱敏和二进制转文本都要区分源字节与展示字节；无法准确映射时不声明无损覆盖。

**日志。** 先保留退出状态、错误位置和恢复引用，再选择首尾或错误附近的片段。若分段展示，必须分别标明范围和中间缺口，不能伪装成连续日志。

日志搜索应支持“在这一个 output ID 中查找错误，然后读其附近”，以减少逐页翻阅。首版可复用已授权的文件搜索能力；若 artifact 不通过普通文件路径暴露，再为账本读取加有界搜索。测试 ID、expected/actual 的可信提取仍沿用 H01/runner 边界，不在通用截断器里猜哪行代表测试通过。

### 6.4 在首次有损裁剪前保存，并声明保存到哪里为止

文件读取应持有稳定版本或恢复快照；shell 的 stdout/stderr 应在采集阶段写入有界存储，同时维护小型可见预览。仅在 ContextManager 收到字符串后另存，无法修复更早的损失。

完整性至少区分：

- `complete`：声明的那次输出或源范围已完整保存；
- `partial`：源/provider/存储上限已造成损失，记录已知缺口和原因；
- `running`：输出尚未结束，可读取到一个已发布的偏移；
- `missing/expired`：引用不存在或已清理；
- `store_failed`：写入失败，未形成可用引用。

只有保存完成并发布后才能向模型承诺可恢复。超出容量时保留多少、是否终止采集，应遵守已有执行约定；不能为了实现恢复无界占内存或磁盘。

保存失败时，若完整内容仍能放入真实 prompt，保留它；否则返回有界诊断并明确 `recoverable=false`，保留真实 exit/timeout 状态。不要虚构文件路径，也不要为“补日志”自动重跑可能已经产生副作用的命令。

恢复必须遵守现有清洗/脱敏规则。审计原始字节与可交给模型的恢复正文可以分开存储；页不能绕过原有处理。对经过变换的内容，不能登记为原始文件全文覆盖。

### 6.5 扩展已有 `recall`，打通实际入口和冷恢复

优先沿用现有账本与工具，只补必要能力：

- 新引用绑定不可变结果 ID；旧 `tool_call_id` 参数在唯一匹配时兼容，歧义时报错。
- 使用源范围/游标定位，避免“页大小改变后 page=2 指向不同内容”。保留旧 page 参数时必须绑定同一分页策略。
- 恢复页使用与 `read_file` 相同的最终可见预算，且不再次外置为另一个结果；回看始终指向原 artifact。
- 持久化结果索引与完整性状态，冷启动后按引用从磁盘加载，而不是只初始化空 map。
- stdio 需要同时核查 per-session 注册、12 工具白名单、显式工具限制和实际模型请求；只增加工具类不算完成。
- MCP 使用自己的任务级存储/预算；只有验证相应接线后才声明支持。不能把 stdio 的 8 KiB 常数硬塞给所有入口。
- 存储及读取由同一 owner 管理。严格沙箱下优先通过受控账本接口读取，不要求模型自行访问工作区外临时路径，也不扩大普通文件权限。

默认 `turn` scope 下，新 session 不应自动继承旧 session 的任意 artifact。若外层修复确实需要上一轮输出，可显式传入授权引用及原有失败证据；这不意味着必须改成 `run` scope 或增加跨题记忆。

### 6.6 与 H02 的接口必须保持保守

H03 只负责产生真实的范围和最终展示；H02 继续判断“当前版本、当前分支、当前 prompt 是否足以支持省略正文或写入”。

当前 H02 的候选凭据按调用参数、输出哈希和最终消息匹配。若 H03 在后端重分页、修改 envelope 或因压力缩小视图，必须同步更新候选来源，或让原候选失效；不能沿用旧页的全文凭据。历史 artifact 的恢复默认只是历史证据，**不自动授予当前磁盘文件的编辑/覆盖权限**。

多页过去曾经覆盖全文，也不代表正文如今仍同时在 prompt 中。页被压缩掉后，继续遵循 H02 的撤销或 retained proof 校验，不能只累计一个永不失效的“看过全文”布尔值。

## 7. 最小改动与迁移判断

本节只描述调研得出的改动边界，不生成额外 todo 或 Milestone 文件。

| 子项 | 复用与改动 | 预期收益/取舍 | 决策 |
| --- | --- | --- | --- |
| H03a | 扩展 `ToolOutputEnvelope` 的源身份、实际范围、完整性与恢复状态 | 为所有后续保证提供可审计依据；增加少量元数据 | **P0 采用** |
| H03b | `read_window` 和最终 prompt 共用有效预算；页和 footer 一起校验 | 减少漏读和错误续读；小页可能增加请求 | **P0 采用** |
| H03c | shell 在首次有损裁剪前保存；失败/超时状态独立保留 | 避免修复最需要的日志丢失；增加有界磁盘占用 | **P0 采用** |
| H03d | 扩展 `recall` 的范围读取、持久索引和 stdio 接线 | 不重跑命令即可恢复；须验证真实 schema 与权限 | **P0 采用** |
| H03e | H02 凭据消费最终范围；历史恢复与当前磁盘读取分开 | 保持缓存、分页和写入的正确性 | **必须联动** |
| H03f | 输出内搜索、相关片段优先、较大页策略 | 有望进一步减少盲目翻页；净 token 收益待测 | **后置实验** |
| H03g | 全局放大上限、无条件豁免读取裁剪、所有文件强制通读、为找日志自动重跑命令 | 没有可靠收益依据，可能放大输入或改变执行结果 | **不采用** |

实施时以最新主线建立分支；若需要 H02 能力，应显式纳入选定 H02 提交，并记录共同基线。不要从旧分析文档反向覆盖已完成的 H02 逻辑。

最小代码落点是已有 `read_file/read_window`、`shell`、通用 execution、ContextManager、`recall` 和实际入口 builder/白名单。`arc/*.py` 只用于确认输入、工具限制和计量路径，不把修改官方测试或外围判分器算作 H03 的收益。

## 8. 对照实验

### 8.1 先验证端到端不变量

以下是建议后续执行的验证场景，本次未新跑这些测试。

| 场景 | 必须观察到的结果 |
| --- | --- |
| 8 KiB、50,000 字节及窗口阈值附近的文件页 | 最终 provider 请求中的正文、范围、续读参数一致；不只检查工具返回值 |
| 文件中间、末尾分别放唯一标记 | 遵循返回游标能找齐所有标记，没有静默跳页 |
| 请求范围比实际返回范围大 | 从实际末行继续，不能使用 requested offset + limit 跳过缺口 |
| 单行超长、中文、emoji、CRLF、无末尾换行 | 字节续读无遗漏且持续前进；输出变换不被当作原始全文 |
| 空文件、EOF、越界游标 | 明确区分，不能把越界请求悄悄钳到最后一页制造重复 |
| 首尾日志中间有唯一失败，stdout 很大而 stderr 很短 | 原文或可恢复范围中找得到失败；exit code/timeout 始终保留 |
| 输出超过采集/存储上限、磁盘满 | 真实标注 partial/store_failed；无虚假完整引用 |
| 恢复一个很大的 artifact | 页完整穿过 execution、ContextManager 和 provider；不发生再次 spill 的循环 |
| 先截短历史再恢复、连续两次压缩、冷启动恢复 | 原引用仍定位同一内容，或返回明确 expired/missing |
| 重复 call ID、不同 task/session、父子 Agent | 不能串记录或越权继承引用 |
| 翻页期间外部修改文件 | 旧游标 stale；不能混版本登记全文 |
| H02 开启，某页被再次投影或从 prompt 删除 | 对应凭据不再授权错误 stub/写入 |
| 多工具并行与极小上下文预算 | 整批预算可解释，所有可恢复提示有效，没有无进展循环 |
| 恢复含副作用命令的历史结果 | 只读原记录，命令执行次数仍为一次 |
| 严格沙箱和工具白名单 | 模型确实可调用合法恢复入口；不依赖手工关闭沙箱 |

前两项建议使用假 provider 捕获真正发出的请求，并把所有返回页按源范围重组后与固定原文比较。只验证单个分页 helper，会漏掉目前最关键的二次截断。

### 8.2 固定官方输入，分开验证恢复与页大小

| 组别 | 策略 | 要回答的问题 |
| --- | --- | --- |
| A | 固定共同基线，保留现有输出行为 | 当前有多少工具页/失败输出实际被截断 |
| B | A + H03a–e，使用一个明确、固定的有效页预算 | 完整恢复链是否改善通过表现和全任务 token |
| C（可选） | B + 一项独立策略：更大有效页，或输出内搜索优先 | 进一步减少往返是否值得其输入成本 |

所有组使用相同 H01/H02 开关和提交；不能把 H02 新增收益混算给 H03。C 不应同时改变页大小、检索策略和压缩阈值，否则难以解释结果。

固定官方需求、测试、模型与推理参数、输入模板、生成档位、session scope、请求/修复预算、资源及实际二进制。小题用于检查额外开销，Evolution 用于检查旧逻辑回归，较长工具任务用于检验大文件/日志恢复。分别记录实际是否进入 tool mode；没有读取大结果的 Tiny/codegen 任务不是 H03 正向效果证据。

指标顺序：

1. 最终官方测试通过数、全通过率、回归数和重复运行稳定性。
2. 静默遗漏、错误续读、失效引用冒充完整原文、错误 H02 命中次数，目标均为零。
3. 全任务 provider 输入/输出 token，包含失败、重试和恢复请求；缓存与推理按 provider 契约统计，避免重复相加。
4. 首次原文字节、最终可见字节、各层裁剪次数、恢复成功率、找到目标片段前的请求数。
5. 同范围重读、日志重跑、页数、只读第一页即完成的比例，以及恢复后产生的修复收益。
6. 磁盘占用、内存、I/O 和耗时作为运行诊断，不计入成绩。

不能以“单次输出更短”或“分页调用更多但每页更省”直接判定节省。每次新调用可能重发历史前缀；应比较整题 token。若通过表现下降，即使 token 更少也不采用。

真实环境实验前按项目约定执行 `source ~/.zshrc`，核实 `OCTOS_BIN` 的实际提交和哈希、必要 provider 配置及隔离路径。源码调研、确定性测试、模型实验和官方验收分别报告，不能互相替代。

## 9. 最终判断

H03 值得做，优先顺序应是：**真实范围与完整性描述 → 最终预算内分页 → 首次裁剪前保存日志 → 接通同一份原文的恢复 → 校验 H02 凭据**。

最直接的实现借鉴来自 Codex 的防二次截断预算处理、DeepSeek 的范围续读与 spill 提示预算、Claude Code 的部分视图和文件引用。三家的损失边界也说明，Octos 需要比“保存一个文件路径”更明确的完整性约定。

这套改动集中在 harness 如何呈现和找回证据，保留既有需求编排与官方验收流程；其价值要由更稳定的正确结果与更低的全任务 token 来证明。

## 参考源码与官方文档

下列源码链接均固定到本次核查的提交。Octos 主线来源使用 `27d057c2`；H02 凭据来源单独固定到 C 分支，避免混淆已合入与实验实现。测试链接仅作为已有测试内容的证据，不表示本次执行过竞品测试。

[o-window]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/tools/read_window.rs#L1-L139
[o-read]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/tools/read_file.rs#L484-L680
[o-read-recovery]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/tools/read_file.rs#L186-L218
[o-limits]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-core/src/utils.rs#L180-L196
[o-execution]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/execution.rs#L2394-L2448
[o-envelope]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/api/context_manager.rs#L2419-L2477
[o-pressure]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/api/context_manager.rs#L3658-L3684
[o-shell]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/tools/shell.rs#L1227-L1269
[o-recall]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/tools/recall.rs#L16-L154
[o-recall-register]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/session_actor.rs#L3532-L3537
[o-profile]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/runtime/profile.rs#L57-L84
[o-bridge]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/api/ui_protocol_transport.rs#L34720-L34738
[o-snapshot]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/api/context_manager.rs#L1678-L1758
[o-fetch]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/api/context_manager.rs#L2375-L2396
[o-receipts]: https://github.com/woshuoduijiushidui/octos-arc/blob/7eaa136ef086a2f9728794d17d8f150482df03d1/crates/octos-agent/src/model_read_receipts.rs#L524-L610
[cc-readme]: https://github.com/anthropics/claude-code/blob/7974a70773fa229e4cc65aa1b356cc21f5c216c4/README.md#L46-L50
[cc-partial]: https://github.com/anthropics/claude-code/blob/7974a70773fa229e4cc65aa1b356cc21f5c216c4/CHANGELOG.md#L3309
[cc-persist]: https://github.com/anthropics/claude-code/blob/7974a70773fa229e4cc65aa1b356cc21f5c216c4/CHANGELOG.md#L5856-L5857
[cc-storage-cap]: https://github.com/anthropics/claude-code/blob/7974a70773fa229e4cc65aa1b356cc21f5c216c4/CHANGELOG.md#L750
[cc-tools-read]: https://code.claude.com/docs/en/tools-reference#read-tool-behavior
[cc-tools-bash]: https://code.claude.com/docs/en/tools-reference#bash-tool-behavior
[cc-directory]: https://code.claude.com/docs/en/claude-directory#application-data
[cx-tools]: https://github.com/openai/codex/blob/5c5308fc9a9ee789049d646ef11e5400384b9c6f/codex-rs/core/src/tools/spec_plan.rs#L968-L1071
[cx-output]: https://github.com/openai/codex/blob/5c5308fc9a9ee789049d646ef11e5400384b9c6f/codex-rs/core/src/tools/context.rs#L369-L565
[cx-history]: https://github.com/openai/codex/blob/5c5308fc9a9ee789049d646ef11e5400384b9c6f/codex-rs/core/src/context_manager/history.rs#L422-L446
[cx-truncation]: https://github.com/openai/codex/blob/5c5308fc9a9ee789049d646ef11e5400384b9c6f/codex-rs/utils/output-truncation/src/lib.rs#L14-L55
[cx-string]: https://github.com/openai/codex/blob/5c5308fc9a9ee789049d646ef11e5400384b9c6f/codex-rs/utils/string/src/truncate.rs#L1-L152
[cx-exec-defaults]: https://github.com/openai/codex/blob/5c5308fc9a9ee789049d646ef11e5400384b9c6f/codex-rs/core/src/unified_exec/mod.rs#L73-L82
[cx-buffer]: https://github.com/openai/codex/blob/5c5308fc9a9ee789049d646ef11e5400384b9c6f/codex-rs/core/src/unified_exec/head_tail_buffer.rs#L5-L123
[cx-drain]: https://github.com/openai/codex/blob/5c5308fc9a9ee789049d646ef11e5400384b9c6f/codex-rs/core/src/unified_exec/process_manager.rs#L1576-L1668
[cx-budget-test]: https://github.com/openai/codex/blob/5c5308fc9a9ee789049d646ef11e5400384b9c6f/codex-rs/core/tests/suite/unified_exec.rs#L1968-L2023
[cx-large-test]: https://github.com/openai/codex/blob/5c5308fc9a9ee789049d646ef11e5400384b9c6f/codex-rs/core/tests/suite/unified_exec.rs#L3454-L3546
[ds-base]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/bundle/base/cordis.patch.yml#L206-L409
[ds-read]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/fs/tool-fs/src/read.ts#L14-L164
[ds-render]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/fs/tool-fs/src/read-render.ts#L10-L170
[ds-read-tests]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/fs/tool-fs/tests/read-render.spec.ts#L26-L116
[ds-bash-local]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/shell/bash-local/src/index.ts#L35-L190
[ds-bash-render]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/shell/tool-bash/src/render.ts#L11-L83
[ds-spill]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/spill/spill-policy/src/index.ts#L125-L204
[ds-spill-doc]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/spill/spill-policy/README.md#L47-L87
[ds-pruner]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/compaction/compaction-tool-result-pruner/src/index.ts#L63-L175
[ds-local]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/spill/spill-local/README.md#L120-L140
[ds-spill-tests]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/spill/spill-policy/tests/spill-policy.spec.ts#L149-L250
[ds-spill-failure-tests]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/spill/spill-policy/tests/spill-policy.spec.ts#L473-L503
