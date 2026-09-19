# H01 M7 预跑证据

本目录当前只包含 M7 运行器开发期间的结论外预跑，不包含正式 A/B/C
实验结果。正式实验尚未开始。

- `preflight-long` 的 A/B/C 摘要由旧版运行器生成。其 `valid=true`
  只表示观察到 compaction completed 事件，但这些事件全部是
  `rejected_no_safe_prefix`，没有安装压缩摘要，不能用于 H01 结论。
- `preflight-effective` 和 `preflight-shared` 已使用“必须实际安装压缩”
  的判定，均因 `no_installed_compaction` 无效。
- `preflight-full-clean` 使用全量预算并观察到 2 次已安装压缩，但被人工
  中断，generation 和 grading 均未完成，因此无效且没有测试时序。
- 其余仅有日志、没有结果摘要的运行也都在完成前中断。

当前运行器采用 ARC 全量默认上界，只按官方测试正确率、provider token
依次判定；时间不计入成绩。每个完成的官方测试仍记录
`started_at`、`ended_at` 和 `duration_ms` 供审计。
