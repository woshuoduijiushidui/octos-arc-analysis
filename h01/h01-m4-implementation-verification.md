# H01 M4 实现与验证：长日志外置与引用

- 日期：2026-09-19
- 分支：`feat/h01-evidence-capsule`
- 基线：M3 commit `d11861b8`
- 状态：完成，未推送远端

## 实现边界

M4 没有新增通用工具日志仓库。Octos 工具输出继续使用现有
`ToolOutputEnvelope.raw_artifact_ref/raw_sha256`、context ledger sidecar 和
`recall(tool_call_id)`。本次只为 ARC acceptance 结果增加任务域内的证据文件：

- 失败或基础设施错误的完整 `RunSummary` 原子写入
  `.arc/evidence/<run_id>.json`。
- 同一 run 的所有 active failures 共用一个 artifact 引用。
- run ID 在新进程中重用且内容不同时，使用
  `.arc/evidence/<run_id>-<sha256>.json`，避免破坏旧 capsule 的引用。
- capsule 只保存有界失败摘要、`artifact_ref`、`artifact_sha256` 和
  `artifact_bytes`，不保存完整 message、stdout 或 browser diagnostics。
- artifact 写入后立即校验存在性、字节数和 SHA-256；capsule 持久化前再次校验。
- 冷启动 replay 读取 capsule 时再次校验引用。缺失、越界、元数据不完整或内容
  被篡改时拒绝加载，不把引用标成可恢复。

完整 artifact 默认不会进入模型输入。模型只看到引用元数据；需要原文时继续显式
调用现有 `read_file`。工具输出本身仍通过既有 `recall` 恢复。

## 代码落点

- `arc/task_evidence.py`
  - 增加 acceptance evidence v1 稳定序列化和原子写入。
  - 增加引用路径、长度、SHA-256 和 replay 校验。
  - 对 failure 的 title/location/status/expected/actual 做 UTF-8 字节级有界化。
- `arc/tests/test_task_evidence.py`
  - 覆盖 artifact 存在、缺失、哈希不一致、超长 UTF-8、共享引用、replay
    和 run ID 重用。
- `crates/octos-cli/src/api/context_manager.rs`
  - 验证 task evidence prompt 只渲染 artifact 元数据。
- `crates/octos-agent/src/tools/read_file.rs`
  - 验证显式 `read_file` 可读取工作区内 `.arc/evidence` 文件。

## 验收场景

| 场景 | 结果 |
| --- | --- |
| artifact 写入后存在，hash/bytes 与文件一致 | 通过 |
| replay 时 artifact 缺失 | 明确拒绝 |
| replay 时 artifact 内容被篡改 | 明确拒绝 |
| 超长 UTF-8 message/stdout/action errors | 原文完整外置，capsule 保持有界 |
| 同一 run 多个失败 | 共用一个引用 |
| 冷启动 replay | capsule 字节稳定，引用重新校验 |
| 默认 prompt | 仅包含 ref/hash/bytes，不展开原文 |
| 显式恢复 | 现有 `read_file` 可读取 artifact |

## 验证结果

- `PYTHONPATH=arc python3 -m unittest arc.tests.test_task_evidence arc.tests.test_octos_stdio`
  - 20 passed。
- `PYTHONPATH=arc python3 -m unittest discover -s arc/tests -t .`
  - 共运行 202 项；除已知 Python 3.9
    `tarfile.TarFile.extract(..., filter="data")` 兼容性错误外通过，5 skipped。
- `cargo test -p octos-core --lib ui_protocol`
  - 165 passed。
- `cargo test -p octos-cli --lib context_manager::tests`
  - 101 passed。
- `cargo test -p octos-agent --lib tools::read_file::tests`
  - 51 passed。
- `cargo test -p octos-agent --lib compaction`
  - 66 passed。
- `cargo fmt --all -- --check`
  - 通过。
- `git diff --check`
  - 通过。

未修改官方 requirements 或 acceptance spec，未增加模型调用。
