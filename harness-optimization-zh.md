**Octos harness 优化候选：固定官方需求与验收**

2026-09-15，分析提交 c599d18c。本文为只读源码评审，未修改 Octos、官方需求或测试，没有新增付费实验。所有收益都是待验证假设，源码接线事实与效果判断分开记录。

**优化边界**

目标是提高同一官方需求、同一官方验收下的最终通过数，其次减少全任务累计 token。可以改变 Octos 的输入呈现、上下文管理、工具选择、编辑策略、失败恢复、预算和交付检查。官方需求语义、用例、断言、判分规则和测试预算作为固定条件。

最严格的可改范围放在 crates/octos-agent、crates/octos-cli 的任务运行时、crates/octos-llm，以及实际被调用时的 crates/octos-arc 原生 harness。不将 arc/grade-local.py 或官方编排器的调整列为 Octos 核心优化收益。arc/*.py 可以用来理解调用行为，但其问题不自动等于 Rust 内核的问题。

**先确认改动会经过哪里**

| 入口 | 实际执行 | 本文建议适用边界 |
|---|---|---|
| 当前自定义包 arc/main.py | Python Flow → octos serve --stdio --solo → conversation loop | stdio 上下文、Agent 构造、工具、模型调用建议生效；原生 Rust Flow 改动不会自动生效 |
| octos arc run --spec ... | Rust ARC Flow；codegen 直接请求模型；tool mode 启动 serve 子进程 | 原生需求/生成/修复策略生效；Agent工具建议主要影响tool mode |
| octos mcp-serve / run_octos_session | 可接收 arc.agent-task.v1 → Agent.run_task | MCP Agent构造、task loop、交付验证建议生效；原生 ARC Flow 不自动参与 |

本地相邻的 requirement compiler 和 hackathon 仓库没有找到调用 Octos 的源码证据，因此不宣称官方当前一定使用 MCP。实际入口必须由运行命令或平台配置确认。入口代码：[main.py](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/arc/main.py#L2683)、[Rust入口](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-arc/src/run.rs#L110)、[MCP入口](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-cli/src/commands/mcp_serve.rs#L483)。

**候选 1：让文件读取缓存与模型可见上下文一致**

已有机制：read_file 可以返回 FILE_UNCHANGED 短提示，避免重复传文件。普通 SessionRuntime 创建并传入 FileStateCache 和 session key，见 [session.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-cli/src/runtime/session.rs#L429)、[:600](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-cli/src/runtime/session.rs#L600)。

接线缺口：stdio 每轮构造新的 request_agent，没有继承 file_state_cache；MCP Agent 构造也没有挂缓存和 parent session key。Agent::new_shared 默认该缓存是 None。因此不能仅凭工具已有缓存代码就断言当前入口已经避免重复读取。出处：[stdio重建](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-cli/src/api/ui_protocol_transport.rs#L34601)、[MCP构建](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-cli/src/commands/mcp_serve.rs#L586)、[缓存命中](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-agent/src/tools/read_file.rs#L393)。

建议：在实际任务入口传入作用域正确的缓存和身份，同时把缓存命中与“该版本、该范围仍在模型可见上下文中”关联。文件未变，不代表压缩后模型仍看得见；历史失效后要允许重新读取，不能只回“看上一次”。已有字段和构造方法应优先复用，不先造全新缓存框架。

验证：同文件重复读取的返回字节数、文件修改后重新返回、不同任务互不共享错误命中、压缩后可重读、每任务输入token和最终通过数。

**候选 2：统一文件分页、执行层裁剪和上下文层预算**

已有机制：read_window 提供最多2000行/48KiB的页，带下一次读取参数，并提供长行 byte_offset 分页。该特性由 OCTOS_READ_WINDOW=1 开启，默认关闭，见 [read_window.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-agent/src/tools/read_window.rs#L1)。

缺口：stdio ContextManager 对工具结果另有约8KiB模型可见限制，见 [context_manager.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-cli/src/api/context_manager.rs#L2431)。48KiB工具页因此不等于48KiB实际可见证据。页尾的续读说明、位于中间的函数或错误可能经二次裁剪丢失。stdio默认12工具也没有完整接入历史原始输出的recall路径，不能只靠“原文已经另存”解决可读性。

建议：先按实际可见预算返回完整、可续读的页，明确实际返回范围、是否完整、下一页位置；确保页尾在后续投影中保留。必要时提供已有原始结果的按需读取能力。先解决链路上的多次截断，不直接把全局限制都调大。

验证：大文件末尾逻辑、单行超长JS、Unicode、错误在日志中间、续读能否覆盖全部内容；读取请求次数、输入token、误删代码造成的回归。

**候选 3：把声明的压缩策略接到实际任务循环，并保留关键证据**

已有机制：MCP读取workspace compaction policy并挂CompactionRunner，见 [mcp_serve.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-cli/src/commands/mcp_serve.rs#L610)。conversation loop 会执行正常preflight/per-turn压缩调用，但task loop正常迭代没有同样的调用，见 [conversation调用](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-agent/src/agent/loop_runner.rs#L1317)、[task准备](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-agent/src/agent/loop_runner.rs#L2655)。task仍有tier1、trim和溢出恢复，不能说完全没有压缩。

另外，默认extractive摘要主要抽用户首行、工具名称和很短的结果首行，见 [compaction.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-agent/src/compaction.rs#L293)。它还主要通过首部 `Error:` 判断失败，其他格式的构建退出码或Playwright失败可能被摘要为正常结果；按旧到新遍历填预算也可能遗漏较新的失败。这不等同于完整保留需求约束、最近失败、改过的接口和待修问题。

建议：补齐现有任务策略接线与工具请求/结果配对保护。摘要保留官方任务约束、已验证行为、实际变更、最近具体失败和下一步；大段原始源码用可定位引用保存。不要按时间简单取前面的若干首行，导致后面实际失败消失。官方system prompt继续按原生契约放入system角色，不改成低优先级普通文本。

验证：超过上下文预算后的需求回忆、工具配对、最新失败保留、源码按需找回、压缩次数和摘要额外token、最终通过数。压缩变小但修复次数变多不一定有效。

**候选 4：已有应用优先精确编辑，并提高编辑失败的可恢复性**

已有 edit_file、diff_edit 和唯一匹配检查，见 [edit_file.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-agent/src/tools/edit_file.rs#L237)、[diff_edit.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-agent/src/tools/diff_edit.rs#L58)。write_file会覆盖整个文件，windowed-read保护默认也未开启。

建议：新文件用完整输出；已存在的大文件优先局部编辑；成功输出返回改动范围及简短diff，而不是整份新文件。匹配失败应给实际文件中的有界邻近证据，让模型修正旧片段；保持歧义拒绝，避免为了少请求而修改错误位置。依据官方限制决定能否用某工具，不能强行覆盖调用者的写入策略。

验证：output token、每修复变更行数、编辑匹配失败次数、重复读取次数、回归数及最终通过。局部编辑如果经常重试，不一定比整文件便宜。

**候选 5：依据具体失败收敛，并在可用验收失败后有界自修复**

已有LoopDetector、分类重试和可选AgentVerifier；conversation还有默认20模型调用/100k active token/300秒的反思检查点，见 [convergence.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-agent/src/agent/convergence.rs#L1)。这些是已有能力，不应重新实现一套重复系统，也不应给每个步骤加付费反思。

MCP生成完成后会检查workspace validators及JSON交付schema，失败直接返回Failed，见 [mcp_serve.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-cli/src/commands/mcp_serve.rs#L715)。可以研究把真实检查错误回到当前任务做一次有界修复，避免外层重跑整个阶段。仅在输入本身合法、允许该验收且预算足够时；非法arc_task必须继续在请求模型前失败，不能转成付费修复。输出schema校验成功也不能等同于官方应用测试通过。

收敛信号应比较操作、文件变化、错误位置和失败观察。相同测试名但失败从缺按钮推进到提交后的后端异常，仍可能有进展；反复相同读/写/错误且代码无有效变化时应切策略。官方未暴露测试时，不推断通过、也不访问隐藏测试，只做授权的构建、语法、交付等检查并返回真实结果。

验证：重复工具调用比例、同因失败重试数、每次修复新增通过数、提前停错次数、修复总token。规则判断优先，必要时再触发模型复盘。

**候选 6：贯通迭代、输出和总token预算；异常用量不归零**

MCP启动固定max_iterations=20，构造AgentConfig主要设置iterations与save_episodes，其他预算/推理/输出设置没有统一从配置映射，见 [mcp_serve.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-cli/src/commands/mcp_serve.rs#L157)、[:591](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-cli/src/commands/mcp_serve.rs#L591)。核心已有max_tokens、chat_max_tokens、reasoning_effort和计入缓存token的预算检查，见 [AgentConfig](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-agent/src/agent/mod.rs#L65)、[budget.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-agent/src/agent/budget.rs#L94)。

建议：先把调用者允许的配置正确映射到实际Agent；实现阶段留出修复和交付的预算，临近上限明确提示剩余额度。预算按阶段/实际请求大小和已证明进展调整，而不是一律压低20轮或输出上限。模型固定时先优化流程；只有官方允许选模型时才评测分档。

MCP run_task错误路径返回cost默认零，虽然核心已能附带partial usage并提供run_task_with_tracker，见 [错误返回](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-cli/src/commands/mcp_serve.rs#L671)、[tracker入口](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-agent/src/agent/loop_runner.rs#L2548)。建议让失败、超时、无用量和真实零用量分开记录，核对丢弃重试的计量，避免优化后只是漏算。

验证：首轮通过、最终通过、output_truncated、budget_exhausted、提前中止、provider所有已知输入/输出/缓存/推理、失败请求累计。注意内核TokenUsage已把cache与非缓存输入归一化为互斥字段，而provider原始prompt常包含cache；两层分别按契约汇总，不能混用公式。

**只在原生ARC Flow实际参与时再做的两项**

第一，完整官方需求的统一呈现。Rust compact codegen当前只传description，CodegenInputs没有完整scenarios/设计/祖先，见 [flow.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-arc/src/flow.rs#L2096)、[codegen.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-arc/src/codegen.rs#L489)。补全的是harness呈现方式，官方文档本身保持固定。普通MCP不会自动调用这个Flow；核心如果没有收到原始输入，也不能凭空恢复外层遗漏的内容。

第二，源码覆盖和生成档位。原生codegen的扩展名集合缺.ts/.tsx/.jsx，可能在React/TypeScript模板上漏掉已有代码，见 [codegen.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-arc/src/codegen.rs#L214)。应先完整识别官方提供的工程，再按需选择相关源码。Tiny用固定静态服务器，按测试字符数就选择它可能不适合短描述但需要服务端持久化的任务；thinking none同样不能仅凭spec长度认定合理。依据任务需要的能力选择，失败后保留已通过行为，不能按题名写特例。

**建议落地顺序**

1. 固定实际Octos入口、二进制、模型、官方输入和官方验收条件；记录包括失败请求的总用量。
2. 文件读取缓存/可见性与分页裁剪配合，优先防止必要信息丢失和旧功能被覆盖。
3. 长任务压缩接线与关键证据保留。
4. 局部编辑、具体错误反馈和无效循环收敛。
5. 预算、阶段工具集合和推理档位的对照评测。
6. 原生ARC需求/生成策略仅在该入口实际使用时实施。

评测仍使用同一官方测试集合，报告首轮通过数、最终通过数、重复运行稳定性，以及全任务输入/输出token、请求数和修复次数。增加首轮token但减少后续无效修复，可能是有效优化；少修几轮省token却少过用例，不符合当前目标。
