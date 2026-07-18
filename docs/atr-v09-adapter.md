# ATR v0.9 / v1 投影边界

工作台是只读投影层，不是 ATR controller。它同时识别两类已审计的目录：

| 输入 | 展示内容 | 不会推断的内容 |
| --- | --- | --- |
| v1 `knowledge/frontier-map.json` + `evidence/sources.jsonl` | 领域、frontier 问题、概念、锚定来源与证据边界 | 空的 claims/edges/skill events 所代表的不存在内容 |
| v0.9 `run-state.json` + `intake.json` + `observability/skill-events.jsonl` | intake topic、active stage、状态、next action、gate 状态、已记录的 skill START/END 动作 | 没有 `knowledge/frontier-map.json` 时的研究问题、文献或知识层级 |

对 v0.9 run，`evidence/sources.jsonl` 为空会成为诊断信息，不能被页面中的领域标题误读为已有证据。新的 ATR run 应通过显式 `build --registry ...` 登记后才会出现在插件可选列表；controller 的 SQLite、事务和 lifecycle 仍是其自己的权威，本仓库不写入它们。
