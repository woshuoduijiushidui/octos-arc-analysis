# H02 M5：真实入口与父子 Agent 文件状态接线验证

- 日期：2026-09-20
- 状态：完成，可进入 M6
- 分支：`feat/safe-file-cache`
- 主线基线：`main@6aacc9fb1a1599ae10f8368921ccf3e3afb7f87e`
- M5 代码提交：`7486c3562c3380a562040161246c189aa05879ec`
- 远程状态：未推送

## 1. 本次完成的行为

1. 新增显式的 `TaskFileState` 和 `ModelBranchFileState`。任务内可共享文件版本账本，
   每次创建模型分支时都会新建独立的读取凭据仓；复制任务状态不会复制父分支凭据。
2. `Agent::with_file_state` 一次性安装版本账本和当前分支凭据。旧的单独 cache/
   receipt builder 保留给兼容调用者，但不会被当作可向子 Agent 传播的完整状态。
3. `SessionRuntime` 启动时创建 root 分支状态。OUP 每轮重建 `request_agent` 时复用
   同一 root 分支，因此在来源正文仍处于最终 prompt 时，跨轮重复读取可以安全返回
   `[FILE_UNCHANGED]`。
4. 修复 OUP prompt bridge 的误判：此前它在临时移除系统提示、尚未把相同系统提示
   放回时就计算 `prompt_replaced`，导致每次正常请求都撤销读取候选。现在比较最终
   实际发送给模型的消息；真正的裁剪、替换和压缩仍会触发失效。
5. MCP 每次 `run_session` 都创建新的任务状态和唯一 root 分支。一次调用内可以
   安全命中，不同调用即使读取同一路径也不会共享凭据。
6. 同步和后台 spawn 在每个 worker 创建时才生成 child 分支。父子和兄弟 worker
   只共享版本账本，不共享读取凭据；工作树隔离模式会按 child 工作区重新绑定 owner。
7. pipeline 通过 `ToolContext` 和 `PipelineHostContext` 传播任务状态，每个节点
   worker 使用独立 branch receipt。只有旧 cache 的调用者继续只获得版本记录能力。
8. gateway `SessionActor` 也改用相同组合状态，避免另一条真实 Agent 构造路径继续
   停留在“只有账本、没有最终可见凭据”的半接线状态。
9. 状态初始化失败、owner 不完整、未配置组合状态或旧调用者只传 cache 时，读取
   去重保持关闭并返回正文，不影响工具执行。

## 2. 生命周期与隔离

| 场景 | 结果 |
| --- | --- |
| 同一 OUP session、同一 root branch、来源仍在最终 frame | 跨 turn 第二次读取可返回 stub |
| OUP 正常重挂载相同 system prompt | 不再误报为破坏性 prompt replacement |
| OUP 发生真实 compaction/替换 | `prompt_replaced=true`，旧 receipt 被撤销 |
| 默认 `OCTOS_SESSION_SCOPE=turn` | 进程/SessionRuntime 关闭后状态随所有者释放，没有全局 receipt map |
| `node`/`run` 复用运行时 | 每次最终 dispatch 仍重新核对 source proof；来源消失即 miss |
| 同一次 MCP `run_session` | 成功发送正文后，后续相同读取可命中 |
| 两次 MCP `run_session` | 使用不同 invocation owner，第二次首次读取返回正文 |
| parent/child 与 sibling child | 共享 ledger，receipt store 指针和 owner 均独立 |
| pipeline nodes | 每个 worker 创建独立 receipt store |
| 仅有 cache 或缺少 owner | 不返回 `[FILE_UNCHANGED]` |

## 3. 新增或强化的测试

- `task_file_state::tests`：验证共享 ledger、独立 receipt、owner 缺失时禁用，以及
  child workspace 重新绑定。
- `rebuilt_agent_reuses_same_branch_receipt_when_source_remains_visible`：模拟 OUP 每轮
  重建 Agent，证明同一 branch 且来源仍可见时可以跨轮命中。
- `h02_m5_stdio_open_and_two_turns_reuse_verified_read_receipt`：直接调用真实
  `session/open` 和两次 `turn/start` 处理链，验证第二轮发送给模型的读取结果为 stub。
- `repeated_read_through_mcp_dispatch_uses_verified_receipt`：验证真实 MCP dispatch
  内的安全命中。
- `separate_mcp_invocations_do_not_share_read_receipts`：验证 MCP 调用之间不复用 receipt。
- spawn 测试验证 parent、child 和 sibling 共享同一 ledger，但 receipt store 不同；
  缺少 session owner 时不创建 receipt。
- pipeline 测试验证每个 worker 独立创建 branch receipt，并验证完整状态从
  `ToolContext` 到 `PipelineHostContext`。
- 原 M3 owner 隔离测试增加“child 先读，parent 首读仍返回正文”的反向场景。
- OUP compaction 测试增加真实压缩后必须报告 `prompt_replaced=true` 的断言。

## 4. 验证结果

运行前执行：

```text
source ~/.zshrc
export PATH="$HOME/.rustup/toolchains/1.96.1-aarch64-apple-darwin/bin:$PATH"
```

通过的命令：

| 命令 | 结果 |
| --- | --- |
| `cargo test -p octos-agent --lib task_file_state::tests` | 3 passed |
| `cargo test -p octos-agent --test h02_m1_file_versions` | 3 passed |
| `cargo test -p octos-agent --test h02_m2_read_receipts` | 12 passed |
| `cargo test -p octos-agent --test h02_m3_receipt_lifecycle` | 4 passed |
| `cargo test -p octos-agent --lib tools::write_file::tests` | 48 passed |
| `cargo test -p octos-agent --lib tools::edit_file::tests` | 37 passed |
| `cargo test -p octos-agent --lib tools::diff_edit::tests` | 11 passed |
| `cargo test -p octos-agent --lib tools::apply_patch::tests` | 49 passed |
| `cargo test -p octos-agent --lib tools::mutation_guard::tests` | 2 passed |
| `cargo test -p octos-agent --lib tools::write_grant::tests` | 15 passed |
| `cargo test -p octos-agent --lib tools::nofollow_tests` | 19 passed |
| `cargo test -p octos-agent --lib tools::read_window::tests` | 16 passed |
| `cargo test -p octos-agent --lib model_read_receipts::tests` | 14 passed |
| `cargo test -p octos-agent --lib tools::spawn::tests` | 94 passed，1 个既有 ignored |
| `cargo test -p octos-agent --test m8_integration_tool_context` | 4 passed |
| `cargo test -p octos-pipeline --test m8_parity` | 6 passed |
| `cargo test -p octos-pipeline --lib file_state` | 2 passed |
| `cargo test -p octos-pipeline pipeline_workers_mint_independent_branch_receipts` | 1 passed |
| `cargo test -p octos-cli --test mcp_serve_integration` | 14 passed |
| `cargo test -p octos-cli h02_m5 --lib` | 2 passed |
| `cargo test -p octos-cli ui_protocol_ws_turn_agent_inherits_complete_root_file_state --lib` | 1 passed |
| `cargo test -p octos-cli in_loop_compaction_emits_lifecycle_notifications --lib` | 1 passed |
| `cargo check -p octos-agent -p octos-pipeline -p octos-cli --tests` | 通过 |
| `cargo clippy -p octos-agent --all-targets -- -D warnings` | 通过 |
| `cargo clippy --workspace --all-targets -- -D warnings -A clippy::nonminimal-bool` | 通过 |
| `cargo fmt --all -- --check` | 通过 |
| `git diff --check` | 通过 |

严格的全工作区 Clippy 仍只被基线文件
`crates/octos-cli/src/commands/serve.rs:878` 的
`clippy::nonminimal_bool` 阻断；该文件不在 M5 diff 中。

没有运行依赖真实模型的外部测试。stdio/OUP 和 MCP 入口测试均使用本地脚本 provider，
但经过真实的 session、Agent loop、tool execution 和最终 provider prompt 路径。

## 5. 完成判断

M5 已把 M1-M4 的强版本、最终可见凭据和生命周期规则接入真实 stdio/OUP、MCP、
gateway、spawn 与 pipeline 构造路径。共享范围被限制为版本账本；每个模型分支都有
独立 receipt store。缺少完整状态时系统只损失去重，不会错误省略正文。

因此 M5 完成条件已满足，可以进入 M6 的观测、全量回归与 B 分支冻结。
