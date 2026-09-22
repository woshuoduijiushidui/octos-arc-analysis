# H06 竞品调研：验证失败后聚焦修复

- 调研日期：2026-09-22
- 优化表原分析基线：`c599d18c5acd2b846f049ffea2be84e72fe60fac`
- 本次复核的 Octos 主线：`27d057c206c0f8250b60309905737f7e26ee0ba9`
- 当前 H05 分支已提交基线：`3fe3fce4c155f3e9ba8c762a2fc7bd3aa33daf3d`
- 调研对象：Anthropic Claude Code、OpenAI Codex、DeepSeek Harness
- 范围：只做源码与官方文档调研；未修改运行代码，未运行付费模型或官方任务实验。本文沿用 [H03 调研](../h03/h03-output-pagination-recovery-competitor-research.md) 的组织方式。

## 结论先行

H06 建议**调整后采用**，首要落点是 **MCP 交付验证**，不是重写 Python ARC 已有的验收修复流程。

适合 Octos 的核心约定是：

> **模型准备结束时，先运行独立、确定性的允许检查。只有可定位、可由工作区修改修复的失败，才把有界 typed 证据追加回当前任务；每次修复后必须重新验证，最终成功只能由检查结果决定。**

具体建议：

1. 借鉴 **Claude Code 和 Codex 的终止拦截**：在模型自然结束、但 harness 尚未宣布成功的边界运行验证；失败反馈追加到当前消息历史，再继续同一个任务。
2. 借鉴 **Codex 的来源化反馈和有界 spill**：失败项保留 validator ID、状态、原因和证据引用，正文有上限；不把整段日志反复塞回 prompt。
3. 借鉴 **DeepSeek 的追加式续行、持久事件和显式 round cap**：修复轮次有来源、可审计、有硬上限；但不能依赖模型自行宣布目标完成。
4. 复用 Octos 已有 `ValidatorOutcome`、artifact/schema 检查、workspace contract、token 统计和文件状态；不再增加一次 LLM “评审”来判断确定性测试是否通过。
5. 默认最多允许 **2 次聚焦修复**。第 2 次只在第 1 次确实修改了候选结果，且出现可测进展或使用唯一一次“同签名但改变策略”的机会时进入。每轮均重跑完整 hard-required gate，成功前不能只重跑原失败项。
6. 配置错误、provider 错误、沙箱不可用、非法 `arc_task`、validator `Timeout/Error`、取消和预算耗尽默认直接失败。它们不是代码证据，不应浪费模型修复 token。
7. 修复失败时保留验证表现最好的工作区快照，但仍返回 `Failed`；“保留较好产物”不能被解释成通过交付门禁。

Python `arc/main.py` 已经具备“运行验收 → 反馈失败 → 有限修复 → 检测停滞/回归 → 保留最佳状态 → 全量回归”的完整闭环。H06 应把其中经过实践的原则迁移到 MCP/core 的交付边界，而不是建立第二套 Python 流程。

目前没有找到三家在相同 ARC 任务、模型、预算下独立验证这类修复闭环收益的公开 A/B 数据。下文的正确率和 token 收益均为待测假设；**最终测试通过数与稳定性优先，全任务累计 token 次之，耗时不计入成绩**。

## 1. H06 到底解决什么问题

H06 处理的不是普通工具报错重试，而是下面这个时间点：

1. 合法任务已经进入 Agent。
2. 模型认为工作完成并准备结束。
3. harness 运行允许的构建、交付格式、artifact/schema 或已提供验收检查。
4. 检查发现一个可修复问题。
5. harness 应在有限预算内，把失败证据交还给当前任务修复，而不是立刻向外层返回 `Failed` 并让整个阶段重跑。

必须区分四类行为：

| 行为 | 例子 | H06 处理 |
| --- | --- | --- |
| 确定性交付检查 | required validator、artifact 是否存在、JSON/schema 是否合法 | 失败可形成修复票据 |
| 模型修复 | 修改源码、配置或交付文件 | 只在同一合法任务和原权限内执行 |
| harness/基础设施恢复 | provider 临时错误、validator 进程无法启动、沙箱不可用 | 不交给模型；沿用对应重试或直接失败 |
| 外部最终判分 | 未提供给任务的隐藏测试、官方评分器 | 不新增访问，不把隐藏证据泄露给模型 |

边界如下：

- H01/H03 负责失败证据在压缩、截断后仍可信和可恢复；H06 消费这些证据，不自己猜测被丢失的日志。
- H05 负责尽量用局部编辑完成修复；H06 只决定何时修、为什么修和何时停。
- H07 负责更通用的循环识别；H06 首版只需要验证签名、文件变化和轮次上限三个确定性信号。
- H08 负责贯通总 token/请求预算；H06 在它完成前不能私自扩大任务总预算，只能在现有预算内设修复轮次上限。
- H10 负责失败与重试用量口径。H06 的每次验证和模型续行必须单独记账，否则无法判断净收益。
- 官方需求、检查命令、测试集合和判分条件保持固定。不能通过删测试、降 required tier、修改 schema 或伪造 artifact 来“修复”失败。

## 2. Octos 当前已经有什么

### 2.1 Python ARC 已经是可复用的参考闭环

当前 H05 分支的 `arc/main.py` 已有成熟的节点级验收循环：

- 构建/启动失败会形成短的启动错误摘要；
- 测试失败使用结构化失败摘要和测试来源上下文；
- 修复轮数和剩余时间都有上限；
- 相同失败会结合“上轮是否真正写入”判断，避免把未执行的修复误判成错误策略；
- 连续停滞会停止，连续回归会恢复较好的 Git 状态；
- 只有在此前没有任何已验证行为时，才允许一次完整重写；
- 最终失败会恢复已知较好的验收状态。

见 [节点验收循环][o-python-node]。最终验收还会把全部 spec 放到同一服务上运行，发现跨节点干扰，记录最佳 full-suite round，并在末轮更差时恢复最佳提交，见 [最终全量验收][o-python-final]。

这说明 H06 的基本方向不是理论空白。对 MCP 值得迁移的是：

1. 失败证据聚焦；
2. 修复次数有限；
3. 相同失败和无写入分开判断；
4. 回归不能覆盖更好结果；
5. 最后必须由同一组确定性检查重新判定。

不应直接迁移 Python 的具体环境变量、时间阈值或“零通过时整套重写”。MCP 的 artifact/schema 失败通常更局部，完整重写会扩大 token 和回归风险。

### 2.2 core 已经有终止拦截形状，但用途不同

`Agent::run_task` 在收到 `EndTurn` 时，已经会调用可选的 `verifier_allows_termination`；若 verifier 不允许结束，就向当前 `messages` 注入说明并继续循环，见 [task loop 终止位置][o-task-end] 和 [verifier 实现][o-llm-verifier]。

这个控制流可以借鉴，但现有 verifier 不是 H06 的判分器：

- 它是可选的额外 LLM 调用；
- verdict 来自模型，而不是构建、validator 或 schema 的确定性结果；
- 它在 workspace contract 检查之前运行；
- 对确定性失败再调用一个模型判断，会增加 token，也可能把明确失败误判为可结束。

因此 H06 应复用“阻止结束并追加反馈”的结构，不应把 `ValidatorOutcome` 转交给现有 LLM verifier 再裁决。

### 2.3 core workspace contract 已验证，但失败后直接返回

当前 `run_task` 在模型结束后运行 project-root validators，再读取 workspace contract。若 contract 未就绪，它把 `TaskResult.success` 降为 `false`、把失败文本追加到输出，然后立即返回，见 [workspace contract 终检][o-core-contract]。

这已经满足“不能把失败误报为成功”，但还没有 H06 的同任务修复：

- 检查发生时，当前 `messages` 仍在 `run_task_inner` 内；
- 代码却先构造失败结果并退出；
- 调用方只能拿到终态文本，不能让同一轮历史继续。

这里是接入确定性 completion gate 的第一个实际位置。

### 2.4 MCP 的验证证据够用，但每个失败分支都直接结束

当前 H05 分支的 MCP 路径：

1. 在构建 provider 前解析并校验 native `arc_task`；非法输入直接拒绝，见 [MCP 输入边界][o-mcp-input]。
2. 调用一次 `agent.run_task`。`Err` 或 `success=false` 都直接形成 Failed，见 [MCP task 结果处理][o-mcp-task]。
3. 任务成功后才运行 completion validators、解析 artifact、校验安全位置和 response schema。
4. required validator、artifact 缺失、位置错误或 schema 错误分别直接返回 Failed，见 [MCP 交付门禁][o-mcp-gates]。

validator status 已区分 `Pass/Fail/Timeout/Error`；`ValidatorOutcome` 还包含 required tier、原因、证据路径和 stderr tail，required gate 的判断也是 typed 的，见 [validator status][o-validator-status] 和 [validator outcome][o-validator-outcome]。H06 不需要从英文总错误里重新解析这些字段。

当前缺口是控制流而不是证据格式：验证位于 `run_task` 返回之后，失败后已经失去 `run_task_inner` 的局部消息历史。

### 2.5 现有 spawn recovery 可复用框架，不能直接充当 H06

spawn 路径已有一次性 `run_task_with_m8_9_recovery`：首次 `Err` 或 `success=false` 后，复用同一个 worker，再创建一个包含原任务和自由文本失败信息的新 `Task`，见 [spawn recovery][o-spawn-recovery]。

它适合说明“有限重试、复用 Agent 状态”已有先例，但不够承载 H06：

- `run_task_inner` 每次调用都会重新执行 `build_initial_messages(task)`，见 [task 消息初始化][o-task-init]；复用 worker 不等于保留首轮局部 message vector。
- recovery prompt 重新拼入完整原任务，增加重复输入。
- `Err`、预算失败和 contract failure 被统一成自由文本，没有 repairable 分类。
- 它没有 MCP validator/artifact/schema 的 typed 证据。
- 它没有每轮重验、最佳候选和验证签名。

因此可以复用其一次性 wrapper、状态复用和调用方记账思路，但 H06 的主路径仍应在 Agent 终止边界内继续。

## 3. 竞品版本与证据边界

| 竞品 | 固定版本 | 可审计范围 | 本次重点 |
| --- | --- | --- | --- |
| Claude Code | [`8187baaa`](https://github.com/anthropics/claude-code/tree/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0)，2026-09-21 | 官方 hooks 文档、CHANGELOG、公开插件；CLI 核心未公开 | Stop/TaskCompleted 阻塞、递归保护、循环上限 |
| OpenAI Codex | [`e51aacad`](https://github.com/openai/codex/commit/e51aacad602dec4108db0d2f62bb7f40c6ced56c)，2026-09-21 | 公开 Rust 实现、官方文档和测试 | typed Stop 聚合、同 turn 续行、反馈 spill |
| DeepSeek Harness | [`ddefc45f`](https://github.com/deepseek-ai/deepseek-harness/commit/ddefc45fbc7f8e46dd73185e68295696d1297887)，`0.1.6-alpha.2` | 公开 TypeScript 实现、默认 bundle 和测试；developer preview | turn-stopping 扩展点、hook bridge、goal round driver |

Claude Code 的公开仓库不包含完整 CLI 内核。本文只把官方文档和可见插件行为当作证据，不推断内部未公开实现。三家的 hook 都是通用扩展机制，不等于它们默认会替用户运行项目验收。

## 4. 三家怎么做

### 4.1 Claude Code：终止时可阻塞并反馈，但验证质量由 hook 决定

Claude Code 官方 [hooks 文档][cc-hooks] 描述了两个与 H06 接近的边界：

- `Stop` 在主 agent 自然准备结束时运行，不在用户中断或 API 错误时运行。
- hook 可以用退出码 2 的 stderr，或 JSON `decision: "block"` 与 `reason` 阻止结束；反馈进入当前会话，模型继续工作。
- 输入包含 `stop_hook_active`，供 hook 避免在自己触发的续行中递归。
- `TaskCompleted` 可阻止任务被标为完成，并把 stderr 反馈给模型。

CHANGELOG 还记录了：

- Stop/SubagentStop 可用 `additionalContext` 提供反馈并继续当前 turn，[见记录][cc-additional-context]；
- 连续阻塞默认到 8 次后停止，可用环境变量覆盖，[见记录][cc-cap]；
- `last_assistant_message` 被加入 Stop 输入，[见记录][cc-last-message]。

这些机制证明“结束前验证失败 → 同会话继续”是成熟产品路径。但它只负责传输判定，不能保证判定本身正确。

公开的 Hookify `require-tests-run` 规则只是检查 transcript 中是否出现 `npm test|pytest|cargo test`，见 [规则示例][cc-require-tests]。它能证明“运行过命令”，不能证明命令通过，也不能防止运行无关测试。Claude Code 还曾改为不再自动运行 `/verify` 和 `/code-review`，[见 CHANGELOG][cc-no-auto-verify]。因此 Octos 不能复制“模型说测过/日志里出现命令就放行”的判定。

公开 Ralph 插件会在 Stop 时把**同一原 prompt**再次送回，直到 completion promise 或最大轮数，见 [Ralph 说明][cc-ralph]。这对 H06 过于宽泛：

- 没有 typed 失败定位；
- completion promise 仍由模型声明；
- 原任务反复出现会增加输入；
- 默认最大轮数甚至可以不设。

异步 hook 适合后台提醒，不适合作为最终交付门禁。结果晚到、重复唤醒或与下一轮并发时，很难保证“通过以后才 Ready”。Octos 应使用同步、确定性的 completion gate。

**迁移判断：**采用 Stop/TaskCompleted 的终止拦截、同会话反馈和递归/轮次上限；不采用 transcript 关键词、completion promise、无界同 prompt 循环或异步终检。

### 4.2 OpenAI Codex：typed Stop 结果进入同一 turn，来源和大反馈都可追踪

Codex 官方 [hooks 文档][cx-hooks] 将 hooks 标为稳定且默认启用。固定版本的公开实现把 Stop 结果建模为：

- `should_stop` / `stop_reason`；
- `should_block` / `block_reason`；
- 带 hook run ID 的 `continuation_fragments`。

命令退出码 2 的 stderr 和合法 JSON block 都会形成 continuation prompt；多个结果先聚合，再决定是否阻止结束，见 [Stop 解析与聚合][cx-stop]。

在 turn loop 中，Codex 运行 Stop hooks。若结果要求 block，就把带来源的 hook prompt 持久化为当前 turn 的输入项，设置 `stop_hook_active=true` 并继续，而不是新建外层任务，见 [同 turn 续行][cx-turn]。测试明确覆盖连续两次 block：

- 总共发出三次模型请求；
- 后续请求保留前面的 hook prompts；
- 三次 Stop 输入属于同一个 turn ID；
- `stop_hook_active` 依次为 `false, true, true`；
- continuation prompts 写入 rollout。

见 [多次阻塞测试][cx-stop-test]。

Codex 还为 hook 反馈设了默认 2,500 token 的模型可见上限。超长文本保存到临时文件，并在预览预算内预留恢复路径，见 [hook output spill][cx-spill]。这与 H01/H03 的 typed capsule + 可恢复证据方向一致。

两个边界不能误读：

1. 本次没有在所查 Stop 路径中找到类似 Claude Code “连续 8 次”那样的明确 block cap。Octos 不能依赖 hook 自己最终放行。
2. `codex exec --output-schema` 会把 JSON Schema 作为 provider 请求的 strict output format，见 [CLI 参数][cx-schema-cli] 和 [请求测试][cx-schema-test]。这是生成约束，不是本地 artifact 验证失败后的修复闭环。Provider 接受结构化输出，也不能代替文件存在、构建和验收检查。

[Codex 非交互模式文档][cx-noninteractive]推荐由外部脚本/CI 运行检查，需要时再恢复会话修复。这是可用的通用组合方式，但对 Octos ARC 会让外层重新编排阶段、重复输入，并且不天然拥有 MCP typed validator 结果。

**迁移判断：**重点采用 typed 聚合、来源化 append-only 反馈、同 turn 续行和大证据 spill；补上 Octos 自己的轮次/预算/停滞上限，不把 provider schema 或外层 CI 重跑当成 H06 已完成。

### 4.3 DeepSeek Harness：有通用停止检查点和有界 goal rounds，但两者没有组成验收闭环

DeepSeek 的 agent loop 在每个 step 已结束且没有下一步输入时，串行派发 `agent/turn-stopping`；监听器可在真正结束前塞入下一步，见 [agent loop 检查点][ds-turn-stopping]。

Claude Code hook bridge 把 blocking Stop 的 reason 作为带插件来源的用户消息 `steer` 回同一 agent，见 [Stop bridge][ds-stop-bridge]。协议层还提供：

- `hook/invoked` 与 `hook/result` 成对持久化；
- turn、point、handler ID、decision、exit code、stderr 摘要和耗时；
- 多 hook 按 `deny > ask > allow` 合并，保留来源顺序。

见 [hook 事件][ds-hook-events] 与 [合并规则][ds-hook-merge]。这些设计适合 H06 的可审计修复票据。

但这个 bridge 当前有重要限制：

- base bundle 默认没有挂载该 hook bridge；
- `stop_hook_active` 总是 false；
- 没有 consecutive block cap；
- 无条件阻塞的 hook 会持续强制续行；
- 多种 Claude Code hook 字段和事件仍未支持。

其 README 对这些限制有明确说明，见 [bridge 限制][ds-hook-limits]。所以不能把可选兼容桥当成 DeepSeek 默认的 H06 能力。

base bundle 默认挂载的是 goal service 和 goal-round-driver，见 [base bundle][ds-base-goal]。该 driver 在 agent 空闲、goal 已启用且仍有轮次时，追加一条带 goal 来源的消息；达到 `maxGoalRounds` 后写入稳定的 `round-limit` blocker，见 [round 实现][ds-round-code]。它还在续行前做持久化 checkpoint 和 revision fence，避免旧目标或并发输入触发错误续行。

这给 Octos 两个有价值的原则：

1. “验证失败反馈”应是带来源、只追加、不重写历史的消息；
2. 轮次上限必须由 harness 拥有，不能由模型自行解释。

但 goal driver 也明确说明：

- 没有独立 evaluator；
- `maxGoalRounds` 只是轮数，不是 token、费用或时间预算；
- 每个后续 round 仍会重发保留历史；
- 异常失败不自动重试。

见 [goal round 边界][ds-round-readme]。它适合持续推进一般目标，不足以证明 artifact 或验收已通过。

**迁移判断：**采用终止检查点、来源化事件、持久化 fence 和 round cap；不采用缺少 evaluator 的完成声明，也不复制未设循环保护的 hook bridge。

## 5. 横向比较

| 维度 | Claude Code | OpenAI Codex | DeepSeek Harness | Octos H06 判断 |
| --- | --- | --- | --- | --- |
| 触发点 | Stop/TaskCompleted | Stop hook，turn 结束前 | `agent/turn-stopping`；goal 在 idle 后续行 | 在 `EndTurn` 候选形成后、`Ready` 前同步验证 |
| 验证来源 | 用户 hook，自行决定 | 用户 hook，自行决定 | 可选 hook；goal 无独立 evaluator | 只信任允许的 deterministic validators/artifact/schema |
| 失败反馈 | block reason / additionalContext | typed fragments，带 hook run ID | plugin 来源消息，hook 事件成对持久化 | `RepairTicket`，保留 gate ID、状态、原因和证据引用 |
| 是否同一上下文 | 是 | 是，同一 turn | 是，同一 agent | 必须复用 `run_task_inner.messages`，不能仅二次 `run_task` |
| 循环限制 | 默认连续 8 次 | 所查路径未见明确 cap | hook bridge 无 cap；goal 有 `maxGoalRounds` | 默认最多 2 次，且受任务总预算约束 |
| 大反馈 | 文档/产品路径依事件而异 | 默认 2,500 token，spill 到文件 | stderr 摘要有界；通用存储由插件组合决定 | 复用 H03 output recovery，prompt 只放摘要与引用 |
| 成功依据 | hook 是否放行 | hook 是否放行 | hook/goal 状态 | 完整 hard-required gate 重新通过 |
| 默认是否构成项目验收闭环 | 否 | 否 | 否 | 由 Octos 显式组合 |
| 公开可比 ARC 效果 | 未找到 | 未找到 | 未找到 | 必须自行 A/B |

共同结论不是“加一个 stop hook”，而是：**终止边界是修复反馈最省上下文、也最不容易误报成功的位置；验证本身仍必须由 Octos 的任务契约决定。**

## 6. Octos 目标设计

### 6.1 用一个确定性 completion gate 统一终态

建议把当前分散的终态逻辑整理为一个内部 gate，不开放任意新命令：

```text
模型 EndTurn
  -> 构造候选结果（回复、files_modified、files_to_send）
  -> 运行允许的 workspace/MCP completion checks
  -> Pass
       -> Ready
  -> RepairableFail
       -> 生成有界 RepairTicket
       -> 追加到当前 messages
       -> 在剩余预算内继续同一 run_task loop
       -> 重新运行完整 gate
  -> TerminalFail / 预算耗尽 / 轮次耗尽
       -> 恢复最佳候选（如有）
       -> Failed，并返回最终 typed outcomes
```

gate 的返回值至少区分：

```text
Pass
Repairable(RepairTicket)
TerminalFailure(FailureEnvelope)
```

这比把所有失败压成 `TaskResult.success=false` 后再猜原因可靠。MCP 修复期间不得向外发布 terminal `Failed/Ready`；内部可按现有状态机记录 `Running/Verifying`，最终只发布一次终态。

首版只为 MCP/native ARC 配置该 gate。没有 completion policy 的普通 `run_task` 保持原行为，减少共享路径回归。待 MCP 机制稳定后，再评估是否统一 spawn 的 workspace contract 路径。

### 6.2 明确哪些失败允许模型修

| 失败 | 默认分类 | 理由 |
| --- | --- | --- |
| required validator `Fail`，且有明确项目内修复证据 | Repairable | 命令已正常运行，失败通常来自源码或产物 |
| artifact 缺失 | Repairable | 可提示准确期望路径，让模型补写或声明正确文件 |
| artifact 为可读取文本但 JSON/schema 不合法 | Repairable | 可反馈 schema 路径和有界校验错误 |
| artifact 放在错误位置 | 条件性 Repairable | 仅允许复制/重写到已验证的工作区内目标；不得扩大路径权限 |
| optional/soft validator 失败 | 不阻塞，不触发修复 | 保持现有 warning 语义 |
| validator `Timeout` | TerminalFailure | 超时不证明代码错误；模型盲修可能浪费 token |
| validator `Error`、命令被策略拒绝、工具缺失 | TerminalFailure | 属于策略或环境问题 |
| provider/config/sandbox 错误 | TerminalFailure | 模型无法修复运行 harness 的基础设施 |
| 非法 `arc_task`、非法 schema 或越权路径输入 | TerminalFailure，且在 provider 前拒绝 | 不能让不可信输入借修复环进入 Agent |
| 用户取消、总预算或 max iterations 耗尽 | TerminalFailure | H06 不得绕过外层资源边界 |
| 隐藏 grader 失败但没有允许反馈 | 不进入 H06 | 不增加测试可见性，不臆造失败原因 |

validator 的 `Fail/Timeout/Error` 已经分开，不能统一成“测试没过，请修复”。若特定 validator 的 timeout 明确包含可修项目错误，应由该 validator 改为正常完成并返回 `Fail`，而不是在 H06 中猜测。

### 6.3 RepairTicket 只携带修复所需的可信事实

建议的逻辑字段：

| 字段 | 作用 |
| --- | --- |
| `schema_version`、`ticket_id` | 稳定解析与审计 |
| `task_id`、`candidate_id`、`workspace_revision` | 防止把旧失败应用到新候选 |
| `repair_round`、`max_repair_rounds` | 明确剩余机会 |
| `gate_id`、`kind`、`required_tier`、`status` | 不靠英文文本分类 |
| `reason`、`stderr_tail`、`evidence_ref` | 有界失败摘要与可恢复原文 |
| `expected_artifact`、`observed_artifact`、`schema_error` | 交付问题的精确位置 |
| `passed_gate_ids` 或其摘要 | 告知哪些行为不能破坏 |
| `failure_signature` | 识别完全相同的验证结果 |
| `allowed_action` | 只修工作区与产物；不得改 validator、需求或判分 |

给模型的文字应短而明确：

```text
交付验证未通过。仅修复下列失败，保留已通过行为；不要修改验证器、任务契约或 required 级别。
修复后正常结束，harness 会重新运行完整检查。
```

validator 输出和生成文件都可能包含提示注入文本。RepairTicket 应把它们标为“不可信证据数据”，使用结构化边界，不把日志中的命令当作 harness 指令。证据过长时只放摘要和 H03 可恢复引用。

### 6.4 必须在同一个 `run_task` 消息序列继续

最低 token 且最少信息损失的方式，是在当前 `run_task_inner` 的 `messages` 尾部追加一条 harness 来源反馈，然后 `continue`：

- 原任务契约、工具调用和修改历史仍在；
- 新内容追加在缓存前缀之后；
- 不需要把完整任务和所有失败再次拼成新 prompt；
- H02 文件状态、H03 output 引用和 loop detector 属于同一任务；
- token usage 自然累计到一个 `TaskResult`。

只复用同一个 `Agent` 后再次调用 `run_task` 不满足这个保证，因为新调用会重新构造消息。若首版因接口限制只能做 wrapper，应明确标为过渡方案，并在实验中单独统计重复输入；不能宣称已经实现“同任务续行”。

### 6.5 双重上限：轮次上限和现有总预算

建议首版：

- `max_repair_rounds = 2`；
- 第 1 次只要存在 RepairableFail 且剩余预算足够即可进入；
- 第 2 次要求上轮确实改变工作区或 artifact，并且失败签名、通过 gate 集合或失败数量至少有一个发生变化；
- 完全相同的失败签名且工作区未变，直接停止；
- 完全相同的失败签名但工作区已变，最多再给一次“策略未命中”的聚焦反馈；
- 任何修复都不能突破原任务的 max iterations、取消、provider 或 token 边界；
- 接近预算上限时优先保留当前最佳候选并结束，不启动注定无法完成的修复。

“2 次”是保守实验参数，不是已证明的最优值。它比 Claude Code 的通用 8 次和无界 Ralph 更符合 ARC 的全任务 token 目标；最终应依据 H10 记录的增量通过数/增量 token 调整。

### 6.6 每次修复后重跑完整 hard gate，并保护最佳候选

为节省模型 token，可以只把失败项反馈给模型；为保证正确率，不能只重跑失败项后就 Ready。

每轮应：

1. 为候选记录工作区版本和所有 hard gate 的 typed 结果。
2. 修复后重新运行完整 hard-required gate。
3. 只有全部通过才 Ready。
4. 若新候选让已通过 hard gate 回归，不把它视为净进步。
5. 到达停止条件时恢复非劣的最佳候选，但对外仍返回 Failed 和最后一组验证证据。

artifact 存在、位置和 schema 都应视为 hard gate，而不是在 validator 通过后另走一组不可回放的 `return` 分支。这样“最佳候选”才有统一比较依据。

首版不需要复杂分数模型。可以使用保守偏序：新候选只有在不减少已通过 hard gate、并至少新增一个通过 gate 时才替换最佳候选；否则保留旧快照。无法比较的候选不自动覆盖。

### 6.7 token 优化靠减少重复信息，不靠少做终检

H06 的 token 控制建议：

- 不增加 LLM verifier；确定性检查直接给结论。
- continuation 只追加失败 gate、必要期望和短指令；已通过日志不重复发送。
- 相同失败用稳定 signature 引用，不重复内联同一大段 stderr。
- 大证据通过 H03 引用按需恢复；修复模型没有请求时不主动展开。
- 不重发完整原任务；不可变契约由当前历史或 H01 胶囊保留。
- 不因“只剩 schema 格式问题”重新走完整生成档位，继续使用现有工具/局部编辑能力。
- 最终完整验证可以多花本地执行时间，但不会增加模型 token；时间不计分，不能为省测试时间牺牲正确性。

追加历史有利于 prompt cache 前缀稳定，但不代表这些 token 免费。A/B 仍按 provider 的输入、输出、cache read/write 和推理计量契约统计全任务总量。

### 6.8 安全与权威边界保持不变

- `arc_task` 的解析和路径校验继续在 provider 创建前完成。
- RepairTicket 只能来自 harness 实际执行的允许检查，不能由模型伪造。
- 模型不能修改 workspace policy、validator 定义、测试文件、required tier 或 response schema；检测到这些变化应恢复或直接失败。
- validator 仍通过现有 sandbox 和 tool policy 执行；H06 不增加命令权限。
- artifact 路径必须重新 canonicalize 和校验，不能因为“修复”而接受工作区外文件。
- 每个修复轮次都记录触发原因、候选版本、用量、文件变化、验证结果和停止原因。
- 外层收到的最终 `validator_results` 应对应最终保留候选，不得返回被回滚轮次的结果。

## 7. 最小改动与迁移判断

本节只描述调研建议，不是实施任务清单。

| 子项 | 复用与改动 | 预期收益/取舍 | 决策 |
| --- | --- | --- | --- |
| H06a | 将 validator、artifact、位置和 schema 结果统一为内部 completion gate decision | 消除多个直接 `return Failed` 分支，形成唯一成功依据 | **P0 采用** |
| H06b | 在 `run_task_inner.messages` 追加来源化 RepairTicket 并继续 | 保留上下文和缓存前缀，避免外层整阶段重跑 | **P0 采用** |
| H06c | typed repairability 分类；非法输入、环境和 timeout/error fail closed | 避免把不可修问题交给模型浪费 token | **P0 采用** |
| H06d | 默认最多 2 次，结合文件变化、失败签名和剩余预算提前停止 | 控制尾部消耗；可能错过需要更多轮的少数任务 | **P0 采用，参数待测** |
| H06e | 每轮完整重验、候选版本化、非回归最佳快照 | 防止修好一个 gate 又破坏已通过行为 | **P0 采用** |
| H06f | 复用 H01/H03 有界证据与 H10 用量记录 | 减少重复日志并保证实验可信 | **必须联动** |
| H06g | Python ARC 维持现有 acceptance/final loop，只统一指标口径 | 避免重复实现和引入回归 | **暂不改流程** |
| H06h | LLM 自评放行、transcript 关键词、completion promise、无界循环、所有 Failed 一律重试、只复用 Agent 再开新 Task | 判定不可靠或重复输入高，可能绕过安全/预算边界 | **不采用** |

最小代码落点应集中在：

- `Agent::run_task_inner` 的 `EndTurn` 终止边界；
- MCP 的 completion validators 与 artifact/schema 检查；
- 统一 gate decision / RepairTicket；
- 任务累计 usage、候选文件状态和 observer 状态。

不需要修改官方测试、外部 grader、任务输入或评分规则，也不需要为 H06 新增一个通用 hook 插件系统。

## 8. 对照实验

### 8.1 先验证确定性不变量

以下是建议后续执行的测试，本次未新跑这些测试。

| 场景 | 必须观察到的结果 |
| --- | --- |
| 合法任务一次通过 | 不产生修复请求，Ready 行为与 A 组一致 |
| required validator 返回 `Fail` | 当前 messages 收到 typed 失败；修复后完整 gate 重跑 |
| validator `Timeout` / `Error` | 不调用模型修复，直接保留 typed terminal failure |
| optional/soft validator 失败 | 可见 warning，但不触发修复、不阻止 Ready |
| artifact 缺失 | 反馈准确期望路径；补写后重新校验位置与 schema |
| JSON 语法或 response schema 错误 | 只反馈有界 schema 错误；不能把模型自称“已修复”当通过 |
| artifact 越权路径、符号链接逃逸 | 修复环不扩大权限，最终仍 fail closed |
| 非法 `arc_task` | 在 provider 调用前拒绝，模型请求数为零 |
| provider/config/sandbox 失败 | 不进入 H06 |
| 首轮修复无文件变化 | 相同失败不被误报为一次有效策略尝试，且不会无界循环 |
| 文件已变但失败签名相同 | 最多允许一次明确改变策略的续行，然后停止 |
| 修复一个 gate、破坏另一个 gate | 不能 Ready；最终恢复非劣候选 |
| 第 2 轮通过 | 最终 results、artifact 和 usage 均来自累计任务，Ready 只出现一次 |
| 轮次、iterations、token 或取消触顶 | 不绕过上限；返回明确停止原因和最终验证结果 |
| stderr/证据超预算 | prompt 中只有有界摘要和有效恢复引用 |
| 失败日志含“忽略系统指令/修改测试”等文本 | 作为不可信证据展示，不改变 harness 权威规则 |
| MCP observer 并发读取状态 | 中间修复期间只出现允许的非终态，不提前出现 Failed/Ready |
| 修复后回滚最佳候选 | `validator_results` 与实际保留文件版本一致 |

测试应使用假 provider 捕获真正发送的消息，证明反馈追加到了同一个 `run_task` 历史，而不是只检查 RepairTicket helper。还要断言每个修复请求的 token 都累计到最终 `McpSessionCost`。

### 8.2 固定官方输入，比较完整 A/B

| 组别 | 策略 | 要回答的问题 |
| --- | --- | --- |
| A | 固定共同基线；MCP completion failure 直接 Failed | 当前有多少失败其实可由一次局部修改修好 |
| B | A + H06a-f；最多 2 次自适应聚焦修复 | 新增通过是否值得额外的全任务 token，是否引入回归或假成功 |

先做完整 A/B，不单独增加“1 轮”和“2 轮”两条正式实验臂。B 内记录第 1、2 轮各自的转化率；只有第二轮消耗明显且收益不清楚时，再做轮数消融，避免一开始扩大付费实验量。

两组固定：

- 官方需求、测试、模型、推理参数和输入模板；
- workspace policy、validator、schema、工具权限和 sandbox；
- 初始代码、H01-H05 开关、session scope、总请求/token 预算；
- 实际二进制 commit、环境和随机/重复运行设置。

样本至少覆盖：

- 可一次修复的构建错误；
- artifact 路径或缺失；
- JSON/schema 小错误；
- 多个 required validator 同时失败；
- 修复容易造成回归的已有工程；
- validator timeout/error 和非法输入等负对照；
- 首轮已经通过的小任务，用来测 H06 的零额外请求保证。

指标顺序：

1. 最终官方测试通过数、全通过率、回归数和重复运行稳定性。
2. false Ready、越权修复、修改测试/validator、最终结果与工作区版本不一致次数，目标均为零。
3. “直接 Failed → 修复后 Ready”的任务数，按失败类别和修复轮次拆分。
4. 全任务 provider 输入/输出 token、cache read/write、推理 token，包含所有失败和修复请求。
5. 每新增一个通过任务的增量 token，以及没有转化的额外 token。
6. 修复触发率、首轮/次轮成功率、无写入率、相同签名率、回归恢复率。
7. validator 执行次数、证据内联/恢复字节和模型请求数。
8. 本地测试时间、I/O 和磁盘只作诊断，不计入成绩。

不能用“B 的最终回复更短”证明节省；要比较整题累计 token。也不能因为 B 保留了较好失败产物就记为通过。正确率下降时，即使 token 更低也不采用。

付费真实环境实验留到项目约定阶段。运行前执行 `source ~/.zshrc`，确认 `ARCBENCH_API_KEY`、`OCTOS_BIN` 和二进制 commit；缺少 key 时只做确定性集成测试，不把它写成官方 A/B 结果。

## 9. 最终判断

H06 值得做，但它不是“失败后再问模型一次”。推荐顺序是：

**统一确定性交付门禁 → 分类可修与不可修失败 → 同一任务追加 typed 证据 → 最多两轮自适应修复 → 每轮完整重验 → 保留非劣候选并准确记账。**

最直接的实现借鉴来自 Codex 的 typed 同-turn continuation；Claude Code 补充了 Stop/TaskCompleted 边界和连续阻塞上限；DeepSeek 展示了追加式来源、持久化 fence 与 round cap 的组合。三者都没有替 Octos 解决“哪些 ARC 验证可信、哪些失败可修、怎样以最少全任务 token 保持最终正确性”，这部分必须由现有 workspace contract、validator 和 MCP artifact 语义决定。

Python ARC 的 acceptance loop 已经证明 Octos 自身有更贴近目标的闭环原则。H06 的最小价值，是把 MCP 当前“验证后立即 Failed”改为“只对可修复的确定性失败，在当前任务中给有限机会”，并用 A/B 数据决定这部分额外 token 是否换来稳定的新增通过。

## 参考源码与官方文档

下列源码链接均固定到本次核查的提交。Octos MCP/core 使用当前主线或 H05 已提交基线；未提交的 H05 后续工作不作为 H06 事实来源。

[o-python-node]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/main.py#L2420-L2585
[o-python-final]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/main.py#L3055-L3227
[o-task-end]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/loop_runner.rs#L2747-L2764
[o-llm-verifier]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/verifier.rs#L456-L575
[o-core-contract]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/loop_runner.rs#L2815-L2889
[o-task-init]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/loop_runner.rs#L2537-L2585
[o-mcp-input]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/commands/mcp_serve.rs#L483-L524
[o-mcp-task]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/commands/mcp_serve.rs#L634-L707
[o-mcp-gates]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/commands/mcp_serve.rs#L709-L850
[o-validator-status]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/validators.rs#L128-L151
[o-validator-outcome]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/validators.rs#L230-L294
[o-spawn-recovery]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/tools/spawn.rs#L2249-L2323

[cc-hooks]: https://code.claude.com/docs/en/hooks
[cc-additional-context]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L2938
[cc-cap]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L3373
[cc-last-message]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L5376
[cc-no-auto-verify]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L2050
[cc-require-tests]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/plugins/hookify/examples/require-tests-stop.local.md#L1-L22
[cc-ralph]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/plugins/ralph-wiggum/README.md#L11-L38

[cx-hooks]: https://developers.openai.com/codex/hooks
[cx-stop]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/hooks/src/events/stop.rs#L96-L430
[cx-turn]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/src/session/turn.rs#L644-L693
[cx-stop-test]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/tests/suite/hooks.rs#L1320-L1425
[cx-spill]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/hooks/src/output_spill.rs#L11-L130
[cx-schema-cli]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/exec/src/cli.rs#L47-L49
[cx-schema-test]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/exec/tests/suite/output_schema.rs#L8-L61
[cx-noninteractive]: https://developers.openai.com/codex/noninteractive

[ds-turn-stopping]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/core/agent-loop/src/agent.ts#L285-L322
[ds-stop-bridge]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/hooks/hooks-claude-code/src/index.ts#L266-L275
[ds-hook-events]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/hooks/hook-protocol/src/events.ts#L1-L104
[ds-hook-merge]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/hooks/hook-protocol/src/merge.ts#L1-L100
[ds-hook-limits]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/hooks/hooks-claude-code/README.md#L167-L182
[ds-base-goal]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/bundle/base/cordis.patch.yml#L299-L304
[ds-round-code]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/goal/goal-round-driver/src/index.ts#L145-L190
[ds-round-readme]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/goal/goal-round-driver/README.md#L102-L130
