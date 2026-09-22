# H07 竞品调研：识别无效循环并切换策略

- 调研日期：2026-09-22
- 优化表原分析基线：`c599d18c5acd2b846f049ffea2be84e72fe60fac`
- 本次复核的 Octos 主线：`27d057c206c0f8250b60309905737f7e26ee0ba9`
- 当前 H05 分支：`feat/local-edit`，提交 `3fe3fce4c155f3e9ba8c762a2fc7bd3aa33daf3d`；H07 相关 loop 源码与上述主线相同
- 调研对象：Anthropic Claude Code、OpenAI Codex、DeepSeek Harness
- 范围：只做源码与官方文档调研；未修改运行代码，未运行付费模型或官方任务实验。本文沿用 [H03 调研](../h03/h03-output-pagination-recovery-competitor-research.md) 的组织方式。

## 结论先行

H07 建议**调整后采用**。三家都提供了值得吸收的局部机制，但本次没有发现一套可以直接复制到 Octos、同时满足 ARC 正确率和全任务 token 目标的通用“语义循环检测器”。

适合 Octos 的组合是：

1. 借鉴 **Codex 对进展、等待和阻塞的严格定义**：只有改变权威状态、完成工作，或获得会改变下一步的新证据，才算进展；状态汇报和未执行计划不算。等待必须绑定仍存活的任务句柄。
2. 借鉴 **Claude Code 的分层熔断**：针对明确的局部循环设置确定性上限，并允许完成检查阻止过早结束；但不能把可选插件或 prompt hook 当作默认核心循环检测。
3. 借鉴 **DeepSeek Harness 对模型请求重试、任务轮次和持久状态的分离**：provider 瞬时失败不应污染任务停滞计数，尝试身份和终止原因应可审计；不能采用其无上限 `always` 重试。
4. 复用 Octos 已有 `LoopDetector`、`LoopRetryState`、`ConvergenceController`、H05 typed 修改结果和外层验收收敛，不再建立第二套互相竞争的循环框架。

核心判断是：

> **“执行成功”“输出很长”“参数不同”“文件写过”都不能单独证明任务有进展。H07 应比较有来源的状态、证据和验证结果，并在确认等价无进展后要求换策略。**

建议先把每次工具结果归一化成有界的 `ProgressObservation`，再建立以下升级顺序：

1. 规则检测到首次重复时，给短而具体的提示，不增加模型请求。
2. 对确定性工具的完全等价重试，在执行前拒绝下一次相同调用，返回 typed 原因。
3. 对参数有变化但目标、结果或失败本质相同的停滞，最多触发现有的一次 tools-disabled convergence 复盘。
4. 复盘后仍出现同类停滞，则停止该回合或返回不可自动重试的 blocker，不再靠改写参数延长循环。
5. 异步等待、provider 重试和外层官方测试修复分别计数，不能混成一个全局阈值。

这比“每 N 步调用一个模型判断是否卡住”更省 token，也比只比较工具名和原始 JSON 参数更不容易漏掉换参数不换方法的循环。

目前没有找到三家在相同 ARC 任务、模型、预算下验证 H07 的公开对照数据。所有收益仍须由本项目实验确认：**最终官方测试通过数与稳定性优先，其次比较全任务累计 token；耗时不计入成绩。**

## 1. H07 到底解决什么问题

H07 处理的是：**Agent 看起来持续行动，但权威状态、诊断证据或验证结果长期没有变好时，怎样及时停止原策略并换一种做法。**

它不是简单的“重复调用检测”。下面几种现象需要分开：

| 分类 | 可接受的证据 | 对 H07 的含义 |
| --- | --- | --- |
| `validation_improved` | 允许的测试通过数增加、失败集合缩小、原失败被修复且无新增回归 | 强进展；清除本轮停滞状态 |
| `state_changed` | 文件最终版本、工作区状态或其他权威对象发生变化 | 说明做了修改，但还不能证明方向正确 |
| `evidence_changed` | 错误位置、expected/actual、退出类别或受影响对象出现有意义变化 | 调查有进展；允许下一步，但不能冒充修复成功 |
| `verified_wait` | 已确认仍存活的进程、任务、session 或 job handle | 单独处理，采用退避和等待上限；不是普通无进展 |
| `no_progress` | 等价操作得到等价结果，或改动后验证签名不变 | 累积停滞；提示、换策略，最终停止 |
| `regressed` | 通过数下降、失败集合扩大或已通过行为重新失败 | 比无进展更强的负面信号；保留或恢复最佳状态 |

“错误变化”是否算进展不能只回答是或否：

- 从“找不到元素”变成“提交后返回 500”，说明执行走得更远，属于 `evidence_changed`。
- 但如果官方测试仍未增加通过项，它不是 `validation_improved`。
- 同一个错误仅多了时间戳、随机 ID、重试次数或输出顺序，不应算新证据。
- 同一测试从一个稳定失败变成另一个稳定失败，可以允许一次针对新证据的行动，但不应无限重置停滞计数。

H07 与相邻项目的边界：

- H05 提供 `modified`、`no_change`、最终文件版本和变更范围；H07 消费这些事实，不重新判断补丁是否正确。
- H06 决定验证失败后是否在同一任务内修复；H07 只判断连续修复是否仍有进展。
- H08 决定总 token、迭代和输出预算；H07 可以提前止损，但不能用停滞判定绕过硬预算。
- H10 负责准确记录失败和重试消耗；H07 的新增提示、复盘和被拦截调用都必须进入相同计量口径。
- 官方测试、评分规则和用户需求保持固定。不能通过少跑测试、隐藏失败或把“有文件变化”当完成来提高表面成功率。

## 2. Octos 当前已经有什么

### 2.1 先区分核心工具回合与外层 ARC 修复

Octos 已经有两层不同粒度的收敛机制：

| 层级 | 当前职责 | H07 应做什么 |
| --- | --- | --- |
| 核心 Agent loop | 一次 conversation/task 内连续调用工具 | 识别重复读取、无效编辑、等价错误和无意义轮询 |
| `arc/main.py` 外层修复 | 运行允许的验收测试，跨修复轮比较结果 | 依据真实测试签名切换 codegen/tools、停止无改善修复、恢复最佳状态 |

外层已经比核心层更接近“语义进展”：

- `failure_signature` 去掉耗时和重试次数，但保留测试文件、状态、位置、错误消息和步骤，见 [失败签名][o-failure-signature]。
- 节点修复遇到相同失败会从 codegen 切到工具模式；连续两次通过数无提升会停止，连续两次回退会恢复最佳状态，见 [节点收敛][o-node-convergence]。
- full-suite 在第一次相同失败后要求改变方法，改变后失败签名仍相同则停止，并最终恢复最佳轮次，见 [全量验收收敛][o-suite-convergence]。
- 如果上一次修复没有写入文件，外层不会错误地把“相同代码再次得到相同失败”解释成修复策略失败。

因此 H07 不应在核心层复制一套“跑完整官方测试、回滚工作区、决定跨节点修复”的系统。核心层应提供更准确的短周期信号，让外层现有判断获得更好的单回合结果。

### 2.2 已有 exact loop 检测，但输入过于字面

`LoopDetector` 当前有三类规则，见 [循环检测器][o-loop-detector]：

1. `record_doom`：连续相同的 `(tool_name, arguments JSON)` 到第 3 次时触发。
2. `record`：最近窗口中长度 1、2、3 的参数签名模式重复 3 轮时触发。
3. `record_result`：连续三次 `(tool_name, arguments JSON, result text)` 完全相同时，在工具结果后追加 `[NO PROGRESS]`。

这些规则成本低、行为确定，应该保留。但原始字符串哈希有两个相反的问题：

- **漏报**：模型只要改变无关参数、命令空白、临时目录、输出格式或读取范围，就能绕过相同签名，即使目标和失败本质没有变化。
- **误当进展**：结果中的时间戳、耗时、随机 ID 或日志顺序发生变化，会生成新哈希，但未必产生新证据。

当前 conversation 路径还存在顺序上的不一致：`record_doom` 在工具执行前拦截第 3 次完全相同调用，[conversation 调用点][o-conversation-precheck]；同一路径的 `record_result` 只有工具执行后才能看到第 3 个结果，[结果记录点][o-result-recording]。因此注释所述“第 3 次先软提示、第 4 次再硬终止”对普通 conversation 的完全相同调用并不成立；第 3 次通常已经不会执行。Verifier 豁免和 task 路径另当别论。

### 2.3 conversation 与 task 路径的保护不一致

conversation loop 在 dispatch 前调用 `record_doom` 和 `record`，可以直接结束重复调用。`run_task_inner` 只创建 detector 并把它交给通用结果处理，[task 接线][o-task-loop]；它没有同等的 pre-call hard check，也没有消费 file churn 或 peer polling signal。

结果是：

- 同一个 detector 类型在不同入口表达不同保证。
- 后台 task 可以收到结果后的软提示，却继续执行 conversation 已经会拦截的精确重复调用。
- file churn 和 peer polling 虽然在通用结果处理里被记录，但只有 conversation 把 pending signal 送入 convergence，[signal 消费][o-signal-consume]。

H07 必须先统一实际使用的入口，否则单测通过不能证明 ARC 运行路径受到保护。

### 2.4 文件“成功”不等于文件真的变化

当前 `record_file_mutation` 只看：

- 工具名是否属于 `write_file`、`edit_file`、`diff_edit`、`apply_patch`；
- 调用是否 `success=true`；
- 参数中能否取到路径。

每次满足就给该路径增加一次 mutation 计数，默认第 5 次触发复盘，第 10 次开始请求模型/provider 升级，[文件 churn][o-file-churn]。

H05 分支已经提供更可靠的 typed 元数据：

- 真修改：`outcome=modified`、`file_modified=true`、`final_version`、`changed_range`；
- 无变化：`outcome=no_change`、`file_modified=false`、相同 `final_version`、空变更范围。

见 [H05 修改结果][o-mutation-report]。但 loop 目前只把工具执行的 success bit 传给 detector，没有使用这些字段。因此一次成功返回的 `no_change` 仍可能被计为“文件修改”；反过来，同一路径多次写入相同最终版本也无法被识别为重复状态。

### 2.5 “有用工具结果”仍依赖文本形状

`is_productive_tool_message` 把 `Exit code: 0` 或长度至少 128 字节且不含部分错误短语的结果视为 productive，[productive 判断][o-productive]。这个信号会允许一次超过硬预算的 grace call。

它适合作为旧工具的保守兜底，不适合作为 H07 的权威进展证据：

- 重复读取同一大文件会持续产生长文本。
- 附加 `[NO PROGRESS]` 的旧结果仍可能超过 128 字节。
- shell 退出 0 只证明命令执行成功，不证明代码、证据或测试结果改善。
- typed `no_change` 比文本长度更可信。

H07 应优先使用结构化结果，只有缺少 typed 元数据的旧工具才回退到文本启发式，并把来源标记为低置信度。

### 2.6 已有 convergence 可复用，但不应频繁调用

conversation loop 已有 tools-disabled `ConvergenceController`。默认每 20 个 action LLM call、100,000 active token 或 300 秒触发，也可以由 file churn 和 peer polling 提前触发，[convergence 规则][o-convergence]。复盘本身是一次真实模型请求，虽然有输出上限和缓存前缀优化，仍会增加 token。

适合 H07 的不是再加一个 verifier，而是：

- 确定性重复先用规则处理；
- 只有“等价无进展但参数不同”或“策略已经漂移”时，才复用现有 convergence；
- 同一个停滞 episode 最多触发一次语义复盘；
- 复盘后的下一次等价失败直接停止，不再周期性复盘同一问题。

已有 verifier lane 也会产生模型成本，而且用途是评估计划/执行证据，不应成为所有 H07 路径的默认依赖。

### 2.7 provider 重试已经有独立状态机

`LoopRetryState` 按 rate limit、context overflow、认证、网络、timeout、工具执行等错误类别分别计数，并返回 continue、切 provider、压缩、升级或 exhausted，[重试状态机][o-retry-state]。

这个分层应保留：

- provider 瞬时失败是“同一步尚未获得任务观察”，不是任务策略无进展。
- 认证、权限或配额等确定性失败应走原有 fail-fast/typed bucket，不需要 H07 再尝试换文件或换测试。
- 只有工具真正执行并产生任务观察后，才进入 H07 的 progress episode。

## 3. 竞品版本与证据边界

| 竞品 | 固定版本 | 可审计范围 | 本次重点 |
| --- | --- | --- | --- |
| Claude Code | [`8187baaa`](https://github.com/anthropics/claude-code/tree/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0)，2026-09-22 | 官方公开仓库中的 README、CHANGELOG、hook 文档与插件；CLI 核心实现未公开 | hook 反馈、停止拦截、局部熔断 |
| OpenAI Codex | [`e51aacad`](https://github.com/openai/codex/commit/e51aacad602dec4108db0d2f62bb7f40c6ced56c)，2026-09-22 | 公开 Rust 核心、Goals extension、测试与配置 | 进展定义、等待边界、失败回合计数、有限重试 |
| DeepSeek Harness | [`ddefc45f`](https://github.com/deepseek-ai/deepseek-harness/commit/ddefc45fbc7f8e46dd73185e68295696d1297887)，`0.1.6-alpha.2` | 公开 TypeScript 核心、默认组合、goal 与 retry 包；developer preview | 通用 loop 边界、持久轮次、请求重试隔离 |

Claude Code 仓库不包含可审计的完整 CLI 核心，因此只能把公开 hook 契约、插件实现和 CHANGELOG 行为当证据，不能反推其内部一定采用了某种通用循环算法。

Codex 的 Goals 是当前 stable 且默认开启的功能，[feature 定义][cx-goals-feature]；但它主要处理跨 turn 的持久目标，不等于核心 tool loop 内置了完整语义停滞检测。

DeepSeek Harness 明确处于 developer preview。其包文档详细说明边界，适合提取设计原则，但不能将默认参数直接当成经过 ARC 验证的最优值。

## 4. 三家怎么做

### 4.1 Claude Code：可插拔反馈与窄范围熔断，不是公开的通用检测器

Claude Code 的公开 hook 能在关键生命周期插入规则或模型判断：

- `PreToolUse` 可以在执行前校验、修改或阻止工具输入。
- `PostToolUse` 可以观察成功结果；CHANGELOG 还记录了 `PostToolUseFailure`。
- `Stop` 可以在 Agent 准备结束时批准或阻止结束，并把理由送回模型。
- CHANGELOG 还记录了针对 API 错误结束回合的 `StopFailure`，[失败 hook][cc-failure-hooks]。

Stop hook 的官方示例就是检查任务是否真正完成，并在不满足时返回 `block`，[hook 文档][cc-stop-hook]。这说明“终止前复核”可以和主循环解耦。但 prompt/agent hook 本身会调用模型，不适合在 Octos 每个工具步骤上运行。

公开变更记录展示了多种**针对已知循环的局部上限**：

- Stop hook 连续阻止默认最多 8 次后结束，避免 hook 自己形成无限循环，[Stop cap][cc-stop-cap]。
- auto-compact 后上下文立刻再次填满，连续 3 次后停止并报可操作错误，[compact thrash][cc-compact-thrash]。
- auto-compaction 连续失败 3 次后熔断，[compact failure cap][cc-compact-failure]。
- WebSearch 和当时的 subagent spawn 都曾设置每 session 200 次上限以阻止 runaway loop，[session caps][cc-session-caps]。

这些机制的共同点是：**先定义一个窄而可观察的失败模式，再给它独立上限**。它们不是一个统一的“只要调用次数多就停止”阈值。

官方仓库中的 `security-guidance` 是可选插件，不是 Claude Code 默认核心。它在 UserPromptSubmit 捕获 baseline，在 PostToolUse 记录 touched paths，在 Stop 时只审查本轮 diff；它还去重已有 finding，并将 Stop 触发次数默认限制为 3，[security stop][cc-security-stop]。可借鉴的是“baseline + touched set + 去重 + 有界复查”，不能把该插件描述成 Claude Code 的通用 no-progress 实现。

**迁移判断：**

- 采用 lifecycle 分层和窄范围熔断思想。
- 采用“阻止结束时必须给具体原因”的交互原则。
- 不采用每步 prompt hook，也不把 Stop hook 当主要循环检测器。
- 不复制 8、3、200 等产品阈值；Octos 应按工具类别和 ARC 风险实验校准。

### 4.2 OpenAI Codex：进展定义最清楚，但工具成功重置仍偏粗

Codex 的 goal continuation prompt 明确定义了三类情况，[continuation prompt][cx-continuation]：

- 进展：改变权威状态、完成工作，或获得会改变下一步的证据。
- verified wait：轮询一个当前确认存活的具体 handle。
- no progress：只汇报状态、写计划，或没有采取可验证行动。

它还要求同一真实 blocker 连续出现 3 个 goal turn 后才标记 blocked。这套定义适合 H07，因为它把“有动作”与“有进展”分开，也避免把合法异步等待误判为死循环。

实现层的计数比 prompt 更粗：

- 默认命名空间的 `exec` 真正执行失败，会把当前 goal turn 标记为 execution failure。
- 同一个 goal 连续 3 个 execution-failure turn 且中间没有成功工具，则停止 goal。
- 任意成功工具都会清空该计数。
- 自动 continuation 连续 3 个完全空回合也会停止。

见 [goal accounting][cx-accounting]。优点是 host 侧确定、可测试、无额外模型调用；弱点是一次无关的成功读取也会清空执行失败计数，因此它不能直接作为 Octos 的语义进展判定。

本次在 Codex core turn loop 中没有找到通用于所有工具的“等价目标 + 等价结果”循环检测器。Goals 解决的是跨 turn 持续执行，不能据此声称每个普通工具循环都受语义保护。

Codex 还把基础设施重试与任务进展分开：

- model provider 默认 request retry 为 4、stream retry 为 5，[provider retry defaults][cx-retry-defaults]；
- tool orchestrator 在 sandbox denial/批准后只执行一次明确的第二次尝试，[sandbox retry][cx-sandbox-retry]。

**迁移判断：**

- 采用其进展、等待、阻塞定义。
- 采用 host 侧有界计数和“空回合不算进展”。
- 调整“任意成功工具都重置”：Octos 只应由相关 state/evidence/validation 信号更新 episode。
- 不引入跨 turn Goals 系统；ARC 已有外层任务与验收循环。

### 4.3 DeepSeek Harness：重试和目标轮次分离，但默认 core 不防语义循环

DeepSeek 的标准 agent loop 是清晰的“调用模型 → 执行工具 → 记录结果 → 继续”。官方包文档明确写出 core **没有内置 turn budget**，工具调用或 steering 可以持续当前 turn；需要上层从生命周期扩展点取消，[agent-loop 边界][ds-agent-loop]。

因此不能把 DeepSeek Harness 当成已经解决 H07 的正面样板。它更有价值的部分是边界拆分。

**目标轮次。** `goal-round-driver` 在同一个持久 session 内继续目标：

- 每个正式进入历史的 round 有稳定的 goal id、revision 和 round number。
- `maxGoalRounds` 限制自动轮次数，默认 goal cap 为 256，[goal 默认值][ds-goal-default]。
- 达到上限后记录 typed `round-limit` blocker。
- 恢复、fork 或取消后不会静默自动继续。

但文档也明确说明：它没有独立 evaluator，round cap 不是 token、时间或 provider 预算，[goal limits][ds-goal-limits]。所以“多轮仍在运行”不能证明语义进展。

**模型请求重试。** 默认 base 组合挂载 `llm-retry`，[默认组合][ds-base]。normal 模式只对选定瞬时错误最多重试 5 次；每次排队和真正开始都有 durable event。`always` 模式会重试所有模型错误且没有次数上限，官方文档明确提示可能无限消耗请求，[LLM retry][ds-llm-retry]。

这里最值得采用的是：

- provider retry 有自己的 attempt identity、failure code 和持久事件。
- 它不伪装成新的任务策略，也不向模型注入假的进展。
- 任务 round cap、provider retry 和 core tool loop 是不同层。

`always` 模式则是反例：H07 不能因为“最终也许会恢复”就允许永久重试确定性认证、配额、协议或上下文错误。

**迁移判断：**

- 采用 durable attempt identity 和分层计数。
- 采用 typed blocker/终止原因。
- 不采用 256 轮默认值，也不采用无限 `always` retry。
- 不依赖模型自行声明完成或阻塞作为唯一判据。

## 5. 横向对比

| 维度 | Claude Code | OpenAI Codex | DeepSeek Harness | Octos 当前 | H07 判断 |
| --- | --- | --- | --- | --- | --- |
| 通用 tool-loop 语义检测 | 核心未公开，不能确认 | 未发现通用实现 | 默认 core 明确无 turn budget | exact args/result 与短周期模式 | 需要在现有 detector 上补 typed 语义，不照搬 |
| 无进展定义 | 可由 hook 自定义 | continuation prompt 定义清楚 | goal 主要依赖模型判断 | 参数/结果哈希和文件次数 | 采用 Codex 定义，host 侧实现保守子集 |
| 文件进展 | 可选插件看 baseline/touched diff | tool success 粒度偏粗 | durable tool result，可由插件扩展 | 只按 success + path 计数 | 使用 H05 `file_modified/final_version/outcome` |
| 错误变化 | 未见统一公开规则 | “改变下一步的证据”算进展 | 无独立 evaluator | 原始结果字符串变化即新签名 | 归一化稳定失败字段，忽略易变噪声 |
| 异步等待 | 有 background task 状态与停止事件 | 要求具体 live handle | goal driver 等 whole-agent idle | peer 工具有特殊分支 | 独立 waiting 状态、退避和上限 |
| 策略切换 | hook block 后反馈模型 | goal continuation 要求重验和行动 | 新 round 继续同一 session | 提示、convergence、模型升级 | 先规则提示，再一次复盘，再终止 |
| 额外模型成本 | prompt/agent hook 会增加 | goal continuation 增加回合 | goal round 和 retry 增加请求 | convergence/verifier 已有成本 | 不增加逐步 evaluator；复用且限制现有复盘 |
| 基础设施重试 | 多个窄熔断 | provider 与 sandbox 重试有界 | normal 有界，always 无界 | `LoopRetryState` 分桶有界 | 保持与 task stall 分离 |
| 跨修复验证 | 无可比 ARC 证据 | Goals 不等同 ARC evaluator | goal 无独立 evaluator | 外层已有测试签名和最佳状态 | 不在核心重复实现 |

三家的共同经验不是某个固定阈值，而是：

1. 用可信状态而不是语言表述判断。
2. 不同失败类别使用不同预算。
3. 等待必须有真实对象可等。
4. 反馈循环自身也必须有上限。
5. 终止要携带可审计原因，不能静默退出。

## 6. 适合 Octos 的目标设计

### 6.1 建立有界的 `ProgressObservation`

建议在工具结果还保留 `ToolResult` 和 `structured_metadata` 时构造 observation，而不是等内容变成一段字符串后再猜：

```text
ProgressObservation
  operation_family   read | search | mutate | validate | execute | wait | other
  target             规范化路径、测试集合、命令类别或 handle
  execution_status   success | failed | blocked | timed_out | unknown
  typed_outcome      modified | no_change | no_match | ambiguous | ...
  state_version      修改后的最终版本摘要，可为空
  evidence_signature 稳定错误/结果摘要，可为空
  validation         passed/failed 集合摘要或通过数变化，可为空
  wait_handle        已确认存活的任务身份，可为空
  source_confidence  typed | trusted_adapter | text_fallback
```

约束：

- 所有文本片段、路径集合和签名都必须有界，不能把完整工具输出复制进 detector。
- typed metadata 优先；只有工具没有结构化结果时才使用文本 fallback。
- 任意 shell 文本中的“10 tests passed”不能自动成为 validation improvement。只有 harness 发起、允许且能识别来源的验证命令或专用验证工具可以写 validation 字段。
- observation 仅用于判断循环，不改变原工具结果，不影响 H05 schema 兼容。

### 6.2 比较“等价失败”，而不是只比较原始参数

建议为无进展比较生成稳定的 `NoProgressKey`：

```text
operation_family
+ normalized_target
+ typed_outcome / error_code
+ stable_failure_location
+ bounded expected/actual or result digest
```

归一化规则应保守：

- 文件路径规范化，但不能合并两个真实不同的文件。
- 去掉耗时、时间戳、重试序号、随机 request ID 和临时目录前缀。
- 保留错误类别、失败位置、expected/actual、退出码和测试步骤。
- read/search 的不同范围若暴露了新内容，算 `evidence_changed`；仅改变 limit 而得到相同可见证据，算等价。
- mutation 参数不同但最终 `no_change` 且文件版本相同，算等价无进展。
- mutation 真正改变最终版本，记 `state_changed`，但只有后续验证改善才升级为强进展。

这与外层 `failure_signature` 的经验一致，但核心层只处理当前工具 episode，不解析或复制整个 Playwright 结果模型。

### 6.3 用 episode 而不是一个全局连续计数

一个停滞 episode 应至少按“目标 + 问题类别”隔离。例如：

- `read:src/app.ts:same-version`
- `mutate:src/app.ts:no-change`
- `validate:REQ-3:same-failure-location`
- `execute:npm-start:permission-denied`
- `wait:job-123:running`

以下事件重置或迁移 episode：

- `validation_improved`：结束相关 episode。
- 新失败位置或新 expected/actual：转成 `evidence_changed`，保留问题关联但允许下一步。
- 修改不同的相关目标：开始新 episode；不清空无关失败的历史。
- provider 请求在获得工具观察前失败：不创建 task episode。
- 无关成功读取：不清除 mutation/validation stall。

episode 状态只保留最近有限个 key、计数、是否已经提示、是否已经复盘和复盘后的策略标记。不得随任务长度无界增长。

### 6.4 分级处理：规则优先，模型复盘只用一次

建议的默认升级过程：

| 阶段 | 触发 | 行为 | 新增模型成本 |
| --- | --- | --- | --- |
| 观察 | 第一次结果 | 记录 typed observation | 0 |
| 定向提示 | 第 2 个等价 no-progress 结果 | 在结果后附短提示，指出目标、结果和可选的新证据方向 | 0 |
| 执行前拒绝 | 提示后再次提交完全相同的确定性调用 | 不执行工具；返回 `REPEATED_NO_PROGRESS` 和最近证据摘要 | 0 |
| 策略复盘 | 参数不同但同 episode 持续无进展，或同文件真实 churn 达阈值 | 复用 tools-disabled convergence，要求选择一个可验证的不同假设 | 最多 1 次/episode |
| 终止 | 复盘后的探测仍返回等价 no-progress | 返回 bounded blocker；本回合不再自动重试该 episode | 0 |

这里的“第 2 个”只适合**确定性、同步、完全等价**结果，例如同一文件版本的相同读取、同一 `no_change` 编辑。验证、构建、网络、并发任务和易波动工具应使用各自更保守的阈值。不要用一个全局数字覆盖所有工具。

策略复盘的输出也必须可检查：

- 明确旧假设是什么；
- 指定一个不同的下一动作类别；
- 说明该动作预期获得什么新证据；
- 不允许仅改写同一命令、同一 patch 或同一读取范围后声称“换了策略”。

若复盘没有产生可识别的新策略，直接进入终止，不再追加第二次复盘。

### 6.5 异步等待单独处理

同参数轮询可能是合理等待，也可能是 busy-wait。判断关键不是结果文字是否变化，而是：

1. 是否有当前仍存活的具体 handle。
2. 工具是否声明为异步状态读取。
3. 距离上次 poll 是否满足最小间隔或退避。
4. 是否超过该 handle 的 bounded wait 次数或 deadline。

有 live handle：

- 返回 `verified_wait`；
- 保留现有 peer polling 提示；
- 优先让 Agent 做独立工作或使用已有 bounded wait；
- observation timeout 后重新检查同一 handle，不能仅因一次超时重启任务。

没有 handle、handle 已终止，或重复结果与任何真实异步对象无关：

- 不标记 waiting；
- 按普通 no-progress 处理。

这能吸收 Codex 的 verified-wait 边界，同时保留 Octos 对 peer 工具的特殊保护。

### 6.6 正确消费 H05 文件元数据

文件类工具的规则应调整为：

- `outcome=no_change` 或 `file_modified=false`：记一次 no-progress，不增加 file churn。
- `file_modified=true` 且 `final_version` 与该路径上一版本不同：记 `state_changed`，增加真实 mutation 计数。
- `file_modified=true` 但 `final_version` 相同：不重复增加真实 mutation；记录重复状态。
- `final_state=unconfirmed`：不能宣称已修改，记低置信度状态并要求读取或验证。
- `changed_range` 只帮助描述改动范围，不代表验证改善。

对未提供 metadata 的旧工具维持兼容 fallback，但 telemetry 要记录 `source_confidence=text_fallback`，便于实验判断误报来自哪里。

### 6.7 conversation 与 task 使用同一状态机

建议把 pre-call 与 post-result 判断收敛为共享接口：

```text
before_call(tool, args) -> Allow | RejectWithObservation
after_result(tool, args, ToolResult) -> ProgressDecision
```

两个实际入口都调用同一顺序：

1. dispatch 前检查已被拒绝的 exact episode 和 terminal tool。
2. 工具完成后构造 observation。
3. 更新 episode，并产生 hint、convergence signal 或 terminal blocker。
4. terminal 决定在当前 task 内标记为不可自动重试，避免 `LoopRetryState` 或下一轮换参数后再次执行。

conversation 可以把 blocker 转成面向用户的简短终止说明；task 应返回 typed failure/output，让调用方决定是否进入外层修复。两者展示方式可以不同，检测语义必须相同。

### 6.8 与外层验收收敛保持单向关系

核心 H07 只输出：

- 本回合是否产生新状态或新证据；
- 哪个 episode 重复；
- 是否已经要求换策略；
- 为什么终止。

外层 `arc/main.py` 继续独占：

- 官方测试通过数与失败集合比较；
- codegen/tools 模式切换；
- 跨修复轮停止；
- 最佳 Git 状态恢复。

不要让核心层因为一个局部 `state_changed` 就重置外层 `stalls`；也不要让外层相同 failure signature 反向清空核心 detector。两层通过 typed 结果传递事实，但各自保留自己的时间尺度和权威来源。

## 7. 最小改动与迁移判断

建议保持局部修改：

| 位置 | 复用内容 | H07 最小变化 |
| --- | --- | --- |
| `loop_detect.rs` | ring buffer、exact cycle、file/peer signal | 增加 bounded observation、episode 和等价 key；保留 exact 快路径 |
| `loop_runner.rs` | 两个 loop、`ToolResult`、terminal tool、signal 消费 | 在结果扁平化前构造 observation；统一 conversation/task 的 pre/post 接线 |
| `convergence.rs` | tools-disabled 复盘、成本计量、缓存友好注入 | 增加 semantic stall reason 和每 episode 最多一次约束 |
| `loop_state.rs` | typed error bucket、exhausted 决策、持久计数 | provider retry 与 task stall 分离；必要时复用 terminal 决策表达 |
| H05 mutation metadata | outcome、file_modified、final_version、changed_range | 只读消费，不改变 H05 输出 schema |
| `arc/main.py` / `acceptance.py` | failure signature、策略切换、最佳状态 | 原则上不改；仅验证 H07 结果不会破坏现有收敛 |

迁移决策：

| 机制 | 决策 | 理由 |
| --- | --- | --- |
| typed state/evidence/validation observation | 采用 | 正确率优先，减少文本误判 |
| exact args/result 快速检测 | 保留并修正顺序 | 成本接近零，对明显循环有效 |
| 忽略易变字段的等价失败签名 | 调整后采用 | 能发现参数抖动，但必须保留诊断差异 |
| 每步 LLM evaluator | 不采用 | 固定增加 token，且判断本身可能循环 |
| 每 episode 一次现有 convergence | 调整后采用 | 只在规则不足时支付模型成本 |
| 任意成功工具清空失败计数 | 不采用 | 无关 read 不能证明相关问题改善 |
| 全工具统一固定阈值 | 不采用 | 同步读取、验证、写入和异步等待风险不同 |
| provider 无限重试 | 不采用 | 确定性错误会无限消耗 token |
| 核心层重复外层测试/回滚 | 不采用 | 会产生冲突判断并扩大改动 |

## 8. 对照实验

### 8.1 先验证确定性不变量

在运行付费任务前，至少覆盖：

1. 同一文件、同一最终版本、同一读取范围连续返回时，第 2 个结果给提示，下一次 exact call 在执行前被拒绝。
2. 输出只改变时间戳、耗时、request ID 或临时路径时，仍归入同一 no-progress key。
3. 错误位置或 expected/actual 真正变化时，记 `evidence_changed`，不会立即终止。
4. H05 `no_change` 成功结果不增加 file churn，也不获得 productive grace。
5. `modified` 且最终版本变化只增加一次真实 mutation；重复同版本不重复计数。
6. 修改文件但验证失败签名不变时，只算 state change，不算 validation improvement。
7. 通过数增加或失败集合缩小时，相关 episode 被清除。
8. 无关成功 read 不清除 execute/validate 的失败 episode。
9. 有 live handle 的重复 poll 进入 verified wait；无 handle 的相同调用进入 no-progress。
10. provider rate limit/stream retry 不增加 task no-progress 次数。
11. conversation 与 task 对同一调用序列给出相同 detector 决定。
12. 一个 episode 最多产生一次付费 convergence；复盘后重复会终止。
13. terminal blocker 在当前 task 中不可通过改写无关参数自动重试。
14. observation 的条数、路径、文本摘要和候选证据严格有界。

还需要反误杀测试：

- 同一文件经过多次真实版本变化并最终通过验证，不应因“编辑次数多”提前终止。
- 分页读取每次得到新范围，应算 evidence change。
- 测试从初始化失败推进到业务断言失败，应允许针对新证据继续。
- formatter 改变最终文件时，以最终版本为准。
- flake 只改变不稳定测试时，不应掩盖稳定失败的停滞；外层现有规则继续负责最终判断。

### 8.2 再做机制 A/B/C

固定模型、需求、工具集合、预算、官方测试和初始仓库：

| 组别 | 内容 | 目的 |
| --- | --- | --- |
| A | 当前 `3fe3fce4` 行为 | 基线 |
| B | typed observation + 等价 key + 规则提示/拒绝；不新增模型复盘 | 验证零额外模型调用的主要收益 |
| C | B + semantic stall 时每 episode 最多一次现有 convergence | 判断付费复盘是否带来足够正确率收益 |

优先加入容易暴露差异的任务：

- 重复读取同一文件或目录；
- 对已是目标内容的文件重复 edit/write；
- patch 参数变化但持续 no-match/ambiguous；
- 重复运行相同失败命令，只改变日志噪声；
- 错误位置逐步变化的正常调试；
- 同一文件多次有效小修后测试才通过；
- 后台 job 合法轮询；
- provider 瞬时失败后恢复；
- 外层节点修复和 full-suite 已经负责切换策略的场景。

### 8.3 指标与采用门槛

指标顺序：

1. 最终官方测试通过数、全通过率、回归数和重复运行稳定性。
2. H07 误终止数：仍有新状态、新证据或验证改善却被拦截，目标为零。
3. H07 漏报数：相同 episode 在复盘后仍重复执行。
4. 全任务 provider 输入/输出 token，包含 convergence、失败请求、provider retry 和外层修复。
5. LLM 请求数、工具实际执行数、被执行前拒绝数、重复 read/no_change/edit/validate 次数。
6. 每类 observation、hint、strategy switch、terminal blocker 的计数与来源置信度。
7. 到首次 validation improvement 的 token，以及最终通过前的无进展 token 占比。
8. 时间和等待时长只作诊断，不计入成绩。

采用门槛：

- B 若在通过数和稳定性不下降时降低全任务 token，可先采用。
- C 只有在 B 基础上带来可重复的额外通过数，或显著减少更昂贵的后续修复，才采用付费复盘。
- 任一组出现稳定误杀有效多步修复，应先收紧该工具类别的判定，不用提高全局阈值掩盖问题。
- 不能以“少调用了工具”代替正确率，也不能以“单回合 token 下降”掩盖外层增加了更多修复轮。

真实环境实验前按项目约定执行 `source ~/.zshrc`，确认 `OCTOS_BIN` 指向记录的提交。付费官方实验还需要 `ARCBENCH_API_KEY`；若缺失，应明确记录为未运行，不能用单元测试结果替代。

## 9. 最终判断

H07 值得做，但不应扩展成新的通用 verifier 或另一套外层 repair controller。最小且可靠的方向是：

> **让现有 loop detector 从“比较原始调用字符串”升级为“比较有来源的任务观察”，再用一次有界策略切换处理规则无法判断的停滞。**

优先顺序应是：

1. 修正 conversation/task 接线差异和现有软硬阈值顺序。
2. 消费 H05 `no_change`、`file_modified` 和 `final_version`。
3. 引入 bounded `ProgressObservation` 与等价失败签名。
4. 将 exact 重复在执行前拒绝，减少无效工具调用及下一轮 prompt。
5. 对语义停滞最多触发一次现有 convergence。
6. 复盘后仍无进展则 typed 终止，并保持 provider retry 与外层验收收敛独立。

最直接的设计借鉴来自 Codex 的进展/等待定义、Claude Code 的窄范围熔断和 DeepSeek 的重试分层。三家的边界同样重要：没有公开证据支持每步模型评审，也没有理由把任意成功工具、文件写入或错误文字变化当作真实进展。

最终是否合入应由 A/B/C 的官方通过数、稳定性和全任务 token 决定，而不是由循环检测命中次数决定。

## 参考源码与官方文档

下列源码链接均固定到本次核查的提交。Octos 核心 H07 文件在当前 `3fe3fce4` 与主线 `27d057c2` 内容相同，因此使用主线链接；H05 typed mutation 元数据单独固定到当前分支提交。测试与文档链接只证明相应机制存在，不表示本次执行过竞品测试或 ARC 付费实验。

[o-loop-detector]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/loop_detect.rs#L1-L309
[o-conversation-precheck]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/loop_runner.rs#L1829-L1851
[o-result-recording]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/loop_runner.rs#L3365-L3407
[o-task-loop]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/loop_runner.rs#L2556-L2601
[o-signal-consume]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/loop_runner.rs#L2075-L2125
[o-file-churn]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/loop_detect.rs#L83-L149
[o-productive]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/loop_runner.rs#L3411-L3419
[o-convergence]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/convergence.rs#L1-L227
[o-retry-state]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/loop_state.rs#L1-L184
[o-mutation-report]: https://github.com/woshuoduijiushidui/octos-arc/blob/3fe3fce4c155f3e9ba8c762a2fc7bd3aa33daf3d/crates/octos-agent/src/tools/mutation_report.rs#L145-L205
[o-node-convergence]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/main.py#L2420-L2516
[o-suite-convergence]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/main.py#L3155-L3205
[o-failure-signature]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/acceptance.py#L377-L397
[cc-stop-hook]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/plugins/plugin-dev/skills/hook-development/SKILL.md#L181-L209
[cc-stop-cap]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L3371-L3375
[cc-compact-thrash]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L4494-L4499
[cc-compact-failure]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L4881-L4885
[cc-session-caps]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L2102-L2108
[cc-security-stop]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/plugins/security-guidance/hooks/security_reminder_hook.py#L1700-L1768
[cc-failure-hooks]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L4788-L4793
[cx-goals-feature]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/features/src/lib.rs#L1666-L1671
[cx-continuation]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/ext/goal/templates/goals/continuation.md#L1-L56
[cx-accounting]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/ext/goal/src/accounting.rs#L109-L229
[cx-retry-defaults]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/model-provider-info/src/lib.rs#L64-L65
[cx-sandbox-retry]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/src/tools/orchestrator.rs#L360-L490
[ds-agent-loop]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/core/agent-loop/README.md#L190-L200
[ds-base]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/bundle/base/cordis.patch.yml#L84-L96
[ds-goal-limits]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/goal/goal-round-driver/README.md#L119-L130
[ds-goal-default]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/goal/goal/src/index.ts#L239-L254
[ds-llm-retry]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/llm/llm-retry/README.md#L25-L58
