# H01 实施 Milestone：任务证据胶囊与三臂对照实验

- 状态：实施中（Milestone M0-M5 已完成）
- 面向对象：后续编码 Agent
- Octos 基线：`main@c599d18c5acd2b846f049ffea2be84e72fe60fac`
- 设计依据：[H01 竞品调研](./h01-context-evidence-competitor-research.md)

## 0. 已确定的决策

- [x] 实现 H01a：task-local typed `TaskEvidenceCapsule`，压缩后确定性重注入。
- [x] 实现 H01b：默认确定性摘要改为证据优先，不再让旧消息按时间顺序先占满预算。
- [x] 实现 H01c：精确保留当前需求契约；长原文使用规范化引用与哈希。
- [x] 实现 H01d：复用现有 artifact 机制保存长日志，capsule 只放结构化字段和可恢复引用。
- [ ] **H01e 可以实验实现，但必须放在独立分支。**它不能混入无模型调用的 H01a–d 分支。
- [ ] **H01f 不实现。**不照搬竞品的固定 token 阈值、跨题 memory、todo/goal 架构或完整插件体系。
- [ ] 最终使用三个变体做对照：原始基线、H01a–d、H01a–e。
- [ ] 评价顺序固定为：官方测试通过情况第一，总 token 第二。

这里的“三个 A/B test”在统计上是**三臂 A/B/C 对照实验**。后文统一使用 A、B、C，避免把“没有 H01e”误解成完全没有 H01。

## 1. 分支和变体

| 变体 | Git 基线/分支 | 功能 | 压缩摘要模型调用 |
| --- | --- | --- | --- |
| A：原始基线 | `main@c599d18c5acd2b846f049ffea2be84e72fe60fac` | 当前行为，不含本轮 H01 改动 | 关闭，使用当前默认 extractive 路径 |
| B：无 H01e | 建议分支 `feat/h01-evidence-capsule`，从 A 切出 | H01a + H01b + H01c + H01d | **不得增加**摘要模型调用 |
| C：有 H01e | 建议分支 `exp/h01e-llm-checkpoint`，从冻结后的 B commit 切出 | B + H01e structured checkpoint | 仅压缩触发时允许一次受控摘要调用 |

分支纪律：

- [x] 开工前确认 A 的工作树干净，并把基线 SHA 写入实验 manifest。
- [x] B 完成并通过确定性测试后先冻结一个 commit，记为
  `B_SHA=6d7d1559b72c3b0a34789909d3056527fdc9d42d`。
- [ ] C 必须执行 `git switch -c exp/h01e-llm-checkpoint B_SHA`；不得直接从 `main` 或未冻结的工作树切出。
- [ ] C 相对 B 的 diff 只允许包含 H01e 的 summarizer、配置、观测字段、测试和必要文档。
- [ ] 如果 B 后续修复，先把相同修复同步到 C，再生成新的 `B_SHA`/`C_SHA` 实验配对；不能拿不同基础实现比较。
- [ ] A/B/C 都用干净 commit 运行。实验 manifest 中记录 `git status --porcelain`，非空则该次结果无效。
- [ ] 不创建 H01f 分支，也不为 H01f 预留抽象层。

## 2. 实现边界与不变量

### 2.1 各层的所有权

- [x] ARC Python 编排器拥有**任务真相**：当前 requirement、依赖、验收场景、阶段和官方测试结果。
- [x] `AcceptanceRunner`/`RunSummary` 拥有**测试真相**：只有真实 runner 结果可以写入 `passed`、`failed`、`verified_behavior`。
- [x] Octos Rust runtime 拥有**对话真相**：canonical transcript、工具调用/结果配对、压缩、artifact 引用和模型可见上下文。
- [x] 模型只能提出 `next_action` 或生成 H01e 的叙事 checkpoint，不能把失败改成通过，也不能修改需求哈希。
- [x] 官方需求和测试只读。不得为了让实验通过而修改、复制后改写或按变体生成不同版本。

### 2.2 行为不变量

- [x] 未启用 H01 的普通 Octos 会话保持 wire 兼容和现有行为。
- [x] capsule 只在当前 ARC task/output 目录内生效，不进入跨题 memory。
- [x] 同一失败按稳定 signature 去重，保留出现次数和最新 run，而不是重复粘贴完整日志。
- [x] `pass` 必须绑定 `run_id` 和被测 source/tree hash。代码发生变化后，旧 pass 只能作为历史证据，不能继续代表当前状态。
- [x] 长原文先持久化成功，再在 capsule 中写引用。引用至少带路径或 artifact ID、SHA-256 和字节数。
- [x] 压缩先构造 candidate，完成 schema/预算/引用校验并持久化后，再原子替换 model-visible history。
- [x] 任意失败、超时、空结果、缺字段或超预算都保留原历史或回退 B 的确定性结果，不能留下半替换状态。
- [x] 最新用户请求、system/developer instructions、tool call/result 配对和现有 plan snapshot 不变量继续成立。

## 3. 最小数据契约

后续 Agent 可以调整 Rust/Python 类型名，但不能弱化字段语义。建议使用下面的 v1 形状：

```yaml
schema: octos.task-evidence.v1
task:
  requirement_id: REQ-1.2
  phase: implement
  requirement_sha256: "..."
  requirement_ref: requirements/requirements.yaml
  acceptance_conditions:
    - "GIVEN ... WHEN ... THEN ..."
  dependencies: [REQ-1.1]
  policies:
    - "official tests are read-only"
source_state:
  tree_sha256: "..."
  changed_files:
    - path: frontend/src/App.tsx
      sha256: "..."
      purpose: "implement REQ-1.2"
verification:
  run_id: acceptance-0007
  source_sha256: "..."
  command: "npx playwright test REQ-1.2-user-login.spec.ts"
  exit_code: 1
  passed: 1
  total: 2
active_failures:
  - test_id: REQ-1.2-user-login
    location: REQ-1.2-user-login.spec.ts:71
    status: timedOut
    expected: "dashboard visible"
    actual: "locator timed out"
    signature: "sha256:..."
    occurrences: 2
    artifact_ref: ".arc/evidence/acceptance-0007.json"
    artifact_sha256: "..."
verified_behavior:
  - test_id: REQ-1.2-registration
    run_id: acceptance-0007
    source_sha256: "..."
next_action: "inspect the redirect and dashboard render after login"
```

字段规则：

- [x] `acceptance_conditions` 来自规范化后的官方 requirement/scenario，不从模型总结中提取。
- [x] `expected`/`actual` 只有 runner 能可靠拆出时才填写；不可靠时保留为空并引用原始 artifact，禁止编造。
- [x] `command` 使用 allowlist 后的测试命令；不把环境变量、密钥或任意 shell 参数复制进模型上下文。
- [x] 所有列表使用稳定排序；重复序列化必须字节稳定，便于哈希、缓存和 A/B 对照。
- [x] capsule 设置独立字节/token 上限。超限时按“当前需求 → active failures → 最新验证 → 改动文件 → next action”顺序保留，长内容转引用。
- [x] schema 版本不从 workspace-policy 或 compaction schema 借用，使用独立常量和兼容性测试。

## 4. Milestone M0：冻结基线并确认真实调用链（已完成）

目标：在写代码前证明 ARC stdio 流程实际经过哪条压缩路径，避免只修改未使用的 helper。

- [x] 保存 A 的 SHA、Rust/Python/Node 版本、模型 ID和默认环境变量。
- [x] 阅读并画出一条实际链路：`arc/main.py` → `arc/octos_stdio.py` → `turn/start` → session/context manager → agent compaction → provider request。
- [x] 用受控长 transcript 触发一次压缩，在 `.arc/octos-events.jsonl` 或测试 observer 中证明实际调用了目标函数。
- [x] 记录 ARC 默认 `OCTOS_SESSION_SCOPE=turn` 的影响；另外确认 `node` scope 下 design/implement/repair 如何共享 session。
- [x] 确认基线的摘要策略、token budget、触发阈值和工具输出 artifact 路径，不靠代码注释猜测。
- [x] 跑基线的聚焦测试并保存结果：
  - `cargo test -p octos-agent --lib compaction`
  - `cargo test -p octos-agent --test compaction_policy`
  - 与实际 stdio 压缩入口对应的 `octos-cli` context-manager/UI-protocol 测试
  - `python -m unittest discover -s arc/tests`
- [x] 在 B 分支新增一份简短 ADR 或实现说明，写清选中的 typed 注入边界及放弃的替代方案。

M0 证据：`./h01-m0-baseline.json`、
`./h01-m0-task-evidence-injection-boundary.md`，以及
`arc_stdio_compaction_characterization_exposes_task_evidence_loss` 自动化测试。
Python 3.9 基线的单一 `tarfile.extract(filter=...)` 兼容性错误已原样记录，
未混入 H01 修复。

- [x] 完成条件：有一个自动化测试能够在修改前失败或明确暴露证据丢失，并证明它覆盖 ARC 实际使用的压缩路径。

## 5. Milestone M1：H01a/H01c——ARC 侧证据 reducer 与任务契约（已完成）

建议落点：新增 `arc/task_evidence.py`，或放入职责相同的现有小模块；不要把 reducer 继续堆进 `arc/main.py`。

- [x] 定义 Python 侧 `TaskContract`、`TaskEvidenceCapsule`、`ActiveFailure`、`VerificationRun` 的序列化形状。
- [x] 从 `Flow.requirement_nodes`、`describe_node(...)`、依赖/祖先约束和原始 requirements 文件生成 task contract。
- [x] 对规范化 requirement 内容计算 SHA-256，同时保存只读原文路径。
- [x] 从 `RunSummary`/`TestOutcome`/`failure_signature(...)` 生成验证结果和 active failures。
- [x] 在以下边界更新 capsule：
  - [x] design/implement turn 之前；
  - [x] 每次 node acceptance 之后、repair turn 之前；
  - [x] regression checkpoint 之后；
  - [x] full-suite 每轮之后；
  - [x] 恢复 best commit 之后重新计算 source hash 和当前验证状态。
- [x] 使用“写临时文件 → flush/fsync（平台允许时）→ replace”的方式原子写入 `.arc/context/task-evidence.v1.json`。
- [x] 遇到无法读取的 requirement、非法 schema 或 artifact 写入失败时明确报错/降级；不得静默写一个看似有效的空 capsule。
- [x] 单元测试覆盖：稳定序列化、需求哈希、失败去重、pass→regression、best commit 恢复、原子写失败和空字段。

- [x] 完成条件：给定相同 requirement、source tree 和 `RunSummary`，重复构造得到完全相同的 capsule；模型文本不能改变测试结论。

M1 实现与验证记录：`./h01-m1-implementation-verification.md`。

## 6. Milestone M2：H01a/H01c——typed 传输与模型可见重注入（已完成）

优先采用 typed 协议字段，不要在普通用户 prompt 中寻找可伪造的 `BEGIN_EVIDENCE` 字符串。一个较小的实现方向是增加 `InputItem::TaskEvidence`，由 ARC stdio driver 在文本输入旁发送；也可以选择等价的现有 typed context-event 接口，但必须在 M0 ADR 中证明它覆盖真实路径。

- [x] Rust 定义与 Python v1 对应的最小 DTO，并执行 schema、长度、路径和哈希格式校验。
- [x] `arc/octos_stdio.py` 在 `turn/start` 中发送当前 capsule；文本 prompt 保持原样，避免 A/B 中需求文本发生额外变化。
- [x] runtime 把它记录为独立 typed context item/event，而不是普通 user message 或 system instruction。
- [x] prompt renderer 把 capsule 标成“任务/验证状态数据”，明确最新用户请求仍决定当前动作。
- [x] semantic compaction 和 legacy/agent compaction 都从同一 canonical typed item 获取 capsule；不要分别解析两套自由文本。
- [x] 只保留最新有效 capsule。旧 capsule 被替换，不与新 capsule叠加。
- [x] 不认识该 input kind 的旧客户端/旧会话继续按当前行为工作；未提供 capsule 时完全走原路径。
- [x] 测试覆盖 wire round-trip、旧 payload、未知 schema、超限、用户伪造同名文本、replay 和多次 compaction。

- [x] 完成条件：强制压缩两次后，模型输入中恰好存在一个最新 capsule；真实 user prompt 仍存在，伪造标记不能获得 typed/pinned 语义。

M2 实现与验证记录：`./h01-m2-implementation-verification.md`。

## 7. Milestone M3：H01b——确定性证据优先压缩（已完成）

主要落点预计包括 [compaction.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-agent/src/compaction.rs) 和 [context_manager.rs](https://github.com/woshuoduijiushidui/octos-arc/blob/c599d18c5acd2b846f049ffea2be84e72fe60fac/crates/octos-cli/src/api/context_manager.rs)。以 M0 找到的真实路径为准。

- [x] 给 capsule 单独预留预算，方式与现有 plan snapshot 类似，但 plan 和 capsule 分别计量，不能叠加后突破总 budget。
- [x] 生成摘要前剥离旧的 capsule block；摘要完成后只附加最新 typed capsule。
- [x] 把 fallback/extractive 选择顺序改为：当前需求契约、active failures、最新 verification、当前 source/change facts、next action、最近叙事、较旧叙事。
- [x] recent zone 和当前用户请求继续原样保留；不得把当前 request 重新总结成 background 指令。
- [x] 工具成功/失败优先使用 typed tool result 或执行状态。只有旧数据没有结构化状态时，才允许保守的文本 fallback。
- [x] 工具调用只保留 allowlist 后的诊断字段，例如工具名、目标相对路径、测试 ID和无敏感信息的命令摘要。
- [x] 连续压缩不得重复嵌套 `Conversation Summary`、plan 或 capsule。
- [x] candidate 未真正减少 token 时拒绝安装；overflow recovery 只有在输入 hash/长度确实变化时才重试。
- [x] 安装 replacement history 前完成所有校验；失败后保留上一份可用历史。

- [x] 完成条件：研究文档第 8.1 节的九个确定性场景全部变成自动化测试，并覆盖真实 ARC stdio 路径中的至少一个集成场景。

M3 实现与验证记录：`./h01-m3-implementation-verification.md`。

## 8. Milestone M4：H01d——长日志外置与引用

H01d 只做 H01 需要的最小衔接，不在本分支重做完整 H03。

- [x] 复用 `ToolOutputEnvelope.raw_artifact_ref/raw_sha256` 和现有 artifact store；禁止创建第二套通用工具日志仓库。
- [x] acceptance 侧复用 Playwright `report.json`/action errors，或把等价完整 `RunSummary` 写到 `.arc/evidence/<run_id>.json`。
- [x] capsule 对长日志仅保存失败摘要、artifact ref、SHA-256、字节数和必要范围信息。
- [x] 引用写入前验证 artifact 已存在且哈希匹配；丢失引用不能标成“可恢复”。
- [x] 默认模型输入不展开完整 artifact。只有既有 recall/read 工具被显式调用时才读取原文。
- [x] 测试覆盖 artifact 存在、缺失、哈希不一致、超长 UTF-8 输出、重复失败共用引用和 replay。

完成条件：长测试日志不会直接塞满 capsule；通过引用可以定位到原始证据，且不修改官方测试文件。

M4 实现与验证记录：`./h01-m4-implementation-verification.md`。

## 9. Milestone M5：B 分支测试、观测和冻结

- [x] 在 harness event 或等价日志中记录：
  - `variant=A|B|C`；
  - capsule schema、字节数、估算 token；
  - compaction 次数、前后 token、summarizer kind；
  - candidate 接受/拒绝及枚举化原因；
  - artifact 写入/找回状态；
  - H01e 额外请求数与 token（B 必须为 0）。
- [x] 日志不记录密钥、完整任意 shell 参数或未裁剪的用户数据。
- [x] 聚焦测试通过：ARC reducer、UI protocol、context manager、agent compaction、artifact replay。
- [x] 运行 `cargo fmt --all -- --check` 和受影响 crates 的 Clippy/测试。
- [x] 运行 `python -m unittest discover -s arc/tests`。
- [x] 运行与改动路径相关的 Rust tests 后，再运行仓库要求的完整回归；不要用重复跑同一测试代替缺失的端到端覆盖。
- [x] 生成 B 的行为说明、配置示例和已知限制。
- [x] 提交并冻结 `B_SHA`，确认 B 中没有 structured LLM checkpoint 或额外摘要请求。

完成条件：B 在关闭 H01 typed input 时兼容原行为；启用后所有确定性不变量通过，且每次压缩不会新增 provider 请求。

M5 行为说明与验证记录：`./h01-m5-b-variant-freeze.md`。

## 10. Milestone M6：H01e 独立实验分支

从冻结的 `B_SHA` 创建 `exp/h01e-llm-checkpoint` 后再开始以下工作。

- [ ] 新增独立 summarizer kind，例如 `llm_structured_checkpoint`；不要偷偷改变已有 `extractive` 的含义。
- [ ] H01e 只总结可丢失的叙事历史。task contract、测试 verdict、active failures 和 artifact metadata 仍以 B 的 typed capsule 为准。
- [ ] prompt 使用固定短结构，至少包含：historical decisions、completed work、unresolved investigation、next suggested action、critical file references。
- [ ] 返回值必须可解析并通过 schema 校验；模型生成内容不能覆盖 trusted capsule 字段。
- [ ] 接受 candidate 前检查：非空、无图片、字段齐全、未截断、在预算内、比被替换区域更小、引用格式合法。
- [ ] 模型超时、provider error、空输出、malformed JSON、缺字段、超预算或“不变小”时，直接使用 B 的确定性摘要。
- [ ] H01e 失败不触发无界重试；一次 compaction 最多一次 H01e 摘要请求。
- [ ] 额外请求必须进入 `.arc/llm-usage.jsonl` 或同口径 usage 流，不能从总 token 中漏记。
- [ ] mock provider 测试覆盖：有效结果、空结果、字段缺失、截断、超长、timeout、provider error、提示注入文本和 fallback 等价性。
- [ ] 检查 `git diff B_SHA...HEAD`，确认没有顺手修改 H01a–d、ARC prompt、官方测试或实验预算。

完成条件：关闭新 summarizer 时 C 与 B 行为等价；开启时每次压缩至多多一个可计量请求，任何失败都安全退回 B。

## 11. Milestone M7：三臂 A/B/C 实验

### 11.1 实验前冻结

- [ ] 选择固定官方任务集合，至少覆盖小任务、中等任务和会触发压缩的长任务。
- [ ] 保存每个任务的 requirements、acceptance tests、初始模板和依赖锁文件 SHA-256。
- [ ] 三个变体使用相同模型、endpoint、reasoning、temperature、最大输出、总时间、每节点时间、修复轮数、工具权限、机器/容器和 Playwright workers。
- [ ] 使用相同 session scope。主实验建议采用能稳定触发压缩的 `node` scope；另保留一组默认 `turn` scope 结果，说明生产默认下的实际影响。
- [ ] 若需要固定 compaction threshold，必须在看结果前写入 manifest，并对 A/B/C 完全相同。该阈值只属于本实验配置，不升级成 H01f 式产品默认值。
- [ ] 先用不计入结论的预跑证明目标长任务三个变体都会至少触发一次压缩；未触发的运行不能用来判断 H01e。
- [ ] 每个 task × variant 至少重复 3 次。若 provider 不支持 seed，按轮次交错运行 A→B→C、B→C→A、C→A→B，减少时间段偏差。
- [ ] 串行运行，避免同一 key 的平台计量窗口被并发污染；以每个输出目录自己的 `.arc/llm-usage.jsonl` 为 token 主来源。
- [ ] 每次运行使用全新 output/data 目录；不得把某组生成的 app、memory、session 或 evidence 带到另一组。

### 11.2 每次运行的 manifest

- [ ] 写入 `.arc/experiment-manifest.json`，至少包含：

```json
{
  "experiment": "h01-abc-v1",
  "variant": "A|B|C",
  "branch": "...",
  "git_sha": "...",
  "git_dirty": false,
  "task_id": "...",
  "requirements_sha256": "...",
  "tests_sha256": "...",
  "template_sha256": "...",
  "model": "...",
  "reasoning": "...",
  "session_scope": "turn|node",
  "compaction_policy": {},
  "time_budget_s": 0,
  "repair_rounds": 0,
  "repetition": 1,
  "run_order": 1
}
```

- [ ] endpoint 只记录稳定标识，不写 API key。
- [ ] 保存原始 usage、runner events、Octos events、最终 grade、capsule、compaction events 和 artifact 索引。
- [ ] 给无 compaction、基础设施错误、OOM、provider 账号错误和被外部中断的运行打无效原因；不得当作功能失败混入统计。

### 11.3 指标

按下面顺序判定，不得用后面的指标抵消前面的退步：

| 优先级 | 指标 | 计算方式 |
| --- | --- | --- |
| 1 | 官方测试通过数 | 每次最终 `passed/total`；同时汇总全部测试通过数 |
| 1 | 任务全通过率 | `all_passed` 的运行数 / 有效运行数 |
| 1 | 稳定性 | 同一任务重复运行的最差值、中位数和离散情况 |
| 2 | 总 provider token | 所有请求的 prompt + completion；另列 reasoning 和 cache hit，包含 H01e、失败请求与重试 |
| 2 | 每个通过测试的 token | 总 provider token / 最终通过测试数；0 pass 时记为不可用而不是除零美化 |
| 3 | 行为诊断 | compaction 次数、额外请求数、修复轮数、重复失败次数、重复读文件/日志次数、耗时 |
| 3 | H01 机制指标 | requirement 保留率、active-failure 字段保留率、artifact 找回率、半写入次数 |

token 口径：

- [ ] 总量必须包含 codegen、repair、compaction summary、provider 重试和失败响应中已计费的 token。
- [ ] `prompt_cache_hit_tokens` 单列，不从 prompt token 中擅自扣除；如需“非缓存输入”指标，另算 `max(prompt-cache_hit, 0)`。
- [ ] reasoning token 若已包含在 completion 中，不重复加入总量；报告中注明 provider 的字段关系。
- [ ] 同时报告请求数，避免 C 用更多小请求造成只看 token 时的误判。

### 11.4 采用规则

- [ ] **B 对 A**：若 B 的官方测试表现下降，H01a–d 不采用并定位回归；不能用 token 节省解释较少的通过数。
- [ ] B 的官方测试表现提高时，可以接受其 token 增量，但必须把增量和新增通过用例一起报告。
- [ ] B 与 A 的测试表现相同时，优先选择总 token 更少的方案；差异落在重复运行噪声内时继续重复，不提前宣布胜出。
- [ ] **C 对 B**：若 C 的官方测试表现下降，拒绝 H01e。
- [ ] C 的官方测试表现提高时，把额外摘要请求/token 作为明确成本报告，再决定是否默认启用或只对长任务启用。
- [ ] C 与 B 的测试表现相同时，只有 C 的总 token 更低且重复运行稳定时才采用 H01e；否则保留 B 为默认。
- [ ] A/B/C 都未发生压缩时，只能说明该任务不受 H01 影响，不能据此判断三者等价。

## 12. Milestone M8：报告、合并与回滚

- [ ] 生成 `octos-arc-analysis/h01-abc-results.md`，逐任务列出每次运行和 aggregate，不只给平均值。
- [ ] 报告记录 A_SHA、B_SHA、C_SHA，以及 B→C 的完整 diff 统计。
- [ ] 对每个无效运行写明原因和是否重跑，不删除不利结果。
- [ ] B 作为独立可审查变更；只有 B 对 A 达到采用规则后才进入主线。
- [ ] C 作为独立实验变更；只有 C 对 B 达到采用规则后才考虑合并 H01e。
- [ ] 若 C 未胜出，关闭 H01e 分支/PR但保留实验报告，不把相关开关和死代码合入 B。
- [ ] H01f 在结论中标记 `not implemented by design`，不新增待办。
- [ ] 提供回滚方法：关闭 typed evidence 后恢复原行为；H01e 可以单独关闭且自动回到 B。

## 13. 编码 Agent 的提交要求

每个提交只完成一个可验证里程碑，提交说明必须包含“行为变化 + 验证命令”。建议顺序：

1. `test(h01): pin failing context-evidence cases`
2. `feat(arc): build trusted task evidence capsule`
3. `feat(protocol): carry typed task evidence into sessions`
4. `feat(compaction): preserve task evidence deterministically`
5. `feat(arc): link acceptance artifacts from task evidence`
6. `test(h01): cover repeated compaction and rollback`
7. 在 C 分支：`experiment(h01e): add validated llm checkpoint summarizer`
8. `docs(h01): record three-arm experiment results`

每完成一个里程碑，更新本文件中的 checkbox，并附上测试输出或 artifact 路径。不要顺手重构无关模块；如果发现 H01 之外的问题，单独记录，不混入 A/B/C 的实现 diff。
