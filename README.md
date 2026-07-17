# ATR Zotero Research Workbench

把 ATR 研究运行中的可审计证据转成一个供研究者阅读、批注与讨论的知识/问题图谱，并以 Zotero 为文献与阅读批注的归档层。

## MVP（已实现）

- 只读导入旧式 ATR v1 run（`evidence/sources.jsonl`、`knowledge/frontier-map.json`、`run-state.json`）
- 输出浏览器内的交互图谱：流程阶段、概念、现实世界研究问题、文献证据以及它们的可追溯关系
- 导出 Zotero 可导入的 CSL-JSON；同时生成每篇文献的阅读提示 Markdown，明确区分“来源原话支持的内容”和“尚未解决的问题”
- 可选使用 Zotero Web API 创建 collection、文献和作为子笔记的阅读卡；没有写权限时绝不写 Zotero
- 含 ATR v2 适配器接口：v2 的 SQLite / immutable artifacts 是权威数据源，工作台只生成派生投影

## 快速开始

```bash
python -m atr_zotero_workbench build \
  /Users/zone/Documents/multilingual-aaai/research-runs/2026-07-17-controlled-multilingual-discovery \
  --out ./output/multilingual
python -m atr_zotero_workbench serve ./output/multilingual
```

打开终端显示的本地地址。点击节点可查看来源、证据边界和建议的人工阅读问题。

## Zotero 7 插件

构建 XPI：

```bash
./scripts/build_zotero_plugin.sh
```

在 Zotero 中选择「工具 → 插件 → 齿轮 → Install Add-on From File…」，选择
`dist/atr-zotero-workbench.xpi`，并确认启用。之后在「工具 → 打开 ATR Research Workbench」查看图谱。

修改 Zotero 中由本工具生成的阅读卡/笔记，会追加到
`output/multilingual/human-input/inbox.jsonl`。回到 Codex 后运行：

```bash
python -m atr_zotero_workbench review-human-input output/multilingual --out output/multilingual/human-input/impact-report.json
```

该命令以 `ATR source ID` 反查受影响的研究问题；它只提出下一步审阅建议，绝不自动变更 ATR lifecycle 或删除旧路线。

导入 `output/multilingual/zotero/items.csl.json` 到 Zotero；`reading-cards/` 中的文件是与每篇文献对应的人工阅读/注释起点。

如需写入 Zotero Web API（需要用户明确配置有写入权限的 API key）：

```bash
export ZOTERO_LIBRARY_TYPE=user
export ZOTERO_LIBRARY_ID=123456
export ZOTERO_API_KEY=... # 不写入仓库
python -m atr_zotero_workbench sync ./output/multilingual
```

## 设计原则

这不是另一个 ATR controller：它不改研究生命周期、不判定科学结论，也不直接读取/写入 Zotero 的本地 SQLite。每个图谱结点都有 `source_id`、文件路径或 ATR artifact ID；推断性问题显式标为 `research_question`，不会伪装成论文结论。

详见 [MVP 设计](docs/mvp-design.md)、[迁移审计](docs/legacy-run-audit.md) 和 [开发/插件调研](docs/zotero-integration.md)。
