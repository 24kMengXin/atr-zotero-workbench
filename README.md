# ATR Zotero Research Workbench

把 ATR topic 投影成 Zotero 原生 Collection、Reader tab、Note tab 与 Item Pane 上下文，让研究者在原生阅读/标注流程中核对证据并把反馈送回 ATR。

当前插件不再提供覆盖 Zotero 主界面的独立 dashboard。交互决策见[原生 Zotero 方案比较](docs/native-zotero-interaction-decision.md)：ATR 负责语义与 provenance，Zotero 原生对象负责阅读、标注和笔记。

## MVP（已实现）

- 把 topic 投影为 Zotero 原生 Collection 树：知识概念按显式 `specializes_concept` 嵌套；现实张力、前沿问题、当前问题卡、细粒度问题和待审查断言形成研究问题森林
- 每个知识/研究节点都有独立原生 Note，并在同一 Collection 中复用其显式关联文献；历史问题版本保留在「历史版本」，不会被当前版本覆盖
- 「Topic 与演化」中同时保留人的 Topic Note 与由真实 ATR timeline 生成的只读过程 Note；缺失历史不会被补造
- Item Pane 可直接选择 `支持 / 需要限定 / 反驳 / 尚不能判断 / 提出新问题`，判断写回对应原生 Note 后只进入 review inbox
- Note marker 精确指向 graph node；Reader annotation 先映射 source，再只沿显式 source-decision 边找到最近受影响对象，生成 review-only packet
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

## Zotero 9 插件

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
`dist/atr-zotero-workbench.xpi`，并确认启用。之后从「工具 → ATR Research」选择 topic。插件会定位对应的原生 Collection，并在 Note tab 打开 topic note；文献从 Collection 或右侧 ATR section 进入原生 Reader tab。

每次升级 XPI 都须在 Zotero 的「Install Add-on From File…」中重新选择该 XPI，然后**完全退出并重启 Zotero**；直接覆盖 profile 内的 `.xpi` 文件不会更新 Zotero 已注册的扩展版本。可在重启前后只读检查候选包和实际注册版本是否一致：

```bash
python3 scripts/check_installed_plugin_version.py \
  dist/atr-zotero-workbench.xpi \
  '/Users/zone/Library/Application Support/Zotero/Profiles/e1tzdljc.default'
```

同步、Reader/Note tab 打开和失败诊断会追加到该 workspace 的 `plugin-runtime.jsonl`。

修改 Zotero 中由本工具生成的阅读卡/笔记，会追加到
`output/multilingual/human-input/inbox.jsonl`。回到 Codex 后运行：

```bash
python -m atr_zotero_workbench review-human-input output/multilingual-agent-action-continuation --out output/multilingual-agent-action-continuation/human-input/impact-report.json
```

该命令还会追加 `human-input/review-queue.json`，并把每条显式的 Zotero 反馈物化为 `human-input/review-packets/HRP-*.json`。后者是供 ATR controller/owner 审查的不可变输入，包含 claim/source target、立场、原文定位和影响路径；它不会自动重写 ATR 结论、生命周期或历史图谱。

该命令以 `ATR source ID` 反查受影响的 research question、问题卡、断言与最近决策节点，并写入插件会读取的 `review-queue.json`。它只提出下一步审阅建议，绝不自动变更 ATR lifecycle 或删除旧路线。

从插件中首次为某篇来源“建立 / 打开我的阅读笔记”时，插件会把该条目加入本 run 的 `ATR · <run id>` collection。它以 `atr-source-id:<ID>` tag 查重；已有条目只会被**加入**该 collection，不会移动、删除或覆盖你的字段和笔记。

由研究 owner 读完 packet 后，才可记录一次不可变的处置；这会把“需要复审什么”追加回 ATR run，并在下一次构建时显示在图中：

```bash
python -m atr_zotero_workbench record-review-disposition \
  output/multilingual-agent-action-continuation \
  --run-dir /path/to/atr-run \
  --packet HRP-... --disposition OPEN_ROUTE_REVIEW \
  --rationale "说明具体哪一处原文定位改变了什么解释" --owner "researcher"
```

允许的处置仅为接受为复审输入、要求澄清、开启 claim/route review 或不改变 lifecycle。该命令不会替代 ATR controller 记录后续的 route/gate 决定。

对于 ATR v2 run，只有已记录且哈希匹配的 `OPEN_CLAIM_REVIEW`、`OPEN_ROUTE_REVIEW` 或 `ACCEPT_AS_REVIEW_INPUT` disposition 才能显式 attach 到当前 subject。该步骤把 packet 注册为内容寻址 artifact，并返回距离 root 最近的受影响对象；它不改变 subject 的 stage 或 version：

```bash
python -m atr_zotero_workbench attach-review-to-v2 \
  output/multilingual-agent-action-continuation \
  --v2-run-dir /path/to/v2-run \
  --disposition-ledger /path/to/legacy-run/decisions/human-review-dispositions.jsonl \
  --packet HRP-... --subject topic-1 --expected-version 3 \
  --atrctl /path/to/auto-research-harness/v2/atrctl.py
```

接着由研究 owner 基于这份 attachment 单独作者化 review artifact；只有该 artifact 满足 v2 transition 的类型契约时，`atrctl transition` 才可能变更 lifecycle。

独立 reviewer 完成人的反馈复核后，用单独作者化的
`human-review-assessment` 记录“保留哪些对象、重审哪些对象、还需哪类
artifact”，再交给 v2：

```bash
python -m atr_zotero_workbench attach-review-assessment-to-v2 \
  output/current-topic \
  --v2-run-dir /path/to/v2-run \
  --assessment /path/to/human-review-assessment.json \
  --subject SUBJECT --expected-version N \
  --atrctl /path/to/auto-research-harness/v2/atrctl.py
```

assessment 仍不改变 lifecycle。插件把它显示为
`03 · 研究问题与断言/05 · 共创复核` 下的原生只读 Note，并提供回到被保留
来源或待重写问题节点的按钮。旧节点、旧边和旧文献不会因复核而移走。

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
