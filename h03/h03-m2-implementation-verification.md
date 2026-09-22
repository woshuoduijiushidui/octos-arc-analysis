# H03 M2：有界原文存储与按范围恢复

- 日期：2026-09-21。
- 分支：两个仓库均为 `feat/output-recovery`，继续 M0 冻结底座。
- `MAIN_SHA=27d057c206c0f8250b60309905737f7e26ee0ba9`。
- `A_SHA=9d65681c3ef0c2b699e2fc68bbaac1d8b0d71cf1`。
- M1 代码提交：`0f69ad4e83f84cebc1fee65d1ece2c7640b5709a`。
- M2 代码提交：`d6f8198ea4005d24db7ba240321c264872f777c9`，仅本地提交，未推送。
- 状态：M2 已完成；文件最终分页、命令流式采集和 stdio 全入口接线仍分别属于 M3、M4、M5。

## 1. 本阶段完成的行为

M2 在现有 `context_ledgers/tool-output/` 目录下增加版本化的
`recovery-v1` 存储，不创建第二套 ContextManager。每次输出先生成完整的模型安全文本，
再写内容块和 manifest，最后用临时文件加原子 rename 发布 `index.json`。索引是提交记录：
只有索引已经指向的 manifest 和正文才可读；崩溃遗留的临时文件、正文或未发布 manifest
不会被解释成完整结果，并会在后续启动时清理。

每个结果仍使用 M1 分配的不可变 `output_id`。持久 manifest 保存 owner、来源、捕获状态、
真实执行状态、已保存范围、分块 SHA-256、整份存储摘要和固定旧分页边界。
`recoverable=true` 只在正文、manifest 和索引全部发布成功后写入视图；保存失败、容量不足、
损坏或旧格式均返回明确错误，不重新执行文件读取或命令。

`recall` 新增三种受控读取方式：

1. `output_id + stream + offset/limit`：以安全文本的绝对 UTF-8 字节位置读取。
2. 上一页返回的 `cursor`：绑定结果 ID、stream、已发布上界和 manifest 版本。
3. 兼容 `tool_call_id + page`：只在 call ID 唯一时使用，page 边界在首次保存时固定。

每页最多 8,192 字节，状态头和恢复参数也计入预算。读取仅 seek 并校验涉及的 64 KiB
内容块，不把整个大结果载入内存。重复读取相同游标得到相同内容；游标过期、位置溢出、
UTF-8 中间位置、越界和超大旧页号都直接报错，不钳位到末页。旧 page 内部若仍超过当前
展示预算，会先返回新 cursor；该固定 page 结束后再给出下一绝对 offset，避免内部缺口。

恢复页保留原 `output_id`，标记 `historical=true`，并沿用原 artifact。恢复结果不会再次
写正文、不会形成 recall 链，也不会触发原命令。最终 provider 投影仍通过 M1 的 typed
来源核对和统一预算重渲染。

## 2. 容量、完整性与权限

| 项目 | M2 实现 |
| --- | --- |
| 单结果 | 最多 16 MiB；stdout/stderr 各最多 8 MiB |
| 每逻辑 session | 64 MiB payload、256 条索引、4 MiB manifest |
| 全数据目录 | 256 MiB，发布前同时预留正文、manifest、索引和临时文件空间 |
| 运行中结果 | 每 session 最多 8 条；完成前因全视图清洗要求只发布 0 字节安全上界 |
| manifest | 单份最多 16 KiB，schema/version 不认识时拒绝 |
| 读取内存 | 64 KiB 校验块加一页正文；不在 ContextManager 锁内做磁盘读取 |
| 生命周期 | 活跃 owner 由共享 lease 固定；非活跃结果 24 小时过期，容量压力按最旧结果清理 |

达到单 stream、单结果或 session 容量时保存可容纳的 UTF-8 完整前缀，并将 capture 改为
`partial`、loss 标为 `storage_limit`。如果连一个非空前缀都不能发布，则保持
`recoverable=false`。物理目录容量不足时只清理没有活跃 lease 的旧结果；活跃结果不会
被删除，也不会通过停止读取 pipe 制造阻塞。命令的持续排空和流式落盘属于 M4，本阶段
没有修改进程处置。

正文只保存 `sanitize_tool_output` 对完整捕获结果生成的统一安全文本。分块发生在清洗后，
因此跨 64 KiB 块或恢复页的长凭据不会绕过清洗；发生变换后坐标明确是 safe-text bytes，
不冒充原文件覆盖。运行中原始文本可能因后续字节改变清洗结果，所以 M2 保守发布 0 字节
并返回 `pending`；最终状态到达后一次冻结安全正文。M4 接入流式采集时再扩展状态化发布。

owner 继续复用 H02 的 workspace、task、logical session、model branch 四维身份。
SessionActor 使用已有文件状态中的稳定 owner 创建输出服务，因此同一合法会话可冷恢复；
child、兄弟分支、其他 task/session/workspace 即使正文哈希相同也不能读取。
模型只能提交 output ID 或 cursor，不能提供 owner。Unix 上目录创建、文件打开、rename、
unlink 和目录枚举均锚定已打开的目录 fd，逐层拒绝 symlink；正文 hard link 也因链接数
不为 1 而拒绝。非 Unix 平台当前明确返回 `recovery_tool_unavailable`，不采用有竞态的
降级路径。

## 3. 状态与错误语义

持久状态沿用 M1 的 `OutputView`，增加：

- `recovery_boundary`：恢复页的固定 stream、读取上界和 manifest 版本。
- `historical`：区分历史 artifact 与当前文件读取；它不会激活 H02 当前文件凭据。
- `availability/stored_ranges/stored_bytes/stored_sha256/recoverable`：发布成功后填写真实值。

主要失败码为：

```text
invalid_cursor | stale_source | ambiguous_call_id | out_of_range |
output_missing | output_expired | output_corrupt | owner_mismatch |
storage_limit | storage_failed | source_incomplete |
unsupported_output_schema | recovery_tool_unavailable
```

运行中记录在同一进程完成后可由同一 `output_id` 原子替换；进程中断留下的
`running` 记录在冷启动时转换为 `partial`、`execution=unknown`、
`loss=capture_interrupted`，不会伪造成功或完整。完成记录不可换内容；相同 ID
再次提交不同来源、正文或调用关系会返回 `stale_source`。

## 4. 实际接线与阶段边界

| 位置 | M2 行为 |
| --- | --- |
| `octos-agent/src/output_store.rs` | 原子存储、索引、lease、容量、校验、范围读取和 cursor |
| `output_recovery.rs` | 保存安全原文、生成恢复状态、历史页重渲染且不重复 spill |
| `tools/recall.rs` | 新 output ID/offset/cursor 合同；H03 关闭保留旧 recall 行为 |
| `agent/execution.rs` | 普通及批准后结果避免在持久化前被旧裁剪再次破坏 |
| `session_actor.rs` | 复用稳定 H02 owner；已有 `RecallTool` 可同进程及冷启动读取 |

ARC 的 `serve --stdio --solo` 仍未在工具策略中注册 `recall`，因此 M2 没有给该入口虚假地
声明可恢复；它继续保持 M1 的 `recoverable=false`。stdio 每 turn 生命周期、压缩后引用、
allow/deny、外层代理裁剪和 MCP 条件性入口统一留在 M5。文件下一页与 H02 最终凭据属于
M3；shell/bash/exec_command 在首次截断前的有界流式保存属于 M4。

## 5. 验证记录

环境为 macOS 26.6.2，`rustc/cargo 1.96.1`。所有 Rust 命令前均执行：

```bash
source ~/.zshrc
export PATH="$HOME/.rustup/toolchains/1.96.1-aarch64-apple-darwin/bin:$PATH"
export OCTOS_OUTPUT_RECOVERY=0
```

M2 测试显式构造开启 policy；回归固定关闭环境开关。所有专项套件先用 `-- --list`
确认非零命中，再串行运行。

| 验证 | 结果 |
| --- | --- |
| `cargo test -p octos-agent --lib h03_m2 -- --test-threads=1` | 16 passed |
| `cargo test -p octos-agent --test h03_m2_recall -- --test-threads=1` | 1 passed；真实 Agent 最终请求连续恢复，持久索引仍只有原结果一条 |
| M1 `h03_m1_output` | 13 passed |
| M0 `h03_m0_dispatch` | 2 passed |
| 旧 `tools::recall::tests` | 3 passed |
| task_file_state / model_read_receipts / file_state_cache | 3 / 17 / 14 passed |
| ContextManager 全模块 | 101 passed |
| SessionActor prompt bridge | 3 passed |
| `cargo check --workspace --tests` | 退出码 0 |
| `cargo fmt --all -- --check` | 退出码 0 |
| Clippy（agent/cli 全 targets） | 仅沿用 M1 已确认的 `nonminimal_bool` 基线豁免后退出码 0 |

不重复累计已包含于 ContextManager 全模块的两个 H03 M1 和一个 H02 用例；本轮聚焦回归
共 **173 passed，0 failed，0 ignored**。M2 新测试覆盖：

- 热/冷恢复后逐页重组 SHA-256 与固定源文本完全一致，含 BOM、CRLF、中文、emoji、
  非零起点和无末尾换行。
- 重复 cursor 结果一致，索引和文件数量不增长；真实 Agent 多次 recall 只保留一份正文。
- 同一 call ID 两次出现返回 `ambiguous_call_id`，精确 output ID 仍分别可读。
- offset/limit/cursor 冲突、负数、溢出、UTF-8 中间位置、EOF 和旧 page 越界。
- 正文块损坏、缺失、未知 schema、发布失败、未发布残留和错误 cursor 版本。
- workspace/task/session/branch 隔离，symlink 祖先/叶子和 hard link 拒绝。
- 单 stream、64 MiB session、256 条索引、8 条 running 上限及活跃 lease 清理保护。
- 长凭据跨块和跨页清洗，非零退出及短 stderr 保留，运行中 pending、完成和中断转换。

准确命令及计数另见 [checks.json](./m2-evidence/checks.json)。本阶段没有运行真实模型、
官方任务 A/B 或 stdio 假模型协议；这些不是 M2 完成条件，分别留给 M5 和 M8。

## 6. 提交

代码提交 `d6f8198e`，共 10 个文件；`git diff --check`、暂存路径和提交后工作树均已核对。
提交钩子在提交成功后因沙箱拒绝写入 `~/.bytesec/commit_hook/commit_result.json` 而返回
非零状态；实际提交对象存在且工作树干净，没有禁用钩子或重复提交。
分析文档、里程碑清单和检查摘要在分析仓库单独本地提交，不推送。
