# `2026-07-17-controlled-multilingual-discovery` 审计

导入对象是旧式 v1 run，而非 ATR v2 run。它声明运行于 `R2_FOCUSED_REVIEW`，没有 active seed，所有 gates 仍为 `PENDING`。可用材料包括：24 条带 URL 的 `evidence/sources.jsonl` 来源，以及 `knowledge/frontier-map.json` 中两条可追溯的 frontier tensions。

缺口：`evidence/claims.jsonl`、`evidence/edges.jsonl`、`observability/skill-events.jsonl` 均为空。因此 MVP 不捏造 worker history 或论文结论：图中“evidence-boundary”节点直接来自 `supports` / `does_not_support` 字段；研究问题直接来自 `frontier-map` 的 question。图谱输出的诊断会保留这些缺口，供后续 ATR v2 artifact adapter 补齐。

迁移策略是读旧产物、构造派生投影；不把旧 run 伪装迁移成 v2，也不修改其 `run-state.json`。
