# multilingual-aaai 历史对齐审计

这是一个只读审计，不是一次“把旧 run 升级为新 run”的批处理。历史目录保留为原始研究过程；每个后续 continuation 必须从经过审计的来源与历史断言重新开始。

运行：

```bash
python3 scripts/audit_historical_programs.py \
  programs/multilingual-programs.json \
  --out output/historical-program-alignment-audit.json
```

## 2026-07-18 基线

- 6 个研究计划、28 个历史 run 都被 catalog 覆盖；
- 28/28 有可解析的 `evidence/sources.jsonl`；
- 没有 JSON 级损坏；
- 这些 run 仍普遍缺少可作为**当前**研究链的 knowledge context、opportunity map、concept map 与 current claim ledger。

因此，审计将历史 source ledger、frontier map、claim history 和记录过程事件标记为可复用的 provenance input；它不会把 source 数量或旧 stage 当作“当前 claim 已经成立”的证据。每个 catalog disposition（`canonical_*`、`merge_as_*`、`retain_as_*`）都会在 JSON 里逐 run 输出，便于后续决定是新建 continuation、只保留为历史，还是因输入损坏而隔离。

首个 continuation `2026-07-18-multilingual-agent-action-continuation` 是该政策的示例：它不改写七个历史分支，而是导入来源、隔离历史 claim，并按新 artifact 逐步补充概念图、现实张力、景观简报和草案问题卡。
