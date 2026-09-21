# H05 竞品调研：已有代码优先局部编辑

- 调研日期：2026-09-21
- 优化表原分析基线：`c599d18c5acd2b846f049ffea2be84e72fe60fac`
- 本次复核的 Octos 主线：`27d057c206c0f8250b60309905737f7e26ee0ba9`
- H02 文件写保护复核：`7eaa136ef086a2f9728794d17d8f150482df03d1`
- H03 已提交实现复核：`d85bd227597ed3de42a56f27267e94db828cb612`；H05 相关文件与 H02 提交内容一致
- 调研对象：Anthropic Claude Code、OpenAI Codex、DeepSeek Harness
- 范围：只做源码与官方文档调研；未修改运行代码，未运行付费模型或官方任务实验。本次工作树中尚未提交的 H03 后续改动不作为 H05 事实来源。

## 结论先行

H05 建议**调整后采用**。目标不应写成笼统的“永远使用补丁”，而应建立一套由文件状态和变更形态决定的编辑协议：

> **新文件或有充分依据的整体重建可以整文件写；已有代码的局部变化优先使用可在当前文件中唯一定位的局部编辑。无法唯一定位时不猜位置、不写文件，而是返回足够完成下一次编辑的当前邻近证据。**

适合 Octos 的组合是：

1. 借鉴 **Claude Code 的短而唯一的 `old_string`、当前内容重新匹配和“局部变化用 Edit”规则**，但不照搬未读文件可直接整份覆盖的放宽行为。
2. 借鉴 **Codex 的文件级 patch 表达、一个调用承载多个 hunk、应用结果进入 diff/审批/追踪链路**，但不照搬“找到第一个近似位置就写”和多文件中途失败后保留部分修改的语义。
3. 借鉴 **DeepSeek 的精确字面匹配、默认唯一、显式 `replace_all`、版本检查与替换共用临界区、成功结果附实际 diff 元数据**。
4. 复用 Octos 已有的 `edit_file`、`diff_edit`、`mutation_guard`、H02 强版本、H03 最终输出预算和现有 diff 展示，不再增加一套平行文件状态系统。

最先应改的是 **stdio/MCP 工具模式中的选择说明、匹配失败反馈和结果元数据**。原生/Python codegen 的整文件协议应单独实验：新建应用继续整文件生成；已有应用只有在相关源文件完整可见且预计整体改写时才保留整文件输出；“已有文件 patch 协议”作为后置实验，不能与核心工具改动一次性混入。

三家都没有公开与 ARC 相同任务、模型、输入和预算下的 H05 正确率/token 对照数据。下文的收益均为待验证假设；**最终官方测试通过数与稳定性优先，全任务累计 token 次之，耗时不计入成绩**。

## 1. H05 到底解决什么问题

H05 处理的是：**模型已经面对一个有工作行为的代码库时，怎样只改需求真正涉及的部分，并在定位失败时低成本恢复，而不是重发或覆盖整个文件。**

需要区分四种写入：

| 写入类型 | 合理用途 | 主要风险 |
| --- | --- | --- |
| 创建新文件 | 目标不存在，模型提供完整内容 | 路径冲突、并发创建 |
| 整文件覆盖 | 文件很小且完整可见，或 harness 已决定从零重建无有效行为的脚手架 | 漏掉未见代码、输出过长、误删旧功能 |
| 单点字面替换 | 一个连续区域可由短而唯一的旧文本定位 | 旧文本失效、重复匹配 |
| 多 hunk patch | 同一文件有多个分散修改，或一次变更涉及增删改多个文件 | hunk 歧义、部分应用、协议生成失败 |

H05 不等于“文件越大越应该 patch”。真正决定写法的是：

- 目标是新文件还是已有文件；
- 模型是否看到了将被整体替换的当前版本；
- 变化是一个连续片段、多个分散片段，还是确实需要整体重建；
- 当前上下文能否唯一定位；
- 失败后是否能在一次短反馈内修正；
- 该路径是工具循环，还是没有工具的 codegen 单请求。

边界如下：

- H02 负责当前版本和写入临界区，H05 不能绕过其 stale/context guard。
- H03 负责把文件页、编辑失败证据和恢复说明完整送到模型；H05 复用其 8 KiB 最终输出预算，不另开大结果通道。
- H06 负责验收失败后的修复轮；H05 只决定该轮如何落盘。
- H07 负责跨调用判断无进展；H05 可以产生 `no_change`、`no_match` 等可靠信号，但不另建循环检测器。
- H09 负责整体工具定义成本。H05 不应同时暴露功能重叠的三个 patch 工具，只为“选择更多”增加每轮固定输入。
- H12 负责原生 codegen 是否找到完整源码；H05 不能用 patch 掩盖源文件识别遗漏。

## 2. Octos 当前已经有什么

### 2.1 实际 ARC 工具面没有暴露 `apply_patch`

默认 coding profile 提供 `write_file`、`edit_file` 和 `diff_edit`，并明确排除 `apply_patch`，理由是前两种局部工具已覆盖编辑需求且默认工具面要保持精简，[coding profile][o-profile]。Rust ARC stdio allowlist 同样不含 `apply_patch`，[stdio tools][o-stdio-tools]。

因此当前实际工具模式不是“四种编辑器自由竞争”，而是：

```text
read_file
  ├─ write_file：创建或整份覆盖
  ├─ edit_file：旧文本 → 新文本
  └─ diff_edit：单文件 unified diff
```

仓库里确实已有功能完整的 Codex 风格 `apply_patch`：支持新增、删除、更新和移动，并在写入前验证所有 section，还能输出结构化 diff metadata，[Octos apply_patch][o-apply-patch]。但它不在默认 ARC 工具面，不能把它写成模型当前可用能力。它所谓“原子”主要是**整批预验证**；真实 I/O 中途失败时仍可能留下已完成 section 或移动目标，代码也会明确报告 partial state。

### 2.2 `edit_file` 已经不是简单的精确替换

当前 `edit_file` 先精确匹配，失败后依次尝试：

1. 逐行去除首尾空白；
2. 合并空白；
3. 统一缩进；
4. 解释转义；
5. 首尾锚点加中间行相似度。

第一个产生候选的阶段决定结果；必须只有一个候选，多个候选拒绝；匹配范围相对 `old_string` 过大也会拒绝，[replacer chain][o-replacer]。这比优化表最初写的“已有唯一匹配检查”更强。

写入时，当前文件会在共享 mutation guard 的每路径锁中重新读取；若有 H02 观察版本，整文件覆盖要求版本一致，而局部编辑可以在当前内容仍唯一匹配时继续。写前还会再次确认文件未发生并发变化，[mutation guard][o-mutation]。这已经吸收了竞品中很重要的一部分“在当前磁盘上重新确认”能力。

仍有四个 H05 缺口：

- **选择规则不完整。** 工具描述解释了各自能做什么，但没有共同说明“新文件用写入、已有局部变化用编辑、何时用多 hunk”。
- **自动模糊范围过宽。** “唯一”只能证明候选只有一个，不能证明 0.65 相似度的 block anchor 仍是语义正确位置。代码、Markdown 尾随空格和字符串转义都可能有语义。
- **失败反馈缺当前证据。** 无匹配时只回显模型提交的 `old_string`；歧义时只给数量。模型通常还要再读一次文件，才能修正锚点，[edit failure][o-edit].
- **成功反馈过少。** 结果只说明路径和 matcher 名，没有实际行范围、变化规模或 formatter 后的真实 diff，[edit success][o-edit]。

此外，`old_string == new_string` 当前会重写同样内容并报告成功。它会制造“发生了修改”的假进展，也可能触发 formatter、快照和后续验证。

### 2.3 `diff_edit` 有唯一性保护，但位置容错太窄

`diff_edit` 会：

- 解析单文件 unified diff；
- 反向应用 hunk，避免前面的改动移动后面的行号；
- 拒绝重叠 hunk；
- 以目标行上下各 3 行为搜索范围；
- 忽略行尾空白进行匹配；
- 只在该小范围内恰好一个候选时写入。

见 [diff parser and apply][o-diff-edit]。

这对刚从同一文件生成的短 diff 有效，但文件在模型思考期间插入超过 3 行后，即使目标上下文在全文件仍唯一，也会失败。失败只返回请求位置和最多三行 expected pattern，不返回当前附近文本，也不提供“全文件存在唯一候选但偏移更大”的恢复信息。

成功结果仅为 `Applied N hunk(s)`。如果 post-edit formatter 又改变了其他行，模型侧结果不会说明最终实际范围。

### 2.4 `write_file` 已有安全护栏，但整文件 token 在调用前已经花掉

H02/H03 分支中的 `write_file` 已具备两层保护：

- 开启窗口保护时，大文件只有在当前 session 已完整读取且版本仍一致时才能整份覆盖；
- 有文件版本 ledger 时，已有文件覆盖在 mutation guard 内要求已观察版本一致。

见 [whole-file guard][o-write]。

这些保护能阻止错误落盘，却不能退回模型已经生成的整文件输出 token。若目标只是改十行，模型先输出数千行，再被工具拒绝，正确性保住了但成本已经产生。因此 H05 的选择提示必须发生在**模型生成工具参数之前**，不能只靠执行期拒绝。

### 2.5 ARC 还有一条完全不同的整文件 codegen 路径

Python Flow 的 compact codegen 会临时移除工具，让模型在一次响应中返回完整 `<<<FILE path>>>` blocks，由 harness 直接整文件写入，[Python codegen][o-py-codegen]。它已有两项正确性保护：

- 已有应用只有在源码总量适合单请求时才走 codegen；大应用转工具模式；
- 模型返回了本轮没有展示过的已有文件时，丢弃该覆盖并切到工具模式，[unseen rewrite guard][o-py-unseen]。

源码中的历史运行记录说明，放宽这一条件让大应用全部走 codegen 虽然更快，却出现 9 个和 29 个已通过节点回归；保守工具模式的一次记录为 66/66 且零回归，[source-fit evidence][o-py-fit]。这些是仓库内记录，不是本次重新执行的实验，但足以说明“整文件更省请求”不能优先于保留旧行为。

Rust 原生 Flow 同样使用无工具的完整文件块协议，并以所有已识别源码是否装入预算决定是否进入该路径，[Rust codegen][o-rust-codegen]。这条路径不经过 `edit_file`/`diff_edit`，所以核心文件工具改好以后，原生 codegen 不会自动获得 H05 收益。

## 3. 竞品版本与证据边界

| 竞品 | 固定版本 | 可审计范围 | 本次重点 |
| --- | --- | --- | --- |
| Claude Code | [`7974a707`](https://github.com/anthropics/claude-code/tree/7974a70773fa229e4cc65aa1b356cc21f5c216c4)，2026-09-20 | 官方工具文档、CHANGELOG、插件；CLI 核心未公开 | Edit/Write 选择、精确唯一匹配、变更后的文件如何处理 |
| OpenAI Codex | [`a6fdb11e`](https://github.com/openai/codex/commit/a6fdb11eda992b706c5e6a21ae5fd8c7376f8e06)，2026-09-21 | 公开 Rust 实现、模型提示和测试 | patch 协议、上下文定位、多文件执行与部分失败 |
| DeepSeek Harness | [`ddefc45f`](https://github.com/deepseek-ai/deepseek-harness/commit/ddefc45fbc7f8e46dd73185e68295696d1297887)，`0.1.6-alpha.2` | 公开 TypeScript 实现、默认组合、README 和测试；developer preview | exact edit、`replace_all`、原子版本保护、实际 diff metadata |

Claude Code 仓库 README 说明该仓库主要公开插件，不能据此声称核心 Edit 算法开源，[Claude README][cc-readme]。`code.claude.com` 是滚动文档；本文记录 2026-09-21 可见行为，不把它与 GitHub commit 伪装成同一个源码快照。

三家都是通用 coding-agent runtime，不是 ARC 的“固定需求 → 按节点生成或修改 → 官方测试 → 修复”专用编排器。能迁移的是编辑不变量与错误恢复方式，不是它们的默认阈值、提示长度或公开成绩。

## 4. 三家怎么做

### 4.1 Claude Code：精确、唯一、短锚点，文件变化后在当前内容上重新判断

官方工具文档明确区分：

- `Edit` 做精确字符串替换，不使用 regex 或 fuzzy matching；
- `old_string` 必须逐字符匹配且默认只出现一次；
- 多次出现时，模型应增加上下文，或显式设置 `replace_all: true`；
- `Write` 创建或整份覆盖；已有文件的局部变化应使用 `Edit`。

见 [Edit 行为][cc-tools-edit] 与 [Write 行为][cc-tools-write]。

Claude Code 的当前行为还允许一种有价值的恢复：文件在上次读取后发生变化时，如果 `old_string` 在**当前内容**中仍精确且唯一，并且读取不需要新权限，编辑仍可执行；结果会提醒文件还有其他变化，依赖周边上下文的后续编辑应重新读取。CHANGELOG 也记录了对应修复，[changed-file edit][cc-current-match]。

读取凭据不只来自独立 Read。单文件的 `cat`、`nl`、`head`、`tail`、受限 `sed`、`grep`/`rg` 等也可满足 read-before-edit，减少“刚通过 shell 看过又被迫 Read 一次”的重复调用，[read evidence][cc-read-evidence]。

token 方向最直接的公开证据是 CHANGELOG 的“Edit 使用更短 `old_string` anchors，减少输出 token”，[short anchors][cc-short-anchors]。这说明局部编辑的收益来自**足够短但仍唯一**，不是把整段文件复制进 `old_string`。

边界同样明确：

- 核心匹配实现、候选排序和错误结果结构未公开，不能声称复刻算法。
- 新版允许部分模型覆盖未读已有文件，[unread write][cc-unread-write]；这对通用交互更灵活，但不适合直接放宽 ARC 的 H02/H03 保护。
- CHANGELOG 多次修复 CRLF、Markdown 行尾空格和 Unicode 引号损坏，[line endings][cc-line-endings]、[unicode edit][cc-unicode-edit]。这证明“只是文本替换”也必须把编码和行尾当作正确性契约。

**对 Octos 的价值**：采用“局部变化用 Edit、锚点尽量短但必须唯一、当前内容仍精确唯一时可安全应用”的原则。保留 Octos 当前磁盘重匹配与版本保护，不复制未读整文件覆盖。

### 4.2 OpenAI Codex：一个结构化 patch 表达多个文件，但匹配和部分失败不能照搬

固定版本中的 GPT-5.2 Codex prompt 要求单文件编辑优先尝试 `apply_patch`，但生成文件、formatter 输出和跨仓库机械替换可使用更合适的生成器或脚本，[editing guidance][cx-guidance]。这是一条按任务形态选择工具的规则，而不是“所有写入必须 patch”。

`apply_patch` 是 freeform grammar tool，支持：

- `Add File`
- `Delete File`
- `Update File`
- `Move to`
- 一个文件内多个 `@@` hunk

见 [tool spec][cx-tool-spec] 与 [patch grammar][cx-grammar]。同一个 patch 表达可以继续用于审批、流式 diff 事件、实际变更追踪和最终摘要，[handler][cx-handler]。

上下文查找按以下顺序降级：

1. 精确行；
2. 忽略行尾空白；
3. 忽略两端空白；
4. 统一常见 Unicode 引号、横线和空格。

但实现返回每一阶段找到的**第一个**位置，不验证该阶段在文件中是否唯一，[sequence match][cx-match]。对通用补丁，这依赖 hunk 上下文和顺序游标降低误配概率；对 ARC 的正确率优先目标，不能把“第一个近似候选”当成唯一定位证明。

Codex 会先解析和计算建议变更以供审批，执行时仍重新运行 patch。多个文件按 section 顺序落盘；前一个新增成功、后一个更新失败时，前面的文件会保留。实现专门记录已确认提交的 delta 和 `exact=false` 的不确定写失败，[apply loop][cx-apply]，测试夹具也明确包含“失败后保留部分成功”场景，[partial fixture][cx-partial]。

它能在可选模式下保留原行尾，并有 CRLF/mixed line ending 测试；这比把文件统一改成 LF 更安全，[line-ending mode][cx-line-ending]。

**对 Octos 的价值**：采用一个调用承载多个 hunk、结构化 grammar、写前计算变更和统一 diff 追踪。不能采用首个模糊候选，也不能把“已预验证”宣传成跨文件事务；如果默认工具面未来启用多文件 patch，必须继续明确 partial state，或实现真正的临时文件加提交/回滚协议。

### 4.3 DeepSeek Harness：默认 exact edit，把安全和展示放在不同层

默认 base 组合挂载 `fs-observation-policy`、`tool-fs` 和文件搜索工具，[base config][ds-base]。模型可见规则直接写明：

- `write` 用于创建或完全替换文件；
- 已有文件的 targeted change 优先 `edit`；
- `edit` 是字面替换，默认 `old_string` 必须恰好出现一次；
- 确实要改所有精确匹配时，显式 `replace_all: true`；
- 默认策略要求先读当前文件。

见 [edit tool][ds-edit]、[write tool][ds-write]。

底层 `applyLiteralEdit` 只做 CRLF→LF 规范化后的精确匹配。零匹配返回 `FS_EDIT_NOT_FOUND`；多匹配且未声明 `replace_all` 返回 `FS_AMBIGUOUS_EDIT`；不会自动进入相似度替换，[literal edit][ds-literal]。

更重要的是，版本校验、读取、匹配和原子替换都在同一个 per-target lock 中完成。stale 在字面匹配之前判断，因此模型看到的是“版本过期，请重读”，而不是对新版本产生误导性的“找不到旧字符串”，[atomic edit][ds-atomic]。观察状态按 session owner 隔离，[observation policy][ds-observation]。

模型收到的成功文本很短；工具内部用应用后的 `before/after` 生成每个 hunk 三行上下文的 diff metadata，并随结果持久化、供 UI 回放，[diff metadata][ds-diff]。这把两类成本分开：

- 模型上下文只需要短确认；
- UI、审计和回放仍能展示真实变化；
- formatter 或实际落盘结果可以用结果态 diff，而不是只展示调用参数中的意图。

边界：

- `replace_all` 仍可能放大错误意图，只能由模型显式选择，不能在歧义时自动升级。
- 默认失败只给 typed code 和补救动作，没有附当前候选片段；模型仍可能多一次 read。
- 本地 `editText` 同时持有原文件和编辑后副本，大文件内存成本较高；这不是 token 成本，但需要保留上限和失败行为。
- 不挂 observation policy 时，provider 允许无版本的 unconditional edit。Octos 不应让是否启用插件决定 ARC 写保护。

**对 Octos 的价值**：最适合直接迁移的是 exact-default、显式 `replace_all`、拒绝 no-op、版本先于匹配、短模型结果加实际 diff metadata。Octos 还应补充有界当前邻近证据，减少失败后的额外读取。

## 5. 横向对比

| 维度 | Claude Code | OpenAI Codex | DeepSeek Harness | Octos 当前 | H05 判断 |
| --- | --- | --- | --- | --- | --- |
| 新建/整写/局部编辑分工 | 文档明确；局部变化用 Edit | prompt 按单文件、生成物、机械改动区分 | system guidance 明确 write 与 edit | 工具各自描述，缺共同选择矩阵 | 增加稳定、短的共同规则 |
| 默认匹配 | 精确 | exact→空白→Unicode，取首个 | CRLF 规范化后的精确字面 | 六级链，首个阶段必须唯一 | exact 默认；近似只作候选 |
| 歧义 | 增加上下文或显式 replace_all | 不显式拒绝全局重复候选 | 拒绝，或显式 replace_all | 拒绝并给数量 | 保留拒绝，补位置与片段 |
| 文件已变化 | 当前内容仍精确唯一时可编辑 | 执行时重新算 patch | version stale 先失败 | 当前内容重新匹配；并发变化拒绝 | 保留 Octos/H02 语义 |
| 多 hunk | 核心未公开 | 一个 patch 可跨 hunk/文件 | replace_all 或多次 edit | `diff_edit` 单文件多 hunk | 改善全文件唯一 fallback |
| 成功反馈 | 产品 UI 有 diff；核心格式未公开 | patch delta 进入事件与追踪 | 短文本 + applied diff metadata | 路径/matcher 或 hunk 数 | 增加真实范围和 diff metadata |
| 失败反馈 | 会引导重读/加上下文 | 回显缺失 expected lines | typed code + remedy | 文本错误；无当前邻近证据 | typed code + 有界当前证据 |
| 多文件失败 | 未公开 | 可能部分应用，记录 delta | 单文件 mutation 原子 | 隐藏的 apply_patch 预验证后仍可能部分应用 | 默认不新增多文件工具 |
| codegen | 不属于公开固定协议 | 生成物可用脚本，不强制 patch | 默认工具循环 | ARC 有独立整文件单请求 | 单独实验，不能一刀切 |

## 6. 适合 Octos 的目标设计

### 6.1 在请求模型前确定编辑类别

选择顺序建议固定为：

| 条件 | 默认动作 | 理由 |
| --- | --- | --- |
| 目标不存在 | `write_file` / codegen 完整文件 | 没有旧行为可误删；无需输出旧文本 |
| 已有文件，一个连续局部变化 | `edit_file` | 最短协议，当前内容可重新确认 |
| 已有文件，同一文件多个分散变化 | `diff_edit` 单次多 hunk | 避免多次模型往返和重复历史 |
| 多个文件各有小改动 | 同一模型响应中批量发出独立局部调用；保持执行串行 | 不为少数场景默认增加另一套大 schema |
| formatter、生成器可可靠产生结果 | 运行生成器，再记录实际 diff | 不让模型手写机器生成内容 |
| 已有文件需要整体重建 | 仅在完整当前版本可见，且 harness 明确判定为重建场景时 `write_file` | 防止遗漏不可见旧功能 |
| fresh codegen | 保留完整文件块 | 一次请求、无工具 schema，适合从零生成 |
| existing codegen/repair | 先保留当前完整可见门槛；patch 输出作为独立实验 | 避免同时改变请求数、协议和编辑语义 |

规则不能只写在用户 prompt 中。应放在稳定的 coding profile/system section 和对应 tool description 中，并由工具执行期保护兜底。这样模型在生成长参数前就能选对工具，同时保持 prompt prefix 稳定。

### 6.2 把三个现有工具接到同一编辑计划

建议复用 `mutation_guard`，将每次已有文件修改统一为以下顺序：

```text
解析参数
→ 在每路径锁中读取当前版本与当前文本
→ 定位所有候选
→ 判定 exact / normalized / ambiguous / no_match
→ 计算候选新内容和 no-op
→ 校验 H02 version/context
→ 写入
→ 可选 formatter
→ 读取最终版本并生成真实变更摘要
→ 撤销旧 read receipt
```

关键点：

- 匹配必须对**当前锁内内容**执行，不能先在工具层找位置、稍后无条件写。
- stale、无匹配、歧义、no-op、权限和 I/O 错误使用不同枚举；H07 才能正确判断是否无进展。
- formatter 后的最终内容才是成功 diff 的依据。调用参数只能表示意图，不能证明实际结果。
- 写入成功但后处理失败时，要如实区分“文件已改”和“展示/快照失败”，不能让模型重复应用同一修改。

### 6.3 收紧自动匹配，保留模糊匹配作为恢复证据

建议的默认自动写入层级：

1. **精确匹配，且全文件唯一**；
2. **仅行尾形式等价的匹配**，例如 CRLF/LF 映射，写回时保留原文件行尾；
3. 其他 `line_trimmed`、空白合并、缩进变换、转义解释和 block similarity 只生成候选，不直接写。

原因是：

- Markdown 两个尾随空格、字符串字面量空格、模板文本、Python 缩进都可能有语义；
- 唯一近似候选不等于正确候选；
- 当前 Octos 已能找到这些候选，改为“提示而不落盘”可以复用现有 matcher，不需要丢掉恢复能力。

自动近似编辑是否保留，应做单独消融。若现有模型大量依赖安全的缩进容错，完全关闭可能增加重试；但 `block_anchor` 这类相似度写入至少应先降为建议模式。

### 6.4 失败结果直接提供下一次编辑所需的最小当前证据

失败结果建议同时提供短文本和 structured metadata：

```text
code=edit_no_match
path=src/app.ts
current_version=sha256:...
searched_old_digest=sha256:...
candidates:
  - lines 118-124, matcher=line_trimmed, score=...
remedy=retry_with_current_exact_text
```

约束：

- 候选来自本次锁内读取的当前文本，不来自旧模型消息。
- 每个候选包含行范围和少量上下文；总量服从 H03 的单结果/整批 8 KiB 预算。
- 多个精确匹配时返回 occurrence count 和起始行；不回显整文件。
- 零精确匹配时可以给少量稳定排序的近似候选，但必须标为 suggestion，不能写入。
- stale 仍优先返回 H02 的重读补救，不用“附近看起来差不多”掩盖版本变化。
- 这些片段只证明局部当前文本，不创建“模型已经看过完整文件”的 H02 receipt。

这样常见恢复从：

```text
edit 失败 → read_file → 再次 edit
```

缩短为：

```text
edit 失败并附当前局部证据 → 再次 edit
```

是否真正减少总 token 仍需实验，因为更丰富的失败结果本身也占输入。

### 6.5 成功结果只给必要摘要，完整 diff 放结构化元数据

模型侧成功结果建议包含：

- 文件路径；
- `exact` / `line_ending_equivalent` / `replace_all` / `diff_hunks`；
- 实际修改行范围或 hunk 数；
- 替换次数；
- formatter 是否额外改变内容；
- 最终短版本 ID。

不重复回显完整 `new_string` 或整文件；它们已经存在于 assistant tool arguments 中。UI、审计和回放使用 applied diff metadata，按现有输出预算裁成上下文 hunk。若 metadata 超限，保存摘要和可恢复引用，而不是把整份 diff重新送进模型。

`old_string == new_string`、patch 前后字节一致、整文件内容相同都返回 typed `no_change`，不写盘、不 formatter、不制造 workspace snapshot。

### 6.6 `replace_all` 只用于明确的精确批量替换

可以给 `edit_file` 增加可选 `replace_all=false`，但规则必须比单点编辑更严格：

- 只允许 exact 或行尾等价匹配，不允许 fuzzy replace-all；
- 写入前返回/记录匹配总数和稳定行位置；
- 所有匹配在同一当前版本上一次完成；
- `old_string` 为空或等于 `new_string` 直接拒绝；
- 过多匹配或结果超出 mutation/output policy 时拒绝，并建议使用项目已有的结构化生成器或明确脚本。

不能在收到 ambiguity error 后由 harness 自动把 `replace_all` 改为 true。只有模型根据任务语义显式选择，才能区分“确实全部替换”和“锚点写得太短”。

### 6.7 改善 `diff_edit`，不急着把 `apply_patch` 加回默认工具面

`diff_edit` 的目标行可继续作为首选位置，但 `±3` 内没有候选时，可以在全文件搜索**唯一的精确/行尾等价 block**：

- 全文件唯一：应用；
- 多个：返回行号和有界片段，拒绝；
- 没有：返回当前位置邻近片段和候选建议，拒绝。

这吸收 Codex 的跨偏移搜索能力，同时保留 Octos 比 Codex 更严格的唯一性。

当前默认 profile 已有 `edit_file` 与 `diff_edit`，不建议同时加入完整 `apply_patch` schema。若未来多文件局部修改占比高，可以做“`diff_edit` 与 `apply_patch` 二选一”的工具面实验，而不是简单叠加：

- 比较新增 schema 输入成本；
- 比较一轮完成多个文件的请求节省；
- 强制记录部分应用；
- 不将跨文件预验证称为真正事务。

### 6.8 codegen 保持混合策略，patch 协议单独实验

直接把 `<<<FILE>>>` 改成 patch 有三类风险：

- 模型可能产生无法解析或无法匹配的 patch，新增一次完整重试；
- 新建应用本来无需旧上下文，patch 只增加协议字符；
- Python 与 Rust Flow 都要实现相同语义，否则不同入口不可比较。

因此建议：

1. **A/B 主实验不改变 codegen 协议**，先验证工具模式 H05。
2. 另设 C 组，只在 existing app 的 implement/repair 且相关源文件完整可见时允许 `<<<PATCH>>>`。
3. 新文件仍用完整 file block；整文件重建保留显式模式。
4. patch 必须先全部解析和匹配，再写入；任一 hunk 不确定时本轮不落盘。
5. 解析失败只允许一次有界回退，计入总请求和 token。

如果 C 的最终通过数不高于 B，且只是输出 token 较低但重试更多，不采用 patch codegen。

## 7. 最小改动与迁移判断

| 子项 | 改动 | 预计正确率方向 | token 方向 | 成本/风险 | 决策 |
| --- | --- | --- | --- | --- | --- |
| H05a | 为现有 `write_file`/`edit_file`/`diff_edit` 增加统一、稳定的选择说明 | 中：减少无必要整写 | 有望减少大文件输出 | 低；需避免重复长提示 | **P1 采用** |
| H05b | no-match/ambiguous 返回 typed code、当前版本、行号和有界候选片段 | 中到高：提高一次重试成功率 | 失败结果略增，可能少一次 read+LLM | 中；必须服从 H03 预算 | **P1 采用** |
| H05c | 成功后记录实际范围、no-op 和 applied diff metadata；模型只收短摘要 | 中：避免误判和重复编辑 | 基本持平或下降 | 低到中；formatter 后需取最终结果 | **P1 采用** |
| H05d | 增加 exact-only、显式 `replace_all` | 中：减少重复调用且保持意图明确 | 有望下降 | 中；错误全替换影响大 | **受控采用** |
| H05e | 自动写入仅保留 exact/行尾等价；其余 fuzzy 只返回候选 | 可能提高误写安全，但也可能增加重试 | 方向待测 | 中；会改变当前已有 matcher 行为 | **独立消融实验** |
| H05f | `diff_edit` 在 `±3` 失败后做全文件唯一 block fallback | 中：减少仅因行号漂移的失败 | 有望减少 read/retry | 低到中；必须继续拒绝歧义 | **P1 采用** |
| H05g | 默认同时暴露 `apply_patch` | 不确定；能力重叠可能让模型选错 | 每轮增加 schema；多文件时可能少请求 | 中到高 | **暂不采用** |
| H05h | existing codegen 增加 patch 输出协议；fresh codegen 不变 | 可能减少跨节点回归，也可能增加解析失败 | 输出可能明显下降，重试可能抵消 | 高；Python/Rust 双入口 | **独立 C 组实验** |
| H05i | 所有已有文件一律禁止整写或一律强制 patch | 会破坏小文件、生成物和明确重建场景 | 表面输出可能下降 | 高；不符合现有工作流 | **不采用** |

建议最小落点：

- `edit_file.rs`：参数校验、匹配分类、typed 失败、候选摘要、no-op、可选 exact `replace_all`。
- `replacer.rs`：返回候选及范围；将 approximate matcher 与可自动写 matcher 分层。
- `diff_edit.rs`：局部位置失败后的全文件唯一 fallback、typed hunk failure、实际范围。
- `mutation_guard.rs`：继续作为版本/并发/当前磁盘匹配边界，不复制另一套锁或版本状态。
- `ToolResult.structured_metadata` 与已有 diff UI：保存 applied hunk，不把完整 diff塞进模型文本。
- coding profile / ARC prompt：只加入短选择矩阵；不新增默认工具。
- Python/Rust codegen：只在独立实验中增加 patch 协议。

## 8. 对照实验

### 8.1 先验证确定性不变量

至少覆盖：

1. 新文件用完整写入成功；同名文件并发出现时拒绝覆盖。
2. 已有文件 exact unique 编辑成功，只改目标范围。
3. exact 多匹配默认拒绝，并返回稳定行位置。
4. `replace_all=true` 只改全部 exact 匹配，报告真实次数。
5. `old_string == new_string` 返回 `no_change`，磁盘、formatter、snapshot 均不变化。
6. CRLF/LF 等价匹配后保留文件原行尾；Markdown 尾随双空格不被宽松 matcher 吞掉。
7. `line_trimmed`/block-anchor 只有候选时不写文件。
8. `diff_edit` 行号偏移超过 3 行但全文件唯一时成功；全文件多候选时拒绝。
9. no-match/ambiguous 候选文本、版本、范围和最终模型可见内容一致，且总结果不超过 H03 预算。
10. 文件在匹配前、匹配后和 formatter 前后变化时，不发生 stale overwrite。
11. formatter 改动扩大时，成功 metadata 反映最终实际 diff。
12. 失败前后文件 hash 不变；任何可能部分写入的 I/O 错误明确标出 `file_modified`。
13. compaction 后旧 receipt 不授权整文件覆盖；失败候选片段不冒充全文 receipt。
14. 默认工具列表不增加 `apply_patch`，关闭 H05 后恢复当前选择和结果格式。

### 8.2 工具模式先做 A/B，再单独评估 matcher

| 组别 | 策略 | 要回答的问题 |
| --- | --- | --- |
| A | 当前 `d85bd227` 行为 | 当前整写、edit/diff 失败和 fuzzy 自动写的基线 |
| B | A + H05a–d + H05f；保留当前 fuzzy 自动写以隔离反馈/选择收益 | 选择说明、typed recovery、no-op、diff metadata、exact replace_all 是否改善结果 |
| C | B + H05e：approximate fuzzy 只提示不自动写 | 收紧 matcher 是否减少回归，代价是多少次额外重试 |

B/C 使用相同 H01–H04 开关与提交基础。若 C 的通过数更稳定但 token 略增，仍可按“正确率优先”采用；若 C 只增加重试且没有减少误写，则保留 B，并至少将 `block_anchor` 单独降级再测。

### 8.3 codegen patch 使用独立实验

工具模式结论冻结后，再比较：

| 组别 | 策略 |
| --- | --- |
| B | 选中的工具模式 H05；现有完整 `<<<FILE>>>` codegen |
| D | B + existing implement/repair patch 协议；fresh/new file 仍完整输出 |

不把 D 与 A 直接比较归因于 codegen patch，否则工具反馈与输出协议的收益混在一起。

固定官方需求、测试、模型、reasoning、session scope、工具定义、请求预算、修复轮数和运行环境。真实环境运行前按项目约定执行 `source ~/.zshrc`，并记录 `OCTOS_BIN` 的提交和哈希。

指标顺序：

1. 最终官方测试通过数、全通过率、回归数和重复运行稳定性。
2. 错误位置写入、歧义误放行、stale overwrite、部分写入误报，目标均为零。
3. 首轮通过数，以及 previously-passing node/spec 被后续修改破坏的数量。
4. 全任务 provider 输入/输出/cache/reasoning token，包含失败编辑、重读、重试和 codegen fallback。
5. 整文件输出字节、patch/edit 参数字节、每次有效变更行数、unchanged rewrite 字节。
6. edit no-match/ambiguous/stale/no-change 次数，失败后下一次调用成功率和额外模型请求数。
7. exact、normalized、各 fuzzy matcher 的触发与最终验收结果；不能只看 matcher 成功率。
8. 请求数、工具调用数、formatter 次数、磁盘 I/O 和耗时作为诊断。

不能以“patch 文本更短”直接判定节省。工具调用参数和结果会在后续请求中重复进入历史；一次失败 patch 再加一次全文读取，可能比首轮整写更贵。只有在通过表现不下降后，才能比较整题累计 token。

## 9. 最终判断

H05 值得做，但应把它从“让模型多用 patch”改写为：

> **让 harness 在模型输出前明确选择创建、整写、单点替换或多 hunk；所有已有文件修改都在当前版本上唯一定位，失败时返回足以修正下一次调用的最小当前证据。**

推荐顺序是：**选择矩阵 → typed 失败与候选证据 → no-op/实际 diff → `diff_edit` 全局唯一 fallback → exact `replace_all` → fuzzy 自动写消融**。这部分先覆盖真实 stdio/MCP 工具模式。

codegen patch 不与上述改动绑在一起。当前完整文件单请求对 fresh app 有明确的低往返价值，已有源码完整可见门槛也有历史回归依据。只有 existing implement/repair 的独立 D 组证明官方测试不下降且全任务 token 更低时，才采用新的 patch 输出协议。

这套设计吸收了 Claude Code 的工具选择和短唯一锚点、Codex 的结构化多 hunk、DeepSeek 的 exact/typed/atomic/diff 分层，同时保留 Octos 的 H02 版本保护、H03 输出边界和 ARC 固定验收流程。它优化的是“少写但写准”，不是单纯把输出格式从整文件换成补丁。

## 参考源码与官方文档

下列源码链接均固定到本次核查的提交。Claude Code 工具文档是滚动页面；其核心实现未公开。Octos 的 H05 工具事实固定到已推送的 H02 C 提交；Python/Rust Flow 和默认工具面固定到 `origin/main@27d057c2`。

[o-profile]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/assets/profiles/coding.json#L1-L25
[o-stdio-tools]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-arc/src/flow.rs#L69-L103
[o-apply-patch]: https://github.com/woshuoduijiushidui/octos-arc/blob/7eaa136ef086a2f9728794d17d8f150482df03d1/crates/octos-agent/src/tools/apply_patch.rs#L1-L34
[o-replacer]: https://github.com/woshuoduijiushidui/octos-arc/blob/7eaa136ef086a2f9728794d17d8f150482df03d1/crates/octos-agent/src/tools/replacer.rs#L1-L115
[o-edit]: https://github.com/woshuoduijiushidui/octos-arc/blob/7eaa136ef086a2f9728794d17d8f150482df03d1/crates/octos-agent/src/tools/edit_file.rs#L74-L352
[o-diff-edit]: https://github.com/woshuoduijiushidui/octos-arc/blob/7eaa136ef086a2f9728794d17d8f150482df03d1/crates/octos-agent/src/tools/diff_edit.rs#L46-L213
[o-mutation]: https://github.com/woshuoduijiushidui/octos-arc/blob/7eaa136ef086a2f9728794d17d8f150482df03d1/crates/octos-agent/src/tools/mutation_guard.rs#L160-L478
[o-write]: https://github.com/woshuoduijiushidui/octos-arc/blob/7eaa136ef086a2f9728794d17d8f150482df03d1/crates/octos-agent/src/tools/write_file.rs#L92-L140
[o-py-codegen]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/main.py#L2038-L2089
[o-py-unseen]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/main.py#L1999-L2036
[o-py-fit]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/main.py#L1845-L1923
[o-rust-codegen]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-arc/src/codegen.rs#L350-L428

[cc-readme]: https://github.com/anthropics/claude-code/blob/7974a70773fa229e4cc65aa1b356cc21f5c216c4/README.md#L48-L50
[cc-tools-edit]: https://code.claude.com/docs/en/tools-reference#edit-tool-behavior
[cc-tools-write]: https://code.claude.com/docs/en/tools-reference#write-tool-behavior
[cc-current-match]: https://github.com/anthropics/claude-code/blob/7974a70773fa229e4cc65aa1b356cc21f5c216c4/CHANGELOG.md#L2249-L2250
[cc-read-evidence]: https://github.com/anthropics/claude-code/blob/7974a70773fa229e4cc65aa1b356cc21f5c216c4/CHANGELOG.md#L3017-L3020
[cc-short-anchors]: https://github.com/anthropics/claude-code/blob/7974a70773fa229e4cc65aa1b356cc21f5c216c4/CHANGELOG.md#L4450-L4453
[cc-unread-write]: https://github.com/anthropics/claude-code/blob/7974a70773fa229e4cc65aa1b356cc21f5c216c4/CHANGELOG.md#L1757-L1760
[cc-line-endings]: https://github.com/anthropics/claude-code/blob/7974a70773fa229e4cc65aa1b356cc21f5c216c4/CHANGELOG.md#L4484-L4487
[cc-unicode-edit]: https://github.com/anthropics/claude-code/blob/7974a70773fa229e4cc65aa1b356cc21f5c216c4/CHANGELOG.md#L5421-L5424

[cx-guidance]: https://github.com/openai/codex/blob/a6fdb11eda992b706c5e6a21ae5fd8c7376f8e06/codex-rs/core/gpt-5.2-codex_prompt.md#L7-L18
[cx-tool-spec]: https://github.com/openai/codex/blob/a6fdb11eda992b706c5e6a21ae5fd8c7376f8e06/codex-rs/core/src/tools/handlers/apply_patch_spec.rs#L1-L28
[cx-grammar]: https://github.com/openai/codex/blob/a6fdb11eda992b706c5e6a21ae5fd8c7376f8e06/codex-rs/core/assets/tools/apply_patch.lark#L1-L19
[cx-handler]: https://github.com/openai/codex/blob/a6fdb11eda992b706c5e6a21ae5fd8c7376f8e06/codex-rs/core/src/tools/handlers/apply_patch.rs#L359-L456
[cx-match]: https://github.com/openai/codex/blob/a6fdb11eda992b706c5e6a21ae5fd8c7376f8e06/codex-rs/apply-patch/src/seek_sequence.rs#L1-L115
[cx-apply]: https://github.com/openai/codex/blob/a6fdb11eda992b706c5e6a21ae5fd8c7376f8e06/codex-rs/apply-patch/src/lib.rs#L423-L533
[cx-partial]: https://github.com/openai/codex/blob/a6fdb11eda992b706c5e6a21ae5fd8c7376f8e06/codex-rs/apply-patch/tests/fixtures/scenarios/015_failure_after_partial_success_leaves_changes/patch.txt
[cx-line-ending]: https://github.com/openai/codex/blob/a6fdb11eda992b706c5e6a21ae5fd8c7376f8e06/codex-rs/apply-patch/src/lib.rs#L62-L86

[ds-base]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/bundle/base/cordis.patch.yml#L261-L271
[ds-edit]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/fs/tool-fs/src/edit.ts#L39-L167
[ds-write]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/fs/tool-fs/src/write.ts#L29-L152
[ds-literal]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/fs/fs-local/src/fsio.ts#L803-L834
[ds-atomic]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/fs/fs-local/src/index.ts#L180-L265
[ds-observation]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/fs/fs-observation-policy/src/index.ts#L17-L94
[ds-diff]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/fs/tool-fs/src/diff.ts#L1-L80
