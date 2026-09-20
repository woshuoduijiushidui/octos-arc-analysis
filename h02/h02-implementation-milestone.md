# H02 实施 Milestone：文件版本与模型可见读取证据

- 状态：M0-M4 已完成，M5 待实施
- 面向对象：后续编码 Agent
- 当前实现基线：`main@6aacc9fb1a1599ae10f8368921ccf3e3afb7f87e`
- 初始 M0 调研基线：`main@c599d18c5acd2b846f049ffea2be84e72fe60fac`
- 设计依据：[H02 竞品调研](./h02-file-cache-context-consistency-competitor-research.md)

本文中的 checkbox 有两种含义：`[x]` 只表示调研阶段已经确定的设计决策，`[ ]` 才是后续编码、验证和实验事项。类型名和文件拆分可以根据代码现状微调，但不得弱化下面的所有权、命中条件、隔离和验收语义。

## 0. 已确定的决策

- [x] **H02a 采用：**把磁盘侧 `FileVersion` 与模型侧 `ModelReadReceipt` 分开；仅有文件未变化不能返回 `[FILE_UNCHANGED]`。
- [x] **H02b 采用：**receipt 只能在工具输出完成截断、sanitize/redaction、ContextManager projection 和最终 prompt 构建后确认。
- [x] **H02c 采用：**B 组对 compaction、trim、history replacement、rewind、resume、fork、task switch 和 cold restore 使用保守失效；无法证明正文仍在当前 frame 时必须重读。
- [x] **H02d 采用：**命中前验证强文件版本；mutation 在真正写入的 provider critical section 内重新校验当前版本或当前 patch context，stale 时失败关闭。
- [x] **H02e 采用：**只有 H02a–d 的正确性语义完成后，才把状态接入真实 stdio/OUP、MCP 和 spawn 路径。
- [x] **H02f 只做独立实验：**C 组仅增加“基于最终 retained item ID 的选择性 receipt 保留”，不同时加入热点文件自动回灌。
- [x] **H02g 明确拒绝：**不把旧 `FileStateCache` 直接接到所有入口，不共享父子模型的可见 receipt，不照搬竞品固定容量、文件数、阈值或未经本项目实测的收益数字。
- [x] 任一状态缺失、解析失败、版本不稳定、范围不可映射或 owner 不匹配时，安全结果都是返回当前正文，而不是返回 stub。
- [x] 评价顺序固定为：官方测试与稳定性 → false stub/stale mutation 安全指标 → 生命周期 contract → token 与时延。
- [x] H02 不扩展为 H01 的任务证据胶囊、H03 的分页/原文恢复、H04 的通用 MCP 压缩策略或 H05 的工具选择策略。

核心命中条件固定为：

```text
can_return_unchanged =
    same_task_and_model_branch
    && current_file_version == receipt.file_version
    && requested_view is covered by receipt.model_visible_view
    && receipt.source_proof is present and untruncated in current_prompt_frame
```

四项中任一项无法证明，结果都是 cache miss。`context_generation` 用来审计和协调 frame 变化，不得仅因 generation 数字相同就跳过 source item 与实际可见范围检查。

## 1. 分支和变体

| 变体 | Git 基线/分支 | 功能 | receipt 生命周期 |
| --- | --- | --- | --- |
| A：当前主线 | `main@6aacc9fb1a1599ae10f8368921ccf3e3afb7f87e` | 当前真实 stdio/MCP 行为；目标 Agent 路径尚未完整接通 cache | 当前实现，不补接线 |
| B：正确性优先 | `feat/safe-file-cache`，从 A 切出 | H02a + H02b + H02c + H02d + H02e | 任一破坏性 frame 变化都清空该 branch 的 receipts |
| C：选择性保留 | 建议分支 `exp/h02-retained-read-receipts`，从冻结后的 B commit 切出 | B + 一项 H02f 优化 | 只保留最终 prompt frame 明确留下且未重新裁剪的 source item receipts |

分支纪律：

- [x] 不从当前 `feat/context-evidence-preservation-llm-summary@804e42a8d42b5e570a5d1d2cb78b01d0a73059d7` 工作树开始 H02；A/B/C 必须共享上表固定的 H02 基线。
- [x] 开工前确认 `c599d18c5acd2b846f049ffea2be84e72fe60fac` 可解析，记录 Rust、Python、Node、模型、默认环境变量和 `git status --porcelain`。
- [x] M0、M1 完成后将两个提交无冲突 rebase 到 `origin/main@6aacc9fb1a1599ae10f8368921ccf3e3afb7f87e`；`git range-diff` 证明补丁等价，并在新基线上重跑全部 M1 聚焦回归。
- [ ] B 通过全部确定性 contract tests 后冻结干净 commit，写入 `B_SHA`；冻结前不得开始 C。
- [ ] C 必须从 `B_SHA` 切出；相对 B 的 diff 只允许包含 retained-item 选择性保留、对应观测和测试。
- [ ] 不在 C 同时实现“选择性保留”和“热点文件自动回灌”。若未来需要测试回灌，另建 C2 实验臂并重新预注册实验。
- [ ] “把旧 cache 直接接上所有入口”只保留为负向回归场景，不得作为可以凭低 token 获胜的实验变体。
- [ ] A/B/C 都从干净 commit 运行；manifest 中 `git_dirty=true` 的运行一律标记无效。
- [ ] 官方 requirements、acceptance tests、模板和依赖锁文件对三组只读且哈希相同。
- [ ] 若 B 后续修复，先把同一修复同步到 C，再冻结新的 B/C 配对；不得比较底座不同的两个 commit。
- [ ] A/B/C 得出结论后，才把采用分支移植或 rebase 到当时的 `main`；必须重新跑 H01/H03/H04 交互回归，不能把 c599 上的通过直接当成当前主干证据。

## 2. 实现边界与不变量

### 2.1 各层的所有权

- [x] 文件 provider / workspace 层拥有**磁盘事实**：canonical target、稳定读取到的 bytes、可信 provider revision 或内容 SHA-256。
- [x] `read_file` 只拥有**读取候选事实**：它读到了哪个版本、哪个请求范围以及准备返回什么；它不能声明模型已经看见正文。
- [x] 通用工具执行层拥有 50KB head/tail、sanitize 和 hook 追加后的**执行层投影事实**。
- [x] 最终 provider dispatch 边界拥有**模型可见事实**：真正发送的 messages 中是否仍有对应 tool call/output、最终可见字节/范围和 projection 结果。基于本次 `c599d18c` 源码复核，stdio 与 MCP 的首选共同候选是 `agent/llm_call.rs::call_llm_with_hooks_mode`；M0 必须重新验证并冻结该边界，不在 ContextManager 内另建一套 cache。
- [x] task/session/model branch owner 拥有自己的 `ModelReadReceipt` 集合；parent、child、fork 和另一 task 不能互相授权 stub。
- [x] 文件 provider 的 mutation critical section 拥有**写入授权事实**：版本或 expected context 的校验必须与实际写入处于同一受保护边界。
- [x] ARC runner 和官方 acceptance tests 拥有**质量结论**；cache hit 数、token 降低或模型自述都不能覆盖真实测试结果。

### 2.2 行为不变量

- [x] `[FILE_UNCHANGED]` 只省略正文，不证明文件正确、测试通过或 mutation 可以绕过 freshness guard。
- [x] 命中必须同时满足 owner、强版本、实际可见范围和当前 source item 四项条件；mtime、size、旧 hash、路径字符串或历史 artifact 任一单项都不充分。
- [x] metadata 只能快速否定 candidate hit；metadata 相同仍要取得当前可信 provider version，或重新流式计算当前内容 SHA-256。
- [x] 正文与版本必须来自同一次稳定 observation；不得组合读取前的 version A 与并发替换后的 bytes B。
- [x] stub 本身不包含正文，不能创建新 receipt，也不能在旧正文已被裁剪时续期旧 receipt。
- [x] partial read 只授权最终实际可见的 partial view；partial → full、不同 range 或不可精确映射的 head/tail 都必须返回缺失正文。
- [x] sanitize/redaction、hook feedback、100KB/50KB/8KiB 任一层改变输出且无法精确映射时，B 组不建立 receipt。
- [x] 磁盘版本 ledger 可以在同一 task 内共享；模型可见 receipt 不能跨 task、workspace、session owner 或 model branch 共享。
- [x] parent/child 最多共享版本查询服务。B 组 child 从空 receipt store 开始；child 的新读取绝不回写 parent receipt。
- [x] compaction、trim、replacement、rewind、resume、fork、task switch 或 cold restore 后，若没有从最终 frame 重新证明 source item，首次 read 必须返回正文。
- [x] cache/receipt 缺失、淘汰、锁中毒、持久化失败、指标写入失败或未知 schema 都只能降低命中率，不能让 read 失败或产生错误 stub。
- [x] 内置 mutation 成功后撤销旧 receipts 并更新/失效版本；除非完整新正文之后真实进入 prompt，否则不得自动把写后内容标为模型已见。
- [x] stale、symlink replacement、并发修改和 expected context 不唯一时失败关闭；不得先授权、后无条件 truncate/rename 覆盖。
- [x] 非 stale 的语法、权限、路径或 schema 错误不得伪装为 stale，也不得进入自动重试。
- [x] 观测只记录枚举原因、owner、版本标识、range 和字节计数，不记录完整文件正文、密钥或任意 shell 参数。
- [x] 关闭 dedup 时恢复为“返回正文”的兼容路径；安全 mutation guard 不随 token 优化开关一起关闭。

## 3. 最小数据契约

后续 Agent 可以调整 Rust 类型名、模块位置和序列化细节，但不能把两个状态重新合并成一个按路径布尔 cache。建议 v1 语义如下：

```yaml
file_version:
  workspace_id: "stable-workspace-owner"
  target_key: "canonical-path-or-provider-id"
  provider_version: "optional-opaque-etag-or-revision"
  content_sha256: "sha256:..."
  size: 12345
  metadata_hint:
    device: 1
    inode: 2
    mtime_ns: 3
    ctime_ns: 4

read_candidate:
  candidate_id: "read-candidate-..."
  tool_call_id: "call_..."
  target_key: "..."
  file_version: "..."
  requested_view: {kind: lines, start: 1, end: 200}
  returned_view: {kind: lines, start: 1, end: 200}
  output_sha256: "sha256:raw-tool-result-output"

model_read_receipt:
  task_id: "..."
  session_owner_id: "..."
  model_branch_id: "root-or-child-id"
  context_generation: 42
  source_proof:
    transcript_item_id: "optional-tool-result-item-id"
    tool_call_id: "call_..."
    arguments_sha256: "sha256:..."
    tool_output_sha256: "sha256:..."
    prompt_occurrence: 3
  target_key: "..."
  file_version: "..."
  model_visible_view: {kind: lines, start: 1, end: 200}
  model_visible_sha256: "sha256:..."
  projection_policy_id: "tool-output-v1"
```

字段规则：

- [x] `workspace_id + target_key` 必须按 provider 的路径策略产生；字符串规范化、symlink/alias 与 workspace boundary 使用同一套既有安全 helper，不另造第二种路径语义。
- [x] `provider_version` 是 provider 给出的可信 opaque revision 时可作为首选 guard；本地 metadata tuple 只是 hint，不能替代内容 SHA-256 的等价证明。
- [x] 本地稳定 observation 至少执行 `stat-before → read/hash → stat-after`；前后 identity/metadata 不一致时最多重试一次，仍不稳定则返回 typed concurrent-change。
- [x] `read_candidate` 是 typed side-channel，不从模型可见文本、`[FILE_UNCHANGED]` 字符串或日志反向解析。
- [x] `read_candidate.output_sha256` 对应 `read_file` 产生的原始 `ToolResult.output`；最终 dispatch 只有在实际 Tool message digest 与它完全相同时才可确认 B 组 receipt。50KB、sanitize、hook、8KiB 或 context-pressure 任一变换都会造成不匹配并保守拒绝。
- [x] source proof 优先使用 transcript item identity；没有 ContextManager item ID 的 MCP/legacy 路径使用最终 messages 中 collision-safe 的 call ID + normalized args digest + output digest + occurrence。不得只使用可能跨 turn 重复的 provider `tool_call_id`。
- [x] `model_visible_view` 描述最终 prompt 中真实可见的连续 range/精确 segments；“全文”“两个 head/tail 片段”和“不可映射”必须是不同状态。
- [x] `projection_policy_id` 或 sanitizer policy 变化时旧 receipt 失效；不能只比较内容长度。
- [x] receipt 的 owner 字段必须全部参与 lookup；不得用进程全局 path map 代替 task/branch 隔离。
- [x] persisted/replayed receipt 只有在恢复后的首个最终 frame 重新证明 source item 和可见 hash 时才可激活；否则按 cold miss 处理。

建议定义稳定的 miss/拒绝原因枚举，至少覆盖：

```text
feature_disabled | missing_state | no_receipt | owner_mismatch |
source_not_visible | source_truncated | view_not_covered |
projection_changed | metadata_changed | digest_changed |
receipt_evicted | lifecycle_cleared | unstable_observation
```

原因枚举用于测试和指标，不参与模型判断。未知原因一律走 miss。

## 4. Milestone M0：冻结基线并证明真实调用链

目标：在改代码前冻结 A，并把 read candidate 从工具执行到最终 provider prompt 的真实路径画清楚；不得根据已有 helper 或注释推断其已经接线。

- [x] 在独立、干净 checkout 中固定 `A_SHA=c599d18c5acd2b846f049ffea2be84e72fe60fac`，保存工具链版本、默认 `OCTOS_SESSION_SCOPE`、模型配置和环境指纹。
- [x] 追踪默认 ARC 链路：`arc/main.py` → `arc/octos_stdio.py` → `octos serve --stdio --solo` → `session/open` / `turn/start` → OUP per-turn `request_agent` → provider request。
- [x] 单独追踪 MCP `run_session` 的 Agent 构造、消息循环和最终 prompt 构建；不要假定它与 OUP 共用 ContextManager。
- [x] 枚举所有 `Agent::new_shared`、`.with_file_state_cache(...)`、`FileStateCache::{get,put,clear}` 和 spawn 传播点，确认 bootstrap Agent、per-turn Agent 与 MCP Agent 的实际差异。
- [x] 追踪一次 `read_file` 输出依次经过工具内 100KB、执行层 50KB head/tail、sanitize/hook、ContextManager 8KiB 和 `for_prompt` context-pressure 处理时，哪些层仍保留 typed metadata。
- [x] 枚举 compaction、trim、history replacement、rewind、resume、fork、task switch、cold restore 的生产入口；特别确认 `run_tier3_and_invalidate_cache` 是否只在测试中调用。
- [x] 枚举 `write_file`、`edit_file`、`diff_edit`、`apply_patch`、shell/formatter/test 外部修改的失效和 provider-side guard；区分“主动 invalidation 优化”与“命中时强校验”。
- [x] 验证 branch-local staged candidate 能经 `ToolContext.file_state_cache` 到达 `call_llm_with_hooks_mode`，并检查 `ToolResult.structured_metadata`、`ToolOutputEnvelope`、`PromptFrame.report` 是否还需最小辅助字段；默认不改持久 wire schema，禁止把 JSON 塞进模型正文再解析。
- [x] 写 characterization tests 或可复现日志，分别证明：mtime-only false-hit 风险、pre-projection 全文误标、parent/child 共享风险、OUP/MCP 接线缺失。
- [x] 反转/拆分当前把“direct tool 连读两次即 stub”当成成功的断言，例如 `should_read_file_tool_return_file_unchanged_when_cache_hit` 和 `threads_file_state_cache_into_read_file_after_m8_8_scheduler`：没有发生成功 model dispatch 时，第二次也必须返回正文。
- [x] 跑基线聚焦测试并保存准确命令、退出码和测试数量；基线失败必须原样记录，不能顺手修成 H02 结果。
- [x] 在 ADR 中记录被放弃的方案：全局 cache、仅 generation epoch、仅 mtime/size、从文本推导 receipt、直接复制 receipt 给 child。

建议优先检查的现有落点：

| 责任 | 当前文件 |
| --- | --- |
| 旧 cache 与 LRU | `crates/octos-agent/src/file_state_cache.rs` |
| read 命中、100KB 处理、view ledger | `crates/octos-agent/src/tools/read_file.rs` |
| 50KB 与 sanitize | `crates/octos-agent/src/agent/execution.rs` |
| transcript item、8KiB、prompt projection | `crates/octos-cli/src/api/context_manager.rs` |
| stdio/MCP 共同的最终 provider dispatch | `crates/octos-agent/src/agent/llm_call.rs` |
| SessionRuntime bootstrap | `crates/octos-cli/src/runtime/session.rs` |
| OUP per-turn Agent | `crates/octos-cli/src/api/ui_protocol_transport.rs` |
| MCP Agent | `crates/octos-cli/src/commands/mcp_serve.rs` |
| parent/child wiring | `crates/octos-agent/src/tools/spawn.rs` |
| mutation ledger/guard | `crates/octos-agent/src/tools/read_window.rs`、`tools/write_file.rs` |

M0 证据：`./h02-m0-baseline.json` 与 `./h02-m0-state-boundary.md`。

- [x] 完成条件：能从真实 stdio 和 MCP 入口分别回答“谁创建版本 ledger、谁拥有 branch receipt、谁确认最终可见、何时清理”，并至少有一个自动化 contract 在 A 上暴露 false-stub 风险、在安全实现上应通过。

## 5. Milestone M1：H02a/H02d——强 `FileVersion` 与稳定读取

目标：先把磁盘事实做对，但暂不启用模型侧 stub。优先演进现有 `FileStateCache` 为版本 ledger，保留可用的 LRU/容量管理，不平行重写整套文件缓存。

- [x] 定义 canonical target 与 `FileVersion`；target identity 必须包含 workspace/provider owner，避免不同 root 的相同绝对/相对字符串碰撞。
- [x] 将 FNV/mtime-only 命中替换为可信 provider revision 或 SHA-256 等价证明；复用仓库已有 SHA-256 helper/dependency，不为同一算法再引入库。
- [x] metadata 不同直接 miss；metadata 相同只进入 candidate path，仍读取/哈希当前 bytes 后比较内容版本。
- [x] 本地读取优先复用 `read_no_follow_with_meta` 持有的同一 fd/identity，并用同一次稳定 observation 生成 bytes 与 version；若仍需前后校验，前后 stat 不一致最多重试一次，随后返回 typed concurrent-change，不登记 ledger/receipt。
- [x] 明确定义普通文件、symlink、canonical alias、文件被替换、读取中 rename/unlink 的行为，并复用现有 no-follow/workspace path policy。
- [x] 版本 ledger 的容量淘汰只导致 miss；淘汰、锁错误或哈希错误不能返回旧版本，也不能阻止正常全文读取。
- [x] 内置 mutation 后继续调用统一的 version update/invalidate API，删掉散落的“只改旧 cache 某字段”分支。
- [x] 暂时保留 dedup 关闭：M1 即使版本相同也返回正文，以便把磁盘正确性与模型可见性分开验收。
- [x] 修正 `file_state_cache.rs` 中无法由公开证据支持的 Claude 参数和“30–60%”收益注释；只描述 Octos 自己的 contract。
- [x] 单元测试覆盖相同内容、内容变化、同 mtime+同 size 改写、恢复旧 mtime、读取中替换、symlink alias、不同 workspace、LRU eviction 和 I/O 错误。

M1 证据：[h02-m1-implementation-verification.md](./h02-m1-implementation-verification.md)。

- [x] 完成条件：任何 read hit 候选都可追溯到当前稳定 bytes 的强版本；旧 mtime、旧 hash 或主动 invalidation 缺失均不能单独制造命中，且产品行为仍始终返回正文。

## 6. Milestone M2：H02b——最终 prompt projection 后确认 receipt

目标：建立从 typed read candidate 到最终 model-visible receipt 的单向确认链；工具读取发生时只产生 candidate，最终 provider prompt 确实包含正文且请求成功后才产生 receipt。

- [x] `read_file` 成功读取时在 branch-local state 中 stage typed candidate：`ctx.tool_id`、normalized args digest、canonical target、强 version、requested/returned view、原始输出 digest 和 candidate ID；失败与 stub 结果不产生 candidate。
- [x] 若 M0 证实 `agent/llm_call.rs::call_llm_with_hooks_mode` 确为两条路径共同的最后边界，就在该处扫描真正发送的最终 `messages`；若不成立，只能改用 M0 证明的等价共同 chokepoint，不能退回 pre-projection 确认。
- [x] 按消息顺序配对 Assistant ToolCall 与 Tool output，用 call ID + args digest + output digest + occurrence 匹配 staged candidate；call ID 可跨 turn 重复，不能单独作为 proof。
- [x] dispatch 前先撤销最终 messages 已不包含的 active receipts，并把可证明的 candidates 标成 pending；只有 provider 请求成功返回、其响应将驱动同一 model branch 后才把 pending 激活。
- [x] candidate 成功激活或被拒绝后即变为 consumed；lifecycle clear 不能让旧 candidate 再次激活。只有新的正文 read 可以 stage 新 candidate。
- [x] hook deny、全部 provider attempts 失败、取消或 silent/internal checkpoint 不得替主工具循环激活 receipt；内部摘要/检查调用使用独立 purpose/branch owner 或显式禁用 activation。
- [x] “已记录到 transcript”“已写 artifact”“进入 UI preview”或仅开始 provider 请求都不等于模型已见。
- [x] B 组不要求修改 ContextManager 持久 wire schema，也不在 ContextManager 内另建缓存；只有选用 transcript item ID 作为额外 proof 时才做最小 side-channel 扩展。
- [x] B 组首版只确认可以精确证明的输出：source item 被保留、未在任何层截断、visible hash 匹配，并且 requested view 可完整映射。
- [x] 对显式 partial read，只有该 partial 的完整结果未被再次裁剪时登记该 range；partial receipt 不能满足 full read 或不相交 range。
- [x] 测试证明完整可见的 partial receipt 可以满足相同范围或其子范围，但任何超出已见覆盖的请求都 miss；不能为了实现简单把“有 partial receipt”退化成整个文件已见。
- [x] 对 head/tail、多段裁剪、redaction 或无法映射的 normalization，保守不登记 receipt；精确 segment 支持留给有明确数据契约的后续小改动。
- [x] 每次 provider dispatch 都用最终 messages reconcile receipts；不在 prompt 中或 digest 已变化的 source proof 不能继续授权。
- [x] 同一轮并行的两个 `read_file` 不能互相命中，因为第一个正文尚未被模型看到；下一次模型请求确认后才允许后续工具轮命中。
- [x] `[FILE_UNCHANGED]` 输出携带最小可审计信息（target、version、view、source item/candidate ref），但该 stub 不创建新 receipt。
- [x] 测试覆盖 direct-tool 连读但未发生 model dispatch、provider 成功/失败、100KB、50KB、8KiB、context-pressure、sanitize、hook feedback、partial→full、不同 range、重复 call ID 和 source item dropped。

M2 证据：[h02-m2-implementation-verification.md](./h02-m2-implementation-verification.md)。

- [x] 完成条件：每一个允许的 stub 都能在 trace 中定位到上一轮成功 provider request 的最终 messages 内一个包含对应版本和范围正文的唯一 source proof；删除、裁剪或变换该消息后同一 read 必须返回正文。

## 7. Milestone M3：H02c——生命周期失效与 model branch 隔离

目标：让 receipt 的生命周期服从模型实际 history，而不是服从进程、路径或磁盘 cache 生命周期。B 组以每次 provider dispatch 的最终 messages reconcile 为正确性闸门，并在少数 canonical lifecycle ownership 点做保守全量 branch clear；不要依赖散落 helper 全部恰好被调用。

- [x] 定义稳定 owner：workspace/task、logical session 和 model branch ID；owner 不完整时该入口保持 dedup disabled。
- [x] compaction 安装 replacement history 后清空当前 branch receipts；即使某条 compaction helper 漏掉 clear，下一次 provider dispatch 的最终-message reconcile 也必须撤销不可见 proof。
- [x] trim、stale tool-result replacement、context-pressure truncate 或 projection policy 变化时清空当前 branch receipts。
- [x] B 组在任何已知 destructive history transition 上全清，即使某个旧 source proof 恰好仍在新 frame；M2 的最终-message reconcile 是遗漏删除的安全网，不得把已 consumed 的旧 candidate 自动复活。选择性保留只属于 C。
- [x] rewind、rollback、resume、teleport 等价恢复、fork、task switch 和 cold restore 均从空 branch receipt store 开始。
- [x] 版本 ledger 可按 task 保留，但其存在、artifact/hash ref 或 `seed_from_replacement_refs` 不能自动重建 visible receipt；恢复后首次 read 返回正文。
- [x] parent 与同步/后台 child 只共享版本查询服务。B 组 child 不复制 parent receipts，child 新 receipts 不回写 parent。
- [x] 即使 child 初始 prompt 文本包含 parent 摘要或文件路径，也不能据此创建 receipt；只有精确 typed source item/body 才有资格。
- [x] task/session B 读取与 session A 相同 target 时不得命中 A receipt；不同 workspace root 的同名文件也不得碰撞。
- [x] receipt eviction、owner store drop 和进程重启都按 miss；不把 receipt persistence 作为 B 的前置能力。
- [x] 清理 API 接受枚举 reason 并进入指标；禁止各处直接清 map 后丢失原因。
- [x] lifecycle 测试覆盖 research 场景 2、9、10、11、12、16，并验证 stub 本身不能跨 compaction 续命。

M3 证据：[h02-m3-implementation-verification.md](./h02-m3-implementation-verification.md)。

- [x] 完成条件：任何不再含原正文 source item 的新 prompt frame 中，首次对应 read 都返回当前正文；child 的读取绝不会让 parent 获得命中。

## 8. Milestone M4：H02d——mutation 在当前磁盘上失败关闭

目标：复用现有 armed `read_window`、epoch 和 `write_no_follow_checked` 链路，把强版本用于真正的写入边界；不要新建一套与现有 mutation guard 竞争的授权系统。

- [x] P0 先闭合仓库当前本地文件 provider 的真实路径；若没有在用的远端文件 provider，不为假想 CAS/ETag 后端预建通用框架。
- [x] 盘点 `write_file`、`edit_file`、`diff_edit`、`apply_patch` 的当前校验点，形成一个共享的 expected-version/context contract；保持工具各自适合的语义。
- [x] 整文件覆盖现有文件时，在 provider critical section 校验 observed/expected version；授权与 truncate/rename 之间不得存在无保护窗口。
- [x] 局部 edit/diff/patch 在当前磁盘上重新匹配 expected old text/context；只有唯一可应用位置才执行，0 次或多次匹配均失败且无部分写入。
- [x] 复用 `read_window` 的 complete/partial/tainted/transformed 与 epoch 判定；H02 不用 receipt 替代已有 write authorization。
- [x] symlink/alias 与 approval 等待期间的 target replacement 使用与 M1 相同的 canonical/no-follow 规则，最终写入前再次验证。
- [x] stale/concurrent-change 返回 typed code、expected/current version 摘要和明确的 reread remedy；错误文本不得泄漏正文或绝对敏感路径。
- [x] stale 后默认要求模型重新读取并重新形成 edit intent；不得在未重新评估意图时自动套用旧整文件内容。
- [x] 若某个现有 provider operation 能证明重试幂等且 context 仍唯一，最多允许一次有界重试；其他错误和第二次 stale 直接返回。
- [x] mutation 成功后原子更新/失效 version ledger，并 eager revoke 当前 branch 指向旧 version 的 receipts；其他 branch 在下次 hit 的强版本比较时惰性失效，只有已经存在 task-local 反向索引时才做跨 branch purge，不为此新建全局 receipt registry。失败不得虚构新 version。
- [x] mutation 工具输出只有在完整新正文最终投影给模型时才可创建新 receipt；普通“write succeeded”不能授权后续 stub。
- [x] 并发测试覆盖：两个 mutation 使用同一 observed version 时至多一个成功；外部 edit、symlink swap、0/多匹配和中途替换都保持原文件或产生单一原子结果。

M4 证据：[h02-m4-implementation-verification.md](./h02-m4-implementation-verification.md)。

- [x] 完成条件：stale mutation 漏放行数为 0；所有失败都有可操作但有界的恢复路径，且既有 read-window/no-follow 安全测试不回归。

## 9. Milestone M5：H02e——接通真实 stdio、MCP 与 spawn 入口

目标：在语义和 contract tests 已稳定后接线。可以使用一个小型显式 `TaskFileState` carrier，也可以在两个真实构造点直接接入；不要仅为 H02 抽出巨型通用 Agent builder。

- [ ] 定义组合状态：task-local/shared `FileVersionLedger` + owner/branch-local `ModelReadReceiptStore`；两者必须能独立 clone/创建，不能藏在一个可误共享的 `Arc<FileStateCache>` 内。
- [ ] `SessionRuntime` bootstrap Agent 使用该组合状态，且 Agent 的最终 `call_llm_with_hooks_mode` 能 reconcile 同一个 branch receipt store。
- [ ] OUP 每 turn 创建的 `request_agent` 显式继承同一 logical session/task 的 version ledger 和正确 branch receipt store；不得只修 bootstrap Agent。
- [ ] 默认 `OCTOS_SESSION_SCOPE=turn` 下 session 关闭即释放 receipts；`node`/`run` scope 只在 source items 仍属于最终 frame 时复用。
- [ ] MCP 每次独立 `run_session` 创建 task-local state；不得把 receipt store 放到 server-global map，也不得跨 MCP caller 复用。
- [ ] 同步和后台 spawn 只共享 version ledger，并在**每一次 child worker 创建时**生成新的 branch receipt store；不能在 `SpawnTool` builder 时只 fork 一次后让多个 siblings 共享，B 组也不做隐式 parent receipt 继承。
- [ ] pipeline/其他 Agent builders 使用同一显式 builder contract；新构造点若未提供完整 state，默认返回正文而不是悄悄启用半套 cache。
- [ ] 保留 cache-off 兼容路径；旧客户端、无 ContextManager 的调用者、单元测试 fixture 和插件工具不因缺 state 崩溃。
- [ ] 用同一套 contract suite 驱动真实 stdio `session/open`/`turn/start` 与 MCP `run_session`，不能只测试手工构造的 `ReadFileTool`。
- [ ] 加入 spawn 集成测试：child read 后 parent 首次 read 返回正文；parent read 后无正文继承的 child 首次 read也返回正文。
- [ ] 更新原来只断言“cache 到达 ToolContext”的测试，使其同时证明“没有有效 final-frame receipt 就不会 stub”。

- [ ] 完成条件：stdio 与 MCP 都能在完整状态下产生安全 hit，在缺失任一状态、跨 task 或跨 branch 时都稳定返回正文；两入口使用相同命中 contract。

## 10. Milestone M6：B 分支观测、回归与冻结

### 10.1 可解释观测

- [ ] 每次 read 记录 `full_body|file_unchanged|error` 结果、稳定 hit/miss reason、task/session/branch owner、view kind 和字节数。
- [ ] 有效 hit 记录 source proof 标识、version 短标识、projection policy 和 receipt age/generation；不得记录正文。
- [ ] 记录 metadata fast reject、hash bytes/latency、unstable observation、receipt clear reason、stale mutation 与 bounded recovery。
- [ ] 记录完整正文 bytes、stub bytes、有效命中次数、因可见性失效重读次数；指标写入失败不改变 read 结果。
- [ ] 确认日志不包含文件正文、secret、完整任意 shell 参数或不必要的绝对用户路径。

### 10.2 必须自动化的确定性场景

- [ ] 1. 同 task、同 branch、同 version、同 range 且 source proof 仍在 frame：第二次 read 允许 stub。
- [x] 2. source proof 被 compaction/trim 删除：磁盘未变也必须返回正文。
- [x] 3. B 组发生 destructive frame change：即使 source item 看似可恢复也先清 receipts。
- [ ] 4. 100KB、50KB、8KiB 或 context-pressure 任一层裁剪：不得登记 full receipt。
- [ ] 5. projection/sanitizer policy 变化，或可见 bytes 改变：旧 receipt 失效。
- [x] 6. 内容改变但 mtime 和 size 恢复：发现变化并返回新正文。
- [x] 7. shell、formatter、测试进程、git 操作或外部编辑器改文件：下一次 read 不得错误命中。
- [x] 8. `edit_file`、`write_file`、`diff_edit`、`apply_patch` 成功后撤销旧 receipts。
- [x] 9. 两 task/session 或 workspace root 读取同名 target：receipt 隔离。
- [x] 10. child read 不授权 parent；parent read 不授权未继承正文的 child。
- [x] 11. rewind 到 read 之前、fork、cold resume 和 task switch：首次 read 返回正文。
- [x] 12. ledger/receipt LRU eviction 或持久化失败：保守 miss，read 仍正确。
- [x] 13. 两个并发 mutation 使用同一 version：至多一个成功，另一个 typed stale。
- [x] 14. 局部 patch context 唯一时成功；0 次或多次匹配失败且无部分副作用。
- [ ] 15. stdio 与 MCP 真实入口运行同一命中/失效 contract。
- [x] 16. 任一无法解释 source proof、version、view 或 owner 的 hit 让测试失败，而非只记 warning。
- [x] 17. 读取过程中并发替换：只允许稳定重读或 typed concurrent-change，不登记混合 observation。
- [x] 18. symlink/canonical alias 不能绕过版本或 stale guard；外部替换 symlink 时失败关闭。

### 10.3 验证命令

后续 Agent 先用 `cargo test -- --list` 校对过滤器和测试二进制名，再记录实际执行命令。预期至少覆盖：

```bash
cargo test -p octos-agent file_state_cache
cargo test -p octos-agent read_file
cargo test -p octos-agent read_window
cargo test -p octos-agent write_file
cargo test -p octos-agent --test m8_integration_cache_handoff
cargo test -p octos-agent --test m8_integration_tool_context
cargo test -p octos-agent --test m8_end_to_end_gate
cargo test -p octos-agent --lib loop_compaction
cargo test -p octos-cli --bin octos context_manager
cargo test -p octos-cli --bin octos ui_protocol
cargo test -p octos-cli --test mcp_serve_integration
cargo test -p octos-pipeline --test m8_parity
python -m unittest discover -s arc/tests
cargo fmt --all -- --check
cargo clippy -p octos-agent -p octos-cli --all-targets -- -D warnings
```

- [ ] 对受影响 crates 运行 Clippy；若仓库已有与改动路径对应的全量 gate，一并运行并记录真实结果。
- [ ] 不用重复跑一个单元测试代替 stdio/MCP、spawn、compaction 和 mutation 的跨层覆盖。
- [ ] 生成 B 的行为说明、已知限制和验证证据，确认不含 retained-item 选择性保留或热点回灌。
- [ ] 提交并冻结干净 `B_SHA`，记录 `git diff A_SHA...B_SHA`、`git status --porcelain` 和所有命令退出码。

M6 未来证据：`./h02-m6-b-variant-freeze.md`。

- [ ] 完成条件：18 个场景全部自动化，false `[FILE_UNCHANGED]` 为 0，stale mutation 漏放行为 0；关闭 dedup 时 read 行为兼容基线，安全 mutation guard 仍生效。

## 11. Milestone M7：H02f 独立实验分支

目标：从 `B_SHA` 只实验 retained-source 选择性保留，验证是否能在不增加错误状态的前提下减少 compaction 后重读。ContextManager 路径优先使用 retained item ID；MCP/legacy 路径使用 M2 定义的 final-message occurrence proof。

- [ ] 从冻结 `B_SHA` 创建 `exp/h02-retained-read-receipts`，开工前确认工作树干净。
- [ ] 最终 prompt frame 生成后，用实际 retained source proofs 与 receipt 求交集；不得根据 summary 文本、路径提及或 artifact ref 推断正文仍在。
- [ ] 只有 source proof 未被裁剪、visible hash/range 未变、projection policy 未变时才保留 receipt，并保留它绑定的原 `FileVersion`；不要求 reconcile 为此额外读盘，但后续每一次 stub 命中仍必须按 M1 重新验证当前 strong version。
- [ ] 任一缺字段、重复 item、不可映射 transform、policy mismatch 或 reconcile 错误都退回 B 的清空行为。
- [ ] stub source proof 不参与保留；它只能引用仍被保留的原正文 proof，不能形成引用链续命。
- [ ] receipt 选择性保留只改变 compaction/frame 生命周期，不改变强版本算法、mutation guard 或 stdio/MCP owner。
- [ ] 测试覆盖完整 tool output 被保留、被删除、被 context-pressure 重新裁剪、policy 改变、重复 call ID 和 summary 只提路径。
- [ ] 检查 `git diff B_SHA...HEAD`，确认没有混入热点回灌、H01/H03/H04/H05、prompt 文案或实验预算变化。
- [ ] 提交并冻结 `C_SHA`，保存与 B 相同的确定性测试和观测证据。

- [ ] 完成条件：关闭 H02f 时 C 与 B 行为等价；开启时仅在最终 frame 可证明仍含正文时减少重读，所有不确定情况与 B 一样保守。

## 12. Milestone M8：三臂 A/B/C 实验

### 12.1 实验前冻结

- [ ] 固定官方任务集合，至少覆盖小任务、中等任务、重复读取同一文件的长工具任务，以及会触发 compaction 的任务。
- [ ] 保存每个任务 requirements、acceptance tests、初始模板和依赖锁文件 SHA-256。
- [ ] 三组使用相同模型、endpoint、reasoning、temperature、最大输出、总时间、节点时间、修复轮数、工具权限、机器/容器和测试 workers。
- [ ] 主实验固定一个能稳定触发重复 read/compaction 的 session scope；另外保留默认 `turn` scope 结果，说明生产默认下的实际收益边界。
- [ ] 在看结果前固定 compaction/projection/cache 容量参数；这些值只属于实验 manifest，不升级为未经验证的产品默认值。
- [ ] 先预跑确认长任务确实触发目标行为；未发生重复 read 的 run 不用于判断 H02 token 收益，未发生 compaction 的 run 不用于判断 C。
- [ ] 每个 task × variant 至少重复 3 次；若 provider 不支持 seed，交错 A→B→C、B→C→A、C→A→B 运行以减少时间段偏差。
- [ ] 串行运行，每次使用全新 output/data/session 目录；不得把一组 workspace、receipt、artifact、memory 或生成结果带到另一组。

### 12.2 每次运行的 manifest

- [ ] 写入 `.arc/experiment-manifest.json`，至少包含：

```json
{
  "experiment": "h02-safe-file-cache-abc-v1",
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
  "session_scope": "turn|node|run",
  "file_state_policy": "baseline|clear-on-destructive-frame|retained-item",
  "projection_policy_id": "...",
  "compaction_policy": {},
  "time_budget_s": 0,
  "repair_rounds": 0,
  "repetition": 1,
  "run_order": 1
}
```

- [ ] endpoint 只记录稳定标识，不记录 API key。
- [ ] 保存原始 usage、runner events、Octos events、最终 grade、read/mutation metrics 和 receipt lifecycle counters。
- [ ] 基础设施错误、provider 账号错误、OOM、外部中断、dirty tree 或输入哈希不一致的运行标记无效，不混入功能失败。

### 12.3 指标与采用顺序

| 优先级 | 指标 | 硬要求/解释 |
| --- | --- | --- |
| 1 | 官方测试通过数、全通过率、回归数、重复运行稳定性 | B/C 不得低于 A 的可靠表现 |
| 2 | false `FILE_UNCHANGED`、stale mutation 漏放行 | 两者都必须为 0 |
| 3 | compaction/rewind/resume/parent-child contract 通过率 | 必须全部通过 |
| 4 | provider input/output/cache/reasoning token | 包含失败请求与重试 |
| 5 | full-body/stub 次数与字节、可见性失效重读 | 解释 token 来源 |
| 6 | hash bytes/latency、磁盘 I/O、请求数、修复轮数、总耗时 | 评估性能成本 |
| 7 | typed stale、恢复成功率、重试次数 | 不允许无界重试 |

- [ ] 先按前三项淘汰不安全/退化变体；只有都合格后才比较 token 与时延。
- [ ] A 的 cache 未完整接线不是 B/C 的通过证明；B/C 仍必须以确定性 false-hit oracle 验证。
- [ ] 旧 cache 直接接线的负向用例即使 token 最低也不得进入采用比较。
- [ ] 分别报告 B 相对 A 的“安全 dedup 总收益”和 C 相对 B 的“选择性保留边际收益”，不把两者合并成一个无法归因的百分比。

- [ ] 完成条件：每个有效 run 都能由 manifest 重放并追溯到固定 commit/输入；采用结论严格按指标优先级得出，而不是挑选个别低 token 样本。

## 13. Milestone M9：报告、采用、主干集成与回滚

- [ ] 生成 `./h02-abc-results.md`，列出原始运行数、无效原因、逐任务结果、聚合方法、置信边界和所有异常；不只给均值。
- [ ] B 只有在官方测试不下降、18 个 contract 全通过、false stub=0、stale mutation 漏放行=0 时才具备合并资格。
- [ ] C 只有在保持 B 全部安全条件且多任务、多次运行稳定减少 token/正文重传时才替代 B；否则采用 B。
- [ ] 若 B/C 都未达到安全门槛，回到 A 的全文读取行为；不得为了已投入成本放宽 oracle。
- [ ] 将选中 commit 移植/rebase 到当时的 `main`，检查与 H01 的 ContextManager 改动、H03 的 projection/recovery、H04 的 MCP compaction 交互。
- [ ] 运行 `git merge-tree --write-tree --messages origin/main HEAD` 或等价无工作树冲突检查，并重新审阅最终 diff；实验分支通过不等于主干组合通过。
- [ ] 在当前主干重新跑 M6 全部 contract、受影响 crates、ARC Python tests 和固定官方任务 smoke；记录新的集成 SHA。
- [ ] 提供单一 dedup kill switch 或等价注入点：关闭后所有 read 返回正文，但强版本 mutation guard 保持启用。
- [ ] receipt/schema 不兼容、state 初始化失败或指标后端失败时自动退回正文；回滚不依赖清理用户 workspace。
- [ ] 移除未采用实验的死代码/死开关；保留结果和明确的拒绝理由，不保留无法测试的半套抽象。
- [ ] 更新源码注释和运维说明，只陈述本次实验实测结果；不重新加入竞品固定参数或“30–60%”之类无证据数字。
- [ ] 明确记录 H02g 为 by-design not implemented，H02f 热点回灌不在本轮交付范围。

- [ ] 完成条件：选中方案在当前主干仍满足所有安全门槛，kill switch 能确定性恢复全文读取，且回滚不会关闭 mutation freshness 保护。

## 14. 后续编码 Agent 的提交与工作要求

### 14.1 推荐提交顺序

1. `test(h02): characterize file cache and prompt visibility boundaries`
2. `feat(h02): introduce strong file version observations`
3. `feat(h02): confirm read receipts after final prompt projection`
4. `fix(h02): isolate receipts across lifecycle and model branches`
5. `fix(h02): enforce mutation freshness at provider boundary`
6. `feat(h02): wire safe file state through stdio and mcp agents`
7. `test(h02): add observability and freeze variant b`
8. `experiment(h02): retain receipts for final-frame source items`（仅 C）

### 14.2 每个 Milestone 的完成格式

- [ ] 一个 commit 只完成一个可验证 Milestone 或一个为保持绿色所需的更小切片；不要把 M1–M5 压成一次大改。
- [ ] 先写/定位能反证目标行为的测试，再做最小实现；不得保留红色中间 commit。A 上的预期失败保存为 M0 证据，B 的提交必须绿色。
- [ ] 每个 commit message/body 记录：行为变化、未改变的边界、准确验证命令与结果、已知限制。
- [ ] 每完成一个 Milestone 才更新对应 checkbox，并附未来证据文档路径；没有命令输出或可观察 contract 不得仅凭代码存在勾选。
- [ ] 修改前重新读取当时主干的实际 caller 和 tests；本文中的建议落点不是授权跳过现状核验。
- [ ] 保持改动小而显式：优先扩展现有 `FileStateCache`、`read_window`、`ToolContext` staged state、`llm_call` 最终 messages reconciliation 和两个真实 Agent 构造点，不新建重复框架。
- [ ] 新抽象必须至少消除两个真实重复 caller 或保护一个明确的不变量；不要为未来可能的远端 provider 预建未使用层级。
- [ ] 对新增公开/跨 crate 类型补充 Rustdoc，写清 owner、生命周期、fail-safe 默认和 thread-safety；避免笼统的“cache entry”命名。
- [ ] 保留用户/其他分支已有改动；提交前检查 `git diff --check`、`git status --short` 和 intended path list，不顺手修改分析目录之外的无关文件。
- [ ] 若实际代码证明某条设计假设不成立，先在 M0 ADR 中记录证据与等价安全方案，再调整 Milestone；不得静默弱化四项命中条件。
- [ ] 遇到无法同时证明磁盘版本与模型可见性的路径，先保持正文回传并继续完成其他入口；不以“暂时命中”换取表面进度。

最终交付不是“cache 已接线”，而是可以被自动化反证的这条 contract：

> 只有当前磁盘版本与当前模型可见证据同时成立，Octos 才省略文件正文；读取证据按 task 和 model branch 隔离，所有 mutation 在当前磁盘上重新校验。
