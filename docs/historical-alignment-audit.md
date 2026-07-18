# multilingual-aaai 历史对齐审计

这是一个只读审计，不是一次“把旧 run 升级为新 run”的批处理。历史目录保留为原始研究过程；每个后续 continuation 必须从经过审计的来源与历史断言重新开始。

运行：

```bash
python3 scripts/audit_historical_programs.py \
  programs/multilingual-programs.json \
  --harness-root /Users/zone/Documents/multilingual-aaai/auto-research-harness \
  --legacy-mapping-index /Users/zone/Documents/multilingual-aaai/alignment/legacy-mapped-v1/legacy-mapping-index.json \
  --out output/historical-program-alignment-audit.json \
  --markdown-out docs/historical-program-disposition-matrix.md
```

## 2026-07-19 深化审计

- 6 个研究计划、28 个历史 run 都被 catalog 覆盖；
- 28/28 有可解析的 `evidence/sources.jsonl`，并通过当前 checker 的结构/引用检查；
- 391 条来源记录只形成 358 个唯一 source ID、326 个唯一 URL 和 352 个唯一标题；进入 Zotero 前必须去重；
- 0/391 声明 access status，0/391 记录带 locator 的全文检查；它们不能被表述为“全文已下载或已读”；
- 28/28 个 run 的当前消费路径均有逐项 `LEGACY_MAPPED` sidecar；164 个 sidecar 覆盖 run snapshot、state、source/claim/edge ledger、实际读取的 frontier/knowledge/opportunity/problem/process artifact；
- 历史 28 个 run 中没有 `concept-map.json` 或 `research-problem-cards/*.json`。现有 frontier、knowledge context、opportunity 与少量 claim 都只能作为历史输入。

因此，28 个 run 仍全部归为 `LEGACY_MAP_INPUT_ONLY`。sidecar 关闭的是“当前到底消费了哪些历史字节”的谱系缺口，不会关闭 source access/fulltext、语义复核或 lifecycle 缺口。这不是删除历史，而是把旧 stage、gate、claim 和 route 从 current 权威中清退。逐 run 的 artifact disposition、source/fulltext 缺口和六个 program 的弹性骨架见 [历史归位矩阵](historical-program-disposition-matrix.md)。

该矩阵已经驱动一个新的 v2 portfolio 与六个独立 child run。它们全部停在 `INTAKE`/version 0，只附加 portfolio/program intake、审计边界、legacy branch index、metadata-only source queue 和 portfolio route-map；没有继承任何旧 stage 或 PASS。route-map 把 6 个 program 与 28 条历史 branch 作为只读导航谱系集中落盘，供 Zotero 全局折叠图使用，不构成 lifecycle transition。对应定义保存在 `programs/v2-intakes/`，可由 `scripts/bootstrap_multilingual_v2_portfolio.py` 与 `scripts/attach_portfolio_route_map.py` 重放和检查。

下一层的跨 run 去重与 Zotero 获取状态见 [来源归并与获取队列](source-inventory-and-zotero-acquisition.md)。391 个 occurrence 已无损归并为 344 个 canonical source；每个 program 的队列已作为 metadata-only attachment 进入其 v2 child version 0。

首个 continuation `2026-07-18-multilingual-agent-action-continuation` 是该政策的示例：它不改写七个历史分支，而是导入来源、隔离历史 claim，并按新 artifact 逐步补充概念图、现实张力、景观简报和草案问题卡。
