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

### C. Collection + 原生 Note + 轻量 Item Pane

把每个 ATR topic 投影成 Zotero Collection。Collection 中放已有/匹配到的文献条目和一份 topic research note；来源条目双击走原生 Reader tab，topic/source note 双击走原生 Note tab。Library 与 Reader 的右侧 Item Pane 只显示当前条目对应的 ATR 语义和跳转按钮。

- 优点：导航、阅读、标注、笔记全部沿用 Zotero 原生对象和 tab；topic 可恢复；多篇来源天然形成阅读队列；人的笔记不被困在插件私有界面；插件只维护映射和反馈协议。
- 缺点：需要谨慎处理来源匹配、Collection 幂等同步和生成内容与人工内容的边界；ATR 的全局图谱不再一次性铺满屏幕。
- 结论：只作为数据投影骨架采用。它解决了对象落在哪里，却没有解决“读 PDF、写人的理解、看研究结构能否同时发生”。此前把它当作最终交互方案，是错误的。

### D. Reader 原生笔记 + 可脱离共读伴随窗

默认工作面不是独立 ATR 页面，而是两种与 Zotero 当前任务同步的原生嵌入：

1. **Reader 原生工作面**：PDF 保持在中央；右侧 Item Pane 用官方 section 承载真正的 Zotero `note-editor`。人的阅读 Note 与 ATR 定位可以同时展开，不再为了看另一方而切换右栏 mode。
2. **Item Pane 入口**：ATR 仍通过官方 `ItemPaneManager.registerSection()` 在当前对象附近给出最小摘要、来源状态、局部图和启动按钮；阅读 Note 是相邻的独立 section，两者各自折叠。
3. **可折叠伴随窗**：点击「三面同看」后，当前局部 ATR 投影在一个可调整、可置顶的小窗中持续显示；过程、知识、问题和当前对象四区可分别折叠，图节点反向打开 Reader、annotation 或同一份 Note。窗口跟随当前 ATR 对象，不拥有第二份研究状态。
4. **Note tab 深度模式**：长篇综合时仍打开同一 Zotero Note 的标签页；伴随窗继续可见。这里复用 Better Notes 已验证的“同一 Note、多种容器”原则，而不复制编辑器。

- 优点：PDF、人的笔记和可视化能够同时看到；窄屏时又能逐层折叠。来源、高亮、Note、图节点始终映射到 Zotero 原生对象。
- 代价：需要维护伴随窗生命周期、跟随选择和置顶状态；但不再侵入 Reader 私有布局去强行并列两个右侧 mode。
- 结论：保留为需要三面同时可见时的增强模式，但不再作为默认主路径。把伴随窗放在第一入口仍然会让插件看起来像 Zotero 外部的第二套工作台。

### E. Zotero 原生标签对 + 可折叠 Item Pane（选定方案）

把 C 的原生对象组织与 D 的同时共读能力重新排序：

1. portfolio 图中的 program 不是“说明卡”，而是进入对应 child authority 的导航入口；
2. topic、problem 与综合判断默认打开真正的 Zotero Note tab，人的理解位于中央编辑器，ATR section 位于右侧可折叠 Item Pane；
3. paper 默认打开真正的 Zotero Reader tab，来源 Note 作为可编辑 section 与 ATR section 同时位于右侧；同一 Note 仍可另开原生标签；
4. paper 的主动作先建立 Reader + 可折叠来源 Note + 可折叠 ATR 定位；伴随窗只在用户选择「便携显示 ATR 定位」时出现，用于窄屏或第二屏布局。

- 优点：日常路径只出现 Zotero 原生标签、原生 Note 与官方 Item Pane section；从组合到 topic、从问题到文献都保持单击可达；窗口不再成为理解系统的前提。
- 代价：窄屏下原文和长篇 Note 仍需在两个标签间切换；因此保留 Reader 右侧 Note 与可选伴随窗作为并置方式。
- 结论：采用。默认路径是原生标签对和折叠右栏，伴随窗是显式增强。

## 决策规则

本方案遵循以下不变量：

- 插件不再向 `zotero-pane-stack` 挂载全屏 overlay，也不把自定义内容 tab 当默认入口。
- 文献必须通过 `Zotero.Reader.open()` / Zotero attachment handling 进入原生 Reader tab。
- Note 必须通过 `Zotero.Notes.open()` 进入原生 Note tab，而不是只在 Library 中选中一条 note。
- ATR section 使用 `Zotero.ItemPaneManager.registerSection()`，同时服务 Library 与 Reader 上下文。
- topic/问题默认进入 Note tab，并在可折叠 Item Pane 中显示 ATR；paper 的唯一主动作打开 Reader，并在 `item` mode 中注册可编辑 Note section，使 Note 与 ATR section 并存。只有显式请求便携定位才打开伴随窗。
- Item Pane 与伴随窗共享同一个当前焦点；节点点击必须反向选择 Zotero item、打开 Note，或用 annotation locator 打开 PDF 精确位置。
- 四区折叠状态与置顶偏好必须持久化；伴随窗只是同一投影的镜像，不拥有单独状态。
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

## 对成熟插件交互与源码的吸收

| 插件 | 观察到的成熟交互 | 本项目吸收的设计原理 | 不照搬的部分 |
| --- | --- | --- | --- |
| [Better Notes](https://github.com/windingwind/zotero-better-notes) | Note tab 以 outline / 原生 note editor / context 三栏组成；splitter 可折叠、宽度和状态持久化；编辑器还能出现在 Reader context pane | 人的 Note 是中心工作对象；辅助信息可折叠、可调尺寸、恢复上次布局 | 不复制一套私有笔记编辑器，不把 ATR 内容混写进人的 Note |
| [Translate for Zotero](https://github.com/windingwind/zotero-pdf-translate) | 动作靠近 Reader 选区；结果默认嵌入 Reader-only Item Pane section；标题栏可切全高或脱离为可调窗口 | 当前选区/annotation 驱动上下文；嵌入是默认，便携窗口是可选镜像 | 不把悬浮窗变成唯一入口，不直接依赖私有 Reader DOM 作为主协议 |
| [Ethereal Style](https://github.com/MuiseDestiny/zotero-style) | 阅读进度进入 Library 列；关系图跟随 collection/selection，可隐藏、调整尺寸、缓存，再反向选择条目 | 轻状态放原生列表；完整图按需展开；选择双向同步 | 不把所有研究语义压缩成标签或颜色，不用视觉连线补造不存在的边 |
| [scite Zotero plugin](https://github.com/scitedotai/scite-zotero-plugin) | Item Pane 只显示支持/反对/提及等紧凑摘要，再用一个入口展开报告 | 侧栏先给最小可判断摘要，细节按需展开 | 不把来源计数伪装成 ATR 的可信度或路线决策 |

这些插件共同表明：好用的 Zotero 插件不是另造一个应用，而是在用户当前对象附近增加可撤回、可折叠、与原生选择同步的能力。

### 2026-07-19 源码复核后的界面纠偏

本轮不只复述插件说明，而是在 repo 内的 `.runtime/upstream-plugin-study/` 浅克隆并核对了三个上游实现（该目录是 gitignored 的本地研究缓存，不进入产品包）：

- Better Notes 的 `Workspace` 使用 outline / 原生 `note-editor` / context 三栏和可持久化 splitter；动态 Note preview 仍通过 `ItemPaneManager.registerSection()` 注入当前 context，并提供“打开标签、关闭预览、占满高度”三个明确动作。
- Translate for Zotero 的 Reader panel 默认是一个 `ItemPaneManager` section；脱离窗口和 full-height 都只是 section header 的次级动作，当前 item 驱动 panel 内容。
- Actions & Tags 先读取 Zotero 当前 tab/selection 再执行动作，说明插件入口必须服从当前阅读上下文，不能要求用户先进入插件自己的首页。

对照后确认 v0.6.0 虽然容器选择正确，信息架构仍然过载：同一 section 同时显示四个模式按钮、四个 ATR 区、重复的来源边界和五个常驻判断按钮；而“原文 + 右栏笔记”没有负责从 Library 先打开 Reader。v0.6.1 因此改成：

1. paper 只有一个主动作「阅读原文并记录我的理解」：获取/打开真实 attachment 后，再把同一 source Note 作为可编辑 section 放到 Reader 右侧；图上的 paper 节点也执行同一路径。
2. 详细 supports / does-not-establish / inspection span 收进「当前对象」折叠区，不在 section 底部重复铺开。
3. 五种人的判断收进「记录我的判断（进入待复审队列）」折叠控件；折叠本身不产生认知事件。
4. Item Pane 只保留一个便携 ATR 次级入口；便携窗内部不再重复“模式切换”按钮，只负责当前定位与反向导航。
5. 碰撞论文的 annotation 允许沿唯一显式路径 `paper → collision review → research problem` 回流；通用 collection/run containment 仍被排除，避免主题相似即错误传播。

## 共读坞信息架构

```text
┌──────────────── Zotero Reader tab ────────────────┐
│ PDF / annotation                                  │
│                                      ┌───────────┐│
│                                      │人的 Note  ││    ┌─ ATR 伴随窗 ─┐
│                                      │原生编辑器 ││    │▾ 过程        │
│                                      │           ││    │▸ 知识        │
│                                      │           ││    │▸ 问题        │
│                                      └───────────┘│    └──────────────┘
└───────────────────────────────────────────────────┘
```

共读坞有三种容器，消费同一份投影而不是形成三个页面：

- **折叠**：一行显示 topic / 当前阶段 / 待复审数量 / 当前来源。
- **紧凑**：只画当前来源或 annotation 的一跳邻域，并显示“可推出 / 不可推出”。
- **展开**：在 Note tab 的 Item Pane 或显式伴随窗中显示 topic 全图、时间线和历史切换；它仍然只消费同一投影。

三个小图共享同一焦点，但不合并语义：过程图回答“怎样走到这里”，知识图回答“这个来源约束了什么概念/断言”，问题图回答“它影响哪个现实张力、问题和候选路线”。任何节点均先定位原生 item/note/annotation，再提供复审动作。

## 首个实现切片

1. 先完成 multilingual-aaai 六个历史 topic、28 个 run 对 ATR v2 的整理；共读坞只消费校正后的 current/history/quarantine 投影，不再让五篇 demo 成为 current。
2. Reader/Item Pane 共读轨道已实现：项目历史/过程、知识定位、现实问题/研究问题与当前对象四个 XHTML 折叠区会恢复 Zotero Preference 状态；v0.6.4 的「阅读原文并记录我的理解」一次建立 Reader + 可编辑阅读 Note section + ATR section，二者在同一右栏分别折叠；「在新标签深度编辑」打开同一 Note；「便携显示 ATR 定位」才打开可置顶镜像。知识/问题区使用可点击的局部 SVG 图。
3. 当前 source/annotation 驱动局部邻域；节点能反向打开原生 Note、item 或 PDF annotation。portfolio 投影另有一张全局 SVG：1 个 portfolio → 6 个 program authority → 28 条只读历史 branch；蓝色 program 现在解析 registry 中完全匹配的 `child_run_id` 并进入对应 Zotero topic，灰色历史节点才打开只读导航 Note。
4. 当前全局图仍可嵌在 Item Pane 的「过程 / 项目总览」折叠区；持续共读时则使用同一投影的伴随窗，不再计划未经验证的 Library 私有 DOM 托盘。
5. Zotero 9 隔离 smoke 已证明 v0.6.4 的 Reader 保持 `item` mode，阅读 Note 与 ATR 拥有不同 pane ID 并同时注册；来源 Note 是 Zotero 原生 `note-editor`，同一份 Note 仍可开标签。伴随窗继续渲染 4 个折叠区和 2 张局部 SVG；portfolio 的折叠 owner-review 队列还能执行 program → registered child authority → exact collision-review Note → 返回 portfolio。action child 投影包含 106 个去重来源、6 个 current source-reviewed knowledge Collection、6 个 historical scaffold Collection 和 16 个研究集合。仍需在日常 profile 完成主观密度验收。

## v0.6.3 的知识图与 owner review 视觉语义

知识图现在明确区分“作者根据元数据搭出的历史骨架”和“worker 已定位原文跨度的当前节点”。历史骨架继续留在历史 Collection，不会因新版投影被删除；当前节点必须携带 locator、evidence relation、observation、boundary 与 review status，Item Pane 和原生知识 Note 都能展开这些字段。

局部图仅用颜色做快速定位，并始终附带文字图例：绿色为受限原文支撑，紫色为部分支撑，橙色为被碰撞复核挑战，灰色为等待更多来源。颜色不代表生命周期 gate，也不替代文字状态。单击概念后先进入原生知识 Note；单击它列出的来源再进入 Reader，并将同一份人的来源 Note 作为可折叠 section 放到右侧。

碰撞复核 Note 同时保持两个层次：上半部分是不可被人的编辑覆盖的 worker 比较结果；下半部分是人的 owner route input。后者在 Item Pane 中折叠，只有明确选择并填写非空理由才写入 Note/Notifier。它精确命中 collision-review graph node，再沿唯一 `is_claim_scoped_reviewed_by` 边到父问题；这仍然只是 review input，不是 controller route transition。

现实问题区还必须显示负面结果。若 bounded search 没有找到合格的独立 workflow/community signal，插件创建灰色「现实证据缺口」节点和原生 Note，而不是显示成空白或伪造张力。Note 明确列出检索截至、为什么现有论文不具备所需来源功能、下一步合法搜索和不能据此推出的结论；它可以链接回受检文献供人复核，但没有显式边时不会连接到问题卡。
