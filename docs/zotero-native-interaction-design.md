# Zotero 原生共读交互设计

## 目标

用户在 Zotero 阅读 PDF 时，应当能够不离开原文地完成三件事：

1. 核对原文并创建 Zotero Reader annotation；
2. 在真正的 Zotero Note 中写入自己的理解；
3. 随时查看当前文献在知识体系、现实问题、研究问题和 ATR 历史中的位置。

插件不创建第二套 PDF 阅读器、第二套笔记数据库或独立 dashboard。ATR 图是 lifecycle authority 的只读投影；人类 Note/annotation 是 review input，不能直接推进 lifecycle。

## 从现有 Zotero 交互提炼的原则

- **Better Notes：同一份 Note，多种原生容器。** 深度写作使用 Note tab；阅读时使用 Reader 右侧的 note editor。入口随任务变化，笔记对象不复制。
- **PDF Translate：短时动作贴近选区和 Reader。** 高频、低承诺操作不应要求离开当前文献。
- **Ethereal Style：图是定位器。** 图节点负责返回 Zotero 条目、Reader 或 Note，不取代条目树和阅读器。
- **Zotero 7+：使用官方 Item Pane section。** 研究上下文属于可折叠 section；不手工注入独立主页面。

## 比较过的三种方案

| 方案 | 阅读与笔记 | 可视化 | 与 Zotero 的一致性 | 判断 |
|---|---|---|---|---|
| 独立三栏工作台 | 复制/嵌入 PDF 与编辑器 | 自由度高 | 产生第二套导航和状态 | 不采用 |
| Note-tab 中心 | 适合跨文献综合写作 | 可放关系图 | 阅读单篇原文时需要切标签 | 保留为深度写作模式 |
| Reader + 原生 Note + 伴随窗 | PDF 始终在中央；右侧持续编辑同一 Note | 可折叠、可置顶窗口显示局部图 | 复用 Reader、Note editor、官方 section 与非模态窗口 | 同时共读增强模式 |
| 原生 Reader/Note 标签对 + Item Pane | 原文和综合 Note 各自保留为 Zotero 标签，来源 Note 以原生 `note-editor` section 嵌入 Reader 右栏 | 阅读 Note 与 ATR 定位分别折叠，必要时才弹出同一投影 | 不引入默认独立窗口；portfolio 可直接进入 child topic | **日常主模式** |

## 选定交互

### 日常主路径

1. 在 portfolio 的蓝色 program 节点上单击，插件按 `child_run_id` 打开对应 topic Collection 与 Zotero Note tab；不会把 program 误当成只读说明 Note。
2. 在 Note tab 中写综合理解，同时从右侧 ATR section 展开过程、知识、问题或当前对象。
3. 单击 paper 节点打开 Zotero Reader tab；选择「原文 + 右栏笔记」把同一来源 Note 作为可编辑 section 放进 Reader 的 Item Pane，并与 ATR section 并存。
4. 只有需要三者同时可见时，在已经打开 Reader + Note 后选择「便携显示 ATR 定位」；关闭镜像不影响任何 Note、annotation 或 ATR 投影。

### 同时共读增强模式

```text
┌──────── Zotero Reader tab ────────────────────────────────┐
│ PDF / EPUB 原文                     右侧 context rail      │   ┌─ ATR 伴随窗 ─┐
│                                     ┌───────────────────┐ │   │▾ 现实/问题图 │
│ 高亮、批注、翻页                     │ Zotero note-editor│ │
│                                     │ 当前来源的理解     │ │   │▸ 知识定位图 │
│                                     │ 当前来源 Review   │ │   │▸ 项目历史   │
│                                     │                   │ │   └─────────────┘
│                                     └───────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

「阅读原文并记录我的理解」把当前来源的 child note 放入 Reader 右侧的原生 Item Pane section。PDF tab 不关闭，Note 与 ATR 定位可以同时展开或分别折叠；需要把图移到另一块屏幕时，再选择「便携显示 ATR 定位」。便携窗不是主入口，也不重复提供模式切换。

### 深度综合

“笔记标签 / 在新标签深度编辑”打开同一个 Zotero Note，而不是生成副本。这个模式用于跨文献综合、长篇结构化写作；回到 Reader 后仍可继续在右侧编辑同一对象。

### 图的导航语义

- paper 节点：打开 Zotero Reader tab；若有 annotation deep link，定位到高亮。
- knowledge/problem/question/claim 节点：在 Reader 中优先固定对应 Zotero Note；无 Reader 时打开 Note tab。
- portfolio 节点：保持在组合 Note；program 节点：进入 registry 中 `child_run_id` 完全匹配的独立 v2 topic；history 节点：打开只读导航 Note。所有动作都不改写 controller authority。
- 折叠状态写入插件 preference；默认展开“现实问题 / 研究问题”和“当前对象”，默认收起“知识定位”及“项目历史 / 过程”。

## 兼容边界

ATR 与阅读 Note section 都使用 Zotero 官方 `ItemPaneManager.registerSection()`；Note section 的正文是 Zotero 自己的 `note-editor`，不是插件复制的编辑器。这个模式直接来自 Better Notes 的 Note preview 原理，避开了私有 `_setPinnedNote()` 和 `item` / `notes` mode 互斥。伴随窗内容 URL 通过 Zotero 7+ 官方示例采用的 bootstrapped `registerChrome()` 注册，并在 shutdown 释放；若原生 editor 初始化失败，安全退回同一 Note 的 Zotero 标签页。

## 验收条件

- 从 ATR 来源条目进入 Reader 后，PDF 保持打开。
- 点击 paper 的主动作后，右侧显示真正的 Zotero note-editor，Note 是该来源的 child note；显式打开便携定位后，ATR 伴随窗可同时可见。
- 伴随窗可置顶、可调整大小，四个语义区独立折叠，并跟随当前 ATR 对象。
- Reader annotation 和 Note 修改仍进入 append-only human-input inbox。
- 切回 Item Details 后，ATR section 的折叠状态仍在，局部图节点可定位回 Reader/Note。
- 若 Reader Notes 内部桥不可用，插件清楚记录 fallback，且 Note tab 仍可编辑。
