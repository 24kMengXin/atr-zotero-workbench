# ATR Zotero Research Workbench

把 ATR 研究运行中的可审计证据转成一个供研究者阅读、批注与讨论的知识/问题图谱，并以 Zotero 为文献与阅读批注的归档层。

当前代码仍是历史 run 的只读原型，**不是**最终的共同研究工作台。下一阶段以 [产品契约](docs/reframed-product-contract.md) 为准：最小单元将从“论文卡片”升级为带原文定位的可核查断言，并把人的结构化阅读判断送入 ATR 的显式复审流程。

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

要把新的 topic/run 加入插件可切换列表，在构建时显式登记它：

```bash
python -m atr_zotero_workbench build /path/to/atr-run \
  --out ./output/my-topic --registry ./output/runs.json \
  --run-key my-topic --label "我的研究主题"
```

工作台只显示这个 registry 中已登记的 run；它不会扫描或自动采纳未审计目录。

关于旧 v1 frontier 投影与当前 harness v0.9 lifecycle 投影的边界，见 [ATR adapter 说明](docs/atr-v09-adapter.md)。

`multilingual-aaai` 的 28 个历史 run 可先用 [历史对齐审计](docs/historical-alignment-audit.md) 全量清点；该脚本只报告可复用输入与缺失链路，不会修改旧目录。

打开终端显示的本地地址。点击节点可查看来源、证据边界和建议的人工阅读问题。

## Zotero 7 插件

构建 XPI：

```bash
./scripts/build_zotero_plugin.sh
```

日常开发不应重复安装 XPI。请先建立独立 Zotero profile，并使用源码侧载：

```bash
./scripts/link_zotero_dev.sh /absolute/path/to/a-development-profile /absolute/path/to/a-development-data-dir
```

完整的调试、验证与发布门禁见[插件开发守则](docs/zotero-plugin-development.md)；日常 profile 仅用于候选 XPI 的最终烟测。

在 Zotero 中选择「工具 → 插件 → 齿轮 → Install Add-on From File…」，选择
`dist/atr-zotero-workbench.xpi`，并确认启用。之后在「工具 → 打开 ATR Research Workbench」查看图谱。

修改 Zotero 中由本工具生成的阅读卡/笔记，会追加到
`output/multilingual/human-input/inbox.jsonl`。回到 Codex 后运行：

```bash
python -m atr_zotero_workbench review-human-input output/multilingual-agent-action-continuation --out output/multilingual-agent-action-continuation/human-input/impact-report.json
```

该命令还会追加 `human-input/review-queue.json`，并把每条显式的 Zotero 反馈物化为 `human-input/review-packets/HRP-*.json`。后者是供 ATR controller/owner 审查的不可变输入，包含 claim/source target、立场、原文定位和影响路径；它不会自动重写 ATR 结论、生命周期或历史图谱。

该命令以 `ATR source ID` 反查受影响的 research question、问题卡、断言与最近决策节点，并写入插件会读取的 `review-queue.json`。它只提出下一步审阅建议，绝不自动变更 ATR lifecycle 或删除旧路线。

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

若要把经人工核验的新闻、行业报告、技术博客或社媒观察接入某个研究问题，使用独立的 [现实世界灵感 ledger](docs/contextual-inspiration-ledger.md)；它始终和学术证据分层呈现。
