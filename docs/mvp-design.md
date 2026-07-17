# MVP 设计：从 ATR 证据到可共同学习的研究工作台

## 用户路径

1. 研究者输入 topic 并由 ATR 建立 run；controller 仍是唯一可改变研究状态的系统。
2. 每一轮 worker 产生带来源的 artifact；工作台读取它们，更新“运行过程”投影。
3. 论文进入 Zotero collection；每篇都有一张阅读卡，包含证据边界、关联概念、相关问题和人工批注区域。
4. 研究者在 Zotero 中阅读、高亮、写自己的反驳/注解；后续同步器再把可选择的注释作为输入 evidence，而非把 AI 摘要当作研究结论。

## 两个彼此相连但不可混同的图

| 图 | 节点 | 边 | 目的 |
| --- | --- | --- | --- |
| 知识图谱 | 领域、概念、论文、可核查主张 | 定义/涉及/支持/限定 | 从前沿向基础概念展开，论文可反查 |
| 问题图谱 | 现实问题、研究张力、假说世界、论文 | 提出/遗留/约束/启发 | 将技术证据与研究品味、现实动机连接 |

MVP 先从已有 `frontier-map` 的 tensions 创建问题节点；每个问题都连到锚定文献，但 UI 标明“由 ATR map 提出，非论文自身结论”。后续版本会摄入新闻/技术博客等带 `source_kind` 的来源，并在 UI 中和学术证据分层显示。

## 数据权威与生命周期

- ATR v2: `atr.sqlite` + immutable artifact ID 是权威；工作台生成可重建 JSON/HTML 投影。
- 历史 v1: 目录是只读审计材料。本 MVP 兼容 `sources.jsonl` 与 `frontier-map.json`，并报告缺失的 claims/edges/observability。
- Zotero: Zotero 本身是书目、附件和人的批注权威。工作台不读取或写入本地 SQLite；写入只走显式配置的 Web API。

## MVP 验收标准

1. 给定已有 v1 run 能生成可打开的图谱与 Zotero 导入包。
2. 每个文献节点保留 URL、`source_id`、支持与不支持的边界。
3. 每个研究问题连接回具体的 `frontier_map` tension 和锚定 source IDs。
4. 不配置 key 时不能对 Zotero 产生任何写操作。
5. 有效 Web API key 时，以 collection + item + child note 的批次写入；响应写入同步审计日志。

## Zotero 插件交互（MVP 已实现）

插件在 Tools 菜单提供“打开 ATR Research Workbench”，在 Zotero 内的自定义 Tab 显示当前生成的图谱。它观察 note item 的新增/修改，把一份不可变的事件副本写入 `output/<run>/human-input/inbox.jsonl`。`review-human-input` 以 source ID 反查最靠近的研究问题，并产出交给 Codex/ATR owner 的更新报告；它不会自动转换 lifecycle 或覆盖既有线路。
