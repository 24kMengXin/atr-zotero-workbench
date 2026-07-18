# 原始目标完成审计

更新时间：2026-07-19。结论：**目标仍未完成**。2026-07-18 版本把一个五篇来源的 bounded UI smoke 误当成目标主线，并过度使用“已证明”。本表已按六个 program、28 个历史 run 的实际范围重判；设计意图和“应该可用”不算完成。

| 原始要求 | 当前判定 | 权威证据 | 尚缺的完成条件 |
| --- | --- | --- | --- |
| 先整理 `multilingual-aaai` 历史 auto-research 产物，能复用的理解后复用，错误/缺口清退或报告 | 部分完成 | [逐项归位矩阵](historical-program-disposition-matrix.md)覆盖 6 program/28 run；391 条来源、manifest、当前 checker、source/fulltext 状态均已落盘；旧 stage/gate/claim/route 已退出 current | 仍需对真正被消费的 artifact 逐项生成 `LEGACY_MAPPED` manifest，并完成来源去重、访问/全文核验和语义复审 |
| 与更新后的 ATR v2 对齐，而不是把 v0.9 stage 伪装成 v2 历史 | 部分完成 | 一个 portfolio + 六个 child authority 均保持 `INTAKE`/v0；六条 child 现在每条 11 个 attachment，新增 source-reviewed knowledge-map 1.1；portfolio 另有 4/2 disposition 汇总；七个 authority controller check 通过 | posterior worker 不是独立 gate reviewer；六条仍需 owner/独立 reviewer 作 route/park/refresh 决策 |
| 插件使用 Zotero 原生 Collection、Reader、Note、Item Pane，不建立独立主界面 | 部分完成 | v0.6.4 的 paper 单一主动作打开 Zotero Reader，并把同一份来源 Note 作为可编辑 Item Pane section 与四区 ATR 定位同时放在右栏；两者分别折叠，深度编辑仍打开同一 Note；便携窗只是显式镜像，不拥有第二份状态；碰撞复核 Note 另有需要理由的折叠 owner review | 尚需日常 profile 人工走查折叠密度与实际长文阅读体验 |
| topic 运行过程可直观看见，且不补造 auto-research 历史 | 部分完成 | portfolio 明示 1→6→28 历史归位图，并在六个 program 节点显示 4 个 `REFRAME`、2 个 `NEEDS_EVIDENCE`；组合图下有折叠的「待我的 owner review · 6」，每项直接进入对应 child authority 的 exact collision-review Note；每个真实问题卡下都有 collision-review 子 Note，显示五类碰撞、残存边界、限制和下一证据；v2 timeline 只读 SQLite | 六条 child 仍只有 INTAKE；尚无经过真实 owner/独立 reviewer 的合法 gate/route/current-history 全链 |
| 自上而下的知识体系逐步展开，知识节点能独立指向文献 | 部分完成 | 六条 program 各有一棵 6 节点 current knowledge-map 1.1：36 个概念含逐节点 locator/relation/boundary，状态为 12 bounded、12 partial、6 collision-challenged、6 pending；旧 36 个 metadata scaffold 作为历史保留。Zotero Note 显示核验状态和原文跨度，点击来源进入 Reader + 人的 Note | 当前只覆盖首轮全文 reduction，不是完备领域共识树；6 个 pending 和所有 partial/challenged 节点仍需补更多独立来源与人的原文复核，层级深度也尚不足 |
| 从论文、技术材料、社区/现实信号形成现实世界张力，而非只做技术 gap | 部分完成（六条已裁决并可视化） | representation/data、state continuity、infrastructure/evaluation 形成受限 opportunity map；action attribution、authorization safety、governance 因缺合格独立现实信号落盘 `NO_ADMISSIBLE_SIGNAL`。后 3 条不再显示成模糊的“缺 opportunity map”，而是 Zotero「现实证据缺口」Note，列出受限检索理由、缺失来源功能、下一步合法工作与不能推出的结论 | 三张 map 与三条 no-signal 均待人的科研品味复核；不能把 no-signal 擅自补成张力 |
| 每个研究问题说明论文主观/客观提出、遗留、解决、挑战了什么 | 部分完成（六个 problem-case 与六个 posterior review） | 六条均有来源角色与五类碰撞复核；action/representation/infra/governance=`REFRAME`，authorization/state=`NEEDS_EVIDENCE` | posterior worker 不等于独立 gate；全量历史来源尚未逐篇语义复审，也未形成 owner route/park 决策 |
| 论文讨论继续产生更细粒度问题节点 | 部分完成 | 六条真实 child 各有 2 个 typed `derived_questions`，共 12 个；12 条均有显式父问题边，其中 11 条至少链接一篇来源，唯一无来源的 `DQ-AUTH-2` 明确询问“是否存在合格 primary workflow asset”，没有伪造证据 | 这些问题来自首轮 source reduction，仍待人的原文复核与 owner route review；尚未形成后续版本化追问链 |
| 人可以离线逐篇读、批注、写 Note，并明确支持/限定/反驳/不确定/提问 | 已证明（隔离环境） | Reader annotation 捕获；Item Pane 五种 typed stance；真实 smoke 捕获 `QUALIFIES`、highlight/comment/page/position | 需要用户在日常库中完成一次真实研究阅读，而非 smoke fixture |
| 从人的修改找到最靠近根/决策的受影响信息，回到 Codex 做认知更新 | 已证明到“待审查输入” | 只沿显式研究边的 BFS impact；直接 source-role → 最近问题距离 1，collision source → collision review → 最近问题距离 2；v0.6.3 修复了 collision-review Note marker 未进入 notifier 的缺口，人的 owner input 先精确命中 collision review、再一跳到父问题；`review-registry` 扫描显式 topic，collection/run containment 不传播 | 尚未用一条用户真实反馈完成后续 scholarly re-review |
| 人的反馈不能自动改 lifecycle，旧节点、旧边和旧文献继续保留 | 已证明 | `REVIEW_INPUT_ONLY`、append-only packet/disposition、历史 projection snapshot；controller attachment 不改变 subject version/state | 无；后续任何自动 route 功能仍必须保持该不变量 |
| 人的处置能触发新的 claim/route review，并把新旧路线并排保留 | 部分完成（代码路径与隔离运行） | v2 已有 owner disposition → isolated `human-review-assessment`；repo-local Zotero 9 三阶段 smoke 验证「共创复核」Note、保留/重审 edge、真实 authority 不变、clone 仍为 `INTAKE`/v0 | 用真实人的 packet 运行 scholarly reviewer；生成新的 problem/collision/route artifact；执行合法 controller decision；重新投影并比较 current/history 链 |
| 插件与 auto-research harness 同时优化 | 部分完成 | 两个真实 pilot形成 source-inspection/Zotero-state SHADOW card；本轮错误 arXiv PDF 被元数据核验拦截并形成 `HCH-source-identity-before-fulltext-inspected-v1` SHADOW card；collision review 已映射为问题卡子 Note | 两张 card 都未达到 OPTIONAL/ENFORCE；需按各自 sample 做 prospective comparison，并验证 identity check 的误拒率 |
| 精确回到 Zotero 原始来源、PDF 与高亮 | 已证明（隔离环境） | 插件在事件发生时生成 user/group-aware `zotero://open-pdf/...page=...&annotation=...`；packet、queue、过程 Note 与 `review-links.md` 保留同一 URI；`Reader.open(..., {annotationID})` 内部重开也已验证 | 仍需在日常 profile 中点击一次真实 packet 链接做人工体验验收 |
| 新 GitHub repo 与本机目录配合 | 已完成当前同步里程碑 | 插件仓库 `24kMengXin/atr-zotero-workbench` 的 `main` 已推送实现提交 `1bb9307`，包含 portfolio、六 child、历史归位、v0.6.4 共读界面与候选 XPI；父仓库 `24kMengXin/multilingual-aaai` 的 `main` 已推送独立 harness 提交 `27f839a`，只包含 knowledge-map 1.1 的四个合同文件。`.runtime`、Zotero profile/data、全文、SQLite 与凭据均未提交；父仓库其他未提交删除未进入该提交 | 后续每次真实 owner review 形成的新 artifact/投影仍需独立、可审计地提交；当前同步完成不等于完整研究闭环完成 |
| 可安装候选 XPI | 部分完成 | `dist/atr-zotero-workbench.xpi` v0.6.4，SHA-256 `4b56006687410b3991b0afe2256a659467a74ff2a3ce80bd449e96e2b9590cf2`；50 项测试与静态合同通过；隔离 Zotero 9 验证 106 个来源、12 个知识 Collection、16 个研究 Collection、1 个现实证据缺口、1 个碰撞复核 Note；Reader 保持 `item` mode，真正的来源 `note-editor` section 与 ATR section 同时注册并分别折叠，同一 Note 仍可开原生标签，annotation/typed owner input 形成 3 个 review-only packet，便携镜像仍有四区/双图。portfolio smoke 另验证 6 program、4 折叠面板、1 张 4/2 disposition 总览、折叠 owner-review 队列、program→child→exact collision-review Note→portfolio 往返且 authority effect 为 NONE | 仍需日常 profile 人工走查折叠密度与实际长文阅读体验 |

## 当前最短的真实完成路径

1. 由 owner/独立 reviewer 审查六个 posterior review：四条是否接受收窄，两条是否按 `NEEDS_EVIDENCE` 停放/补证据；只有实际消费的历史 artifact 才生成 `LEGACY_MAPPED` manifest。
2. 继续补齐六条 child 的 fresh、去重、全文核验知识树；不把 28 条历史 run 的零 concept-map 状态伪装成已经完成的知识体系。
3. 在日常 Zotero 用当前 v0.6.4 候选人工验收 portfolio program 单击、问题卡→碰撞复核子 Note、owner route review，以及 paper 的「阅读原文并记录我的理解」是否让阅读 Note 与 ATR 定位在同一右栏同时可见。
4. 在日常 Zotero 安装候选 XPI，由用户完成一条真实 annotation/typed stance；Codex 生成 packet，用户记录 disposition，隔离 reviewer 产出新 artifact。
5. controller 合法保持、分叉或停放后重新投影，人工确认旧节点/旧边/旧文献仍在历史，新版本成为 current target。
