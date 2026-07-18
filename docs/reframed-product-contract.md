# 重新定义：ATR × Zotero 共同研究工作台

> 本文取代早期 MVP 的产品边界。早期版本只把一个 ATR run 渲染为列表和静态图；它不是本项目要交付的共同研究环境。

## 目标不是「把结果放进 Zotero」

目标是一条可反复进入的研究回路：

```text
topic → ATR 的探索动作与候选判断 → 原始材料
      ↑                                  ↓
  重新审查 / 分叉 / 保留历史 ← 人在 Zotero 的定位阅读、批注与反驳
```

研究者不是为 AI 摘要背书。每一个由 AI 提出的定义、关联、问题或研究机会，都必须能回到原始材料；研究者可以在同一位置赞同、限定、反驳或提出新问题。AI 的下一步只能把这些反馈作为新的、可审查的输入，不能改写人的笔记、原始来源或旧版研究链路。

## 四类不可混同的对象

| 对象 | 权威位置 | 必须携带的内容 | 绝不能伪装成 |
| --- | --- | --- | --- |
| 原始来源 | Zotero item / attachment / URL | 书目信息、稳定键、定位符（页码/段落/高亮/时间戳） | AI 的结论 |
| 可核查断言 | ATR immutable artifact | 断言文本、提出者、证据/反证来源定位、适用条件、置信度 | “一篇论文的完整观点” |
| 人的阅读判断 | Zotero note 中带稳定 block ID 的反馈 | 立场、针对的断言/来源定位、理由、原文摘录、问题 | 自动确认的证据 |
| 研究路线决策 | ATR controller artifact | 采纳/搁置/分叉、理由、依赖的断言与人的反馈、时间 | 对历史的覆盖 |

这里的最小工作单元是 **claim（可核查断言）**，不是 paper（论文）。一篇论文可以支持、限制或反驳多个断言；一个断言也可以由多篇论文和人的阅读判断共同约束。

## 两张图与一条时间线

### 1. 知识—证据图

从 topic 的工作定义向下展开为概念、子概念、可核查断言和来源定位：

```text
概念/定义 ──细化为──> 子概念 ──由──> 断言
                                  ├──支持/限定/反驳──> 来源定位
                                  └──被阅读判断审查──> 人的反馈
```

- 概念层级是逐步长出来的，不是一次性由模型画出的“知识树”。
- 每条概念边与断言边都显示提出它的 artifact 和版本。
- 点开来源必须先看到**原文位置、可推出内容、不可推出内容**，再看到 AI 摘要。

### 2. 现实问题—研究机会图

它不是把新闻/博客塞进文献列表，而是单独建模：

```text
现实情境/主体 → 可观察摩擦或矛盾 → 研究问题
                                     ├──已有工作解决了什么
                                     ├──已有工作留下什么条件或缺口
                                     └──可区分的候选机制/干预
```

每个现实节点标记来源类型、日期、范围、事实/观点状态；它只能启发问题，不能自动成为学术证据。每个研究问题至少能追溯到：现实情境、相关学术断言、一个可证伪条件和一个尚未解决的分歧。

### 3. 研究演化时间线

时间线记录：topic intake、每一个 worker 动作、输入 artifact、输出 artifact、质量门、人的反馈、路由决策和重新打开的分支。图上的每条线都有 `created_by`、`created_at`、`supersedes/contested_by`；旧线保留且可切换查看，绝不被最新总结抹去。

## Zotero 的职责

Zotero 是研究者的阅读场，而不是一个被插件复制的数据仓库。插件需要提供：

1. 从工作台节点深链到精确 Zotero item、PDF、笔记或高亮；
2. 为一个 **claim review** 建立/定位笔记块，而非只创建一篇泛泛的“阅读卡”；
3. 让研究者明确选择反馈类型：`支持`、`需要限定`、`反驳`、`尚不能判断`、`提出问题`；
4. 捕获带 block ID 和来源定位的增量事件，保留原笔记；
5. 显示反馈会影响哪些断言、问题与路线，以及影响是“待审查”而非已经自动生效。

插件不应试图把复杂图谱挤在 Zotero 主窗口的一张 XUL 长表里。Zotero 内应提供深链、反馈和轻量状态；完整的可缩放图、时间线、版本比较和路线审查是同一工作台的专用视图，但两边共享同一不可变事件/投影协议。

## 对 ATR 的约束

ATR controller 仍是唯一可以推进 lifecycle 的系统。来自 Zotero 的反馈先生成 `human-review-packet`：它列出目标断言、原笔记 block、影响路径和建议复审范围。controller 显式接受后，才产生新的 claim review、route decision 或 branch；任何自动化都不得把「笔记被修改」等同于「研究结论已更新」。

## MVP 的真实验收闭环

以一个真实 topic 为例，以下六步都必须可演示：

1. 输入 topic 后，看到 ATR 的实际动作和每步 artifact，而不是补造的流程图；
2. 选择一条 AI 断言，打开它引用的 Zotero 原始来源和精确定位；
3. 在该断言对应的 Zotero 笔记块中作出有类型的判断；
4. 工作台显示该判断影响的最近断言、研究问题和历史分支；
5. 研究者明确触发审查，ATR 产生新的审查 artifact 或保留原路线的理由；
6. 新旧图、来源和判断均可并排比较，且没有任何旧记录被删除或改写。

## 当前实现与仍未完成的验收证据（2026-07-18）

`graph.json` 与 legacy/v0.9 adapter 已不再只是论文列表：它们能投影 source-grounded concept tree、现实张力、问题卡、细粒度 review question、item-contract audit、时间戳 artifact、历史 projection snapshot、Zotero source/claim stance、immutable human-review-packet、owner disposition 与隔离 `human-review-assessment`。历史问题卡版本也会保留并显示其替代关系。Zotero 插件不再把这些对象铺成 XUL overlay；它将 topic/source 映射到原生 Collection、Reader、Note 与 Item Pane，并在「Topic 与演化」中生成一份只依据真实 timeline 的过程 Note，在「共创复核」中显示独立 reviewer 的结论、保留对象与待另写版本对象。Item Pane 提供五种 typed stance，但任何 stance 仍只产生 review input。完整图谱继续作为 ATR 的可审计派生投影保留。

但这些能力不等于完成上述 MVP。当前证据与缺口如下：

| 验收对象 | 当前证据 | 仍缺什么，因而不能宣称完成 |
| --- | --- | --- |
| topic → 实际过程 | v0.9 harness 记录 gate/stage；新 `run_instrumented.py` 以后会记录真实 Codex execution attempt（声明 skill 与实际 skill invocation 分开） | 当前 multilingual continuation 迁移前没有原生 skill-event，不能倒灌伪历史；尚需一个从新 topic 开始的端到端真实 run |
| 原始来源与定位 | Zotero 条目以 `atr-source-id` 幂等映射；隔离 Zotero 9 smoke 已验证 Reader PDF 打开、原生 highlight/comment/page/position 捕获，并以 `zotero://open-pdf/...&annotation=...` 和 `Reader.open(..., {annotationID})` 精确反向打开既有 annotation | 真实研究来源仍需阅读者核对 locator；隔离 profile 不能替代日常库人工点击验收 |
| 人的反馈回流 | Item Pane 五种判断 → Note typed stance → review queue → immutable packet → append-only owner disposition → isolated assessment；三阶段隔离 smoke 已验证 `QUALIFIES`、Reader annotation、最近节点回显，以及 `05 · 共创复核` 原生 Note。assessment 明确保留来源、请求 evidence review，且 clone stage/version 不变 | 已证明代码路径，但仍缺真实人的处置后另行产出新 collision/route/claim artifact 并形成 current/history 分支的学术案例 |
| 知识与现实问题图 | concept map、opportunity map、问题卡与论文 role/细粒度问题均有 source IDs 和不成立边界；contextual sources 独立分层 | 不是完整领域 ontology；现实材料不提供部署影响估计或 gap certificate |
| 历史保留 | 图投影快照、历史问题卡版本与 supersession relation 均可比较 | 尚未提供任意两个分支的完整并排互动比较；原始 artifact 的版本化仍依赖 harness 的 append-only政策 |
| Zotero 运行时 | repo-local 隔离 profile 已在 Zotero 9.0.6 验证菜单、Item Pane 注册、21 份 Note、Reader tab、annotation、6 个知识 Collection、13 个研究 Collection、过程 Note、论文问题角色与 typed stance；构建前仍执行 manifest/contract/static validation | 尚未在日常 profile 安装并人工走查候选 XPI；隔离 profile 的 PASS 不能替代用户日常库中的最终体验验收 |

因此剩余运行时门禁不再是“代码能否在 Zotero 启动”，而是：安装候选 XPI 到日常 profile 后，由真实研究者走查 Collection/Note/Reader/Item Pane 的阅读体验，并完成一次“人的处置 → controller 新 review artifact → 保留/分叉路线”的端到端共创循环。通过前不能宣称完整目标完成。
