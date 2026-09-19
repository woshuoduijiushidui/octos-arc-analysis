# Octos ARC Harness 分析

本仓库记录对 [woshuoduijiushidui/octos-arc](https://github.com/woshuoduijiushidui/octos-arc) 的流程梳理、Harness 优化方向和逐项竞品调研。

当前分析基线：`octos-arc@c599d18c5acd2b846f049ffea2be84e72fe60fac`。

## 文档索引

- [仓库与生成链路导读](./repository-walkthrough-zh.md)
- [Harness 优化分析](./harness-optimization-zh.md)
- [Harness 优化点总表](./harness-optimization-table.md)
- [H01 竞品调研：保留关键上下文证据](./h01-context-evidence-competitor-research.md)
- [H01 实施 Milestone：任务证据胶囊与三臂对照实验](./h01-implementation-milestone.md)
- [Windows Python 单元测试原始日志](./python-unittest-windows.log)

优化目标按优先级排列：

1. 通过更多官方测试用例；
2. 在通过表现不下降的前提下减少总 token；
3. 使用固定需求、固定官方测试和可复现实验验证收益。

`test-temp/` 是本地测试产生的临时目录，不属于分析成果，已通过 `.gitignore` 排除。
