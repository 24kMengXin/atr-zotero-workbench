# 现实世界灵感 ledger

`evidence/contextual-sources.jsonl` 是可选的、逐行 JSON 的来源账本。它用于把新闻、技术博客、政策/行业报告、杂志或经过人工核验的社媒观察连接到 ATR 的**研究问题**，但绝不把它们升级为学术证据。

每行至少应有 `source_id`、`title`、`url`、`kind`、`supports`、`does_not_support`、`why_it_matters` 和 `related_tension_ids`（数组）。例如：

```json
{"source_id":"CTX-001","title":"已核验的部署报告","url":"https://example.org/report","kind":"REPORT","supports":"真实部署中存在的观察","does_not_support":"任何因果或学术结论","why_it_matters":"说明某个 frontier tension 在现实环境中的摩擦","related_tension_ids":["FT-EXAMPLE"]}
```

构建器会强制将该文件的条目标为 `contextual_inspiration`，并只生成 `inspired_by_context` 边。工作台会以“现实世界启发（不是学术证据）”单独呈现；空 ledger 保持为空，不会自动搜索或编造材料。
