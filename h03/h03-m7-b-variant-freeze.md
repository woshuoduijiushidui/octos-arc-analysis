# H03 M7 完整 B 冻结：有界输出搜索

## 1. 冻结结论

- 状态：M7 已完成，H03 完整 B 已冻结。
- 共同底座：`A_SHA=9d65681c3ef0c2b699e2fc68bbaac1d8b0d71cf1`。
- M6 起点：`fbcfd6b85214fa12316303f16599dbb3a97437ce`。
- 完整 B：`B_SHA=4c542e534e957d69a5ee05d24ffb7e166beb78bb`。
- 分支：`feat/output-recovery`；仅本地提交，未推送。
- 最终二进制 SHA-256：
  `9061d50af703fdccd43960538de4f9864f86fabc714a8e45f341e930495aafe4`。

完整 B 包含 M1-M6 的真实范围、8 KiB 分页、持久恢复、命令输出采集、真实入口和观测，
以及本阶段新增的输出内有界字面量搜索。没有增加第三组实验分支、语义索引、新 agent、
更大页面或新的模型调用。

## 2. 搜索合同

搜索复用 `recall` 工具。启用 `OCTOS_OUTPUT_RECOVERY` 后：

- 普通恢复继续使用 `output_id/stream/offset/limit/cursor/page`；
- 搜索使用 `output_id + query`，可选 `stream/offset/max_matches`；
- `query` 是大小写敏感的字面量，不执行正则；
- 搜索必须使用合法 output ID，不接受旧 `tool_call_id`，owner 校验与恢复完全相同；
- 返回绝对字节位置和有界安全片段，模型再用原有 offset/limit 读取目标位置；
- 搜索结果不保存成新 artifact，也不重新执行来源命令。

冻结参数：

| 参数 | 值 |
| --- | --- |
| 单次扫描 | 1 MiB |
| query | 最多 256 个 Unicode 字符、1,024 UTF-8 字节 |
| 每次匹配 | 默认及最大 8 个 |
| 每个片段 | 最多 64 字节 |
| 搜索结果 | 最多 7,680 字节，为 hook 留出 512 字节 |
| 普通恢复页 | 8,192 字节，保持 M6 不变 |

搜索以 UTF-8 字符边界推进，并额外读取最多一个 query 的重叠区，因此跨 64 KiB 存储块和
1 MiB 扫描窗口的匹配不会丢失。达到扫描上限时返回 `scan_limit + next_offset`；达到匹配
上限时，next 指向第一个尚未返回的匹配。匹配位置允许重叠，不会因前一个匹配跳过后一个。

结果同时区分：

- `stored_search_complete`：已保存范围是否全部扫描；
- `artifact_complete`：来源是否完整保存；
- `search_complete`：两者都成立时才为 true；
- `incomplete_reason`：`scan_limit/match_limit/artifact_pending/artifact_partial`。

因此 partial artifact 即使已扫完所有保存字节，也不会宣称整个源输出无匹配。运行中或取消
的搜索只读已发布、安全化后的 artifact；单次工作固定有界，取消不会修改索引。

## 3. 安全、入口与成本

OutputStore 保存前已对整份输出执行清洗，搜索只读取这份模型安全文本，不接触审计原文。
测试证明原始凭据无法命中或出现在搜索结果中。不同 workspace/task/session/branch 的 owner
不能搜索彼此 output ID。

搜索结果是小型 JSON，不走普通恢复页的二次持久化；最终 prompt 会原样保留该结果并计入
现有上下文预算。H02 仍只接受最终可见的 `read_file` 来源，搜索和历史恢复不会产生当前
文件读取凭据。

stdio/solo 开启 H03 时最终 `recall` schema 包含 `query/max_matches`。关闭 H03 时
`recall` 不出现，搜索也不可用。MCP 同 invocation 的 `recall` schema 已验证包含搜索字段，
并继续复用 M5 的 invocation-local owner；跨 invocation 不共享 artifact。

按项目 `estimate_tool_tokens` 同等算法计算：

- M6 `recall` 工具声明：156 estimated tokens；
- M7 完整 `recall` 工具声明：243 estimated tokens；
- 搜索新增成本：87 estimated input tokens；
- 工具数量不变，没有新增一整份工具声明。

## 4. T25-T28

| ID | 证据 | 结果 |
| --- | --- | --- |
| T25 | `h03_m7_literal_search_finds_multiple_and_cross_block_matches` | 完整无匹配、多匹配、重叠匹配和跨块位置正确 |
| T26 | `h03_m7_search_limits_resume_without_skipping_and_partial_stays_explicit`、`h03_m7_cancelled_search_is_bounded_and_does_not_change_the_artifact` | scan/match/snippet/result 均有界；next 不跳过；partial 和取消不伪称完整 |
| T27 | `h03_m7_search_rejects_invalid_and_foreign_requests_and_uses_safe_text` | 非法组合、越权和原始密钥查询失败；只搜索安全文本 |
| T28 | `h03_m7_search_then_recall_reaches_the_final_provider_without_new_artifacts`、真实 stdio 搜索 | 最终 provider 收到位置并取回目标；artifact 仍 1 条，命令仍执行 1 次；H03 off 无搜索 |

T01-T24 沿用 M6 的测试映射，并在最终 B 上重新执行 H03、H02、ContextManager、OUP、
shell、压缩和 MCP 回归。M7 没有改变页预算、持久格式、命令执行或 H02 授权语义。

## 5. 联合回归

环境为 macOS 26.6.2 arm64，`rustc/cargo 1.96.1`、系统 Python 3.9.6。真实运行前执行
`source ~/.zshrc`，Rust 命令显式使用项目固定工具链。

| 验证 | 结果 |
| --- | --- |
| H03 存储、命令、观测和搜索 | 33 passed |
| M0-M3 + M7 最终 provider | 23 passed |
| H02 M1-M3 | 19 passed |
| ContextManager | 101 passed |
| OUP | 47 passed |
| shell / command capture / recall | 44 / 4 / 6 passed；shell 1 ignored |
| 压缩 policy 与恢复占位符 | 16 passed |
| MCP 完整集成 | 18 passed |
| read_file / read_window | 57 / 16 passed |
| model receipts / file state | 17 / 14 passed |
| workspace check / Clippy / fmt / Python 编译 / diff | 全部退出码 0 |
| ARC Python 外层 | 408 ran；399 passed、8 skipped、1 error |

ARC Python 唯一错误来自系统 Python 3.9 不支持
`tarfile.extract(filter=...)`，位置是未修改的 `arc/main.py:562`。实施清单已预先记录这项
环境基线；本阶段没有修改或跳过该测试。Clippy 只沿用既有 `serve.rs`
`nonminimal_bool` 豁免。

准确命令、数量和退出码见 [checks.json](./m7-evidence/checks.json)。

## 6. 真实 stdio

同一最终二进制执行两套 loopback fake provider 场景：

1. [恢复回归摘要](./m7-evidence/recovery-regression/summary.json)：热恢复、冷恢复、审批、
   并行结果、一次 provider 重试和受限工具模式全部通过；副作用命令执行 1 次。
2. [搜索摘要](./m7-evidence/search-contract/summary.json)：初始首尾预览不含日志中部目标，
   搜索定位到绝对偏移 16,000，随后按位置恢复目标；搜索和恢复后持久索引仍只有原命令
   artifact，命令执行 1 次。H03 关闭时最终 schema 不含搜索。

两套脚本均退出码 0。恢复脚本 PASS 后宿主沙箱仍会额外打印一次已知的进程启动提示，但
没有影响脚本断言、摘要或退出码。

## 7. 差异审查与下一阶段

`A_SHA..B_SHA` 只包含 H02 必要底座、H03 实现、测试和本地验证脚本；没有修改官方需求、
官方测试、模板、评分器、模型参数或任务预算。M7 相对 M6 仅修改搜索相关实现和测试。

代码提交钩子在提交对象创建后因沙箱拒绝写
`~/.bytesec/commit_hook/commit_result.json` 返回非零；`B_SHA` 已核对存在，代码工作树
干净。未禁用钩子，未推送远程。

本阶段没有运行付费模型或官方任务 A/B，因此只冻结确定性通过的完整 B，不对正确率和
全任务 token 收益作结论。M8 可从该 `B_SHA` 开始固定官方输入并执行 A/B 对照。
