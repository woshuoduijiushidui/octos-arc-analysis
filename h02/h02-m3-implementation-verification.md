# H02 M3：生命周期失效与模型分支隔离验证

- 日期：2026-09-20
- 状态：完成，可进入 M4
- 分支：`feat/safe-file-cache`
- 主线基线：`main@6aacc9fb1a1599ae10f8368921ccf3e3afb7f87e`
- M3 提交：`14a60ded231d1889ef35617430886e3f34bb931b`
- 远程状态：未推送

## 1. 本次完成的行为

1. 新增 `ReadReceiptOwner`，完整记录 workspace、task、logical session 和
   model branch。任一字段为空时不能创建 owner。
2. `ModelReadReceiptStore::new()` 现在是禁用态；只有通过完整 owner 创建的
   store 才会暂存或命中 receipt。receipt 的 workspace 必须与文件版本一致。
3. candidate 和已激活 receipt 都限制为最多 256 条。超出容量时淘汰最旧条目，
   后续读取只会退化为返回正文。
4. 新增带枚举原因的统一 `clear` API，记录清理次数、最后一次原因、被清除数量，
   并写入 lifecycle clear 和 cleared entries 指标。
5. 每次清理都会推进 store generation。清理前已经从最终 prompt 生成、但尚未
   激活的 pending receipt，之后不能重新激活。
6. legacy context trim、旧工具结果替换、声明式 preflight/turn compaction、
   tier-1 tool-result replacement，以及 ContextManager 报告的 compaction 或
   prompt replacement 都会清空当前 branch receipt。
7. projection policy 改变使用同一清理 API，不再只做无原因的筛除。
8. mutex 中毒会先清空 candidate/receipt，再按 miss 继续，不会产生错误 stub。

## 2. 生命周期边界

- rewind、rollback、resume、teleport、fork、task switch 和 cold restore 不从
  历史、artifact、hash 或版本账本恢复 receipt；这些入口后续启用 dedup 时必须
  创建新的完整 owner store。
- 当前 stdio/MCP 生产入口尚未启用 receipt，这是 M5 的工作。因此这些入口当前
  天然返回正文，不在 M3 提前加入半套 owner 推导。
- `SpawnTool` 和 delegate 的 child Agent 继续只接收 `FileStateCache`，不会复制
  parent 的 `ModelReadReceiptStore`。同步 child、后台 child 和 parent 的模型可见
  状态保持独立。
- `FileStateCache` 可以跨 parent/child 或 fresh Agent 复用；测试证明共享磁盘版本
  不会自动生成模型可见 receipt。
- M2 的最终 provider messages 核对仍保留为兜底。即使某个未来入口遗漏主动
  `clear`，source proof 不在最终 prompt 时也会撤销 receipt。

## 3. 场景覆盖

| Research 场景 | M3 证据 |
| --- | --- |
| 2：source proof 被 compaction/trim 删除 | legacy trim、旧结果替换、声明式压缩、tier-1 和 PromptContext replacement 均有测试；替换后的首次读取返回正文 |
| 9：task/session/workspace 隔离 | 相同文件分别使用不同 task、session 和 workspace owner，均不能借用已有 receipt |
| 10：parent/child 隔离 | 独立 branch store 共享同一版本账本；parent 不授权 child，child 也不写回 parent |
| 11：rewind/fork/cold resume/task switch | 新 owner store 和同 owner 的全新 store 都从空状态开始；保留版本账本时首次读取仍返回正文 |
| 12：淘汰与状态丢失 | candidate/receipt 容量测试验证最旧条目淘汰后安全 miss；锁中毒与 store 重建也只丢失优化 |
| 16：命中可解释性 | receipt 同时绑定完整 owner、强版本、view、source proof 和投影策略；缺少 owner 的默认 store 完全禁用 |

## 4. 验证结果

运行前执行：

```text
source ~/.zshrc
export PATH="$HOME/.rustup/toolchains/1.96.1-aarch64-apple-darwin/bin:$PATH"
```

通过的命令：

| 命令 | 结果 |
| --- | --- |
| `cargo test -p octos-agent --lib model_read_receipts::tests` | 13 passed |
| `cargo test -p octos-agent --lib agent::llm_call::tests` | 11 passed |
| `cargo test -p octos-agent --lib agent::loop_compaction::tests` | 6 passed |
| `cargo test -p octos-agent --lib agent::compaction::tests` | 2 passed |
| `cargo test -p octos-agent --test h02_m1_file_versions` | 3 passed |
| `cargo test -p octos-agent --test h02_m2_read_receipts` | 11 passed |
| `cargo test -p octos-agent --test h02_m3_receipt_lifecycle` | 4 passed |
| `cargo test -p octos-agent --test m8_integration_cache_handoff` | 2 passed |
| `cargo test -p octos-agent --test compaction_wiring` | 3 passed |
| `cargo test -p octos-agent --test compaction_policy` | 12 passed |
| `cargo check -p octos-agent --all-targets` | 通过 |
| `cargo clippy -p octos-agent --all-targets -- -D warnings` | 通过 |
| `cargo clippy --workspace --all-targets -- -D warnings -A clippy::nonminimal-bool` | 通过 |
| `cargo fmt --all -- --check` | 通过 |
| `git diff --check` | 通过 |

严格的全工作区 Clippy 仍只被基线文件
`crates/octos-cli/src/commands/serve.rs:878` 的
`clippy::nonminimal_bool` 阻断；该文件不在 M3 diff 中。

另尝试了 `cargo test -p octos-agent --lib`。M3 相关用例均通过，但全量套件中
若干依赖本机 macOS sandbox、后台进程和 send-file 路径的既有用例失败或超过
60 秒，最终进程被 `SIGKILL`，因此不把该次运行记为通过证据。所有 M3 直接影响
的确定性测试均已单独完整退出并通过。

未调用真实模型。

## 5. 完成判断

当前 receipt 只能存在于一个完整、明确的模型分支 owner 中。任何已知的破坏性
prompt 变化都会全量撤销该分支的 candidate 和 receipt；淘汰、恢复、父子分叉、
owner 缺失或内部锁异常都只会让下一次读取返回正文。旧 stub 不会在压缩后续命，
旧 pending candidate 也不能越过清理边界重新激活。

因此 M3 的生命周期失效和模型分支隔离条件已满足，可以进入 M4。
