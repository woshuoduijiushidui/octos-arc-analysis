# H09 实施 Milestone：统一工具清单并验证真实 token 收益

- 状态：M0-M7 待实施
- 面向对象：后续 coding agent
- 设计依据：[H09 竞品调研](./h09-tool-definition-overhead-competitor-research.md)
- 关联约束：[H03 实施清单](../h03/h03-implementation-milestone.md)、[H05 实施清单](../h05/h05-implementation-milestone.md)、[优化总表](../harness-optimization-table.md)
- 编写日期：2026-09-22
- 调研时 Octos 主线：`27d057c206c0f8250b60309905737f7e26ee0ba9`
- 调研时 H05 B/C：B `8287e8f8`；C `bb53c733`

本文是实施 todo list，不代表代码已经完成。只有同时具备代码、自动化验证和可追溯证据时，
才能把 `[ ]` 改成 `[x]`。文件名、类型名和测试名可随最新主线调整，但分组边界、正确率优先、
计量口径和停止条件不得静默弱化。

## 0. 后续 Agent 先读这一节

H09 当前不是把 13 个 provider 工具重新缩到 9 个。这个删除已经由 Python 代理完成：

```text
A 当前路径
内核 specs = 13
代理删除 4 个
provider 实际收到 = 普通工具模式 9 / minimal 8 / codegen 0
```

第一阶段 B 只把同一份最终清单提前到内核：

```text
B 目标路径
内核 specs = provider 最终清单
预算、指纹、可调用性和 provider 请求共用该清单
代理正常情况下删除 0 个
```

因此必须牢记：

1. **B 相对 A 的直接 provider 工具 schema token 收益预计接近 0。**
2. B 的价值是修正双重事实来源、释放被 4 个无效 schema 占用的内核预算，并建立可信计量。
3. 只有后续 C 在不降低正确率的前提下把 9/8 进一步收窄，才能声明 H09 新增了工具 schema token 收益。
4. 若没有合格 C，允许最终结论是“13→9 的收益已由现有代理实现；H09 只采用 B 的一致性修复，不宣称新增 token 节省”。

目标合同：

```text
工具清单由 harness 的确定性模式选择
同一 session 内保持稳定
模型可见 = registry 可调用 = 内核预算 = prompt 指纹 = provider 实际请求
权限策略只能继续收窄，不能重新加入工具
任何进一步删除都必须通过独立实验
```

评估顺序固定为：

1. 官方测试通过数、回归数和重复运行稳定性。
2. missing-tool、unknown-tool、不可调用但被宣传、错误 fallback 和错误权限扩大，目标均为零。
3. 全任务累计 provider input/output/cache/reasoning token，包含失败、重试和新增请求。
4. 工具 schema 的数量、规范字节和真实 token 只用于解释总量。
5. 请求数、工具调用数和耗时用于诊断；耗时不计入成绩。

### 0.1 A/B/C 到底是什么

| 组别 | 内容 | 可以得出的结论 |
| --- | --- | --- |
| A | 当前实现：stdio 内核通常 13 个，代理最终发送 9/8 个；codegen 0 个 | 当前真实正确率、总 token 和双层清单基线 |
| B | 与 A 相同的最终 9/8/0 清单，但在 Agent/registry 构造前确定；代理只作兼容保护 | 单一事实来源是否正确；不能把历史 13→9 收益再次记入 H09 |
| `C_i` | 从 B 出发，一次只删除一个有证据的工具或使用一份预先声明的更小静态 roster | 该单项是否产生新的净 token 收益且不降低正确率 |

不同 `C_i` 是独立实验臂，不能把多个删除混成一个 C 后再猜是哪项造成回归。

### 0.2 执行原则

1. 开工先 `git fetch origin main`，从当时最新 `origin/main` 创建 `feat/tool-roster` 或独立 worktree；不要直接在当前 H05 分支继续堆叠。
2. 检查 `octos-arc` 与 `octos-arc-analysis` 的工作树。不得删除、覆盖或提交用户已有的未跟踪目录和改动。
3. 若最新主线尚未包含 H03/H05 的选中能力，先建立可追溯共同底座并单独验证；依赖收益不能记入 H09。
4. M1-M3 只形成 B；M5 才允许形成 `C_i`。不得在同一提交里同时前移清单、删除新工具和改写工具描述。
5. 每个 Milestone 完成后本地提交；不推送远程，不创建 PR，除非用户另行明确要求。
6. 不修改官方需求、测试、模型、reasoning、session scope、请求预算、修复轮数或超时来制造收益。
7. 不让 AI 或另一个模型动态判断本轮应该暴露哪些工具；roster 只能来自明确模式、配置和已注册能力。
8. 不恢复 LRU/`activate_tools`，不实现 deferred Tool Search，不引入 PTC/`run_code`，不缩短现有工具 schema 文案；这些均不属于 B。
9. H10 的失败/重试 usage 口径在付费实验前必须可用。unknown 不能记为 0。
10. 真实环境运行前执行 `source ~/.zshrc`。缺少 `ARCBENCH_API_KEY`、provider key、endpoint 或 `OCTOS_BIN` 时，写明缺少项和补充位置，不反复重试。

| Milestone | 主要产出 | 对应分组 |
| --- | --- | --- |
| M0 | 最新共同底座、真实调用图、A 请求证据和计量口径 | A |
| M1 | 在进程/session 建立前选择规范静态 roster | B |
| M2 | registry、预算、指纹、provider 与代理兼容保护统一 | B |
| M3 | 确定性验收、观测与 B 冻结 | B |
| M4 | 固定官方任务 A/B 对照，单独决定是否采用 B | A/B |
| M5 | 基于证据的一次一项 `C_i` 消融 | `C_i` |
| M6 | 固定官方任务 B/`C_i` 对照，选择或停止 | B/`C_i` |
| M7 | 最新主线集成、默认值、回滚和最终结论 | 选中方案 |

## 1. 分支、依赖和开关

### 1.1 M0 必须冻结的版本

- [ ] 记录两个仓库的当前分支、HEAD、`origin/main`、工作树和未推送提交；不自动清理。
- [ ] 从最新 `origin/main` 创建 H09 分支或独立 worktree，记录 `MAIN_SHA`。
- [ ] 核对 H03 `recall`、H03 最终输出预算、H05 编辑工具和 H10 usage 计量是否已在主线；逐项记录“已包含、需移植、不适用”。
- [ ] 若需移植依赖，先形成独立依赖提交并跑专项回归，冻结共同底座 `A_SHA`；此时 H09 行为仍关闭。
- [ ] 记录 A 的 `OCTOS_BIN` 路径、二进制 SHA-256、Rust/Python 版本、实际 H03/H05/H10 开关和 provider 非敏感标识。
- [ ] 固定官方实验任务、输入/测试哈希、模型、reasoning、模板、session scope、请求预算、修复轮数、超时和重复次数。

### 1.2 H09 开关

优先复用已有配置。如果需要独立 A/B 开关，建议保持一个 harness 级枚举：

| 值 | 行为 |
| --- | --- |
| `legacy` | A：保持当前内核清单和代理过滤 |
| `canonical` | B：在内核启动前传入最终 roster；代理正常路径不再删除 |

建议名为 `OCTOS_ARC_TOOL_ROSTER=legacy|canonical`。若最新主线已有等价入口，可以改名，但必须满足：

- [ ] 实验期默认 `legacy`；只有 M4 采用 B 后才考虑切换默认。
- [ ] 未设置与 `legacy` 等价；未知值关闭 H09 并给出有界诊断，不静默开启。
- [ ] `OCTOS_STDIO_SOLO_TOOLS` 继续作为现有内核收窄机制，不再增加第二套 Rust 工具策略。
- [ ] H09 关闭时，最终 provider 请求、代理删除行为和 codegen 无工具路径与 A 一致。
- [ ] `C_i` 不新增一串永久布尔开关；使用实验 manifest 或已有 allow-list 固定精确 roster。

### 1.3 优先核对的真实代码路径

| 职责 | 优先阅读位置（相对 `octos-arc/`） |
| --- | --- |
| stdio/solo 基础清单与 allow-list | `crates/octos-cli/src/runtime/profile.rs` |
| registry 可见、可调用与稳定排序 | `crates/octos-agent/src/tools/registry.rs` |
| 每轮 `tools_spec` 取得 | `crates/octos-agent/src/agent/loop_runner.rs` |
| H03 固定预算与 prompt fingerprint | `crates/octos-agent/src/agent/llm_call.rs`、`agent/prompt_cache.rs` |
| stdio 子进程环境与 profile 创建 | `arc/octos_stdio.py` |
| session 生命周期、minimal/codegen 模式 | `arc/main.py::OctosDriver`、`verify_text`、`codegen_turn` |
| provider 前最终过滤与 usage shape | `arc/llm_proxy.py` |
| chat fallback | `arc/main.py::run_octos`、`OctosDriver._run_stdio` |
| Python 回归 | `arc/tests/test_llm_proxy.py`、`test_main_helpers.py` |
| H03/H05 回归 | `crates/octos-agent/tests/h03_*`、`h05_*` |

## 2. 不可破坏的约束

- [ ] B 在冻结的 H03-on 底座上，普通工具模式最终 roster 保持：

```text
diff_edit, edit_file, glob, grep, list_dir, read_file, recall, shell, write_file
```

- [ ] minimal 模式只在 session/process 建立前从上述集合移除 `shell`；codegen 继续使用已有 deny-all + 0 tools 路径。
- [ ] H03 关闭或 `recall` 未注册时，最终集合自然少一个；实现不得用固定数量伪造缺失工具。
- [ ] profile、全局 ToolPolicy、provider policy 和显式 operator allow-list 仍可继续收窄 roster；H09 不重新加入被政策删除的工具。
- [ ] 同一 session 内工具名称、schema 和顺序保持字节稳定。模式必须变化时，先关闭旧 session/process 再建立新清单，或保守保留原 superset。
- [ ] 模型看到的每个工具都能通过同一 registry 路由调用；被删除的工具不能继续出现在 system prompt、tool search 建议或补救文字中。
- [ ] 不把 `tool_search` 当作隐藏工具恢复入口。B 不升级它，不发送它，也不新增 activation 状态。
- [ ] 普通模式保留 H03 `recall` 和 H05 `diff_edit/edit_file/write_file`；没有 `C_i` 证据前不删除任何一个。
- [ ] 不因 `grep`、`glob`、`list_dir` 功能看似重叠就直接删除；模型调用习惯和额外请求也属于成本。
- [ ] Python 代理仍可为旧二进制或 chat fallback 做兼容过滤，但必须记录原因；新内核正常 stdio 路径的删除数必须为 0。
- [ ] system prompt 的现有裁剪、reasoning、destream、请求上限和 provider 路由保持不变。
- [ ] 工具描述、参数 schema、权限、审批、沙箱和文件写保护保持不变；H09 不通过弱化 schema 换 token。
- [ ] 正常日志只记录名称、数量、字节、hash、模式和原因，不记录完整 schema、prompt、工具参数、源码或凭据。
- [ ] Python 新代码兼容 Python 3.9；不使用只在更高版本可用的语法或标准库参数。

## 3. 最小 roster 与观测约定

不要求新建 `ArcToolRoster` 类型。优先用一个纯函数和现有 `OCTOS_STDIO_SOLO_TOOLS` 完成；
只有多个真实消费者需要共享结构时才增加小型值对象。

每个进程/session 至少能解释：

```text
roster_mode
requested_tool_names
effective_tool_names
tools_count
tools_bytes
tools_hash
roster_source
proxy_removed_count
proxy_guard_reason
```

约定：

- [ ] `requested_tool_names` 是 harness 模式选择的有序名称；`effective_tool_names` 是注册与政策过滤后的真实集合。
- [ ] `tools_hash` 对最终规范序列化的 schema 计算，不能只 hash 名称后声称 schema 未变。
- [ ] hash、bytes 和 count 的输入必须与真正发给 provider 的 `tools` 数组相同。
- [ ] provider 没有 `tools` 字段时记录 0；无法确认 usage 时记录 unknown，不从请求字节猜成 provider token。
- [ ] 代理兼容删除记录名称和原因，但不输出 schema 正文。
- [ ] 同一 roster 在不同进程、重试和相同配置下序列化结果一致。

## 4. Milestone M0：冻结 A、调用图和基线证据

**目标：**先证明实际请求和所有例外路径。M0 不改变工具行为。

- [ ] 完成第 1.1 节，冻结 `MAIN_SHA`、依赖提交和 `A_SHA`。
- [ ] 追踪 `main.py → OctosDriver → OctosStdioSession → serve --stdio --solo → profile/registry → loop_runner → llm_call → llm_proxy → provider`。
- [ ] 分别追踪普通工具、minimal、codegen、provider retry、stdio 重启和 session scope `turn/node/run`。
- [ ] 单独追踪 `_run_stdio` 失败后的 `octos chat` fallback；确认它是否具有与 stdio 相同的内核 roster。
- [ ] 使用 fake provider 或 `OCTOS_ARC_PROXY_DUMP=1` 捕获 A 的真正 provider 请求，证明冻结底座上的 13→9、13→8、0→0 事实。
- [ ] 同时记录 proxy 前后工具名称、顺序、规范 schema 字节和 hash；不要只读取源码常量推断。
- [ ] 证明 H03 fixed budget 和 prompt fingerprint 当前消费的是 proxy 前 `tools_spec`，而 provider usage 对应 proxy 后请求。
- [ ] 检查最终 system prompt 是否提到已删除的 `ask_user_question/check/tool_search/update_plan`；只有真实出现时才把清理纳入 B。
- [ ] 固定一次至少两轮工具调用，证明 A 的 provider 工具数组是否在 turn 内字节稳定。
- [ ] 准备无付费模型的基线夹具，覆盖普通、minimal、codegen、policy deny 和 chat fallback。
- [ ] 记录当前 provider tokenizer 对 13、9、8、0 个工具 schema 的实际 token；没有可用 tokenizer 时标 unknown，并保留字节数。
- [ ] 新增测试只能固定当前事实或目标合同，不把主分支永久留在红色状态。

**完成条件：**A 的每条实际入口都有最终请求证据；B 的唯一差异和 chat fallback 处理方式已经确定。

## 5. Milestone M1：在 session 建立前选择 B roster

**依赖：**M0。**目标：**复用现有 allow-list，让正常 stdio 内核从一开始只注册最终工具面。

- [ ] 用一个确定性 helper 返回 `legacy/canonical` 和 `full/minimal/codegen` 对应 roster；不要调用 LLM、关键词分类器或运行时启发式。
- [ ] full/minimal 的名称只定义一次，并通过同一值设置 stdio 子进程的 `OCTOS_STDIO_SOLO_TOOLS`。
- [ ] B 优先由 ARC harness 设置现有 allow-list，不直接把 Rust 的 13 工具 stdio 默认常量改成 9；若现有入口已足够，不为扩大改动量修改 Rust 生产代码。
- [ ] 在 `OctosStdioSession` 启动前完成环境设置；进程启动后不得修改环境并假装 registry 已更新。
- [ ] roster 变化时，`OctosDriver` 必须先关闭旧 session/process；`turn` scope 不额外重启，`node/run` scope 不得跨 roster 复用。
- [ ] codegen 继续使用现有 `without_tools()` 和 profile deny-all，不重写第二套无工具机制。
- [ ] `legacy` 完全保持当前行为，包括代理过滤；`canonical` 的普通/minimal 最终工具能力与 A provider 已有能力等价。
- [ ] `OCTOS_STDIO_SOLO_TOOLS` 与 ToolPolicy 使用交集语义；显式 deny 后不能被 canonical roster 加回。
- [ ] `recall` 未注册或 H03 关闭时按真实 effective set 处理，不因期望 9 个而启动失败。
- [ ] 不修改通用 `octos chat --profile coding`、MCP、ACP、gateway 或非 ARC stdio 默认工具面。
- [ ] 不新增独立 Rust registry 或复制 `ToolSpec`；继续使用现有 `retain`、`specs()` 缓存和名称排序。
- [ ] 单测覆盖模式解析、未知值、full/minimal/codegen、环境传递、session 关闭和 policy 交集。

**完成条件：**canonical 普通/minimal 在第一次 LLM 请求前已分别得到预期 effective roster；尚未依赖代理删除。

## 6. Milestone M2：统一最终请求并保留兼容保护

**依赖：**M1。**目标：**让 B 的预算、指纹和 provider 请求真正一致，同时不破坏旧二进制与 fallback。

- [ ] 代理从同一 canonical roster 获得 expected set；不得维护另一份独立 `DROP_TOOLS` 真源。
- [ ] canonical 正常 stdio 请求中，代理过滤前后工具数组相同，`proxy_removed_count=0`。
- [ ] legacy 继续使用当前过滤行为，保证 A 可重放。
- [ ] 对旧内核或 chat fallback，代理可以 fail-safe 删除 expected set 外工具，但必须记录 `roster_source=proxy_compat`、删除数量和原因。
- [ ] 若决定让 chat fallback 也在内核前收敛，使用现有 profile/ToolPolicy；不要为了 H09 新建一个长期维护的 chat 工具系统。
- [ ] stdio 正常路径、chat fallback 和 codegen 的模型可见工具都必须可调用；隐藏工具调用返回既有 typed unknown/denied，不伪装成功。
- [ ] `llm_call` 的 H03 fixed budget 自动看到最终 roster；不要在预算层硬减“四个工具”的估算值。
- [ ] prompt fingerprint、稳定前缀 hash、工具 count 和 schema hash均来自最终 `tools_spec`。
- [ ] 代理保留 system prompt trim、路由、reasoning、usage、destream 和请求预算逻辑；只改变工具 roster 的所有权。
- [ ] codegen 仍同时由 kernel deny-all 和 provider 无工具请求保护；不能只依靠代理 `strip_all_tools`。
- [ ] 若最终 prompt 含已删除工具指导，只删除被证据证明无效的对应句子；不顺手重写整份 worker prompt。
- [ ] fake provider 捕获并比较 A/B 第一请求的最终 `tools` 数组：名称、顺序和 schema 必须 byte-equivalent。
- [ ] 多轮工具调用验证 B 的工具数组不变化；重试和 provider fallback 不重新加入工具。

**完成条件：**B 正常路径不再发生代理工具删除；最终 provider 能力与 A 等价，预算和指纹描述同一份实际请求。

## 7. Milestone M3：观测、确定性回归与 B 冻结

### 7.1 最小观测

- [ ] 每请求记录 roster mode/source、最终 count/bytes/hash、proxy 删除数和 phase。
- [ ] 每 turn 记录工具调用名、unknown/denied/missing-tool、请求数和重试数；不记录完整参数。
- [ ] 关联 provider input/output/cache/reasoning usage；失败 usage 按 H10 口径处理。
- [ ] 记录 H03 因工具 schema 变小而新增的可见输出字节，避免把它误记为 schema token 节省。
- [ ] 指标写入失败不改变模型请求或任务结果。

### 7.2 B 的确定性验收矩阵

| ID | 场景 | 判定点 |
| --- | --- | --- |
| T01 | legacy full | 内核 13、provider 9，A 可重放 |
| T02 | canonical full | 内核/provider 均为预期 9，代理删除 0 |
| T03 | canonical minimal | 内核/provider 均为预期 8，不含 `shell` |
| T04 | codegen | 内核/provider 均为 0，不出现工具指导 |
| T05 | H03 off / `recall` 未注册 | effective roster 自然减少，不伪造 9 |
| T06 | global/provider policy deny | 只继续收窄，不被 roster 或代理加回 |
| T07 | operator allow-list | 维持已有交集语义和兼容诊断 |
| T08 | 同 turn 多请求 | 名称、顺序和 schema hash 字节稳定 |
| T09 | `turn/node/run` scope 跨模式 | 不跨不同 roster 复用 session |
| T10 | provider retry/fallback | roster 不变化，不重复计算错误来源 |
| T11 | stdio 失败进入 chat fallback | 最终仍不超过 expected roster，并标记 compat |
| T12 | removed tool 名称调用 | 不可见；执行层拒绝，不能内部绕过 |
| T13 | H03 大输出 + `recall` | 恢复能力保留，预算按最终 roster 计算 |
| T14 | H05 创建、编辑、diff、验证 | 现有工具行为和 schema 不回归 |
| T15 | normal logs / opt-in dump | 普通日志无 schema/prompt/参数；dump 仍显式开启 |

- [ ] T01-T15 均有自动化测试或有证据的“不适用”；T02-T04、T08、T11 至少检查最终 provider JSON。
- [ ] 对 A/B 最终工具数组做规范序列化比较；不能只比较 count。
- [ ] 回归 H03 输出预算/恢复、H05 B/C 编辑工具和 Python proxy/main helper。
- [ ] 检查 `git diff --check`、Python 3.9、Rust fmt；定向 Clippy 新增告警为零，主线遗留告警单列。
- [ ] 审查 `A_SHA..HEAD`，不含 `C_i` 删除、Tool Search、schema 文案压缩、官方输入变化或无关重构。
- [ ] 本地提交并冻结 `B_SHA`，记录二进制哈希、有效配置、T01-T15 证据和限制。

**完成条件：**B 正常 stdio 路径使用单一 roster，行为与 A provider 能力等价，所有例外路径均可解释和回滚。

## 8. Milestone M4：固定官方任务 A/B 对照

### 8.1 开跑条件

- [ ] B 已通过 M3；用户确认可以运行真实模型实验。
- [ ] 执行 `source ~/.zshrc`，确认 `ARCBENCH_API_KEY`、provider 配置、`OCTOS_BIN`、二进制哈希、端口和隔离目录。
- [ ] H10 能记录失败、重试和丢弃响应的真实 usage；否则 M4 暂停，不用不完整数据宣称节省。
- [ ] A/B 固定需求、测试、模板、模型、reasoning、session scope、工具权限、请求预算、修复轮数、超时和其他已采用优化配置。
- [ ] 每个 task×variant 使用独立 workspace/data/session；重复次数和交错运行顺序预先固定。

### 8.2 每次运行记录

- [ ] `MAIN_SHA/A_SHA/B_SHA`、实际运行 SHA、git dirty、二进制路径和 SHA-256。
- [ ] task、输入/测试/模板哈希、模型、reasoning、重复序号和运行顺序。
- [ ] roster mode/source、每请求工具 count/bytes/hash、proxy 删除数和实际调用工具。
- [ ] provider input/output/cache/reasoning token、请求数、失败和重试；unknown 不记零。
- [ ] H03 最终可见输出字节、`recall` 次数、missing/unknown/denied 工具和 chat fallback。
- [ ] 最终逐用例原始报告、首轮通过、最终通过、回归和重复稳定性。

### 8.3 B 的采用判断

- [ ] 先比较官方正确率和稳定性，再比较全任务 token。
- [ ] B provider 首轮工具 schema 理应与 A byte-equivalent；不把 13→9 的历史差额记为 B 收益。
- [ ] B 若因正确预算减少恢复请求或提高正确率，可记录为间接效果，但必须有请求轨迹证明。
- [ ] B 若正确率下降、出现工具缺失或 fallback 增多，先修正并重新冻结，不能用 token 更低掩盖。
- [ ] B 若正确率不下降、最终能力一致且双层清单问题归零，可以作为一致性基础采用；H09 的“新增 token 收益”仍记为未证明。
- [ ] 保存逐 run manifest、原始报告和聚合结果；不挑最好一次。

**完成条件：**明确“采用 B 作为一致性基础”或“保留 A”，并单独写明 H09 token 收益仍未证明。

## 9. Milestone M5：选择并实现单项 `C_i` 消融

**依赖：**M4 已得到稳定 B。**目标：**只对有充分证据的一个工具做静态消融。

- [ ] 汇总 B 的完整官方任务工具调用分布、missing-tool、shell 替代、额外请求和失败类型。
- [ ] 候选必须在预定任务与重复中持续低使用，或存在已验证的等价能力；一次未调用不构成删除依据。
- [ ] 在写代码前计算候选 schema 的 provider tokenizer token 和全任务理论上限，收益过小时直接停止。
- [ ] 每个 `C_i` 最多删除一个工具或改变一条预声明 phase roster；不得批量删除后做归因。
- [ ] roster 仍在 session/process 建立前确定；禁止按 prompt 关键词、前一轮调用或 AI 判断动态增删。
- [ ] 不引入 `tool_search`、deferred loading、LRU 或 activation 作为补救。
- [ ] 若删除后模型改用 shell、增加 read/grep 轮次或产生 unknown call，全部计入该 `C_i` 成本。
- [ ] H03 开启时默认保护 `recall`；H05 选中行为所需编辑工具默认保护。要消融必须另有专项安全证据。
- [ ] 为候选工具准备“任务确实需要它”的反例，证明删除时要么有明确等价路径，要么该 `C_i` 应被否决。
- [ ] 运行 T02-T15 和候选专项；A/B 代码保持不变。
- [ ] 每个有效 `C_i` 独立本地提交并记录 `C_i_SHA`、与 B 的唯一 diff、schema 理论节省和确定性证据。

**停止条件：**

- 没有满足证据门槛的候选；
- 单轮理论节省小于一次额外请求的保守成本；
- 确定性测试出现能力缺口、额外 fallback 或缓存不稳定；
- 需要动态搜索才能弥补删除。

满足任一条件即停止 C，不为了“必须有 token 优化”继续删工具。

## 10. Milestone M6：固定官方任务 B/`C_i` 对照

- [ ] 只对通过 M5 的 `C_i` 运行付费实验；无候选时本 Milestone 标记“不适用”，不虚构 C。
- [ ] 复用 M4 的任务、模型、预算、重复次数、隔离方式和运行顺序；唯一变量是该单项 roster。
- [ ] 每次只比较 B 与一个 `C_i`，不能把多个实验结果合并成一个最优样本。
- [ ] 先比较最终通过数、回归和稳定性；任何下降默认否决 `C_i`。
- [ ] 正确率不下降后，比较全任务累计 token、请求数、重试、fallback 和 cache usage。
- [ ] 只有全任务 token 稳定下降，且没有 missing/unknown 工具和额外安全风险，才采用 `C_i`。
- [ ] 仅 schema 更短、某次 cache hit 更高或单次运行 token 更低均不足以采用。
- [ ] 保存失败样本和逐 run 原始报告；基础设施错误与产品错误分开，但不得删除产品失败。
- [ ] 多个 `C_i` 均通过时，从同一 B 分别比较；若要组合，组合必须作为新的独立实验重新验证。

**完成条件：**选出一个有完整证据的更小 roster，或明确确认当前 9/8 已是本轮保守边界。

## 11. Milestone M7：采用、最新主线集成与回滚

- [ ] 汇总 B 的一致性结论与各 `C_i` 的 token 结论，明确区分“工程修复”和“新增收益”。
- [ ] 重新拉取最新 `origin/main`，在不改写冻结 SHA 的前提下集成选中实现，记录 `INTEGRATION_SHA`。
- [ ] 核对与最新 H03、H05、H06-H08、H10、ToolPolicy、provider adapter 和 chat fallback 的组合。
- [ ] 若集成改变 roster、schema、prompt、session 生命周期或 usage 口径，重跑对应对照；旧实验不能自动证明新组合。
- [ ] 提供独立回滚：关闭 H09 回到 A；撤销 `C_i` 回到 B；均不关闭 H02/H03/H05 的既有保护。
- [ ] legacy 兼容过滤只有真实旧二进制/fallback 消费者时才保留；无消费者后删除死分支及其重复常量。
- [ ] 更新优化总表中的真实状态：B 是否采用、是否存在新增 token 收益、哪些方向暂缓。
- [ ] 跑受影响 Rust/Python 测试、格式、定向 Clippy 和官方 smoke，区分基线失败与新增失败。
- [ ] 每个 Milestone 的代码和分析证据分别本地提交，记录 SHA；远程推送等待用户指令。

**完成条件：**选中方案在最新主线上可重放、可回滚；文档没有把历史 13→9 或 B 的一致性修复重复算作 H09 token 收益。

## 12. 测试、提交和交接要求

### 12.1 候选验证命令

先用 `-- --list` 或测试文件清单确认过滤器确实命中；零测试不能算通过。

```bash
cargo test -p octos-cli stdio_lean_defaults
cargo test -p octos-cli stdio_tool_allowlist
cargo test -p octos-agent --test h03_m1_output
cargo test -p octos-agent --test h03_m2_recall
cargo test -p octos-agent --test h03_m3_file_pages
cargo test -p octos-agent --test h05_m2_typed_recovery
cargo test -p octos-agent --test h05_m3_mutation_results
cargo test -p octos-agent --test h05_m4_diff_fallback
cargo test -p octos-agent --test h05_m5_replace_all
cargo test -p octos-agent --test h05_m6_observability
cargo test -p octos-cli --test mcp_serve_integration

cd arc
python3 -m unittest discover -s tests -p 'test_llm_proxy.py'
python3 -m unittest discover -s tests -p 'test_main_helpers.py'
cd ..

cargo fmt --all -- --check
cargo clippy -p octos-agent -p octos-cli -p octos-arc --all-targets -- -D warnings
git diff --check
```

新增 H09 的真实 stdio + fake provider 测试必须检查最终 request body。只测 roster helper、
Rust 常量或 Python 代理过滤函数不能证明端到端一致。

严格 Clippy 若命中主线遗留告警，先在 `A_SHA` 用相同命令复现；只把新增告警归到 H09。

### 12.2 每个 Milestone 的本地提交

- [ ] 一个 commit 只完成一个可验证 Milestone，或一个为保持绿色所需的更小切片。
- [ ] 提交信息写实际行为，例如“在 stdio 启动前固定 ARC 工具清单”“记录代理兼容删除”，不只写 `H09 M1`。
- [ ] 提交前运行相关专项、`cargo fmt --all -- --check` 和 `git diff --check`。
- [ ] 不提交真实凭据、完整 provider prompt/schema dump、临时工作区、大日志或与 H09 无关的格式化变化。
- [ ] 分析仓库中的验证记录与代码仓库提交分开；不推送远程。

### 12.3 每个 Milestone 的交接格式

- [ ] 用通俗中文列出完成行为、未完成项和明确没有做的范围。
- [ ] 列出修改文件、关键入口、`MAIN_SHA/A_SHA/B_SHA/C_i_SHA`、开关和实际默认值。
- [ ] 列出最终 roster 名称、count/bytes/hash、代理删除数和普通/minimal/codegen/fallback 覆盖情况。
- [ ] 列出准确测试命令、通过/失败/跳过数量和退出码；基线失败与新增失败分开。
- [ ] 列出 provider usage 是否完整；缺少 `ARCBENCH_API_KEY` 或其他配置时明确说明。
- [ ] 列出证据路径、代码 commit、分析 commit、工作树状态和下一 Milestone 起点。
- [ ] 没有自动化证据的项目不勾选；发现设计假设错误时先更新清单，再实施等价安全方案。

后续 agent 不应为了让 H09 看起来“有收益”而跳过 B、批量删除工具或引入动态搜索。最好的结果
可能是 B 修正一致性、C 无合格候选，并明确记录当前 provider 工具面已经足够小。
