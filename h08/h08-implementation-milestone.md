# H08 实施 Milestone：贯通并校准执行预算

- 状态：M0-M11 待实施
- 面向对象：后续 coding agent
- 设计依据：[H08 竞品调研](./h08-execution-budget-competitor-research.md)
- 关联约束：[H06 聚焦修复](../h06/h06-verification-failure-focused-repair-competitor-research.md)、[H07 无进展策略切换](../h07/h07-no-progress-strategy-switch-competitor-research.md)、[优化总表](../harness-optimization-table.md)
- 编写日期：2026-09-22
- 调研时主线：`octos-arc origin/main@27d057c206c0f8250b60309905737f7e26ee0ba9`
- 文档编写时本地代码分支：`feat/local-edit@bb53c733`；不能作为未来 H08 的开工基线

本文是实施 todo list，不代表代码已经完成。只有代码、确定性测试、真实入口证据和本地提交
同时具备时，才能把 `[ ]` 改成 `[x]`。类型名和文件位置可随最新主线调整，但唯一账本、
H10 门槛、交付保留额、实验隔离和正确率优先的验收语义不得静默弱化。

## 0. 后续 Agent 先读这一节

H08 不是简单地把某个 token 数调小，而是让同一个任务的外层 Flow、stdio/MCP/chat 入口、
核心 Agent 和 provider 请求对预算有一致理解：

```text
外层 runtime 拥有唯一 run 总账和分配权
入口只传本 turn 的不可变预算覆盖，不传可伪造的累计已用量
核心 Agent 执行 turn/response 限制并返回真实 usage 与 typed 终态
proxy 只做 provider 兼容、usage 捕获和紧急上限，不拥有阶段策略
最终测试、未完成节点最低额度和交付修复保留额不能被前期探索提前花掉
```

评估顺序固定为：

1. 官方最终通过数、回归数和重复运行稳定性。
2. 漏跑节点、漏跑最终测试、截断误成功、丢失最佳工作区和未计费失败，目标均为零。
3. 全任务累计 provider token，包含失败、重试、压缩、续写和派生任务。
4. 请求数、工具调用数、I/O 和耗时只用于解释结果；耗时不计入成绩。

### 0.1 A/B/C/D 的唯一含义

| 组别 | 内容 | 唯一要回答的问题 |
| --- | --- | --- |
| A | 最新共同底座，H08 关闭，保持当前有效入口和预算行为 | 当前正确率、稳定性和完整 token 基线是多少 |
| B | A + typed turn budget 接线 + canonical shadow ledger；不新增累计预算决策，不调整阶段阈值 | 字段贯通和统一观测是否正确，是否引入入口回归 |
| C | B + H10 可信用量 + 统一账本执法 + 阶段软信封 + 未完成节点最低额度 + 最终交付保留额 + typed 收尾/检查点 | 重新分配预算能否在不降正确率时减少无效消耗 |
| D | C + 按阶段设置 reasoning effort 和单次输出上限 | 逐阶段请求配置能否进一步降低 token 且不增加截断或回归 |

- [x] A/B/C/D 的变量边界已由调研确定；后续不得把接线、累计执法和 reasoning/output 调参合进一个实验提交。
- [x] B 是影子模式，不得因为影子账本“预测将超限”而取消请求、跳过修复或改变 prompt。
- [x] C 的保护对象同时包含 `unfinished_nodes_minimum` 和 `delivery_reserve`，不能只为最后一次修复留额度。
- [x] D 只与已冻结的 C 比较；不得用 A 直接归因 D 的收益。

### 0.2 H10 是硬门槛

H10 负责准确记录正常响应、失败响应、retry、partial response、compaction、continuation 和
subtask 的用量。H08 只消费 H10 的可信结果，不在本任务中顺手重写一套计费器。

- [x] H10 完成前允许实施 M0-M4 的字段接线、fake usage 和影子记账。
- [x] H10 完成前允许为 M5-M6 写纯函数和默认关闭的执行骨架，但不得开启累计硬决策。
- [x] C 的冻结和任何 A/B/C/D 付费收益结论都必须等待 `H10_READY_SHA` 及其验证证据。
- [x] `unknown`、缺失、超时前未结算和 MCP 错误分支的 usage 不能按 `0` 处理。
- [x] 若 H10 尚未就绪，H08 应在 B 冻结后明确等待，不得扩大 H08 范围去实现 H10。

H10 的最小就绪证据必须证明：

```text
同一 provider attempt 只入账一次
失败、重试和部分输出不会丢失已发生的用量
reasoning token 若已包含在 output 中不会重复相加
压缩、续写和派生调用带同一个 run identity
未知用量保留 unknown 状态，不制造虚假的节省
```

### 0.3 实施顺序

| Milestone | 主要产出 | 对应分组 |
| --- | --- | --- |
| M0 | 最新底座、真实调用图、outgoing request 和 H10 readiness | A |
| M1 | typed contract、校验和单一 resolver | B |
| M2 | stdio/OUP 与 chat fallback 接线 | B |
| M3 | MCP 接线和兼容行为 | B |
| M4 | canonical shadow ledger、等价回归和 B 冻结 | B |
| M5 | 阶段分配器、bank 和两类保留额 | C |
| M6 | 请求前准入、提醒、typed 终态和统一检查点 | C |
| M7 | H06/H07/最终套件集成和 C 冻结 | C |
| M8 | 确定性 phase policy 与逐阶段请求配置 | D |
| M9 | D 的截断/路由回归和冻结 | D |
| M10 | 固定官方任务 A/B/C/D 对照 | A/B/C/D |
| M11 | 采用、最新主线集成和独立回滚 | 选中方案 |

## 1. 分支、开关和共同底座

### 1.1 开工纪律

- [ ] 检查 `octos-arc` 和 `octos-arc-analysis` 的分支、工作树、未跟踪文件及未推送提交；不自动清理或覆盖用户改动。
- [ ] 执行 `git fetch origin main`，从当时最新 `origin/main` 创建 `feat/execution-budget` 或等价独立 worktree，并记录 `MAIN_SHA`。
- [ ] 核对最新主线已包含哪些 H01-H07/H10 能力；需要移植的共同依赖单独提交和验证，其收益不得算入 H08。
- [ ] 冻结共同底座 `A_SHA`，记录二进制路径和 SHA-256、Python/Rust/Node 版本、模型路由、provider、工具列表及全部有效配置。
- [ ] 每个 Milestone 完成后本地提交；不 push、不创建 PR，除非用户另行明确要求。
- [ ] 真实环境运行前执行 `source ~/.zshrc`；缺 `ARCBENCH_API_KEY` 或其他配置时，明确写出名称和补充位置，不把未运行写成通过。

### 1.2 建议开关

若最新主线已有统一配置对象，可调整命名，但必须保留下面两个正交维度：

| 配置 | 默认 | 用途 |
| --- | --- | --- |
| `execution_budget.mode = off | shadow | enforce` | `off` | A、B、C 的行为隔离 |
| `execution_budget.phase_tuning = false | true` | `false` | C 与 D 的 reasoning/output 隔离 |

可提供兼容环境变量别名：

```text
OCTOS_EXECUTION_BUDGET=off|shadow|enforce
OCTOS_EXECUTION_BUDGET_PHASE_TUNING=0|1
```

- [ ] `off` 与 A 的协议、请求和停止行为兼容；不得因新代码存在而额外注入 prompt 或 usage 文本。
- [ ] `shadow` 解析并记录决策，但不得改变调用、修复轮、测试执行或 provider 请求。
- [ ] `enforce` 只有在运行时确认 H10 accounting complete 后才可启用；不能只靠一个可伪造环境变量宣称 ready。
- [ ] phase tuning 只有在 enforce 生效时才可改变 reasoning/output；关闭时必须与 C 等价。
- [ ] 未知值失败关闭并留下有界诊断；不静默进入 `enforce`。
- [ ] 不删除或偷换现有 `OCTOS_MAX_ITERATIONS`、`OCTOS_ARC_MAX_TOKENS` 等含义；迁移时记录旧值到新 resolver 的映射。

### 1.3 M0 优先核对的路径

| 职责 | 优先阅读位置（相对 `octos-arc/`） |
| --- | --- |
| Python Flow、总量守卫和阶段流程 | `arc/main.py` |
| stdio 客户端与 `turn/start` | `arc/octos_stdio.py` |
| proxy 路由、reasoning、output floor 和 usage | `arc/llm_proxy.py` |
| Rust ARC driver/Flow/policy | `crates/octos-arc/src/driver.rs`、`flow.rs`、`policy.rs`、`routing.rs` |
| AgentConfig 与 turn 预算 | `crates/octos-agent/src/agent/mod.rs`、`agent/budget.rs`、`agent/loop_state.rs`、`agent/loop_runner.rs` |
| OUP wire contract 和 turn resolver | `crates/octos-core/src/ui_protocol.rs`、`crates/octos-cli/src/api/ui_protocol_transport.rs`、`runtime/turn_policy.rs` |
| chat fallback/gateway | `crates/octos-cli/src/commands/chat.rs`、`commands/gateway/gateway_runtime.rs` |
| MCP 配置、执行和 cost 出口 | `crates/octos-cli/src/commands/mcp_serve.rs` |
| provider usage 类型 | `crates/octos-core`、`crates/octos-llm` 中的 `TokenUsage`/response 类型 |

路径只用于导航。M0 必须先证明 Python 与 Rust 哪条 ARC Flow 是官方真实入口；不能让两条
路径各自拥有一份 run 总账。

## 2. 所有权和不可破坏的约束

### 2.1 唯一所有者

| 层 | 唯一职责 | 禁止承担 |
| --- | --- | --- |
| 外层 Flow/runtime | `run_id`、累计账本、阶段、bank、在途预占、未完成节点最低额度、交付保留额和准入决策 | 伪造 provider usage；管理上下文窗口 |
| stdio/chat/MCP adapter | 校验并传递本 turn 的不可变覆盖，返回 usage/终态 | 接受调用方回写的 `cumulative_used`；自行再分配总预算 |
| 核心 Agent | 执行 turn iteration/token/output 限制，保留 partial usage，生成 typed stop/checkpoint | 为整个 ARC 需求树分阶段；重置 run 总账 |
| proxy/provider adapter | provider 字段兼容、最终请求约束、usage 捕获和紧急 cap | 用统一 floor 放大 H08 cap；决定是否跳过节点或修复 |
| H10 accounting | 规范化完整 usage 和 attempt identity | 决定 H08 阶段策略 |

- [ ] 一个 `run_id` 在任一时刻只有一个 authoritative ledger owner；重连、fallback、MCP 或子任务不能新建“满额”账本。
- [ ] Python 与 Rust 都需要支持时，共享同一持久/IPC 事实或明确只有一方为 owner；不得靠运行后合并两个独立累计值。
- [ ] ledger snapshot 对消费者只读；任何 wire request 都不能携带并覆盖 authoritative `cumulative_used`。
- [ ] context occupancy、累计花费和下一响应 allowance 分开建模，不能复用同名 `token_budget`。

### 2.2 行为不变量

- [ ] 不修改官方需求、测试、判分器、模型、初始模板或工具集合来制造 token 节省。
- [ ] 所有需求节点仍需获得约定的最低实现机会；达到普通阶段软上限不能直接跳过剩余节点。
- [ ] 最终全量测试始终运行；测试本身不消耗模型 token，不能以预算为由省略。
- [ ] 普通实现、调查和节点修复不能花掉 `unfinished_nodes_minimum + delivery_reserve`。
- [ ] 只有 H07 typed 证据证明测试新增通过、失败集合缩小或有效文件变化时，才允许从同一 run 的 bank 借额度。
- [ ] 模型自述“有进展”、重复读取、重复截断、相同 provider 错误和无变化写入均不算借款依据。
- [ ] 达限保留最佳已验证工作区；不能用更差的 WIP 覆盖先前通过更多测试的状态。
- [ ] incomplete tool call 不执行；partial response 保留 finish reason 和已发生 usage，但不能包装成成功。
- [ ] 任何 H08 显式 `max_output_tokens` 都是上限。proxy floor、profile 默认或后续 model route 不能把它抬高。
- [ ] provider 不支持指定 effort/cap 时明确降级或拒绝 D，不伪造“配置已生效”。
- [ ] `unknown` usage 不参与“节省”计算；enforce 模式下存在未结算 unknown in-flight 时不得继续按完整余额准入。
- [ ] 单次输出上限与最大并发共同界定最坏超量；文档不能宣称 provider 回报前可以绝对零超量。
- [ ] H03/H04 的上下文压缩、H06 的修复判定、H07 的进展分类和 H13 的模型选择保持各自所有权。

## 3. 最小数据契约

类型名可以按仓库惯例调整；字段语义、单位和所有权必须固定。

### 3.1 入口只传 `TurnBudgetOverrides`

```text
TurnBudgetOverrides
  policy_version
  run_id
  phase
  max_iterations
  max_turn_tokens
  max_output_tokens
  reasoning_effort
```

- [ ] 所有预算字段可选，缺失表示按 resolver 继承；不能同时用缺失和 `0` 表达同一件事。
- [ ] `max_iterations=0` 若需保留现有“无限”语义，必须显式测试；H08 enforce 的 Flow 不得发出无限 turn。
- [ ] token 字段统一使用整数 token 单位并做范围校验、溢出保护和合理上限检查。
- [ ] phase 使用封闭枚举，例如 `design | implement | node_repair | regression_repair | final_repair | final_check`；不能从 prompt 文本猜测。
- [ ] 不包含 `cumulative_used`、`banked`、`reserved_for_delivery` 等 runtime-owned 可变字段。
- [ ] continuation、retry 和 fallback 继承同一 `run_id`，只允许 owner 生成新的受限 turn override。

### 3.2 账本消费 H10 usage，不另造公式

至少保留以下互斥 bucket：

```text
uncached_input
cache_read
cache_write
output
reasoning_subset_of_output
```

- [ ] `reasoning_subset_of_output` 只作解释，不再次加入总量。
- [ ] 每个 usage delta 有稳定 attempt identity、run identity、phase、来源类型和 complete/unknown 状态。
- [ ] retry、compaction、continuation、subtask 与普通 response 进入同一 fold；replay/重复事件幂等。
- [ ] ledger 保存 settled usage 与 admitted in-flight reservation，不能只在响应后检查。
- [ ] 数值采用 checked/saturating 边界并输出 overflow 诊断；不能 wrap 后恢复余额。

### 3.3 typed 预算终态

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

- [ ] 使用现有 error/result envelope 扩展 canonical 字段，不新增两套同义 error string。
- [ ] `used`、`reserved` 和 `partial_usage` 缺失时表达 unknown，不能填零。
- [ ] 文本只给简短原因和下一步；完整结构走已有 metadata/event 通道。
- [ ] dirty worktree 在累计 token、迭代、请求和时间达限时走同一检查点策略；clean worktree 不制造空提交。

### 3.4 唯一 resolver

配置优先级固定为：

```text
显式本 turn 覆盖 > Flow phase policy > profile/gateway 配置 > provider 默认
```

- [ ] 解析、合法性校验和优先级在一个共享 resolver 中完成；stdio、chat、MCP 不各写一套。
- [ ] resolver 返回最终 effective config 和来源标签，供 manifest/测试核对。
- [ ] 下游可因 provider 能力进一步收紧，不能放大上游显式上限。
- [ ] `off` 时不改变旧 resolver 结果；`shadow` 记录新旧差异但使用 B 规定的实际值。

## 4. Milestone M0：冻结底座、真实调用图和 H10 门槛

**目标：**不改行为地确认真实入口、最终请求和用量可信边界。

- [ ] 完成第 1.1 节，记录 `MAIN_SHA`、依赖提交和 `A_SHA`。
- [ ] 追踪 Python/Rust ARC Flow 到 stdio、chat fallback、MCP、核心 Agent、proxy、model route 和 provider 的完整调用链。
- [ ] 明确官方任务实际使用 Python Flow、Rust Flow 或两者何种组合，并指定唯一 ledger owner。
- [ ] 记录 `AgentConfig.max_iterations/max_tokens/chat_max_tokens/reasoning_effort` 的默认值、`0/None` 语义和每条入口的覆盖情况。
- [ ] 用 fake/capture provider 抓取路由完成后的真实 outgoing request；不能仅凭 profile 中的 `65536` 或 proxy 的 `32768` 推断有效 `max_tokens`。
- [ ] 分别记录 stdio 普通 turn、continuation、chat fallback 和 MCP 的迭代、turn token、output token、reasoning 及请求次数字段。
- [ ] 证明当前普通 OUP turn 未配置时的真实迭代行为、chat 的 `OCTOS_MAX_ITERATIONS` 行为和 MCP 固定 20 的行为。
- [ ] 复现 proxy output floor 及 route 后覆盖，确认最终 cap 由哪一层决定。
- [ ] 建立 H10 readiness matrix：normal、provider error、retry、partial、compaction、continuation、subtask、MCP error 各自是 complete/partial/unknown。
- [ ] 固定不付费的基线夹具：字段缺失、显式覆盖、路由放大、错误零 cost、重复 usage、reasoning 重复计算和重连新账本。
- [ ] 固定后续官方任务、输入/测试/模板哈希、模型、reasoning、并发、重试、H01-H07 开关、修复轮和重复次数。

**完成条件：**A 可重放；最终 outgoing request 和 ledger owner 有证据；H10 未覆盖项被明确列为 gate，而非默认为零。

## 5. Milestone M1：typed contract、校验和单一 resolver

**依赖：**M0。**对应：**B。**目标：**先统一字段语义，不改阶段决策。

- [ ] 在最小共享协议层定义 `TurnBudgetOverrides` 和 phase enum；避免 Python/Rust/MCP 各自发明字段名。
- [ ] 为新字段提供向后兼容的 optional serde/JSON 解析；旧客户端和旧 profile 在字段缺失时保持 A 行为。
- [ ] 实现单一 resolver 及来源标签，覆盖显式 turn、Flow policy、profile/gateway 和 provider default 的优先级。
- [ ] 明确 `None`、`0`、负数、浮点、超大整数、未知 enum 和未知 policy version 的处理。
- [ ] 将 `max_turn_tokens` 映射到 `AgentConfig.max_tokens`，`max_output_tokens` 映射到 `chat_max_tokens`，不交叉复用。
- [ ] reasoning effort 使用现有 provider capability/type，不增加字符串透传后再猜测的第二套逻辑。
- [ ] effective config 只记录非敏感值、来源和 policy version；不记录 prompt、key 或 endpoint 凭据。
- [ ] 单测 old/new payload round-trip、缺失字段、非法字段、优先级、0 语义、收紧不放大和跨语言 fixture。
- [ ] 本地提交 M1；H08 mode 默认仍为 off。

**完成条件：**同一输入在所有入口调用同一个语义 resolver；旧 payload 兼容，新 payload 不含 runtime-owned 累计值。

## 6. Milestone M2：stdio/OUP 与 chat fallback 接线

**依赖：**M1。**对应：**B。**目标：**让默认 ARC 主路径真正收到本 turn 预算。

- [ ] 扩展 OUP `turn/start` 的可选预算字段，并同步 Rust schema、Python client、fixture、日志和 fake server。
- [ ] Python `OctosDriver` 与活跃的 Rust ARC driver 都按 M0 结论传递同一 contract；非活跃实现只保持编译兼容，不建立第二套策略。
- [ ] OUP server 在创建 `AgentConfig` 前调用共享 resolver；不得在 transport 深处重复覆盖。
- [ ] 普通 turn、内部 continuation、断线重连和 session 恢复保持同一 `run_id` 与不增大的预算。
- [ ] chat fallback 从同一 `TurnBudgetOverrides` 派生 CLI/config；不只传 `--max-iterations` 而丢失 output/reasoning。
- [ ] B 保持当前阶段阈值和修复策略；若修复了“配置存在但 stdio 未生效”的历史缺口，单独记录行为差异和边界样本。
- [ ] 用 capture provider 断言最终 outgoing request 的 output cap/reasoning，且 route/proxy 未放大显式 cap。
- [ ] 真实 stdio + fake provider 验证缺失字段、显式字段、continuation、MaxTokens、provider error 和取消。
- [ ] 本地提交 M2，并记录协议 fixture 版本。

**完成条件：**stdio 与 chat 对同一 override 得到相同 effective `AgentConfig`，真实 provider 请求与 manifest 一致。

## 7. Milestone M3：MCP 接线和兼容行为

**依赖：**M1-M2。**对应：**B。**目标：**移除 MCP 只能固定 20 次的接线缺口。

- [ ] 为 MCP task/session 请求增加同一组可选 turn budget 字段；旧调用方缺失字段时仍保持现有默认 20。
- [ ] MCP Agent 构造使用共享 resolver，不再只覆盖 `max_iterations/save_episodes`。
- [ ] standalone MCP 未提供 `run_id` 时保持本地 turn 语义，不伪装成受 Flow 总账保护；由 ARC Flow 调用时必须沿用其 `run_id`。
- [ ] MCP success、soft terminal 和 error 都回传可用的 typed usage/终态；H10 未提供准确 error usage 时标 unknown，不在 H08 中伪造零成本修复。
- [ ] MCP 的 output/reasoning 经过 provider route 后仍不超过显式上限。
- [ ] 测试旧 client、新 client、非法 budget、默认 20、显式覆盖、provider error、partial usage 和取消。
- [ ] 更新 MCP schema/说明的当前行为，不声称 H10 尚未证明的完整计量。
- [ ] 本地提交 M3；H08 mode 默认仍为 off/shadow 可选，不能 enforce。

**完成条件：**MCP 与 stdio/chat 共用字段和 resolver；旧请求兼容，错误用量不再被 H08 当成可信零值。

## 8. Milestone M4：canonical shadow ledger 与 B 冻结

**依赖：**M1-M3。**对应：**B。**目标：**先证明一份账能覆盖真实路径，不用它改变行为。

- [ ] 在 M0 选定的 Flow/runtime 中创建每 run 唯一 ledger；adapter、Agent 和 proxy 只能提交事件或读取 snapshot。
- [ ] 接入 H10 已提供的 canonical usage delta；未就绪 bucket/路径保留 unknown。
- [ ] 区分 settled usage、in-flight reservation、context occupancy 和 response allowance；B 中 reservation 只影子计算。
- [ ] normal、error、retry、compaction、continuation、subtask、MCP 和 chat fallback 共享 run identity。
- [ ] 使用 attempt identity 去重；事件 replay、重连和重复 completion 不得重复入账。
- [ ] reasoning 作为 output 子集展示，证明不会重复加入 cumulative total。
- [ ] 记录 shadow decision：若启用 C，本请求会被 admit/conserve/stop 的原因和余额；实际请求仍按 B 执行。
- [ ] 对比旧 proxy 统计、核心 `TokenUsage` 和 canonical ledger；差异必须有来源解释，unknown 不强行对平。
- [ ] A/B 确定性回归：任务、请求顺序、测试执行和修复入口不因 shadow decision 改变；协议接线差异单列。
- [ ] 记录固定 schema/prompt/manifest 增量，避免 B 本身引入大段每 turn 文本。
- [ ] 冻结 `B_SHA`、二进制哈希、policy version 和验证证据；本地提交，不 push。

**完成条件：**B 在所有真实入口产生可追溯的一份 run 账，影子模式不改变工作流；H10 缺口被显式保留。

## 9. Milestone M5：阶段分配器、bank 和两类保留额

**依赖：**M4；H07 typed progress contract 已可消费。**对应：**C 骨架。**目标：**以纯确定性逻辑分配额度。

核心公式至少保护：

```text
protected_remaining = unfinished_nodes_minimum + delivery_reserve
spendable_now =
  cumulative_limit
  - settled_used
  - admitted_in_flight
  - protected_remaining
```

- [ ] 定义 run hard limit、phase soft envelope、bank、unfinished node minimum、delivery reserve 和 minimum useful request；不共用一个字段。
- [ ] `unfinished_nodes_minimum` 至少覆盖每个未完成需求节点的最低有效实现机会，并随节点完成确定性释放。
- [ ] `delivery_reserve` 至少覆盖最终全量测试后一次证据驱动修复及必要复验/失败分类；最终测试本身不扣模型 token。
- [ ] 样本不足时使用显式静态下限；样本足够后只用已结算同类阶段 usage 的中位数或预注册保守分位数。
- [ ] phase soft envelope 可以借同一 run 的 bank，但永远不能突破 hard limit 或 protected remaining。
- [ ] 借款只消费 H07 typed progress，不解析模型自然语言；H07 信号缺失时借款失败关闭。
- [ ] 快节点节余按保守比例进入 bank；不能把尚未使用的 future reserve 当成已节省额度。
- [ ] phase 转换由 Flow 状态机产生，覆盖 design、implement、node repair、regression repair、final repair、final check。
- [ ] 纯函数测试零预算、极小预算、单节点、多节点、超大数、unknown usage、负余额、并发预占和 reserve 释放。
- [ ] 用历史 manifest 离线 replay，比对不同分配结果；不得用离线预测宣称真实 token 收益。
- [ ] 本地提交 M5；enforce 仍保持不可启用，直到 M6 与 H10 gate 完成。

**完成条件：**给定同一 ledger、需求树和 typed progress，分配结果完全确定；任何普通阶段都不能侵占两类保留额。

## 10. Milestone M6：请求前准入、提醒、typed 终态和检查点

**依赖：**M5 和 `H10_READY_SHA`。**对应：**C。**目标：**在 provider 调用前执行可恢复的预算决策。

- [ ] runtime 启动 enforce 前验证 H10 capability/version；不满足时拒绝 enforce 或明确降级 shadow。
- [ ] 每次 provider 请求前刷新 settled usage，检查 unknown in-flight，并按估计输入 + 本次 output cap 预占额度。
- [ ] 并发请求原子预占；不能让两个请求同时看见同一份完整余额。
- [ ] provider 返回后用真实 usage 对账并释放差额；error/partial/retry 同样结算。
- [ ] 实现 `normal -> conserve -> delivery_only -> exhausted` 的确定性状态转换，阈值来自剩余工作和 reserve，不只看固定 80%。
- [ ] conserve 禁止无证据探索和重试，但允许有预算的明确落盘/验证动作；delivery_only 只允许受保护的交付修复。
- [ ] `remaining < minimum_useful_request` 时不发模型请求，返回 typed `budget_exhausted`。
- [ ] 预算提醒只在成功写入模型历史后标记 delivered；取消或失败前未入历史可重试，不能重复注入。
- [ ] grace call 全 run 最多一次，且必须有 H07 typed progress、明确可完成动作、成功预占和不侵占 reserve。
- [ ] MaxTokens continuation 也要走 admission；不能无条件再花两次完整响应。
- [ ] 累计 token、iteration、request、output 和 time 达限统一生成 typed terminal，并为 dirty worktree 保存检查点。
- [ ] incomplete tool call 不执行；已生成安全文本、partial usage、finish reason 和 remaining work 被保留。
- [ ] 用 fake provider 覆盖超量一个请求的误差边界、并发竞争、取消、重复提醒、grace、unknown usage 和 clean/dirty checkpoint。
- [ ] 本地提交 M6；尚未完成 M7 全链验证前 C 默认关闭。

**完成条件：**任何新 provider 请求都先准入并预占；达限保留事实、用量和最佳成果，不跳过最终测试或伪装完成。

## 11. Milestone M7：C 的工作流集成、回归和冻结

**依赖：**M6、H06/H07 可消费 contract。**对应：**C。**目标：**把预算执法接入固定 ARC 交付流程。

- [ ] 将需求节点、节点验证、聚合回归、最终套件和最终修复映射到明确 phase；不靠 label/prompt 模糊匹配。
- [ ] H06 修复入口先请求 budget admission，再按失败证据决定动作；预算拒绝不能改写失败集合。
- [ ] H07 progress/no-progress 事件驱动 bank 借用和 grace；provider retry 与策略切换仍是独立状态机。
- [ ] 现有 `wound_down()` 迁移为 C 状态的兼容视图或单一调用点；不得保留两个相互冲突的总量停止器。
- [ ] 未完成节点在 hard exhaustion 前获得最低机会；真正 hard exhausted 时记录未完成清单，不能标记已执行。
- [ ] 最终全量测试无条件执行；只有其后的模型修复受 delivery reserve 和 hard limit 控制。
- [ ] best-state restore、manifest、scoreboard 和退出状态能区分预算耗尽、测试失败、provider 失败及基础设施失败。
- [ ] off=A、shadow=B、enforce=C 的端到端 fake provider 测试使用相同任务夹具并断言唯一变量。
- [ ] 覆盖小任务、多节点、难节点借款、多轮修复、最终回归、provider transient error、MCP 和大文件截断。
- [ ] C 的每个 usage bucket 都通过 H10 completeness gate；任一必需路径 unknown 时停止冻结，不补记零。
- [ ] 冻结 `C_SHA`、`H10_READY_SHA`、二进制哈希、policy/ledger schema version 和验证证据。
- [ ] 本地提交 M7；付费实验前默认仍保持 A，除非用户明确授权。

**完成条件：**C 的完整流程可确定性复现，受保护工作不会被普通阶段挤占，所有预算停止均可恢复和审计。

## 12. Milestone M8：D 的 phase policy 与逐阶段请求配置

**依赖：**M7 已冻结 C。**对应：**D。**目标：**只改变每阶段 reasoning 和单次输出，不改总账算法。

- [ ] 从 `C_SHA` 创建独立 D 提交；C 的 hard limit、reserve、bank、准入和修复轮保持不变。
- [ ] phase 由 Flow 状态显式传入，不从 prompt 文本、文件名或模型自述推断。
- [ ] 先记录 C 各阶段实际输入/output/reasoning 分布和截断位置，再预注册 D 的候选档位。
- [ ] 为 design/root-cause、small implement、large implement、failure classify、focused repair、final delivery 分别定义 policy。
- [ ] 简单分类和小修复优先低 effort/小输出；复杂根因只在证据复杂时提高一次，不能每次失败自动升级。
- [ ] 大文件实现按可落盘的文件/patch 大小分配，不依赖一个全局巨大 output floor。
- [ ] 同一 warm context 内避免逐请求抖动 effort；只在明确 phase/session 边界变化，减少缓存失效。
- [ ] provider capability resolver 映射 adaptive effort、fixed thinking 和 non-reasoning model；unsupported 必须可见。
- [ ] 显式 H08 output cap 在所有 proxy 注入和 model route 之后仍是最终上限；不能被 `max_tokens_min` 放大。
- [ ] response cap 不足以完成最小落盘动作时，在 admission 前缩小任务或拒绝，不先请求后依赖续写。
- [ ] phase policy 不改变模型、工具、需求、测试、修复轮或 H06/H07 判定。
- [ ] 本地提交 M8；phase tuning 默认关闭。

**完成条件：**D 的每个请求都能从 manifest 解释“为什么是此 effort/cap”，且唯一变化是 phase request policy。

## 13. Milestone M9：D 的截断、路由回归和冻结

**依赖：**M8。**对应：**D。**目标：**证明调小请求不会破坏可落盘结果。

- [ ] capture 最终 outgoing request，逐 provider/model 证明实际 effort/cap 与 resolved policy 一致。
- [ ] 覆盖 reasoning 与 visible output 共用上限的 provider，验证仍有足够空间完成工具参数或代码块。
- [ ] 覆盖短分类、小补丁、多文件修改、大文件 codegen、压缩后新窗口、MaxTokens 和 partial tool call。
- [ ] 截断后的 continuation/fallback 必须重新 admission，记录累计成本；不把较短首响应单独算作节省。
- [ ] 比较 C/D 的请求数、截断、续写、失败重试、落盘成功和完整 token；正确率门槛优先。
- [ ] 若某 provider 无法可靠执行 phase cap，只对该 route 保持 C 配置并标记 D unsupported；不得静默混入结果。
- [ ] 冻结 `D_SHA`、policy table、provider capability matrix、二进制哈希和确定性验证证据。
- [ ] 本地提交 M9；官方实验前 D 仍默认关闭。

**完成条件：**D 在所有支持 route 上真实生效，不增加未完成写入或截断误成功；unsupported route 被明确隔离。

## 14. Milestone M10：固定官方任务 A/B/C/D 对照

### 14.1 开跑条件

- [ ] A/B/C/D 均有冻结 SHA、相同共同依赖和通过的确定性验证；`H10_READY_SHA` 已固定。
- [ ] 执行 `source ~/.zshrc` 并确认 `ARCBENCH_API_KEY`、模型 endpoint、真实 `OCTOS_BIN`、二进制哈希和隔离目录。
- [ ] 缺任何凭据或配置时写明名称和补充位置，停止付费实验；不把 unknown 记成零或继续反复探测。
- [ ] 固定全量官方任务、输入/测试/模板哈希、模型/provider 版本、并发、网络重试、H01-H07/H10 开关和重复次数。
- [ ] 每个 task×variant 使用独立 workspace/data/session/run id；不得共享生成产物、账本、cache artifact 或长期记忆。
- [ ] 建议每组至少 3 次并交错运行顺序；资源不足时如实标记未完成，不用少量 smoke 代替全量结论。

### 14.2 每次运行记录

- [ ] `MAIN_SHA/A_SHA/B_SHA/C_SHA/D_SHA/H10_READY_SHA`、实际运行 SHA、git dirty、二进制路径和 SHA-256。
- [ ] task、repetition、run order、输入/测试/模板哈希、模型、provider、reasoning、全部有效预算配置和 policy version。
- [ ] 每阶段 resolved turn/output/reasoning、admission、reservation、bank 借还、两类 reserve 和 typed stop。
- [ ] uncached input、cache read、cache write、output、reasoning subset、请求数、retry、compaction、continuation 和 subtask。
- [ ] usage completeness/unknown、最终逐例报告、首轮通过、回归、稳定性、截断、未完成节点和 best-state restore。
- [ ] 到最终套件时剩余额度、实际使用的 delivery reserve、被 reserve 修复救回的测试数。
- [ ] 外部基础设施失败单列；H08 引起的提前停止、漏测、死锁、错误路由或 checkpoint 丢失是产品失败。

### 14.3 判定顺序

1. 先比较最终通过数、全通过率、回归和重复稳定性。
2. 再检查漏节点、漏最终测试、unknown usage、截断误成功和成果丢失，确定性目标为零。
3. 正确率不下降后，比较全任务累计 token 的中位数和尾部，而不是单次最好结果。
4. B 先用于证明接线与观测可信；C-B 归因预算分配，D-C 归因 phase request policy。
5. 通过数下降时不因 token 更少采用；通过数提高但 token 增加时先保留正确率收益，再单独优化策略。
6. 少跑测试、跳过节点、漏记失败、把 unknown 当零或只统计可见 output 均不算节省。

- [ ] 保存逐 run manifest、原始官方报告和聚合结果；失败样本不得删除。
- [ ] 结论明确为采用 C、采用 D、保留 A/B，或证据不足；不得把未完成实验写成收益。

**完成条件：**全部有效 run 可追溯，变量隔离成立，采用结论遵守正确率优先和完整用量口径。

## 15. Milestone M11：采用、最新主线集成和独立回滚

- [ ] 根据 M10 选择 A、C 或 D；B 只作为接线/观测阶段，不因“代码已写”自动成为默认策略。
- [ ] 重新 `git fetch origin main`，在不改写冻结 SHA 的前提下把选中实现集成到最新主线，记录 `INTEGRATION_SHA`。
- [ ] 核对最新 H01-H07/H09-H13、stdio/chat/MCP、Python/Rust ARC、proxy route、Agent budget 和 checkpoint 的组合。
- [ ] 若集成改变 usage、入口、模型路由、修复流程或 phase 语义，重跑受影响对照；旧结果不能自动证明新组合。
- [ ] 提供独立回滚：phase tuning 可从 D 退回 C；enforce 可退回 shadow/off；关闭 H08 不关闭 H10 计量或 H02/H03 安全能力。
- [ ] 未采用的策略默认关闭；删除无维护价值的实验死代码，但保留 schema 向后兼容和实验记录。
- [ ] 更新优化总表、有效配置说明和运行 manifest，不创建第二份相互漂移的预算文档。
- [ ] 跑受影响全量 Rust/Python 测试、格式、Clippy、真实 stdio fake provider 和官方 smoke，区分基线失败与新增失败。
- [ ] 每个 Milestone 的代码与分析证据分别本地提交并记录 SHA；远程推送等待用户明确指令。

**完成条件：**选中方案在最新主线上仍满足正确率、完整计量和 token 门槛；每层可独立回滚且不会损坏已有成果。

## 16. 测试、提交和交接要求

### 16.1 候选验证命令

先用 `-- --list` 或 Python 测试文件清单确认过滤器确实命中；零测试不能算通过。下面是后续
agent 的候选命令，不是本文已运行记录。

```bash
# 先发现真实测试名
cargo test -p octos-agent --lib -- --list | rg 'budget|loop_state|usage|checkpoint|max_token'
cargo test -p octos-cli --lib -- --list | rg 'turn_policy|ui_protocol|reasoning|budget'
cargo test -p octos-cli --test mcp_serve_integration -- --list
cargo test -p octos-arc -- --list | rg 'budget|driver|flow|policy|routing'
cd arc
python3 -m unittest discover -s tests -p 'test_*.py' -v
cd ..

# Rust 专项与跨层回归
cargo test -p octos-agent --lib agent::budget
cargo test -p octos-agent --lib loop_state
cargo test -p octos-cli --lib turn_policy
cargo test -p octos-cli --test mcp_serve_integration
cargo test -p octos-arc

# Python Flow/proxy 专项；新增测试后补入准确模块名
cd arc
python3 -m unittest -v \
  tests.test_llm_proxy \
  tests.test_banked_surplus \
  tests.test_node_budget \
  tests.test_main_helpers \
  tests.test_rust_engine
cd ..

# 最终静态检查
cargo check -p octos-agent -p octos-cli -p octos-arc --all-targets
cargo fmt --all -- --check
cargo clippy -p octos-agent -p octos-cli -p octos-arc --all-targets -- -D warnings
git diff --check
git status --short
```

- [ ] 新增真实 stdio + fake/capture provider 集成测试，断言最终 outgoing request，而不只断言中间 config。
- [ ] 新增 MCP error/partial usage 和旧客户端兼容测试。
- [ ] 新增 ledger 幂等、重连、retry、compaction、continuation、subtask、unknown 和并发预占测试。
- [ ] 新增 Flow 小任务、多节点、reserve、bank、H06/H07、最终套件和 best-state restore 测试。
- [ ] Python 测试保持 3.9 兼容，不使用 `tarfile.extract(filter=...)` 等更高版本专属 API。
- [ ] Clippy 若命中主线遗留告警，先在 `A_SHA` 用同命令复现并记录；不得顺手修改无关模块，也不得把新增告警归为基线。

### 16.2 每个 Milestone 的本地提交

- [ ] 一个 commit 只完成一个可验证 Milestone，或一个为保持绿色所需的更小切片。
- [ ] 提交信息写实际行为，例如“贯通 turn 预算覆盖”“记录 run 级影子用量”“为最终修复保留额度”，不只写内部编号。
- [ ] 提交前运行相关专项测试、`cargo fmt --all -- --check` 和 `git diff --check`。
- [ ] 不提交真实凭据、付费响应中的敏感数据、临时 workspace、无界日志或与 H08 无关的格式化变化。
- [ ] 分析仓库中的验证文档与代码仓库提交分开；不 push。

### 16.3 每个 Milestone 的交接格式

- [ ] 用通俗中文说明完成行为、未完成项和明确没有做的范围。
- [ ] 列出修改文件、关键入口、依赖 SHA、功能开关、实际默认值、ledger owner 和 H10 readiness。
- [ ] 列出准确命令、命中测试数、通过/失败/跳过数和退出码；基线失败与新增失败分开。
- [ ] 列出 capture 的 effective config/outgoing request、usage completeness 和 unknown 路径，不输出凭据。
- [ ] 列出证据路径、代码 commit、分析 commit、工作树状态和下一 Milestone 起点。
- [ ] 没有自动化证据的项目不勾选；源码推翻假设时先更新本清单，再实施满足同一不变量的最小方案。

后续 agent 不应把 M1-M9 压成一次大改。B、C、D 只有在接线、预算分配和请求调参分开后
才有可解释的实验价值；正确率、最终测试和可信计量没有守住时，token 更低也不能采用。
