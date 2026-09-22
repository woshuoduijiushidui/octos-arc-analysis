# H03 M3：文件分页与最终读取凭据

- 日期：2026-09-21。
- 分支：两个仓库均为 `feat/output-recovery`，继续 M0 冻结底座。
- `MAIN_SHA=27d057c206c0f8250b60309905737f7e26ee0ba9`。
- `A_SHA=9d65681c3ef0c2b699e2fc68bbaac1d8b0d71cf1`。
- M2 代码提交：`d6f8198ea4005d24db7ba240321c264872f777c9`。
- M3 代码提交：`2ced3def863a895c740559a891e2d256f2e13edf`，仅本地提交，未推送。
- 状态：M3 已完成；命令首次截断前采集属于 M4，stdio 持久 recall 注册与冷恢复入口属于 M5。

## 1. 本阶段完成的行为

H03 开启时，`read_file` 无论 `OCTOS_READ_WINDOW` 是否开启，都先从同一个 no-follow
文件描述符读取正文、元数据和 SHA-256 强版本，再由 M1 的统一 8,192 字节渲染器生成
最终文件页。无范围大文件直接返回第一页；显式行范围大于当前页预算时只显示实际装得下
的连续子范围，不再让模型按原始 `offset + limit` 猜测下一页。

每个非终止文件页增加：

```json
{
  "read_file_next": {
    "same_path": true,
    "arguments": {
      "offset": 220,
      "end_line": 3029,
      "source_sha256": "sha256:..."
    }
  }
}
```

调用方沿用上一条工具调用的 path，并合并 `arguments`。行模式从最终可见末行的下一行
继续；如果下一行本身超过页面预算，则自动切换为 `byte_offset`，从真实 UTF-8 字节末端
继续。显式 `end_line/limit` 会转换为固定 `end_line`，显式 `byte_limit` 会随剩余范围
递减，因此后续页不会越过最初选择范围。

`source_sha256` 是前一页读取到的强内容版本。后续调用重新做稳定读取并比较摘要；文件即使
保持相同大小并恢复原 mtime，只要正文改变就返回 `stale_source`，不会把两个版本拼接。
不带版本参数表示主动开始一个新读取。H03 关闭时该参数不可用，原工具 schema 与输出保持
共同底座行为。

## 2. 最终请求与 H02 凭据

文件版本、调用请求范围和选择边界以 `FileReadEvidence` 保存在运行时 typed 来源中，
不从工具正文 JSON 反解析。工具执行、hook、ContextManager 投影和最终 Agent 预算检查
完成后，`call_llm_with_hooks_mode` 才读取最终 messages：

1. 按 assistant tool call 与 tool result 的实际顺序配对。
2. 同时核对规范化 call ID、参数摘要、最终正文摘要和当前 `OutputView`。
3. 从最终 `visible_ranges` 生成 H02 `FileView::Lines/Bytes/Full`。
4. 将该候选交给现有 `prepare_dispatch`；只有真实主模型返回非空成功响应后才激活。

因此，初始请求范围 30–3029 行如果最终只看见 30–219 行，H02 只登记 30–219。
30–219 内的相同/子范围可以返回 `[FILE_UNCHANGED]`，第 220 行及后续范围必须重新读取。
最终页因上下文压力从 8 KiB 收紧到 1,300 字节时，候选随最终页重建；旧投影不会继续授权。

provider 失败、取消、before-LLM 拒绝和 silent 内部调用不会激活候选。ContextManager
替换、压缩或删除工具结果时沿用 H02 现有清理逻辑。恢复历史 artifact 的 `recall` 记录
没有 `FileReadEvidence`，且工具名不是 `read_file`，不会成为当前文件凭据。

如果解码或 `sanitize_tool_output` 改变文件正文，视图改用 safe-text 坐标并标记
`loss=source_transformed`；不生成 raw `read_file_next`，也不登记 H02 候选。合法 owner、
强版本和可见范围三者缺一时均保守返回正文或明确错误，不产生缓存命中。

## 3. 范围和边界

| 场景 | 结果 |
| --- | --- |
| 行页 | 1-based、首末行包含；next 为最终可见末行 + 1 |
| 字节页 | 0-based `[start,end)`；起点和终点必须是 UTF-8 边界 |
| 超长行 | 当前页装不下一整行时返回字节页，下一页从实际字节末端继续 |
| 显式行范围 | 后续页保留原选择的实际 `end_line` |
| 显式字节范围 | 后续页的 `byte_limit` 等于选择终点减当前实际末端 |
| 空文件 | 空正文、无伪造 `1-0` 范围，状态为 EOF |
| 范围结束 | `selection_end`，不冒充整个文件 EOF |
| 文件结束 | `eof`，不再生成下一页参数 |
| 文件变化 | `stale_source`，要求不带旧版本重新开始 |
| 变换/清洗 | safe-text 坐标；无 raw 文件续读或 H02 授权 |

每次直接读取新页都会分配新的 output ID，即使 provider 重复使用同一 call ID。
M2 `recall` 同一 artifact 的分页仍保持原 output ID，两类身份不会混淆。

## 4. 实际入口

| 位置 | M3 行为 |
| --- | --- |
| `tools/read_file.rs` | 统一 H03 行/字节选择、强版本校验、选择边界和 typed 文件证据 |
| `output_recovery.rs` | 从最终可见范围生成 `read_file_next`，按最终 digest 登记 H02 候选 |
| `agent/llm_call.rs` | 在真正 provider 请求成形后登记候选，成功响应后沿用 H02 激活 |
| `ContextManager` / AppUI bridge | 继续用 M1 typed 重渲染；最终范围、digest 和持久 envelope 同步 |

ARC `serve --stdio --solo` 已实际验证文件页和版本化 next 到达 fake provider。
该入口尚未注册持久 `recall`，因此仍诚实显示 `recoverable=false`；M5 接通后才同时提供
直接读当前文件和读取历史 artifact 两条路径。MCP、spawn 和跨进程工具策略也仍按 M5
边界处理。

## 5. 验证记录

环境为 macOS 26.6.2，`rustc/cargo 1.96.1`。Rust 回归固定
`OCTOS_OUTPUT_RECOVERY=0`，M3 测试显式注入开启 policy；另用
`OCTOS_OUTPUT_RECOVERY=1` 独立复跑 M3 集成套件。所有命令前执行：

```bash
source ~/.zshrc
export PATH="$HOME/.rustup/toolchains/1.96.1-aarch64-apple-darwin/bin:$PATH"
```

| 验证 | 结果 |
| --- | --- |
| `h03_m3_file_pages` | 6 passed；最终 provider 分页、1,300 字节压力、长行、显式范围、stale、H02 成功/失败和清洗 |
| `tools::read_file::tests` | 57 passed；包含 H03 × read-window × dedup 四组合及版本参数拒绝 |
| M2 存储与 Agent recall | 16 / 1 passed |
| M1 / M0 | 13 / 2 passed |
| H02 M1–M3 | 3 / 12 / 4 passed |
| llm_call / compaction / loop_compaction | 11 / 2 / 6 passed |
| read_window / mutation_guard / nofollow / write_file | 16 / 2 / 19 / 48 passed |
| model_read_receipts / file_state_cache | 17 / 14 passed |
| M8 end-to-end gate | 2 passed |
| ContextManager / SessionActor bridge / H02 stdio+MCP wiring | 101 / 3 / 2 passed |
| `cargo check --workspace --tests` | 退出码 0 |
| `cargo fmt --all -- --check` | 退出码 0 |
| Clippy（agent/cli 全 targets） | 仅沿用 M1 已确认的 `nonminimal_bool` 基线豁免后退出码 0 |

不同测试函数只计一次，聚焦回归合计 **357 passed、0 failed、0 ignored**。
准确命令和计数见 [checks.json](./m3-evidence/checks.json)。

真实 stdio 使用最终源码构建的 `target/debug/octos`，SHA-256 为
`0033bfd085c272960c986a0289cd9dabd7be1ac473565298e124484a6f63b918`：

- H03 on：本机 fake provider 共 5 个请求；文件请求 30–3029 行最终收到 8,183 字节、
  行 30–219、源字节 `[948,7338)`，next 精确为 offset 220、end_line 3029，并绑定
  `sha256:4d4fbc409a5ced6c094c5f6b8a44691d1f2d3a06626829114fd2e84578b63a68`。
- H03 off：3 个基线场景、7 个请求全部通过，继续复现原 8,204 字节输出和旧截断行为。
- 两次 stdio 都设置 `OCTOS_DANGER_FULL_ACCESS=0`；没有审批事件，也没有放宽沙箱。

本阶段没有运行付费模型或官方 ARC A/B，不对正确率和 token 收益作结论。

## 6. 提交

代码提交 `2ced3def`，共 8 个文件。提交前后均核对格式、差异和工作树。
提交钩子在提交成功后因沙箱拒绝写入 `~/.bytesec/commit_hook/commit_result.json`
而返回非零状态；实际提交对象存在，没有禁用钩子或重复提交。
分析文档、清单和检查摘要在分析仓库单独本地提交，不推送。
