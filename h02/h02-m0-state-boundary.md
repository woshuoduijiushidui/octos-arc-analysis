# H02 M0：基线与文件读取状态边界

- 日期：2026-09-20
- 状态：完成，可进入 M1
- 初始调研基线：`octos-arc@c599d18c5acd2b846f049ffea2be84e72fe60fac`
- 当前实现基线：`octos-arc/main@6aacc9fb1a1599ae10f8368921ccf3e3afb7f87e`
- 实现分支：`feat/safe-file-cache`
- M0 测试提交：`0e236311`（rebase 前为 `7d4f81e6`）
- 结构化环境记录：[h02-m0-baseline.json](./h02-m0-baseline.json)

M0 的源码事实最初在 `c599d18c` 上采集。M0、M1 后续已无冲突重放到
`main@6aacc9fb`，`git range-diff` 显示补丁完全等价，并在新基线上重新验证。

## 1. M0 结论

当前代码不能安全地把旧 `FileStateCache` 直接接到 stdio 和 MCP：

1. 它只用路径和 `mtime` 决定命中，没有重新核对当前内容哈希。
2. `read_file` 在模型最终看到输出之前就把读取记为“已缓存”；后续还有 50KB、脱敏、hook、8KiB 和上下文压力处理。
3. stdio 的启动 Agent 有缓存，但真正处理每轮请求的新 Agent 没有继承它；MCP 每次运行创建的 Agent 也没有缓存。
4. spawn 的同步和后台子 Agent 直接共享父 Agent 的同一个缓存实例，子 Agent 读过的正文可能让父 Agent 收到空 stub。
5. 唯一会在 tier-3 压缩后清缓存的 helper 只被测试调用，生产压缩、回退、恢复和工作区回滚都没有统一清理点。
6. `ToolResult.structured_metadata`、`ToolOutputEnvelope` 和 `PromptFrame.report` 各自保留了部分信息，但不存在从读取候选一路绑定到最终 provider 请求的类型化凭据。

因此 M1 只能先建立可信文件版本且继续返回正文；M2 才能在最终 provider 请求成功后建立模型可见读取凭据。

## 2. 默认 ARC stdio 真实调用链

默认环境变量均未设置时，入口走 Python 引擎、stdio 驱动和 `turn` 会话范围。

```text
arc/main.py::main
  -> Flow::run / 节点生成与修复
  -> OctosDriver::run
  -> OctosDriver::_run_stdio
  -> OctosDriver::_get_session
  -> OctosStdioSession::__init__
       启动 octos serve --stdio --solo
  -> profile/local/create + profile/llm/upsert
  -> session/open
  -> turn/start
  -> ui_protocol_transport::run_standalone_turn
  -> appui_context_history_for_agent
       加载/重建 ContextManager，必要时先压缩，再 for_prompt
  -> Agent::new_shared 创建 per-turn request_agent
  -> request_agent.with_prompt_context_manager(AppUiPromptContextBridge)
  -> Agent::process_message_tracked_with_attachments
  -> prepare_prompt_with_context_manager
  -> call_llm_with_hooks_mode
  -> LlmProvider::chat_stream / chat
```

关键代码：

- `arc/main.py:741-750`：默认 `OCTOS_DRIVER=stdio`、`OCTOS_SESSION_SCOPE=turn`。
- `arc/main.py:790-804`、`878-908`：创建、复用和关闭 stdio session。
- `arc/octos_stdio.py:25-40`：启动 `octos serve --stdio --solo`。
- `arc/octos_stdio.py:182-198`：发送 `session/open` 和 `turn/start`。
- `crates/octos-cli/src/runtime/session.rs:429`、`577-608`：bootstrap Agent 创建并持有一个 `FileStateCache`。
- `crates/octos-cli/src/api/ui_protocol_transport.rs:32456`、`33110`：真实 per-turn 入口和预请求 ContextManager 投影。
- `crates/octos-cli/src/api/ui_protocol_transport.rs:34601-34738`：重新创建 `request_agent` 并挂载 prompt bridge，但没有 `.with_file_state_cache(...)`。
- `crates/octos-agent/src/agent/loop_runner.rs:565,1354,2666`：每次 provider 请求前调用 prompt bridge。
- `crates/octos-agent/src/agent/llm_call.rs:72-175`：接收最终 `messages` 并进入 provider 调用。

### stdio 的四个归属答案

| 问题 | A 基线答案 |
| --- | --- |
| 谁创建版本 ledger | `SessionRuntime::bootstrap` 创建旧 `FileStateCache`。 |
| 谁拥有 branch receipt | 不存在 `ModelReadReceipt`；bootstrap cache 也没有进入真正的 per-turn Agent。 |
| 谁确认最终可见 | `AppUiPromptContextBridge`/`ContextManager::for_prompt` 决定最终消息，但不向文件缓存回传确认；`call_llm_with_hooks_mode` 直接发送 `messages`。 |
| 何时清理 | 当前目标 Agent 没有 cache 可清；ContextManager 会替换/压缩消息，但没有文件读取凭据清理协议。 |

## 3. MCP `run_session` 真实调用链

```text
MCP tools/call: run_octos_session
  -> dispatch_run_octos_session
  -> RealSessionDispatch::run_session
  -> 每次调用创建 LLM、EpisodeStore、ToolRegistry
  -> Agent::new_shared("mcp-serve")
  -> 可选 with_compaction_runner
  -> Agent::run_task
  -> prepare_task_messages / legacy or declarative compaction
  -> call_llm_with_hooks_mode
  -> LlmProvider::chat_stream / chat
```

关键代码：

- `crates/octos-agent/src/mcp_server.rs:600-668`：MCP 工具调用转给 dispatch。
- `crates/octos-cli/src/commands/mcp_serve.rs:483-605`：每个 `run_session` 创建独立 Agent，但没有文件缓存。
- `crates/octos-cli/src/commands/mcp_serve.rs:610-630`：只在 workspace policy 存在时挂载通用 compaction runner。
- MCP 没有 AppUI `ContextManager`，因此不能假定它与 stdio 共用 transcript item ID 或 8KiB 投影。

### MCP 的四个归属答案

| 问题 | A 基线答案 |
| --- | --- |
| 谁创建版本 ledger | 没有创建。 |
| 谁拥有 branch receipt | 不存在。 |
| 谁确认最终可见 | `call_llm_with_hooks_mode` 是最后共同边界；它只接收最终 `messages`，不持有文件读取候选。 |
| 何时清理 | 没有文件状态可清；每次 `run_session` 的 Agent 生命周期结束时整体释放。 |

## 4. `Agent::new_shared` 与缓存接线盘点

生产调用点：

| 调用点 | 用途 | 文件缓存 |
| --- | --- | --- |
| `runtime/session.rs:577` | AppUI/stdio 的 SessionRuntime bootstrap Agent | 新建并接入 |
| `api/ui_protocol_transport.rs:34601` | 真正处理 OUP 每轮请求的 Agent | **未接入** |
| `commands/mcp_serve.rs:599` | MCP 每次 `run_session` 的 Agent | **未接入** |
| `autonomy/agent_orchestrator.rs:3049` | 原生 specialist worker | **未接入** |

其余 `Agent::new_shared` 命中位于测试代码或注释。其他实际传播点：

- gateway `SessionActor` 在 `session_actor.rs:3174,3977` 创建并接入 cache。
- pipeline 在 `octos-pipeline/src/handler.rs:899` 继承 host cache。
- spawn 同步路径在 `tools/spawn.rs:3985-3987`、后台路径在 `4606-4612` 直接 clone 同一个 `Arc<FileStateCache>`。
- `spawn_tool_propagates_parent_caches_via_builders` 用 `Arc::ptr_eq` 自动证明父子拿到同一实例。

`FileStateCache` 的生产读写点：

- `get`：只有 `read_file` 命中路径，输入仅有 path 和当前 `mtime`。
- `put`：`read_file` 正文返回后登记；resume 可通过 `seed_from_replacement_refs` 写入一个 `UNIX_EPOCH` 占位条目。
- `invalidate`：`write_file`、`edit_file`、`diff_edit` 成功后调用；`apply_patch` 对候选路径调用。
- `clear`：只有 `run_tier3_and_invalidate_cache` helper 调用。全仓唯一调用方是 `m8_integration_cache_handoff` 测试，生产循环没有调用它。

## 5. 一次 `read_file` 到最终 prompt 的状态变化

| 阶段 | 当前处理 | 仍保留的类型化事实 | 丢失/缺少的事实 |
| --- | --- | --- | --- |
| `read_file` 命中前 | `metadata` 取 mtime；`cache.get(path, mtime)` | path、mtime、旧 entry | 当前内容哈希、稳定 observation |
| `read_file` 正文 | no-follow 读取、行范围、工具内 100KB 限制 | 局部 `read_meta`、输出字符串 | 没有 typed candidate ID |
| cache `put` | 在工具返回前写入 path/mtime/FNV hash/size/range | 工具认为的范围 | 模型尚未看见；hash 不会在命中时重算 |
| `ToolResult` | 返回 output；`read_file` 的 `structured_metadata=None` | 普通字符串 | target/version/range/output digest side-channel |
| 通用执行层 | 50KB head/tail、sanitize、hook feedback | 只把插件自带 metadata 另行上报 | 读取身份与被变换后的正文解绑 |
| ContextManager | 默认保留 8KiB；记录 raw hash、item ID、裁剪原因、policy | `ToolOutputEnvelope` 和 `PromptFrame.report` | canonical target、FileVersion、requested/visible view、args digest |
| context pressure | 可再次裁剪 tool output 或丢弃 item | truncated/dropped item IDs | 没有对应 receipt 可撤销 |
| provider 边界 | `call_llm_with_hooks_mode(messages, ...)` | 最终 `Message` 列表 | 没有 staged candidate，也不能确认/拒绝 receipt |

对应代码：

- `file_state_cache.rs:189-202`：命中只比较 `mtime`。
- `read_file.rs:365-405`：读正文前就可能返回 stub。
- `read_file.rs:672-709`：100KB 处理后、模型投影前写 cache。
- `agent/execution.rs:2394-2455`：50KB、sanitize、hook 后只形成普通 Tool `Message`。
- `context_manager.rs:323-400`：现有 envelope/report 可描述最终投影，但字段不足以绑定文件版本和请求范围。
- `context_manager.rs:2419-2476`：默认 8KiB 可见内容和 raw digest。
- `context_manager.rs:2939-3272`：`for_prompt` 再做配对、上下文压力裁剪和丢弃。
- `agent/llm_call.rs:72-175`：最终共同发送边界。

结论：M2 可以把 `call_llm_with_hooks_mode` 作为 stdio/MCP 的共同确认候选，但必须先从 `read_file` 经 `ToolContext`/执行层保留 typed candidate。不能从模型可见文本反向解析。

## 6. 生命周期入口

| 生命周期 | 生产入口与 A 基线行为 | H02 B 组要求 |
| --- | --- | --- |
| stdio pre-turn/in-loop compaction | `appui_context_history_for_agent` 和 `AppUiPromptContextBridge::prepare_prompt` 调用 `ContextManager::compact_context`，替换最终消息；不触碰 file cache | 当前 branch receipts 全清，并在最终消息上重新核对 source proof |
| legacy trim/tool-result replacement | `agent/loop_compaction.rs:27-60` 修改消息；挂 ContextManager 时跳过 legacy old-result truncation | 无论走哪条路径都撤销不可见 receipt |
| tier-3 | `run_tier3_and_invalidate_cache` 能清 cache，但只有测试调用 | 在真实调用点统一接入，或由最终消息 reconcile 兜底 |
| rollback/rewind | `session/rollback` 裁剪历史并重建 ContextManager | 新 frame 首次读取返回正文 |
| resume/cold restore | gateway 会从 replacement refs seed 旧 cache；AppUI 从 snapshot/history 重建 ContextManager | ledger 可保留，receipt 从空开始，不能由 artifact/hash 自动恢复 |
| fork/spawn | ContextManager 为 child 生成裁剪后的独立 history；文件 cache 却共享父 Arc | 只共享版本查询，child receipt store 为空 |
| task switch | Agent/task 可变化，没有文件 receipt owner | owner 必须包含 task/session/model branch；切换时从空 receipt 开始 |
| workspace snapshot restore | `raw_snapshot_restore` 只恢复磁盘，没有 file cache invalidation | 下一次命中必须强校验版本；当前 branch 旧 receipt 主动撤销 |

## 7. mutation 现状

| 工具/来源 | 当前保护 | 当前缺口 |
| --- | --- | --- |
| `write_file` | opt-in window 模式记录 byte coverage 和 epoch；大文件完整可见时使用 `write_no_follow_checked`；write grant 路径可使用 confined checked write | 默认未开启时，小文件/普通覆盖仍可直接写；没有统一 expected `FileVersion` |
| `edit_file` | 当前磁盘重新读取；old string 需唯一匹配；write grant 时复用同一个受限句柄 | 无 fence 时读取后重新打开写入，仍有竞争窗口；没有统一版本错误类型 |
| `diff_edit` | 当前磁盘重新读取并匹配 hunk | 读取和写入分离；匹配策略可选第一个邻近结果，不是统一唯一上下文 contract |
| `apply_patch` | 先规划全部 section，再执行；每个候选路径主动失效 cache | 规划与实际写入之间可变化；多文件执行中可能产生已明确报告的部分结果 |
| shell/formatter/test/git/外部编辑器 | 无文件缓存通知 | 必须靠下一次 hit 的强版本核验，不能依赖主动 invalidation |

主动 invalidation 只能减少无用比较，不能成为正确性依据。M4 应复用现有 no-follow、write fence 和 read-window epoch，而不是新增一套平行写入框架。

## 8. 自动化证据

新增或拆分的测试：

| 测试 | 证明内容 | A 上结果 |
| --- | --- | --- |
| `h02_m0_characterization_get_ignores_content_hash_when_mtime_matches` | 相同 mtime 时，`get` 返回旧 hash entry；当前 hash 根本没有传入 | 通过 |
| `h02_m0_characterization_caches_full_before_final_prompt_projection` | 8KiB 以上输出已被记为 full，且 `structured_metadata` 为空 | 通过 |
| `h02_m0_characterization_full_cache_entry_precedes_truncated_prompt_projection` | 把同一次真实读取送入 ContextManager 后，cache 仍标为全文，但最终可见内容已按 8KiB 策略裁剪 | 通过 |
| `h02_m0_characterization_cache_stub_follows_body_dispatch` | Agent 内第二次 read 前确实有一次包含正文的 provider 请求；不再只用“cache 接上了”解释 stub | 通过 |
| `spawn_tool_propagates_parent_caches_via_builders` | spawn 持有与 parent 相同的 cache `Arc` | 通过 |
| `h02_m0_characterization_oup_and_mcp_agents_omit_file_cache_wiring` | bootstrap 有 cache，而 OUP per-turn 和 MCP Agent 构造均未接入 | 通过 |
| `h02_contract_returns_body_until_a_model_dispatch_confirms_visibility` | 没有 provider dispatch 时第二次直读必须返回正文 | **预期失败**：A 返回 `[FILE_UNCHANGED]` |

安全契约标记为 `ignored`，因此普通基线测试保持绿色；显式运行它会稳定暴露 A 的错误行为。M2 实现完成后应移除 `ignore`，让它进入普通回归集。

完整命令、退出码和数量见 [h02-m0-baseline.json](./h02-m0-baseline.json)。未调用真实模型。

验证摘要：

- Rust 聚焦测试、MCP 集成测试、`cargo fmt --all -- --check` 和 `octos-agent` Clippy 均通过。
- `octos-agent + octos-cli` 联合 Clippy 被基线文件 `crates/octos-cli/src/commands/serve.rs:878` 的 `clippy::nonminimal_bool` 阻断；该行不属于 H02，本里程碑未顺手修改。只允许这一条已知告警后，两个 crate 的全部 target 均通过 Clippy。
- 系统没有 `python` 命令；改用 `PYTHONPATH=arc python3 -m unittest discover -s arc/tests` 后运行 179 项，173 通过、5 跳过、1 个基线错误。错误来自 Python 3.9.6 不支持 `tarfile.TarFile.extract(..., filter="data")`。
- `source ~/.zshrc` 后仍没有 cargo/rustc shim；验证时显式把 `~/.rustup/toolchains/1.96.1-aarch64-apple-darwin/bin` 加入 `PATH`。

## 9. 放弃的方案

- **全局 cache**：路径相同不代表 task、session、workspace 或模型分支相同。
- **只有 generation epoch**：generation 相同不能证明 source item 仍在最终 prompt，也不能证明范围未被裁剪。
- **只有 mtime/size**：外部程序可以同大小改写并恢复时间；M0 测试已证明当前 API 不检查 live hash。
- **从 `[FILE_UNCHANGED]` 或正文文本反推 receipt**：字符串会被截断、脱敏、hook 改写，也可由普通工具输出伪造。
- **把 parent receipt 复制给 child**：child 的初始 prompt 会经过独立 fork sanitizer，不能假定包含 parent 看过的正文。
- **直接把旧 cache 接到 OUP/MCP**：会把当前潜在风险变成目标入口的稳定 false stub。

## 10. M1 输入约束

M1 应只完成磁盘事实，不启用 stub：

1. 从同一次稳定读取产生 bytes 与强 `FileVersion`。
2. metadata 只做快速否定；候选命中仍重新取得可信 revision 或 SHA-256。
3. 版本 key 包含 workspace/provider owner 和 canonical target。
4. 所有读取错误、锁错误和不稳定 observation 都退回正文或 typed concurrent-change。
5. 即使版本相同也继续返回正文，直到 M2 能在最终 provider 请求成功后确认 receipt。
