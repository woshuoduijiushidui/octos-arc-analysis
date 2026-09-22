# H09 竞品调研：减少无关工具定义开销

- 调研日期：2026-09-22
- 优化表原分析基线：`c599d18c5acd2b846f049ffea2be84e72fe60fac`
- 本次复核的 Octos 主线：`27d057c206c0f8250b60309905737f7e26ee0ba9`
- 本次调研采用的 H05 已提交基线：`3fe3fce4c155f3e9ba8c762a2fc7bd3aa33daf3d`
- 调研对象：Anthropic Claude Code、OpenAI Codex、DeepSeek Harness
- 范围：只做源码与官方文档调研；未修改运行代码，未运行付费模型或官方任务实验。本文沿用 [H03 调研](../h03/h03-output-pagination-recovery-competitor-research.md) 的组织方式。

## 结论先行

H09 建议**调整后采用**，但要先承认 Octos 已经完成了大部分最明显的工具裁剪，不能把历史收益重复计算为 H09 的新增收益。

当前 ARC stdio/solo 内核先把通用 coding 工具面缩到 13 个；代理再固定删除其中 4 个，所以普通工具轮实际发给 provider 的是 9 个，minimal 模式再删除 `shell` 后是 8 个，codegen 则是 0 个。剩余问题主要不是“还挂着几十个工具”，而是：

1. **最终工具集合在代理层才被改写**。内核的上下文预算和 prompt 指纹仍按改写前的 13 个 schema 计算，模型实际可见、内核认为可见、预算统计和缓存观测不是同一份清单。
2. **现有 `tool_search` 不是延迟加载器**。它只搜索已经通过 profile/policy/context filter 的可见工具，并只返回名称、描述和标签；被过滤掉的工具无法靠它恢复，返回结果也不会把 schema 注入后续请求。
3. **剩余 8–9 个工具都是固定 ARC 工作流中的基础能力**。为了省下少量 schema 而增加一次搜索调用，往往会重发整段历史，且会增加漏工具和错误调用风险，净 token 未必下降。
4. **动态工具收敛会改变缓存前缀**。按每次迭代猜测工具需求、LRU 驱逐或临时增删 schema，可能省当前请求，却让后续请求失去前缀复用；Octos 历史上已经因工具被静默逐出而出现能力不可用。

适合 Octos ARC 的方案是：

- 把代理已有的固定删除规则前移到内核的 stdio/solo 启动工具清单，让**模型可见 = 可调用 = 预算计算 = prompt 指纹 = provider 实际收到**。
- 为工具模式保留一个按名称排序、在一个 turn 内不变化的核心清单；codegen 继续使用 0 工具。若确实需要不同阶段清单，只在新进程或新 session 建立前确定，不能在同一工具循环中来回切换。
- 第一轮不要再删 `read_file`、搜索、编辑、写文件、`shell` 或 H03 的 `recall`。先用真实调用轨迹和官方 A/B 证明某个工具长期无用，再逐个做消融。
- 暂不为 ARC 的 8–9 个核心工具实现 Claude Code/Codex 式延迟加载。未来只有在插件或 MCP 目录明显扩大时才考虑，并且必须具备 provider 能力协商、完整 schema 返回、立即可调用、静态核心工具常驻和不支持时全量回退。
- ARC 中当前被代理删除的 `tool_search` 可继续不发给模型；除非它以后真正能发现并加载隐藏工具，否则把它算作“按需工具入口”会产生错误安全感。

这意味着 H09 的首个实现版本主要是**统一事实来源并建立可信实验底座**，不应宣称相对当前 provider 请求已经节省大量 token。真正的新增 token 收益要来自后续有证据的工具消融或大型扩展目录的延迟加载。

目前没有找到三家在相同 ARC 任务、模型、预算和缓存条件下验证工具裁剪收益的公开对照数据。下文的收益均为待测假设；**最终通过数与稳定性优先，全任务累计 token 次之，耗时不计入成绩**。

## 1. H09 到底解决什么问题

H09 处理的是：**每次模型请求都携带工具名称、描述和参数 schema 时，怎样减少不会使用的固定输入，同时不让模型失去完成任务所需的能力。**

需要区分四种机制：

| 机制 | 模型起始时看到什么 | 后续怎样获得能力 | 主要风险 |
| --- | --- | --- | --- |
| 全量工具 | 所有可用工具的完整 schema | 直接调用 | 每轮固定输入最大，工具选择更嘈杂 |
| 静态精简清单 | 当前工作流所需工具的完整 schema | 清单外能力不可用，或另开明确 profile/session | 误删工具会直接降低正确率 |
| 按阶段清单 | 当前阶段的完整 schema | 阶段边界切换清单 | 切换会改变缓存前缀，阶段判断错误会丢能力 |
| 按需延迟加载 | 核心工具 + 搜索/目录入口 | 搜索返回完整定义，并由协议允许随即调用 | 多一次模型往返；依赖 provider 协议与可靠检索 |

“只隐藏 schema”不等于“能力仍然存在”。一个可靠方案至少要回答：

1. 模型怎样知道隐藏工具存在？
2. 搜索结果是否包含可调用所需的完整 schema，而不只是名称？
3. 搜索后是下一轮注入工具，还是 provider 允许从搜索结果直接调用？
4. 执行路由、权限、审批和 schema 是否引用同一个工具身份？
5. provider 不支持延迟工具协议时怎样回退？
6. 工具集合改变后，历史请求、恢复会话和 prompt cache 是否仍一致？

H09 不负责缩短工具结果，那是 H03；不负责分配迭代和模型输出额度，那是 H08；不负责修复 usage 漏记，那是 H10。工具 schema 的**真实 provider 输入 token**仍应由 H10 的统一计量口径记录。

官方需求、测试和判分条件保持固定。不能通过移除官方任务实际需要的工具、跳过验证或把失败转成文本回答来制造 token 收益。

## 2. Octos 当前已经有什么

### 2.1 通用 coding profile 已经做过一次大幅收敛

Octos 在提交 [`c7f28d9e`][o-lean-commit] 中把默认 coding profile 从 49 个工具、约 44.6 KB schema、约 11K token/轮，缩到 18 个工具、约 14.5 KB、约 3.6K token/轮，并保留 `coding-full` 作为完整工具面入口。这说明“工具定义是每轮固定成本”已经被项目识别和处理过。

但随后提交 [`ba268804`][o-soften-commit] 修正了一个关键假设：profile 过滤会物理删除 registry 中的工具，而 `tool_search` 只搜索过滤后的可见集合，没有 activation 工具。因此被精简掉的 spawn、memory 和 shell alias 并不能按需恢复。该提交恢复这些能力，只删除被 `edit_file`/`diff_edit` 覆盖的 `apply_patch`。

这个历史很重要：

- 静态 profile 确实可以显著降低固定 schema 成本。
- “有一个名为 `tool_search` 的工具”不能证明被删能力仍可发现或可调用。
- 优化必须以最终执行链路为准，不能只看配置描述。

更早的 [`172fb2be`][o-rfc0-commit] 已删除 LRU 工具延迟和 `activate_tools`。原因之一是关键 spawn-only 工具曾因空闲驱逐从模型视图中消失，模型随后正确地报告“没有这个工具”。当前 registry 的约定是：除 internal-hidden、provider policy、context filter 和 active context 排除外，所有 enabled 工具每轮都发出完整 schema，[`specs()`][o-registry-specs] 会缓存结果并按名称排序，避免 HashMap 顺序破坏 prompt cache。

### 2.2 ARC stdio/solo 已经是更小的固定清单

最新主线的 stdio/solo 默认清单有 12 个工具；当前 H05 分支接入 H03 `recall` 后有 13 个，[H03 M5 验证](../h03/h03-m5-implementation-verification.md)记录了该入口接线：

```text
ask_user_question, check, diff_edit, edit_file, glob, grep, list_dir,
read_file, recall, shell, tool_search, update_plan, write_file
```

该入口先应用 coding profile，再用固定白名单 `retain`；`OCTOS_STDIO_SOLO_TOOLS` 还能在进程启动时进一步收窄，而且只能删、不能增加未注册工具，见 [stdio/solo 清单与环境变量][o-stdio-profile] 和 [实际收敛位置][o-stdio-retain]。

这已经符合 H09 的大方向：ARC 不会把通用聊天、浏览器、媒体、消息、长期记忆、流水线或子 Agent 工具全部发给模型。

### 2.3 最终 provider 工具集仍由 Python 代理二次修改

ARC 代理默认删除：

```text
spawn, ask_user_question, check, tool_search, update_plan, exec_command
```

其中 `spawn` 和 `exec_command` 本来就不在当前 stdio/solo 清单。因此普通工具轮的实际集合是 9 个：

```text
diff_edit, edit_file, glob, grep, list_dir, read_file, recall, shell, write_file
```

small-task minimal 模式再删除 shell 类工具，当前 stdio 实际只再少一个 `shell`，成为 8 个。codegen 通过新 session 的无工具路径和代理 `strip_all_tools` 使用 0 工具，见 [代理裁剪][o-proxy-trim]、[minimal shell 切换][o-minimal] 和 [codegen 无工具路径][o-codegen].

问题在于这个删除发生在 HTTP 请求离开内核之后：

- agent loop 先从 registry 取得完整 `tools_spec`，[每轮都把它交给 LLM][o-loop-tools]；
- H03 输出预算把这份 schema 的序列化字节计入固定输入；
- prompt cache 指纹也对这份 schema 计算工具数量和 hash；
- 最后 Python 代理才删掉 4 个实际 schema。

依据见 [LLM 固定预算][o-llm-budget] 与 [prompt 指纹][o-llm-fingerprint]。因此当前 provider 真正计费的请求已经较小，但内核的预算、观测和故障诊断仍描述另一份工具面。H09 首先应消除这类“双重事实来源”。

### 2.4 当前 `tool_search` 不能承担能力恢复

Octos 的 catalog snapshot 明确来自“当前模型可见工具”，会再次应用 internal-hidden、provider policy、context filter 和 active context 过滤，[见 registry catalog][o-catalog]。`tool_search` 随后只在该 catalog 中做名称/描述/标签匹配，返回：

```json
{"name": "...", "description": "...", "tags": ["..."]}
```

它不返回输入 schema，不改变 registry，也没有“加载后可调用”的协议，[见工具实现][o-tool-search]。所以：

- profile 或 `retain` 已删除的工具不在搜索目录里；
- provider request 里被代理删除的 `tool_search` 本身也不可调用；
- 即使保留它，也只是在 8–13 个已知工具中检索元数据，不能成为 Claude Code/Codex 式延迟加载器。

对 ARC 来说，当前 `tool_search` 的一次调用成本很可能高于它对小清单的帮助。除非重做其契约，否则继续从 provider 工具面删除是合理的。

### 2.5 现有缓存稳定性基础可直接复用

Octos 已有三项适合 H09 的基础：

1. `ToolPolicy`、profile filter、provider policy、context filter 和 stdio/solo allow-list 已能在 registry 边界收敛工具。
2. `cached_specs` 避免每次重建同一 schema 列表。
3. 工具按名称排序，保证相同集合字节稳定，[对应提交][o-sort-commit]。

H09 不需要重新发明 LRU、分类器或每轮动态路由。最小改动是让现有收敛能力更早得到**最终 ARC 清单**，并让后续所有预算、指纹和 provider 序列化共用这一结果。

## 3. 竞品版本与证据边界

| 竞品 | 固定版本 | 可审计范围 | 本次重点 |
| --- | --- | --- | --- |
| Claude Code | [`8187baaa`][cc-commit]，2026-09-21 | 官方文档、CLI reference、CHANGELOG；CLI 核心未公开 | MCP Tool Search、`alwaysLoad`、静态工具限制、缓存稳定修复 |
| OpenAI Codex | [`e51aacad`][cx-commit]，2026-09-21 | 公开 Rust 实现及测试 | 每轮工具计划、Direct/Deferred/Hidden、BM25 schema 搜索、协议回退 |
| DeepSeek Harness | [`ddefc45f`][ds-commit]，`0.1.6-alpha.2`，2026-09-17 | 公开 TypeScript 实现、preset、文档与快照 | 单一组装边界、per-agent restrict、稳定顺序、固定极简 preset |

Claude Code 的 GitHub 仓库仍主要公开 changelog、插件和分发材料，不包含完整 CLI 内核。本文对其机制只采用官方文档明确声明的行为，不把闭源实现细节当作已审计源码。

三家面对的工具规模不同。Claude Code 和 Codex 的延迟加载主要解决大量 MCP、connector 或插件工具；DeepSeek 的 preset 解决产品角色之间的静态能力差异。Octos ARC 当前实际只有 8–9 个核心工具，不能只因为竞品有 Tool Search 就推断同一机制在 ARC 上有净收益。

## 4. 三家怎么做

### 4.1 Claude Code：大量 MCP 工具延迟，核心能力与例外保持常驻

Claude Code 官方 [MCP Tool Search 文档][cc-mcp-search] 将工具搜索用于大量 MCP 定义：启动时先提供工具名称和 server instructions，需要时再由 Tool Search 取得定义，而不是把每个 MCP schema 都放入初始上下文。

配置边界包括：

- `ENABLE_TOOL_SEARCH=true` 或未设置时启用延迟工具搜索；
- `auto` 在 MCP 工具定义占上下文比例达到默认 10% 时启用，`auto:N` 可改阈值；
- `false` 关闭，回到 upfront loading；
- 不支持 Tool Search 的模型或 provider 会回退到全量加载；
- server 配置 `alwaysLoad: true`，或单工具 `_meta["anthropic/alwaysLoad"]`，可让关键工具跳过延迟；
- 工具描述和 server instructions 各自限制为 2 KB，避免异常定义挤占上下文。

这里最值得借鉴的不是阈值数字，而是**能力协商 + 关键工具常驻 + 完整回退**。模型不会因为 provider 不支持特殊协议就突然失去工具。

CLI 还有两类容易混淆的控制：

- `--tools` 限制 built-in 工具的实际可用集合；
- `--allowedTools` 只是把匹配调用设为免审批，不等于增加或删除工具。

官方 [CLI reference][cc-cli] 还提供 `--bare`：关闭多数自动发现，但仍保留 Bash、文件读取和文件编辑。这与 ARC 的静态核心清单思路更接近，而不是让每个基础文件工具都经过搜索。

Claude Code 的 CHANGELOG 连续记录了工具集合变化导致的缓存和能力问题：

- 晚连接工具改为 deferred，保持会话工具列表 byte-stable；
- MCP 断开、升级或中途新增工具不再重写既有工具列表；
- resume 时不再重渲染已加载的 MCP 定义；
- `alwaysLoad` server 中途连接后可在下一轮直接使用；
- 延迟工具在压缩后丢失输入 schema、首轮 bypass 未就绪等问题均需要专门修复。

对应证据见 [byte-stable 修复][cc-byte-stable]、[动态工具与恢复修复][cc-dynamic]、[`alwaysLoad`][cc-always-load] 和 [描述上限][cc-description-cap]。这说明延迟加载不是“加一个搜索工具”即可完成，而是一套跨启动、重连、压缩、恢复和 provider 协议的状态机。

**迁移判断：**

- 采用核心工具常驻、扩展工具延迟、能力不支持时全量回退的原则。
- 采用同一会话工具列表尽量 byte-stable 的原则。
- 不复制 10% 阈值。ARC 当前工具数太少，且计分看全任务 token，不看单次 schema 占比。
- 不把闭源产品文档中的行为写成 Octos 已有能力。

### 4.2 OpenAI Codex：按能力构建工具路由，搜索结果本身携带可调用 schema

Codex 在每个 turn 根据 tool policy、模型能力、provider 能力、环境、feature 和 MCP 配置构建 `ToolRegistry` 与最终 router，[见构建入口][cx-plan]。这不是用自然语言分类器猜工具，而是由明确运行状态决定工具面。

其工具暴露有多种状态，包括 Direct、Deferred、CodeModeOnly 和 Hidden。对 MCP 工具：

- 模型支持 search tool 且 provider 支持 namespace tools 时，MCP 工具可设为 Deferred；
- 不满足条件时改为 Direct，而不是保留一个模型无法使用的延迟协议；
- tool/server policy 仍可把工具完全 Hidden；
- 每个 MCP server 还支持 `enabled_tools` allow-list 和 `disabled_tools` deny-list，[见配置][cx-mcp-config]。

对应实现见 [MCP 注册与默认暴露][cx-mcp-exposure]、[暴露策略][cx-exposure-policy] 和 [能力检查][cx-search-capability]。Agent plugin 的 MCP schema 还设有单工具 8,000 字节、总计 64,000 字节的硬边界；超限工具会 Hidden，而不是无限扩大请求。该边界服务的是插件安全和请求可控性，不是适合直接复制到 ARC 的收益阈值。

Codex 的 `tool_search` 与 Octos 当前实现有本质区别：

1. 只索引 exposure 为 Deferred 的工具。
2. 用 BM25 搜索预建文档，默认返回上限是 8。
3. 检索文本包含工具名、描述、namespace、参数名和 schema 描述，不只搜工具名。
4. 搜索结果返回完整可加载 schema，并标记 `defer_loading=true`。
5. provider 将 `tool_search_output` 保留在请求历史中；后续请求不必把命中的工具重复加入顶层 `tools` 数组，模型仍可直接调用。

实现见 [搜索 handler][cx-search-handler]、[搜索文本与 schema 规范化][cx-search-index]。集成测试明确检查：第一轮顶层只有 `tool_search`、目标工具未出现；第二轮历史中带搜索结果 schema；随后模型直接调用目标工具；第二、第三轮顶层工具数组仍不注入该目标，[见端到端测试][cx-search-test]。

这个设计比“下一轮重建工具数组并增加命中项”更有利于前缀稳定，但它依赖 provider 对 `tool_search`、namespace 和 `defer_loading` 的协议支持。Octos 当前 OpenAI-compatible ARC 代理没有证明支持同样语义，不能只复制 JSON 字段。

**迁移判断：**

- 借鉴 typed exposure、同一 router 管可见与可调用、policy 先于搜索、provider capability gate。
- 若未来做扩展目录搜索，借鉴对名称、描述和 schema 字段的检索，以及搜索结果返回完整定义。
- 不为当前 8–9 个核心工具移植整套协议；搜索往返和实现复杂度可能超过节省。
- 不把 Codex 的 8,000/64,000 字节上限当作 ARC 的最优参数。

### 4.3 DeepSeek Harness：按 preset 和 agent 静态组合，显式保护缓存稳定

DeepSeek Harness 把 prompt sections 与 tools 合并为 `PromptAssembly { sections, tools }`，agent loop 每一步只消费一份 assembly；tool filtering 或 progressive disclosure 都应在这个统一边界改写，[见架构决策][ds-assembly]。这与 Octos 当前“内核预算一份、代理最终请求另一份”形成鲜明对比。

普通 native 模式的行为是：

- 每个 agent 看见其 scope 下允许的完整 schema；
- `ctx.tools.restrict(filter)` 用 allow/deny mask 收窄继承工具；
- schema 默认按名称字典序排列，也可用显式 `toolOrder` 固定位置；
- visible set 或顺序不变时前缀稳定，注册、卸载、restriction 或重排都可能从首个变化位置破坏缓存。

依据见 [tools package][ds-tools]、[schema token/cache 说明][ds-tools-cost] 与 [system-prompt package][ds-prompt]。

它没有在所查版本中提供通用、默认的 Tool Search 延迟加载包。架构把 assembly rewrite 留作未来扩展点，不等于产品当前已经实现 progressive disclosure。

DeepSeek 更值得 Octos 借鉴的是**预先声明完整角色清单**：

- standard preset 在 plan mode 中故意保持工具目录不变，只用规则禁止修改工具，明确理由是 request-cache stability，[见 standard preset][ds-standard].
- minimal preset 则是另一套独立、固定的 agent composition，只暴露一个持久 shell；快照把初始工具列表固定为一个 `bash`，且没有动态 changes，[见 minimal preset][ds-minimal] 和 [快照][ds-minimal-snapshot].

这两种选择并不矛盾：同一 session 内稳定，新的角色/session 可以从一开始选择另一份固定清单。

DeepSeek 的 PTC mode 把多工具呈现为 `run_code` 加生成 SDK，但官方文档明确说它是“schema 换 SDK 文本和一个 transport schema”，不承诺普遍减少 token，[见 PTC 说明][ds-ptc]。对 Octos ARC 直接改成代码执行代理，会改变工具协议、错误恢复、权限和模型训练先验，不属于 H09 的最小改动。

**迁移判断：**

- 采用单一 assembly/registry 事实来源和确定性排序。
- 采用“按 session/preset 固定，而不是按迭代抖动”的工具清单。
- 可参考 minimal preset 为 codegen 保持独立 0 工具模式。
- 不采用 PTC 作为本轮 token 优化，也不把未来扩展点写成现成功能。

## 5. 横向比较

| 维度 | Claude Code | OpenAI Codex | DeepSeek Harness | Octos ARC 现状 |
| --- | --- | --- | --- | --- |
| 核心策略 | built-in 静态工具 + 大型 MCP 延迟搜索 | 每 turn typed router；MCP 可 Direct/Deferred/Hidden | preset/agent 静态组合；可 restrict | stdio 固定 13 个，代理再删成 9/8 |
| 搜索结果 | 官方文档声明按需发现 MCP 定义 | 返回完整 schema，历史中的搜索结果可直接授权调用 | 未发现通用延迟搜索实现 | 只返回可见工具的名称/描述/标签 |
| 不支持协议 | upfront loading 回退 | Direct exposure 回退 | 始终使用完整 visible set | 没有延迟协议 |
| 关键工具常驻 | `alwaysLoad`；bare 仍有 Bash/read/edit | core tools 与 exposure policy 分开 | preset 明确挂载 | 核心文件/搜索/edit/shell 常驻 |
| 工具顺序 | CHANGELOG 强调 byte-stable | namespace/spec 规范化并由 router 构建 | 字典序或显式 `toolOrder` | registry 按名称排序 |
| 阶段变化 | 主要用 agent/CLI 工具范围 | 由明确 turn context 与 capability 决定 | standard plan 故意不换 catalog | proxy 可按 minimal/codegen 后置删除 |
| 可见与可调用一致性 | 文档行为强调可用性与回退 | 同一 registry/router 管理 | 同一 scoped registry 管理 | 代理删除后与内核预算/指纹不一致 |
| 最适合的规模 | 大量 MCP/connectors | 大量 MCP、动态和扩展工具 | 固定角色或产品 preset | 当前只有 8–9 个实际核心工具 |

共同规律不是“所有产品都动态裁剪”，而是：

1. **小而固定的核心集合直接提供。**
2. **只有大而稀疏使用的扩展目录才值得按需发现。**
3. **可见性、可调用性和权限必须由同一份结构化状态决定。**
4. **同一会话尽量保持 schema 字节稳定。**
5. **provider 不支持延迟协议时要保守回退，不能静默丢能力。**

## 6. 适合 Octos ARC 的目标设计

### 6.1 一份规范工具清单贯穿完整请求

对每个 ARC model turn，在 Agent 构造前生成一次 `ArcToolRoster`（名称仅为说明，不要求新增同名类型），至少包含：

- 固定模式：`tool_full`、`tool_minimal` 或 `codegen_none`；
- 按名称排序的工具名；
- roster 版本或稳定 hash；
- 选择依据：明确 harness phase/config，不使用模型分类结果；
- 必需工具不变量。

同一份清单必须同时驱动：

1. registry `retain` / ToolPolicy；
2. `ToolRegistry::specs()`；
3. 执行层的可调用检查；
4. H03 固定输入预算；
5. prompt fingerprint 与缓存观测；
6. provider 请求 `tools`；
7. H10 的工具数量和 schema 字节统计。

Python 代理可保留断言，检查不该出现的工具确实不存在；不再作为正常请求的主要工具过滤器。这样代理若仍删到工具，应被记录为配置错误，而不是默默改变请求。

### 6.2 默认保留当前实际 9 工具，不继续猜测删减

普通工具模式的第一版候选应与当前 provider 实际请求保持一致：

```text
diff_edit, edit_file, glob, grep, list_dir, read_file, recall, shell, write_file
```

原因：

- `read_file`、`glob`、`grep`、`list_dir`覆盖定位与读取，不应在没有调用轨迹时假定某项冗余；
- `diff_edit` 是 H05 主路径，`edit_file` 仍是补充编辑能力；
- `write_file` 负责新文件；
- `shell` 负责项目检查和必要命令；
- `recall` 是 H03 的恢复入口，删除它会使大输出恢复承诺失效。

`ask_user_question`、`check`、`update_plan` 在无人值守 ARC 流程中已有外层替代或不适用；当前代理也已删除。`tool_search` 对被过滤工具没有恢复能力，保留只增加 schema 和潜在调用。此处是对**现有实际行为的内核化**，不是新一轮能力削减。

minimal 模式可继续在新 turn/session 建立前去掉 `shell`；codegen 继续 0 工具。若同一 Agent/session 会跨模式复用，则优先保持 9 工具稳定，不能为了少一个 schema 在中途改写前缀。应由实际 session 生命周期和缓存观测决定，而不是仅看阶段名称。

### 6.3 暂不对核心工具做按需搜索

为 8–9 个工具增加搜索通常要付出：

- `tool_search` 自身 schema；
- 一次模型决定与工具调用；
- 搜索结果 token；
- 下一次请求重发历史；
- 检索失败、别名不匹配和模型不知道何时搜索的风险。

即使单轮省下几个 schema，只要增加一次请求，全任务 token 就可能上升。ARC 的核心工具名和工作流非常稳定，静态清单比动态检索更适合。

### 6.4 为未来大型扩展目录保留明确门槛

未来如果 ARC 确实接入大量 MCP/plugin 工具，可单独设计 deferred catalog，但必须同时满足：

1. 静态核心 8–9 工具始终直接可见。
2. provider capability handshake 明确支持搜索结果中的 schema 与后续调用。
3. 搜索目录包含隐藏扩展工具的完整、权限过滤后元数据。
4. 搜索结果返回完整 schema 和稳定工具身份，不只返回名称。
5. 搜索命中后执行 router 立即可解析同一工具。
6. provider 不支持时回退到经过 allow-list 的完整扩展集合。
7. late connection、disconnect、resume、compaction 和 schema 更新都有确定性测试。
8. 只有当扩展 schema 占用和实际稀疏使用达到实测门槛时启用。

这个能力应与当前 metadata-only `tool_search` 使用不同的 typed 契约，或明确升级现有契约；不能让同名工具在不同入口表现为两种语义。

## 7. 最小改动与迁移判断

本节只给出调研结论，不是实施计划。

| 子项 | 复用与改动 | 预期收益/取舍 | 决策 |
| --- | --- | --- | --- |
| H09a | 用现有 `OCTOS_STDIO_SOLO_TOOLS` / ToolPolicy 在 Agent 构造时固化当前实际 9/8/0 工具清单 | 统一可见、可调用、预算、指纹和 provider 请求；相对当前 provider token 基本不变 | **P0 采用** |
| H09b | 保留 `specs()` 缓存和按名称排序；给最终 roster 记录 count、bytes、hash | 让 cache 和 A/B 可审计；增加极少量日志 | **P0 采用** |
| H09c | 将 Python proxy 的工具删除改为断言或兼容兜底，不再作为正常路径的事实来源 | 避免双层配置漂移；需保证旧内核兼容路径清楚 | **P0 采用** |
| H09d | 普通工具模式先保持 9 个，minimal 保持 8 个，codegen 保持 0 个 | 正确率风险最低；第一阶段没有额外大幅 token 收益 | **采用** |
| H09e | 用真实调用数据逐项消融 `list_dir`、编辑工具等候选 | 可能继续减少固定 schema；任何漏能力都可能增加重试 | **实验后决定** |
| H09f | 为大型 MCP/plugin catalog 实现真正 deferred search | 大目录下可能显著节省；协议、恢复和缓存复杂度高 | **当前 ARC 暂缓** |
| H09g | 每迭代分类、LRU 驱逐、根据上一轮调用增删工具 | 当前轮可能更小，但容易丢能力并破坏缓存 | **不采用** |
| H09h | 随意缩短参数 schema 或描述 | 可能省 token，但会改变模型调用质量和输入约束 | **不作为首选** |
| H09i | 直接复制 PTC / `run_code` | 改变工具协议和模型行为，收益不确定 | **不采用** |

最小落点是 stdio/solo profile 构造、现有 allow-list/ToolPolicy、prompt fingerprint 与代理断言。无需修改官方任务、测试、模型提示内容或外层工作流。

## 8. 对照实验

### 8.1 先验证端到端不变量

以下是建议后续实施时运行的确定性验证，本次没有修改代码或新跑这些测试。

| 场景 | 必须观察到的结果 |
| --- | --- |
| 普通工具 turn | registry、`specs()`、预算、fingerprint、provider body 均为同一 9 工具 |
| minimal 新 turn/session | 启动时即为 8 工具；provider 代理无需再删除 `shell` |
| codegen | registry/model path 与 provider body 均为 0 工具，不只在代理末端删除 |
| 同一工具 turn 的多次请求 | 工具名称、顺序和 schema 字节完全一致 |
| 两次独立进程使用同一 roster | 序列化结果和 roster hash 一致 |
| 工具调用 | 每个模型可见名称都能路由执行；隐藏名称返回 typed unknown/denied，不被 search 虚假宣传 |
| `tool_search` 被移除 | prompt 不再引导调用它；无未知工具重试 |
| H03 恢复 | `recall` 在所有需要恢复的工具模式可见且可调用 |
| H05 编辑 | `diff_edit`、`edit_file` 和 `write_file` 的既有场景均不回归 |
| proxy 兼容兜底 | 新内核请求触发零次代理工具删除；旧内核路径有明确记录 |
| roster 配置错误 | 缺少必需工具、重复名或未知名时启动失败，不静默继续 |
| provider 不支持 tools | 进入已有 tool-free/codegen 路径或明确失败，不伪装成功 |

测试应捕获真正发往 provider 的 JSON，而不只断言 registry 单测。否则无法证明代理、provider adapter 或路由层没有再次改变工具集合。

### 8.2 A/B/C 设计

| 组别 | 策略 | 目的 |
| --- | --- | --- |
| A | 当前实现：内核 13，代理实际发 9/8，codegen 0 | 真实线上基线 |
| B | 与 A 相同的最终 9/8/0 清单，但在 registry/Agent 构造时完成，代理只断言 | 验证统一事实来源不降低正确率；provider token 理应接近 A |
| C | 可选消融：在 B 上一次只删除一个有真实低使用证据的工具，或预先声明另一份固定 phase roster | 验证是否存在额外净 token 收益，不能与 B 的接线修复混算 |

B 不是为了证明“9 比 13 省 token”，因为 A 的 provider 已经只收到 9。B 的成功标准是：

- 官方通过数和稳定性不下降；
- 无 missing-tool、unknown-tool 或额外重试；
- 内核统计与 provider body 完全一致；
- prompt 指纹能解释实际缓存命中；
- provider 总 token 与 A 在同等请求轨迹下基本一致。

C 才是剩余 schema 缩减的收益实验。每次只改变一个清单因素，并保留返回 B 的快速回退。不要把“某工具在一次样本中没调用”当作永久删除证据。

固定官方需求、测试、模型、推理参数、模板、H01–H05 状态、session scope、请求预算和修复策略。分别记录 codegen、普通工具和 minimal 工具 turn，不能把不同模式的自然 token 差异算作 H09。

指标顺序：

1. 最终官方测试通过数、全通过率、回归数和重复运行稳定性。
2. missing-tool、unknown-tool、工具搜索、因工具缺失改走 shell、额外模型请求和修复轮数。
3. 全任务 provider 输入/输出/cache/reasoning token，包含失败与重试。
4. 每次请求的 `tools_count`、规范序列化字节和 provider tokenizer 实际 token。
5. roster hash、工具数组 hash、稳定前缀 hash、cache read/write token 和缓存命中率。
6. 每个模式、阶段和工具的调用次数，以及“暴露但从未调用”的比例。
7. 耗时只作诊断，不计入成绩。

不能只比较 schema 字符数。删除一个工具如果导致模型多发一次请求、用 shell 重新实现能力或因未知调用重试，全任务 token 可能更高。

真实环境实验前按项目约定执行 `source ~/.zshrc`，核实 `OCTOS_BIN` 和两个仓库提交。付费官方实验还需要 `ARCBENCH_API_KEY`；缺少时只能完成静态与确定性验证，不能把它写成官方 A/B 结论。

## 9. 最终判断

H09 值得继续，但当前优先级不是再造一个动态 Tool Search。Octos 已经从通用 49 工具降到 ARC provider 实际 8–9 个，最便宜且最可靠的下一步是：

> **把现有最终工具清单前移到内核，保证一份稳定清单贯穿注册、可调用性、预算、指纹和 provider 请求，再用真实任务数据决定是否继续删除。**

Claude Code 和 Codex 证明延迟加载适合大量 MCP/插件工具，但也展示了 provider 兼容、恢复、动态连接和缓存稳定性的复杂成本。DeepSeek Harness 说明另一条同样有效的路线：按 agent/preset 预先选择固定清单，并在同一 session 内保持稳定。后者更符合当前 ARC 的固定工作流和小工具面。

因此本轮决策是：**静态核心 roster 调整后采用；核心工具按需加载暂缓；大型扩展目录的 deferred search 保留为条件性后续方向。**任何新增优化都必须以通过率不下降为前提，并比较整题累计 token，而不是单轮 schema 大小。

## 参考源码与官方文档

下列外部源码链接均固定到本次核查的提交。尚未推送的 Octos H03/H05 分支源码使用工作区相对链接，并由文首提交号固定；Claude Code 的运行内核未公开，其机制引用官方滚动文档和固定 commit 的 CHANGELOG，官方文档内容可能在 commit 之后继续更新。

[o-lean-commit]: https://github.com/woshuoduijiushidui/octos-arc/commit/c7f28d9e718b0ba9efbbba7582962920efaf43a5
[o-soften-commit]: https://github.com/woshuoduijiushidui/octos-arc/commit/ba2688041ac872958531ae2666eed736ccbc1d4d
[o-rfc0-commit]: https://github.com/woshuoduijiushidui/octos-arc/commit/172fb2be61e9748084eda49813b39fd0b84a318f
[o-sort-commit]: https://github.com/woshuoduijiushidui/octos-arc/commit/b6b864bb
[o-stdio-profile]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/runtime/profile.rs#L57-L103
[o-stdio-retain]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-cli/src/runtime/profile.rs#L1577-L1599
[o-registry-specs]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/tools/registry.rs#L700-L750
[o-catalog]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/tools/registry.rs#L1383-L1436
[o-tool-search]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/tools/coding_tools.rs#L3125-L3226
[o-loop-tools]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/loop_runner.rs#L1307-L1315
[o-llm-budget]: ../../octos-arc/crates/octos-agent/src/agent/llm_call.rs#L89-L104
[o-llm-fingerprint]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/crates/octos-agent/src/agent/llm_call.rs#L136-L153
[o-proxy-trim]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/llm_proxy.py#L270-L335
[o-minimal]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/main.py#L1780-L1794
[o-codegen]: https://github.com/woshuoduijiushidui/octos-arc/blob/27d057c206c0f8250b60309905737f7e26ee0ba9/arc/main.py#L2038-L2057

[cc-commit]: https://github.com/anthropics/claude-code/tree/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0
[cc-mcp-search]: https://code.claude.com/docs/en/mcp#scale-with-mcp-tool-search
[cc-cli]: https://code.claude.com/docs/en/cli-reference#cli-flags
[cc-byte-stable]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L645
[cc-dynamic]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L707-L715
[cc-always-load]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L3810
[cc-description-cap]: https://github.com/anthropics/claude-code/blob/8187baaaafb3a9ada02d3d6fb4e8d68587aef6b0/CHANGELOG.md#L4608

[cx-commit]: https://github.com/openai/codex/tree/e51aacad602dec4108db0d2f62bb7f40c6ced56c
[cx-plan]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/src/tools/spec_plan.rs#L130-L186
[cx-mcp-exposure]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/src/mcp_tool_exposure.rs#L19-L147
[cx-exposure-policy]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/src/tools/spec_plan.rs#L189-L268
[cx-search-capability]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/src/tools/spec_plan.rs#L624-L637
[cx-mcp-config]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/config/src/mcp_types.rs#L250-L272
[cx-search-handler]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/src/tools/handlers/tool_search.rs#L28-L255
[cx-search-index]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/tools/src/tool_search.rs#L12-L180
[cx-search-test]: https://github.com/openai/codex/blob/e51aacad602dec4108db0d2f62bb7f40c6ced56c/codex-rs/core/tests/suite/search_tool.rs#L553-L832

[ds-commit]: https://github.com/deepseek-ai/deepseek-harness/tree/ddefc45fbc7f8e46dd73185e68295696d1297887
[ds-assembly]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/.agents/notes/archived/architecture/2026-06-11-tool-schemas-in-prompt-assembly.md#L8-L23
[ds-tools]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/core/tools/README.md#L10-L81
[ds-tools-cost]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/core/tools/README.md#L154-L169
[ds-prompt]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/core/system-prompt/README.md#L153-L165
[ds-standard]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/preset/agent-presets/presets/standard/agent.cordis.yml#L101-L125
[ds-minimal]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/preset/agent-presets/presets/minimal/agent.cordis.yml#L1-L69
[ds-minimal-snapshot]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/snapshots/web/minimal-preset/tool-schemas.expected.json#L1-L21
[ds-ptc]: https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/core/tools/README.md#L171-L202
