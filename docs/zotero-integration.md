# Zotero 集成决策记录

2026-07-18 的旧决定曾把产品分成“外部 workbench + 未来自定义 Tab”。该边界已经被真实阅读流程否定：研究者不应离开 Zotero 的 Library、Reader 与 Note，也不需要第二套论文浏览器。

## 当前采用的分层

- **ATR authority：** v2 SQLite controller 与 immutable artifacts 决定 lifecycle；`graph.json` 和 `zotero/native-projection.json` 都是可重建投影。
- **Zotero native projection：** topic → Collection 根；知识概念和研究问题节点 → 可折叠 Collection + 原生 Note；source → 可在多个节点 Collection 复用的原生条目/Reader tab；当前对象语义 → Item Pane section。
- **反馈桥：** 只接收带稳定 ATR marker 的 Note 和已映射来源的 Reader annotation，生成 review-only、append-only 的 human review packet；不能直接改变 lifecycle。
- **Web API：** 仍是明确授权后的可选批量同步通道，不是本地插件运行的前提。

自定义 ATR 内容 Tab、全屏 overlay 和外部 dashboard 均不再是主交互。完整方案比较与选择依据见[原生 Zotero 交互决策](native-zotero-interaction-decision.md)。插件不得直接读写 `zotero.sqlite`。

研究问题投影是“有证据的森林”而不是强制单树：现实张力、frontier question、problem、derived question 只有在 ATR graph 存在明确关系时才嵌套或传播反馈。历史版本保留独立 Note；marker 查找解析并比较完整 graph node ID，禁止用字符串前缀误合并版本。多个 ATR source ID 指向同一 DOI/URL/精确标题时复用一个 Zotero 条目，但每个 source ID tag 都必须保留。

参考：<https://zotero-chinese.com/plugin-dev-guide/>、<https://zotero-chinese.com/user-guide/plugins/better-notes>、<https://www.zotero.org/support/dev/client_coding/plugin_development>、<https://www.zotero.org/support/dev/web_api/v3/write_requests>。
