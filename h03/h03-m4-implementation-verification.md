# H03 M4 实现与验证：命令输出在首次截断前保存

## 1. 结论

- 状态：M4 已完成。
- 代码提交：`d7931fbc55515aeb882b5feeca806e05f5582bd1`，仅本地提交，未推送。
- 覆盖入口：前台 `shell`、非 TTY `bash`、非 TTY 且不 yield 的 `exec_command`。
- 保持边界：后台 `shell` 与 TTY/yield `exec_command` 不伪造历史输出，统一返回不可恢复状态。
- M5 仍负责 stdio 注册 `recall`、冷启动恢复、压缩后恢复和其他入口接线。

## 2. 采集与保存

新增 `tools/command_capture.rs` 作为三个前台命令工具的共用采集层：

1. stdout 和 stderr 用独立异步任务并发排空，不再由 `wait_with_output()` 无界收集。
2. 每个 stream 使用 15 KiB 读取缓冲、32 KiB 尾部缓冲和不超过约 16 KiB 的
   UTF-8 校验暂存，排空阶段每 stream 不超过 64 KiB 内存。
3. 每个 stream 最多向匿名临时文件写入 8 MiB；单命令最多 16 MiB，同时采集槽最多 8 个。
   达到上限或临时文件失败后仍继续读取 pipe，不因停止读取造成子进程阻塞。
4. 命令终止后只读取有界临时内容，沿用 M2 的整段清洗，再原子发布安全文本。这样长凭据
   跨读取块时仍由完整规则处理，而不是用固定 overlap 猜边界。
5. 超过上限的原始尾部只记录“已排空但未保存”，不直接展示未与中间内容一起清洗的片段。
   首尾预览来自同一段已完整清洗并可恢复的安全文本。

临时落盘失败时，如果 32 KiB 尾部缓冲覆盖了全部输出，仍可安全清洗并展示；如果只覆盖
输出后段，则不展示这段不完整原文，只保留 partial、总量或 unknown 以及失败原因。

## 3. 状态与进程生命周期

命令启动后先开始排空，再发布 metadata-only 的 `running` 记录。正常结束后按真实
`ExitStatus` 写入退出码和 signal；非零退出与成功输出使用同一保存路径。

超时时先标记 `timed_out`，再沿用 SIGTERM、短暂等待、SIGKILL 的进程组清理，并等待
双流收尾后发布已捕获内容。`shell` 前台路径补齐了独立进程组，后台路径不受影响。

用户取消时，现有 drop guard 会先标记 `cancelled` 并终止进程组；独立采集任务继续排空、
释放 build-cache usage claim，并把部分安全输出登记到原 output ID。测试同时确认进程组
消失、取消状态可查询、取消前文本可恢复。

## 4. 展示与恢复

命令首次展示现在从已保存安全文本生成确定性的首尾片段：

- stdout/stderr 分别标注 stream 和 `[start,end)`；
- 中间缺口明确写出范围，并给出从首段末端继续的 `recall` 参数；
- `source_totals`、`capture`、`execution`、`success` 和存储范围都位于 8,192 字节总预算内；
- 历史 `recall` 仍按连续页读取，不把首尾片段误认为连续全文；
- 超过 8 MiB、临时落盘失败或最终账本写入失败时，状态分别保持 partial 或
  `store_failed`，不会生成虚假完整引用。

真实 stdio 的三个命令结果均显示两个 stdout 范围、完整短 stderr 和退出码 7。当前
stdio 尚未注册 `recall`，所以最终请求仍诚实标注 `recoverable=false`；这是 M5 的既定边界，
不影响 M4 已验证的存储与同进程恢复能力。

## 5. 验证结果

环境为 macOS 26.6.2，`rustc 1.98.1`、`cargo 1.98.1`。所有真实运行前均执行
`source ~/.zshrc`，stdio 场景设置 `OCTOS_DANGER_FULL_ACCESS=0`。

| 验证 | 结果 |
| --- | --- |
| M4 专项 | 7 passed：三入口、非零退出、超时、shell 孙进程、特殊路径不可恢复、存储失败、不重跑 |
| 共用采集层 | 4 passed：超 8 MiB、短 stderr、UTF-8 跨块、无效编码、临时落盘失败后继续排空 |
| 取消路径 | 1 passed：进程组退出、`cancelled` 持久状态、取消前输出可恢复 |
| M2 存储回归 | 18 passed |
| shell 回归 | 44 passed、1 ignored |
| M0-M3 回归 | 22 passed |
| workspace check / Clippy / fmt | 全部退出码 0 |

全量 `tools::coding_tools::tests` 为 88 passed、1 failed。唯一失败
`exec_session_captures_all_output_when_process_exits_at_deadline` 位于未修改的 TTY/yield
路径；该时序探针要求 40 次 5 ms 竞争至少一次正好观察到 completed，本机两次均只观察到
running，因而报告“test is vacuous”。相关 TTY 实现未改，M4 前台非 TTY、超时和取消专项
均通过。

真实 stdio：

- H03 on：5 次 provider 请求；文件加 `shell`、`bash`、`exec_command` 共 4 个结果。
  三个命令各执行一次，最终命令视图分别为 3,234 / 3,249 / 3,249 字节，均包含
  stdout 首尾、`UNIQUE_STDERR_FAILURE` 和退出码 7。
- H03 off：3 个基线场景全部通过；shell 副作用计数仍为 1，保留共同底座行为。
- 最终二进制 SHA-256：
  `bfa40155add6a5be418f94dbf3df3fbcc5b9266a327299b0813754d1e5b6c22c`。

完整命令与计数见 [checks.json](./m4-evidence/checks.json)。本阶段没有运行付费模型或
官方 ARC A/B，不对正确率和 token 收益作结论。

## 6. M5 起点

M5 从代码提交 `d7931fbc` 开始，重点是把现有持久 `recall` 注册到真实 stdio/solo，
并验证压缩、冷启动、审批继续和受限工具模式。M4 不扩大后台 shell、TTY/yield 或 MCP
的恢复承诺。
