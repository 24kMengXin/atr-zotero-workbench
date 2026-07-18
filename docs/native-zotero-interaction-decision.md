# ATR × Zotero 原生交互方案与决策

## 要解决的真实任务

插件的主路径不是“查看一个 ATR 仪表盘”，而是：

1. 从一个研究 topic 进入待核对来源；
2. 在 Zotero 原生 Reader 标签中阅读、跳转和标注 PDF；
3. 在 Zotero 原生 Note 标签或 Reader 右侧笔记区继续写判断；
4. 把明确属于该 topic/source/claim 的 Note 与 annotation 变更送回 ATR 人工复审 inbox；
5. 保留 Zotero 条目、附件、标注和笔记作为人的工作空间，ATR 投影只提供语义和 provenance。

因此，覆盖 `zotero-pane-stack` 的独立工作台不是一个可继续修补的界面问题，而是错误的产品边界。

## 候选方案

### A. 自定义 ATR 标签页

在 Zotero 标签栏新增一种 ATR tab，在其中展示 topic、问题、来源和状态；点击来源再打开 Reader tab。

- 优点：研究结构能完整显示，导航自由度高。
- 缺点：仍然创造第二套内容浏览器；会与 Library、Reader、Note 三套原生心智模型竞争；插件还要自行维护 tab 生命周期、菜单状态、可访问性和布局。
- 结论：不采用。它比旧 overlay 好，但没有修正“ATR 自己拥有主界面”的根本问题。

### B. Reader-first 侧栏

只在 Reader 的右侧 Item Pane 注册 ATR section；从当前 PDF 查看问题、证据边界和关联来源。

- 优点：阅读时上下文最贴近原文；适合来源级核对；与 Translate for Zotero 一类插件的交互位置一致。
- 缺点：没有打开 PDF 时缺少 topic 入口；跨来源队列和研究 Note 不自然；无法单独承担 topic 导航。
- 结论：作为局部组件采用，不能单独成为完整方案。

### C. Collection + 原生 Note + 轻量 Item Pane（混合方案）

把每个 ATR topic 投影成 Zotero Collection。Collection 中放已有/匹配到的文献条目和一份 topic research note；来源条目双击走原生 Reader tab，topic/source note 双击走原生 Note tab。Library 与 Reader 的右侧 Item Pane 只显示当前条目对应的 ATR 语义和跳转按钮。

- 优点：导航、阅读、标注、笔记全部沿用 Zotero 原生对象和 tab；topic 可恢复；多篇来源天然形成阅读队列；人的笔记不被困在插件私有界面；插件只维护映射和反馈协议。
- 缺点：需要谨慎处理来源匹配、Collection 幂等同步和生成内容与人工内容的边界；ATR 的全局图谱不再一次性铺满屏幕。
- 结论：采用。全局结构不占据独立主界面，而是进一步投影成可折叠的原生 Collection 层级；每个节点仍以 Note/来源条目进入 Zotero 的阅读工作流。

## 决策规则

本方案遵循以下不变量：

- 插件不再向 `zotero-pane-stack` 挂载全屏 overlay，也不创建自定义内容 tab。
- 文献必须通过 `Zotero.Reader.open()` / Zotero attachment handling 进入原生 Reader tab。
- Note 必须通过 `Zotero.Notes.open()` 进入原生 Note tab，而不是只在 Library 中选中一条 note。
- ATR section 使用 `Zotero.ItemPaneManager.registerSection()`，同时服务 Library 与 Reader 上下文。
- 同步优先复用带 source tag、DOI、URL 或精确标题匹配的现有 Zotero 条目；不移动、不删除、不覆盖用户字段。
- 自动生成的 topic/source note 创建后不自动覆盖，以免破坏人工内容。
- 只有带 ATR marker 的 Note，或属于已映射 ATR 来源的 annotation，才进入 `human-input/inbox.jsonl`。
- Note/annotation 反馈是复审输入，不直接推进 ATR lifecycle。

## 当前原生骨架

每个 topic 下固定保留五个一级分区：Topic 与演化、知识体系、研究问题与断言、来源阅读、历史版本。

- 知识体系只按显式 `specializes_concept` 形成父子 Collection；每个概念 Collection 包含一份概念 Note 和直接关联的来源条目。
- 研究问题与断言包含现实世界张力、前沿研究问题、当前问题卡、待审查断言四个分区。
- 当前 problem 是独立 Collection；`generates_finer_review_question` 明确生成的细粒度问题嵌套在它下面。
- 没有显式 tension/question → problem 边时保持为森林，不为了视觉连贯编造链路。
- 被 supersede 的 problem/claim 版本进入历史版本，并用完整 graph node marker 与当前版本严格区分。

## 对成熟插件交互的吸收

- Better Notes 已从单一“workspace”转向可打开多个原生 note tab/window，并让 note editor 同时存在于 note tab、Library item pane 和 Reader context pane。ATR 采用同一原则：Note 是工作对象，不是仪表盘里的文本框。
- Translate for Zotero 将选择后的动作放在 Reader 选区弹窗和 Item Pane，并且只有在 note editor 活跃时才提供“加入 Note”。ATR 同样把来源级动作放回 Reader/Item Pane，而不是要求用户离开文献。
- Ethereal Style 把阅读状态、标签和关系等信息投影到 Library columns / Item Pane，并让 Library selection 与图谱定位互相联动。ATR 因此把 topic 队列放在 Collection，把语义摘要放在 Item Pane。

## 首个实现切片

1. 工具菜单按 registry 列出 topic；选择后同步并定位原生 Collection。
2. 为 topic 创建一份原生 standalone note，随后用原生 Note tab 打开。
3. 来源匹配/创建后加入 topic Collection；Item Pane 提供“阅读文献”“打开 topic note”“打开来源 review note”。
4. PDF attachment 通过原生 Reader tab 打开；没有 attachment 时明确提示，不伪造可阅读状态。
5. 捕获 ATR-marked note 修改及 ATR source 下 annotation 的 text/comment/page/position，写入人工复审 inbox。
6. 「Topic 与演化」同时包含人的 Topic Note 与由真实 ATR timeline 生成的过程 Note；后者不接收研究输入，也不补造缺失事件。
7. Item Pane 为知识、张力、问题、断言与来源 review note 提供五种 typed stance；点击只修改对应原生 Note，并生成 `REVIEW_INPUT_ONLY` 事件。
