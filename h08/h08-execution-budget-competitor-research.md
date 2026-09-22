# H08 竞品调研：贯通并校准执行预算

- 调研日期：2026-09-22
- 优化表原分析基线：`c599d18c5acd2b846f049ffea2be84e72fe60fac`
- 本次复核的 Octos 主线：`27d057c206c0f8250b60309905737f7e26ee0ba9`
- 当前本地 H05 分支：`feat/local-edit`，已提交基点 `3fe3fce4`；本次未把尚未提交的 H05 工作纳入 H08 结论
- 调研对象：Anthropic Claude Code、OpenAI Codex、DeepSeek Harness
- 范围：只做源码与官方文档调研；未修改运行代码，未运行付费模型或官方任务实验。本文沿用 [H03 调研](../h03/h03-output-pagination-recovery-competitor-research.md) 的组织方式。

## 结论先行

H08 建议**调整后采用**。Octos 不缺预算开关，缺的是一份贯穿外层 Flow、stdio/MCP 入口、核心 Agent 和模型请求的统一预算事实。

当前最影响结果的不是某个阈值偏大或偏小，而是下面四件事同时存在：

1. 外层 Flow 有全任务 token/turn 守卫，但只在若干修复入口检查，且达到上限后的策略是统一停止后续修复。
2. 核心 Agent 已有迭代总量、累计 token、单次输出和推理强度四类配置，但实际入口没有完整传入。
3. 默认 ARC stdio `turn/start` 不传执行预算；它被核心识别为交互 turn，未配置时迭代上限为 `0`，所以外层的 `OCTOS_MAX_ITERATIONS=500` 只保证 chat 回退路径。
4. 代理层把所有响应的 `max_tokens` 至少抬到 32,768，再用请求次数到点后删除工具来结束 turn。这能避免过早截断，却不能为实现、修复和终检分别保留额度。

适合 Octos 的方案不是照搬竞品的固定数字，而是建立一个 **runtime-owned 的 typed 执行预算信封和累计账本**：

- **硬总上限**：约束全任务累计 provider 用量，所有正常响应、失败重试、压缩、续写和子任务都入同一账本。
- **软阶段信封**：实现、节点修复、回归修复、最终套件修复可以借用已节省额度，但不能占用最低交付保留额。
- **最低交付保留额**：至少覆盖最终全量测试后的一个证据驱动修复和一次复验；测试本身不消耗模型 token，但后续修复会消耗。
- **每次请求控制**：独立设置单次输出上限和推理强度。不能把累计任务预算、上下文窗口、思考预算和可见输出当成同一个数。
- **接近上限时收尾**：先提示和收敛，再禁止新探索；只有存在可验证进展且仍有已预留额度时才允许一次收尾调用。
- **typed 终态与检查点**：预算耗尽必须带 scope、维度、已用量、上限、保留额、阶段、最后进展和 partial usage；token 上限也要像迭代上限一样保留工作区成果。

三家最值得吸收的部分分别是：

- **Claude Code**：外层 turn/金额上限覆盖子代理，推理强度是独立成本旋钮。
- **Codex**：主线程与子代理共享累计账本、按剩余额度发提醒，并把上下文窗口预算与累计 rollout 预算明确分开。
- **DeepSeek Harness**：`maxTokens` 和 `reasoningEffort` 是逐请求可覆盖的 typed 配置，压缩、重试和用量记录都有明确边界。

三家都没有直接给出 Octos 所需的“固定需求树 + 分节点实现 + 官方测试 + 修复 + 最终套件”阶段分配器。Octos 的差异化价值应放在**交付保留额和基于真实进展的额度再分配**，而不是再增加一个统一硬切数字。

目前没有找到三家在相同 ARC 任务、模型和总预算下验证这些机制的公开对照数据。下文的收益是待测假设；仍按项目既定顺序评估：**最终测试通过数与稳定性优先，其次减少全任务累计 token，耗时不计入成绩。**

## 1. H08 到底解决什么问题

“预算”至少包含六种不同约束，不能共用一个字段：

| 预算维度 | 约束对象 | 达限后的正确动作 |
| --- | --- | --- |
| 全任务累计预算 | 从需求开始到最终交付的所有模型调用 | 停止新增工作，保留最佳状态，返回 typed 终态 |
| 阶段信封 | 实现、节点修复、回归修复、最终修复 | 软限制；有可验证收益时可借用，但不能侵占交付保留额 |
| turn 请求/迭代预算 | 一次 Agent 循环中的模型往返 | 提前提醒，最后一轮只收尾，不再探索 |
| 单次响应输出预算 | 一次 provider 响应的推理和可见输出 | 缩小任务或分块；截断不能伪装成成功 |
| 上下文窗口预算 | 当前请求的输入容量 | 压缩、裁剪或新窗口；它不是累计花费 |
| 推理配置 | 单次请求愿意投入的隐藏推理 | 按任务阶段和难度调节，不能只按剩余 token 粗暴关闭 |

H08 的直接边界是：

- H03 负责工具输出分页和原文恢复；H08 只保证这些元数据和恢复动作有请求额度。
- H06 负责验证失败后的修复流程；H08 决定修复是否能启动、最多可花多少，以及必须为后续复验保留多少。
- H07 负责识别无进展循环；H08 消费其进展信号来决定是否继续，不重新发明循环分类。
- H10 负责完整、可信地统计失败和重试消耗；H08 的累计硬上限依赖这份账。H10 未完成前，只能做接线与影子决策，不能宣称节省。
- H13 负责模型档位选择；H08 只给选定模型设置允许的输出和推理配置。

官方需求、测试集合和评分规则保持固定。不能通过少跑测试、隐藏失败、减少必要实现节点或把截断输出当作完成来获得“token 节省”。

## 2. Octos 当前已经有什么

### 2.1 核心 Agent 的预算能力比实际入口完整

`AgentConfig` 已经区分：

- `max_iterations`：一次 turn 的迭代上限，`0` 表示无限；
- `max_tokens`：一次 turn 的累计输入、输出和缓存 token 上限；
- `chat_max_tokens`：单次模型响应上限；
- `reasoning_effort`：推理强度；
- `max_timeout`：只在没有近期活动时触发的运行超时。

见 [AgentConfig][o-agent-config]。核心累计 token 口径把规范化后的 uncached input、output、cache read、cache write 相加，[预算检查][o-core-budget] 在进入下一轮前判定是否达限。因此触发上限的那次响应已经发生，仍可能超过上限一个请求；若要限制最坏超量，还必须同时约束单次输出，并在并发场景预占额度。

核心还已有三种收尾保护：

1. 迭代数约到 80% 时发送一次非强制提醒。
2. 达到迭代或累计 token 上限时，若此前有 productive tool call，可放行一次全局唯一 grace call，并明确要求本轮写出成果。
3. provider 返回 `MaxTokens` 时，task loop 最多续写两次；达到次数后返回失败，并保留已生成片段。

见 [预算提醒与 grace call][o-core-warning]、[输出截断续写][o-output-continuation]。这些机制方向正确，但目前彼此独立：

- 80% 是固定迭代比例，不知道还剩多少节点、测试和修复。
- grace call 只看“曾有 productive tool call”，不知道调用是否会挤掉最终修复保留额。
- 两次输出续写不检查全任务剩余额度；对于整文件 codegen，继续输出也未必能形成可落盘文件。
- dirty worktree 检查点只覆盖 `MaxIterations`，明确排除了 `MaxTokens` 和 timeout，[检查点实现][o-budget-checkpoint]。

### 2.2 ARC stdio 主路径没有接入外层迭代上限

外层创建 `OctosDriver` 时读取 `OCTOS_MAX_ITERATIONS`，chat 回退会把它作为 `--max-iterations` 传给 CLI，[driver 与 chat 回退][o-driver]。但默认 stdio 路径发送的 `turn/start` 只有 session、turn id 和文本输入，[stdio 请求][o-stdio-turn] 没有迭代、累计 token 或单次输出字段。

OUP 服务端按执行意图区分 turn：普通 `turn/start` 是 interactive，只有内部 continuation 才是 autonomous。未在 profile 配置时，interactive 的隐式迭代上限是 `AgentConfig` 默认值 `0`，[OUP turn 配置][o-oup-turn]、[turn policy][o-turn-policy]。因此：

> 默认 ARC 主路径中的 `OCTOS_MAX_ITERATIONS=500` 并没有成为核心 Agent 的 500 次上限。

这不等于运行完全无界。外层仍有每 turn 时间限制，代理层也可限制请求次数。但多个控制器对“还剩多少”的理解不一致，核心的 80% 提醒、grace call 和迭代耗尽检查点无法按外层设定工作。

reasoning 也存在类似的分层：OUP 已支持 turn 级 `reasoning_effort` 及持久化优先级，但当前 Python stdio 客户端没有发送它，主要依靠本地代理改写请求。

### 2.3 外层已有总量守卫，但不是阶段预算器

Python Flow 已有较成熟的时间分配：

- 总时间按节点数扩展；
- 每个节点按“剩余时间 / 剩余节点”得到基础份额；
- 已经省下的时间只借出一半，保留另一半给后续节点；
- 修复是否启动会参考真实修复耗时；
- 节点、回归检查和最终套件都受剩余时间约束。

见 [Flow 初始化与总量守卫][o-flow-budget]、[结余分配][o-banked-surplus]、[最终套件修复][o-final-repair]。这说明 Octos 已经有适合 token 预算复用的工作流骨架，不需要从竞品复制一个通用 agent 调度器。

token 侧目前只有：

- proxy 累加 `prompt_tokens + completion_tokens`；
- 默认上限按节点数计算；
- `wound_down()` 达限后不再进行修复，但剩余节点仍各做一次实现，最后仍跑一次全量测试；
- turn 数还有独立上限。

见 [成本守卫][o-flow-budget]、[provider 用量累计][o-proxy-usage]。问题是它只区分“还能修”与“不能修”，没有表达：

- 当前阶段可花额度；
- 必须为最终套件修复保留的额度；
- 已完成快节点节省了多少 token；
- 一次新请求最坏会花多少；
- 达限是哪个维度、哪些工作已完成、是否可安全恢复。

而且该总量只存在于 Python proxy。绕过 proxy、走 MCP、发生未记录 usage 的异常或将来引入子任务时，都可能出现不同口径。

### 2.4 代理层同时承担了输出、推理和请求次数策略

代理层当前会：

- 为 DeepSeek 请求注入 reasoning 配置；
- 将低于配置值的 `max_tokens` 统一抬高，默认最低 32,768；
- 记录每次 provider usage；
- 达到 turn 请求数后删除工具 schema，追加“立即总结”的用户消息。

见 [请求上限与输出下限][o-proxy-policy]、[代理请求处理][o-proxy-dispatch]。这解决过真实的 4,096 输出截断问题，但有三个 H08 风险：

1. **只有下限，没有按阶段的上限。** 简短验证、失败分类和小修复也获得 32,768 的响应空间。
2. **输出与推理共用 provider 上限。** reasoning model 可能先消耗大量推理额度，留给文件正文的空间仍不确定。
3. **到点才删工具。** 请求次数守卫不知道当前是否正在调查、修改、验证或交付，也不知道最终套件保留额。

因此代理层适合做 provider 兼容和最后一道执行保护，不适合作为唯一预算策略拥有者。

### 2.5 MCP 是最明确的接线缺口

MCP server 在启动时把 `max_iterations` 固定为 20，创建 Agent 时只覆盖该值和 `save_episodes`，其余 `max_tokens`、`chat_max_tokens`、`reasoning_effort` 均回落到默认值，[MCP 启动配置][o-mcp-budget]、[MCP Agent 配置][o-mcp-agent]。

这会造成两个问题：

- 外层调用者无法按任务规模或阶段传递预算。
- 同一个核心 Agent 的 typed 能力在 stdio、chat 和 MCP 三条入口上行为不同。

此外，MCP 的 `run_task` 错误分支仍返回默认零成本，[MCP 错误出口][o-mcp-error]。这属于 H10，但会直接污染 H08 的实验判断：未计量失败看起来既便宜又“及时停止”。

## 3. 竞品版本与证据边界

| 竞品 | 固定版本 | 可审计范围 | 本次重点 |
| --- | --- | --- | --- |
| Claude Code | [`8187baaa`](https://github.com/anthropics/claude-code/tree/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0)，2026-09-21 | 官方文档、CHANGELOG、插件；CLI 核心未公开 | turn/金额上限、子代理计费、thinking/effort |
| OpenAI Codex | [`e51aacad`](https://github.com/openai/codex/commit/e51aacad602dec4108db0d2f62bb7f40c6ced56c)，2026-09-21 | 公开 Rust 实现及测试 | 上下文预算、共享 rollout 预算、提醒和推理强度 |
| DeepSeek Harness | [`ddefc45f`](https://github.com/deepseek-ai/deepseek-harness/commit/ddefc45fbc7f8e46dd73185e68295696d1297887)，`0.1.6-alpha.2` | 公开 TypeScript 实现、默认 bundle 及测试；developer preview | 单次输出、逐请求推理、重试计量、压缩与 goal rounds |

Claude Code 的 [README][cc-readme] 说明该仓库不是完整 CLI 源码。因此本文只把官方文档描述为产品行为，不推断内部调度算法，也不声称滚动文档与固定 Git commit 完全同步。

Codex 的 `token_budget` 和 `rollout_budget` 在固定版本中都标为 `UnderDevelopment` 且默认关闭，[feature 定义][cx-features]。它们是值得研究的实现，不是稳定默认行为。

DeepSeek Harness 自身处于 alpha。它的模块边界和 typed 数据适合作为设计参考，但固定默认值没有 Octos ARC 任务上的公开校准证据。

## 4. 三家怎么做

### 4.1 Claude Code：外层限制清楚，但没有公开阶段分配算法

Claude Code 的非交互模式提供两种直接上限：

- `--max-turns`：限制 agentic turn 数，默认无限，达限以错误退出；
- `--max-budget-usd`：限制 API 调用金额，子代理花费计入；达到上限后拒绝新子代理并停止仍在运行的后台子代理。

见官方 [CLI flags][cc-cli]。Agent SDK 对应暴露 `maxTurns` 和 `maxBudgetUsd`，[SDK Options][cc-sdk] 还把 `effort`、`thinking` 和已弃用的 `maxThinkingTokens` 分开。

这带来三个可迁移原则：

1. 总预算应覆盖主任务和派生任务，而不是让每个子代理各自认为额度完整。
2. 达限必须影响仍在运行和新建的工作，不能只在主线程下一轮检查。
3. 轮次数和金额是两种约束，不能互相替代。

推理成本也被明确当成独立旋钮。官方成本文档说明 thinking 默认开启，thinking token 按 output token 计费；简单任务可以降低 effort 或关闭 thinking。固定 thinking 模型可用 `MAX_THINKING_TOKENS`，adaptive reasoning 模型忽略非零固定值，应改用 effort，[thinking 成本说明][cc-thinking]。

CHANGELOG 还能确认两个边界：

- `--max-budget-usd` 后来专门修复了后台子代理未被停止的问题，[预算修复][cc-budget-fix]。
- `--max-turns` 达限时，已排队消息的保留也需要专门修复，[turn 修复][cc-turn-fix]。

这说明“有一个上限字段”不等于所有并发、排队和恢复路径都已经受控。

**不适合直接照搬的部分：**

- 美元成本依赖模型价格和供应商计费，Octos 当前优化目标是跨任务比较 token，不应把价格当唯一真相。
- 固定 turn 上限不知道当前 turn 是调查、编码、修复还是最终交付。
- 官方公开材料没有阶段保留额，也没有可审计的“何时允许超出某阶段额度”算法。

### 4.2 OpenAI Codex：把上下文余量与全局累计预算分开

Codex 固定版本里有两个名称相近但语义不同的机制。

**`token_budget` 是上下文窗口预算。** 它根据当前 context window 的剩余空间注入提醒，并可在余量为零时留出 fallback prompt 缓冲，[上下文预算逻辑][cx-token-budget]。模型 metadata 默认只把 context window 的 95% 视为可用输入，auto compact 上限最多为窗口的 90%，[模型窗口计算][cx-context-window]。

这解决的是“当前请求还能放多少历史”，不是“整个任务已经花了多少 token”。把它拿来做 H08 总量守卫会混淆重复输入成本和上下文占用。

**`rollout_budget` 才是累计任务账本。** 它由 root session tree 的 `AgentControl` 共享：

- 优先使用 provider 返回的 `codex_rollout_budget_units`；
- 否则按 `output × sampling_weight + non_cached_input × prefill_weight` 累加；
- 每个 thread 都会收到越过阈值后的剩余额度提醒；
- 压缩进入新 context window 后会重新陈述当前剩余量，而不会重置累计账；
- 达限返回 typed `SessionBudgetExceeded`。

见 [共享账本][cx-rollout-budget]、[typed 达限][cx-rollout-stop]、[提醒注入][cx-rollout-reminder]。测试明确覆盖子代理使用同一预算、压缩调用计入预算，以及新窗口重述剩余额度，[rollout 测试][cx-rollout-tests]。

这里最值得 Octos 借鉴的是**共享身份和提醒确认**，不是其具体权重。提醒只有成功写入历史后才标记已投递，取消不会永久吞掉提醒。

但当前实现并不是严格的请求前硬上限。用量在 provider 返回完成事件后才记录并抛出 `SessionBudgetExceeded`，[usage 记录位置][cx-rollout-record]；测试甚至让预算耗尽后的下一 turn 再收到一个 provider 响应，然后再次报错。也就是说，达到上限的响应已经付费，后续若没有更外层的准入检查还可能继续付费。Octos 不能直接复制这一点。

Codex 对 reasoning 的处理强调缓存稳定性：同一 context window 内固定请求 effort，成功压缩后才建立新基线；review 换模型时若原 effort 不受支持，会选择该模型支持列表的中间档或默认档，[effort pin][cx-effort]、[review 适配][cx-review-effort]。这比按每次请求随意改变 effort 更稳，但它优化的是通用会话和缓存。Octos 的固定阶段边界更清楚，可以只在阶段切换或新 session 开始时改变，而不必在一个 warm prefix 中频繁抖动。

### 4.3 DeepSeek Harness：逐请求控制完整，但没有全任务硬上限

DeepSeek Harness 的 Agent 选项直接暴露 `reasoningEffort` 和 `maxTokens`，其中 `maxTokens` 明确定义为每次 conversation request 的最大输出，[Agent options][ds-agent-options]。每一步请求都经过 `agent/request` waterfall，插件可在发送前覆盖配置；有效值随后写入 request header 并用于请求，[逐请求解析][ds-agent-request]。

DeepSeek provider 默认：

- reasoning effort 为 `high`，也可设 `off/low/high/max`；
- 每次输出默认上限 256,000；
- Messages 协议把 `maxTokens` 映射为 `max_tokens`，session title 强制关闭 thinking；
- 不同 provider/model 可通过请求 waterfall 改写。

见 [provider 配置][ds-provider-config]、[Messages 序列化][ds-messages-request]。这证明“推理”和“单次输出”应该是 typed、逐请求可见的配置，不应只在透明代理里隐式改写。

达到 `max-tokens` 后，Agent 会把该状态设为 sticky turn 终态，不自动续写；被截断的 tool call 会从可执行 block 中删除，避免执行半截 JSON，[Agent 终态][ds-agent-stop]、[截断 tool call][ds-truncated-tool]。这比把不完整 tool call 当成功安全，但对整文件生成不够：核心不会自动恢复可见文本，也不会判断重试是否值得。

它的 token meter 会把 provider usage 按 uncached input、output、cache read、cache write 分桶累计。`llm/retry-started` 会关闭当前 attempt 的替换槽，使下一次重试作为新增消耗计入，[用量 fold][ds-token-meter]。默认 transient retry 最多 5 次，[重试策略][ds-retry]。因此它能记录重试成本，却没有在所查默认组合里发现一个使用累计值拒绝新模型调用的 run-wide token/currency budget。

上下文压缩是另一套独立机制：默认在 routed context window 的 80% 触发，保留最近 16%，摘要输出最多 8,192 token，并允许一次额外压缩尝试，[压缩策略][ds-compaction]。其文档也明确承认这些比例尚无语料校准、估算对 CJK 和 JSON Schema 可能偏低，[压缩边界][ds-compaction-limits]。这些数字不应复制成 Octos 的执行预算比例。

DeepSeek 的长期 goal 默认最多 256 rounds，但官方文档明确说明它只限制轮数，不计量 token、货币、时间或 provider quota，[goal 默认值][ds-goal]、[goal 边界][ds-goal-limits]。这再次说明“能自动跑很多轮”不等于“有累计成本控制”。

## 5. 横向对比

| 维度 | Claude Code | OpenAI Codex | DeepSeek Harness | 对 Octos 的判断 |
| --- | --- | --- | --- | --- |
| 全任务累计上限 | `maxBudgetUsd`，含子代理 | feature-gated shared weighted rollout budget | 未发现默认 run-wide token/currency cap | 需要自己的统一 token 账本 |
| turn/round 上限 | `maxTurns`，默认无限 | 主要依赖累计预算与其他 loop 控制 | goal 有 round cap，但明确不是 token 预算 | 只作安全后备，不能承担阶段分配 |
| 单次输出上限 | SDK 公开 thinking 配置；CLI 未公开通用逐阶段输出策略 | 所查 Responses 主路径未见通用用户级 output cap | `maxTokens` typed 且逐请求可覆盖 | Octos 应直接贯通 `chat_max_tokens` |
| 推理控制 | effort + adaptive/fixed thinking | effort 按 context window 固定，review 适配模型能力 | `reasoningEffort` 逐请求可覆盖 | 应按阶段切换，并遵守 provider 能力 |
| 上下文压力 | auto compact，与成本统计分开 | 95% 可用窗口、最多 90% auto compact | 80% 触发、保留 16% | 不能拿 context occupancy 代替累计花费 |
| 接近总上限 | 金额/turn 达限停止 | 剩余额度提醒，达限 typed error | 无统一累计提醒 | 采用多级提醒，但阈值由剩余工作推导 |
| 子任务与重试 | 子代理计入金额上限 | root 和 subagents 共用账本 | retry 被计量但没有累计拒绝器 | 所有派生调用必须共享 run id 和账本 |
| 达限成果保护 | 公开资料未给出通用算法 | typed error；未见工作区检查点设计 | max-tokens 保留安全文本、丢弃 tool call | 扩展 Octos 已有检查点到所有预算终态 |
| 阶段保留额 | 未公开 | 未发现固定工作流保留额 | 未发现 | Octos 最应补的差异化能力 |

共同经验是：

1. 预算必须由 harness 强制，不能只靠 prompt。
2. 模型要看见剩余量和收尾要求，但提醒不能代替执行层上限。
3. 推理、输出、上下文和累计消耗必须分别表达。
4. 重试、压缩、子任务和后台工作都是实际消耗，不能在主账之外。
5. 达限要有 typed 终态，不能把部分结果包装成成功。

共同缺口是：三家都没有公开一套可直接迁移到 Octos 固定阶段流程的“交付保留额 + 按测试进展借用额度”策略。

## 6. 适合 Octos 的目标设计

### 6.1 先定义一个唯一预算信封

建议由 Python Flow 创建 run 级信封，核心 Agent 只消费本 turn 的派生视图。概念结构如下：

```text
ExecutionBudgetEnvelope
  run_id
  phase: design | implement | node_repair | regression_repair | final_repair | final_check
  cumulative_limit
  cumulative_used
  reserved_for_delivery
  phase_soft_limit
  turn:
    max_iterations
    max_requests
    max_tokens
  response:
    max_output_tokens
    reasoning_effort
  accounting:
    include_retries = true
    include_compaction = true
    include_subtasks = true
```

这里的 `cumulative_used` 是账本快照，不允许调用方自行回写。所有入口只携带 `run_id` 和本次派生额度，真正累计由一个 runtime owner 完成。

配置优先级建议固定为：

> 显式本 turn 覆盖 > Flow 阶段策略 > profile/gateway 配置 > provider 默认

任何层都只能进一步收紧全任务硬上限，不能把调用方传入的剩余总量重新放大。

### 6.2 总账与上下文账必须分开

建议至少记录四个互斥 provider bucket：

```text
uncached_input
cache_read
cache_write
output
```

若 provider 另有 reasoning token，它应作为 output 的可解释子集记录，不能再次加到总量中。未知用量必须标成 unknown，不能按零处理。

同时维护但绝不混算：

- `context_occupancy`：当前请求能否装下，用于压缩；
- `cumulative_usage`：整个 run 已经付出的处理量，用于 H08；
- `response_allowance`：下一次最多允许生成多少，用于控制最坏超量。

这部分应直接复用核心 `TokenUsage` 规范化和 H10 的 partial usage，不在 Python 与 Rust 各写一套不同公式。

### 6.3 用交付保留额替代统一硬切

当前 `wound_down()` 达限后统一关闭修复，容易出现“前面节点都实现了，但最终套件发现回归却没有额度”的情况。建议把可用量定义为：

```text
spendable_now =
  cumulative_limit
  - cumulative_used
  - reserved_for_delivery
  - admitted_in_flight
```

`reserved_for_delivery` 不采用固定百分比，而由剩余工作估算：

- 最终全量测试本身不需要模型 token；
- 至少一轮最终修复的预计输入；
- 该轮允许的推理与输出；
- 修复后的必要复验或失败分类；
- 已知会发生的压缩/恢复开销。

估算先用同类阶段最近若干次的 provider usage 中位数或保守分位数；样本不足时用显式静态下限。它与现有 `repair_durations` 的思路一致，但统计对象改为 token。

阶段信封是软的：

- 快节点节省的额度进入 bank；
- 有新测试通过、失败集合缩小、有效文件变化等可验证进展时，可以借用 bank；
- 无进展、重复截断或重复 provider 错误不能借；
- 任何借用都不能突破全任务硬上限和最低交付保留额。

这比“每节点固定 N token”更适合难度高度不均的需求树，也延续了现有 `banked_surplus()` 的保守规则。

### 6.4 请求准入必须发生在 provider 调用前

只在响应回来后检查会天然超量。每次请求前应执行：

1. 刷新已结算 usage，并确认没有 unknown 的在途结果。
2. 为并发请求预占额度；当前 Flow 大多串行，但 MCP/子任务不能假设永远串行。
3. 估算输入成本，结合本次 `max_output_tokens` 得到最坏可控增量。
4. 若不足以完成一个“最小有用动作”，不发请求，直接进入收尾或 typed budget exhaustion。
5. provider 返回后用真实 usage 对账，释放预占差额。

输入 token 在 provider 回报前可能只能估算，因此所谓硬上限应诚实说明误差边界。最坏超量必须被单次输出上限和最大并发数共同约束，不能宣称绝对零超量。

### 6.5 每个阶段独立设置推理与输出

不建议继续让所有请求统一获得至少 32,768 输出 token。建议先按工作形状设策略，再通过实验校准具体数值：

| 阶段 | 推理策略 | 输出策略 |
| --- | --- | --- |
| 设计/复杂根因定位 | 中或高；仅在输入证据复杂时提高 | 中等，要求结论短、不要重写源码 |
| 小节点首次实现 | 低或关闭；简单度由需求和现有代码共同判断 | 按预计变更规模给足，优先局部编辑 |
| 大节点首次实现 | 中；复杂接口或多文件时再提高 | 按文件/补丁分块，不靠一个巨大统一上限 |
| 测试失败分类 | 低到中 | 小，输出只需定位和下一步 |
| 有证据的修复 | 中；重复失败且证据变化时可提高一次 | 覆盖局部修改，不为长解释付费 |
| 最终收尾 | 不新增探索；必要时低推理 | 只允许完成当前写入或简短交付说明 |

对 adaptive reasoning provider 使用 effort，不尝试设置无效的固定 thinking token。对“thinking 与可见输出共享上限”的 provider，必须验证最终可见代码空间，不能只看 `max_tokens` 数值。

### 6.6 接近上限时按状态收敛

固定 80% 提醒可保留为兜底，但主要阈值应由剩余工作决定：

- `remaining > reserve + next_phase_estimate`：正常执行；
- `remaining <= reserve + next_phase_estimate`：进入 conserve，减少探索、降低无必要推理、禁止无证据重试；
- `remaining <= reserve`：停止普通实现/节点修复，只允许最终测试、已开始写入的安全完成和保留额内的最终修复；
- `remaining < minimum_useful_request`：不再发模型请求，保存最佳状态并返回 typed 终态。

grace call 只能在同时满足下列条件时放行：

- 自上次提醒后有可验证进展；
- 当前有明确、可完成的交付动作；
- 已为这次调用预占额度；
- 不侵占最终交付保留额；
- 全 run 只允许一次，不因每次工具成功而刷新。

### 6.7 达限必须保留成果并说明为什么

建议统一终态：

```text
budget_exhausted
  scope: run | phase | turn | response
  dimension: cumulative_tokens | iterations | requests | output_tokens | time
  limit
  used
  reserved
  phase
  last_progress
  partial_usage
  checkpoint
  remaining_work
```

工作区有变更时，累计 token、迭代、请求次数和时间达限都应走同一检查点策略；clean worktree 不制造空提交。provider 已返回部分输出时，保留 partial response 和 finish reason，但未完整生成的 tool call 不执行。

对 ARC Flow，最终交付仍以实际测试和最佳 git 状态为准。预算耗尽不能覆盖一个更好的已验证版本，也不能把“保存了 WIP”写成“任务完成”。

## 7. 最小改动与迁移判断

建议分三层落地，避免一次重写整个 harness。

| 层级 | 最小改动 | 复用能力 | 迁移判断 |
| --- | --- | --- | --- |
| 入口接线 | 扩展 OUP `turn/start` 和 MCP 请求的可选预算字段；chat 回退保持兼容 | `AgentConfig`、已有 reasoning turn override | **采用** |
| 核心执行 | 将预算派生值写入 `AgentConfig`；统一 typed stop；所有预算 stop 走检查点 | `check_budget`、80% 提醒、grace、partial usage、checkpoint | **调整后采用** |
| Flow 分配 | 建 run ledger、阶段信封和最终交付保留额；proxy 降为兼容/执行层 | `wound_down`、`banked_surplus`、repair duration、best-state restore | **调整后采用** |
| 单次请求 | 按 phase 传 `chat_max_tokens` 和 `reasoning_effort`，替代统一 output floor | model routes、proxy injection、provider capability | **调整后采用** |
| 上下文 | 继续由 ContextManager/compaction 管理，不计入阶段剩余量 | H01/H03/H04 机制 | **保持独立** |
| 计量 | 所有异常、重试、压缩和子任务归入同一 run id | `TokenUsage`、proxy usage、H10 partial usage | **H10 前置** |

首轮实现不需要：

- 引入美元价格调度；
- 复制 Codex 的 weighted provider units；
- 复制 DeepSeek 的 80%/16% 压缩比例；
- 让模型自行修改预算；
- 建立通用多代理调度器；
- 改变官方需求、测试或判分。

建议的兼容策略是所有新字段可选。未提供信封时保持当前行为；提供信封时由入口记录最终 resolved 配置，便于确认“配置写了但没有生效”。

## 8. 对照实验

### 8.1 先做无模型的接线与不变量验证

在付费实验前，用 mock provider 覆盖：

1. stdio、chat fallback、MCP 对同一个预算信封解析出相同的 `AgentConfig`。
2. 显式 turn 值覆盖 phase/profile 默认；总硬上限不能被下游放大。
3. 正常响应、失败响应、retry、compaction、输出续写和子任务都只计一次且都计入 run 总账。
4. reasoning token 若已包含在 output 中不重复相加。
5. 达到 soft phase 信封但仍有 bank 时可以借用；没有进展时拒绝借用。
6. 普通阶段不能消耗 `reserved_for_delivery`。
7. 达限前只投递一次提醒；取消前未成功入历史的提醒可重试。
8. 并发请求先预占，不能各自看到同一份完整余额。
9. `MaxTokens`、累计 token、迭代和时间达限都能保留 dirty worktree；clean worktree不生成空提交。
10. 任何 unknown usage 都不能被当作零，也不能产生“节省”结论。

### 8.2 再做分阶段实验

建议按因果关系逐步比较，而不是一次打开所有策略：

| 组别 | 变化 | 目的 |
| --- | --- | --- |
| A | 当前行为 | 基线 |
| B | 只贯通字段和统一记账，保持当前有效阈值 | 证明接线不改变结果 |
| C | B + 阶段软信封 + 最终交付保留额 + typed 收尾 | 测试预算重新分配 |
| D | C + 按阶段的 reasoning/output 配置 | 测试 token 优化 |

B 必须先与 A 在相同随机条件下等价，才能把 C/D 的变化归因于策略，而不是入口差异。

固定项：

- 官方需求、测试集合和评分条件；
- 模型与 provider 版本；
- 初始模板和仓库提交；
- 工具集合、H01-H07 开关和 session scope；
- 并发度、机器资源和网络重试策略；
- 每组重复次数。

主要指标按优先级排序：

1. 最终通过数。
2. 多次运行的通过稳定性。
3. 全任务累计 provider token，分 uncached input、cache read、cache write、output 和 reasoning 子集。
4. 每个新增通过测试消耗的额外 token。
5. 截断次数、失败重试次数、无进展修复次数、预算终态数量。
6. 到最终套件时剩余 token、实际使用的交付保留额、被保留额救回的测试数。

判定规则：

- 通过数下降时，不因 token 更少而采用。
- 通过数相同且稳定性不降时，再比较累计 token 的中位数和尾部。
- 通过数提高但 token 增加时，先保留正确率收益，再单独优化 reasoning/output；不能用总 token 单指标否决。
- 少跑测试、跳过节点、截断未落盘或漏记失败 usage 不算节省。

### 8.3 需要专门覆盖的任务形状

- 小任务：验证阶段策略不会因预算框架本身增加大量固定输入。
- 多节点任务：验证快节点节省额度可被难节点借用，同时最终套件仍有保留额。
- 大文件 codegen：验证 output cap 足够落盘，且截断后不会无条件再花两次完整响应。
- 工具模式长调查：验证接近上限时能从探索切到写入。
- 多轮修复：验证只有失败集合缩小或有效代码变化时才继续。
- provider transient error：验证每次付费 retry 都计入总账。
- MCP 任务：验证不再固定 20 次且错误出口不显示零成本。

## 9. 最终判断

H08 的决策是：**采用统一预算信封与账本，调整后采用竞品的提醒、共享累计和逐请求控制，不采用任何竞品的固定阈值。**

实施顺序应为：

1. 先完成 H10 所需的可靠计量，并把 stdio、MCP、chat 的已有字段贯通。
2. 保持当前阈值做等价验证，确认每条实际入口使用了预期配置。
3. 加入最终交付保留额和基于进展的软阶段信封。
4. 最后单独校准 reasoning 和单次输出，避免把接线、分配和模型行为混成一个实验。

最重要的不变量是：

> **预算策略可以让昂贵请求更少，但不能让最终测试、可恢复成果和必要修复先消失。**

## 参考源码与官方文档

### Octos

[o-agent-config]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/mod.rs#L65-L110
[o-core-budget]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/budget.rs#L83-L145
[o-core-warning]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/loop_runner.rs#L1240-L1296
[o-output-continuation]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/loop_runner.rs#L2951-L2982
[o-budget-checkpoint]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/budget.rs#L577-L623
[o-driver]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/main.py#L684-L730
[o-stdio-turn]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/octos_stdio.py#L188-L198
[o-oup-turn]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/api/ui_protocol_transport.rs#L32922-L32971
[o-turn-policy]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/runtime/turn_policy.rs#L1-L49
[o-flow-budget]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/main.py#L1488-L1605
[o-banked-surplus]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/main.py#L2661-L2706
[o-final-repair]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/main.py#L3055-L3264
[o-proxy-policy]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/llm_proxy.py#L338-L380
[o-proxy-dispatch]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/llm_proxy.py#L485-L541
[o-proxy-usage]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/llm_proxy.py#L672-L690
[o-mcp-budget]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/commands/mcp_serve.rs#L145-L164
[o-mcp-agent]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/commands/mcp_serve.rs#L575-L605
[o-mcp-error]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/commands/mcp_serve.rs#L671-L682

### Claude Code

[cc-readme]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/README.md#L46-L50
[cc-cli]: https://code.claude.com/docs/en/cli-reference#cli-flags
[cc-sdk]: https://platform.claude.com/docs/en/agent-sdk/typescript#options
[cc-thinking]: https://code.claude.com/docs/en/costs#adjust-extended-thinking
[cc-budget-fix]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L2001-L2004
[cc-turn-fix]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L2341-L2345

### OpenAI Codex

[cx-features]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/features/src/lib.rs#L1665-L1689
[cx-token-budget]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/src/session/token_budget.rs#L161-L224
[cx-context-window]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/protocol/src/openai_models.rs#L452-L536
[cx-rollout-budget]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/src/rollout_budget.rs#L18-L112
[cx-rollout-stop]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/src/agent/control/budget.rs#L11-L35
[cx-rollout-reminder]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/src/session/rollout_budget.rs#L7-L33
[cx-rollout-record]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/src/session/mod.rs#L4616-L4661
[cx-rollout-tests]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/tests/suite/rollout_budget.rs#L31-L466
[cx-effort]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/src/session/reasoning_effort.rs#L93-L157
[cx-review-effort]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/src/session/review.rs#L45-L70

### DeepSeek Harness

[ds-agent-options]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/core/agent/src/runtime-types.ts#L27-L35
[ds-agent-request]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/core/agent-loop/src/agent.ts#L501-L600
[ds-agent-stop]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/core/agent-loop/src/agent.ts#L353-L493
[ds-provider-config]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/llm/llm-deepseek/src/config.ts#L17-L65
[ds-messages-request]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/llm/llm-deepseek/src/protocols/messages/serialize.ts#L121-L138
[ds-truncated-tool]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/llm/llm/src/assembler.ts#L108-L166
[ds-token-meter]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/llm/token-meter/src/usage-projection.ts#L14-L150
[ds-retry]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/llm/llm/src/retry-policy.ts#L14-L103
[ds-compaction]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/compaction/compaction-basic/README.md#L58-L75
[ds-compaction-limits]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/compaction/compaction-basic/README.md#L228-L257
[ds-goal]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/goal/goal/README.md#L12
[ds-goal-limits]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/goal/goal/README.md#L151-L160
