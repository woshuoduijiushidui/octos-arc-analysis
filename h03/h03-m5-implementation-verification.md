# H03 M5 实现与验证：真实入口、压缩和冷启动恢复

## 1. 结论

- 状态：M5 已完成。
- 代码提交：`d85bd227597ed3de42a56f27267e94db828cb612`，仅本地提交，未推送。
- stdio/solo：模型可看到并调用 `recall`；同一 session 在进程退出后仍能恢复原输出。
- MCP：同一次调用内可恢复；不同调用使用不同 owner，明确不支持跨 invocation 恢复。
- 策略：全局工具策略、provider 策略和 stdio 最终白名单都能禁用 `recall`。禁用后不保存
  可恢复正文，也不在输出或压缩占位符中建议调用不存在的工具。

## 2. SessionRuntime 与真实 stdio

`SessionRuntime` 现在用文件读取状态的完整 owner 创建 `OutputState`：

- workspace 来自规范化工作区；
- task 与 logical session 都使用当前 session key；
- model branch 固定为根分支；
- 持久目录与该 session 的 transcript root 相同。

同一 session 的每个 AppUI/OUP turn 继续显式复用缓存中的同一个 `Arc<OutputState>`。
冷启动时相同 session 会重建出相同 owner，并重新打开磁盘索引；不同 session 的 task/session
维度不同，不能读取彼此输出。

`recall` 在 profile、全局策略和 stdio 白名单应用前注册。最终工具表允许它时才打开持久
存储。每 turn 动态注册 `spawn` 等工具后，stdio 会再次执行最终白名单，修复后台工具保留
规则绕过 `OCTOS_STDIO_SOLO_TOOLS` 的问题。

## 3. 压缩与 ContextManager

两条压缩路径都在替换工具结果时保留结构化字段：

- 原工具名、call ID、turn 和原始字节数；
- 可恢复时保留 `output_id`，以及 cursor 或 stream/offset；
- 不可恢复时保留 `recovery_tool_unavailable`；
- 旧版 v1 占位符缺少新字段时仍可正常反序列化。

恢复参数只从支持 H03 的工具结果读取，并校验 `recoverable=true`、头部与恢复参数中的
output ID 一致、ID 为 UUID、cursor 长度受限。压缩闭环测试使用占位符中的实际参数调用
持久 `recall`，成功取回被压缩掉的目标文本。

H03 开启时，session_actor 注册的 `recall` 优先走同一个 `OutputState/OutputStore`，
不会再把历史正文送回旧 50KB 固定页后再次截断。H03 关闭时旧账本行为保持不变。

## 4. MCP、子进程与安全边界

MCP 每次 `run_session` 创建 invocation-local owner 和存储句柄。测试证明：

- 同一次调用中，`read_file` 后的 `recall` 能恢复中间片段；
- 全局 deny 和 provider deny 都会从最终 schema 移除 `recall`；
- 下一次 invocation 即使复用 call ID，也只能得到 `source_incomplete`，不能读取前一次正文。

因此 M5 不宣称 MCP resume 或跨 invocation 冷恢复。spawn/pipeline 公共构造点保持编译兼容；
child 通过现有 `with_file_state` 获得自己的 branch owner，不继承父级读取凭据或父级
OutputStore。

`recall` 不接收文件路径，只读取 host 已绑定 owner 的受控账本。OutputStore 继续使用
no-follow 文件描述符、owner 校验、内容摘要和范围校验；错误返回 `owner_mismatch`、
`stale_source`、`out_of_range` 等明确状态，不请求放开任意目录。

## 5. 真实 stdio 验证

真实 `serve --stdio --solo` 使用 loopback fake provider，完整执行两次进程：

1. 首次 provider 请求故意返回 HTTP 500，运行时重试成功。
2. 同一批并行读取 `large.txt` 和 `parallel.txt`，两个结果都到达下一次 provider 请求。
3. `shell` 命中审批规则，客户端批准后继续；命令副作用计数为 1。
4. 同进程调用 `recall`，恢复 `STDIO_RECOVERY_SENTINEL`。
5. 关闭进程，以相同 session/profile/data 重新启动，再次调用 `recall`，恢复同一片段。
6. 单独以 `OCTOS_STDIO_SOLO_TOOLS=read_file` 启动，最终 schema 只有 `read_file`，
   输出为 `recoverable=false` 且不含 `recall` 参数。

最终二进制 SHA-256：
`d107092d882c5d7be33399a1506abf2262b4a92382e1544a8a2716f1dbf9ad4a`。
摘要见 [summary.json](./m5-evidence/summary.json)，完整请求、事件和持久索引位于
[m5-evidence](./m5-evidence/)。

## 6. 回归结果

环境为 macOS 26.6.2，`rustc/cargo 1.98.1`。真实运行前执行了 `source ~/.zshrc`。

| 验证 | 结果 |
| --- | --- |
| M0-M3 专项 | 22 passed |
| H03 存储、命令与冷恢复 | 23 passed |
| 压缩占位符与实际恢复闭环 | 4 passed |
| compaction policy | 12 passed |
| MCP 完整集成 | 18 passed |
| SessionRuntime / stdio profile | 各 1 passed |
| workspace check / Clippy / fmt | 全部退出码 0 |
| 真实 stdio M5 | 热恢复、冷恢复、审批、并行、重试、受限模式全部通过 |

`octos-cli --lib` 全量结果为 3,687 passed、8 failed、10 ignored。8 个失败均可独立复现且
不在本次变更：4 个是 macOS inherited-flock 时序基线，4 个因当前沙箱拒绝写
`~/.octos/cache/verified/` 的 skill 测试缓存。M5 相关 SessionRuntime、审批继续、压缩桥接、
重试和协议测试均通过。准确命令与结果见 [checks.json](./m5-evidence/checks.json)。

本阶段没有运行付费模型或官方 ARC A/B，不对正确率和 token 收益作结论。

## 7. M6 起点

M6 从代码提交 `d85bd227` 开始，重点补充恢复链指标、裁剪原因、调用次数和确定性回归，
不再扩大 M5 已冻结的入口范围。
