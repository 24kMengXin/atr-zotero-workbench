# 原始目标完成审计

更新时间：2026-07-18。结论：**目标仍未完成**。本表只接受当前文件、测试、真实 Zotero 运行或外部仓库状态作为证据；设计意图和“应该可用”不算完成。

| 原始要求 | 当前判定 | 权威证据 | 尚缺的完成条件 |
| --- | --- | --- | --- |
| 先整理 `multilingual-aaai` 历史 auto-research 产物，能复用的理解后复用，错误/缺口清退或报告 | 已证明 | `output/historical-program-alignment-audit.json`、`docs/historical-alignment-audit.md`、`docs/harness-zotero-alignment-findings.md`；历史目录保持只读，continuation 与 v2 intake 分开 | 后续新的历史目录若出现，仍需走同一审计，不能自动继承 stage/claim |
| 与更新后的 ATR v2 对齐，而不是把 v0.9 stage 伪装成 v2 历史 | 已证明 | v2 intake 的 SQLite authority、content-addressed artifact、attachment-only migration；`atrctl check` 与插件 SQLite projection 测试通过 | 无；这是迁移边界，不等于新 topic 已完整跑通 |
| 插件使用 Zotero 原生 Collection、Reader、Note、Item Pane，不建立独立主界面 | 已证明 | `docs/native-zotero-interaction-decision.md` 的 A/B/C 比较与 C 方案；静态门禁禁止 `zotero-pane-stack`；真实 Zotero 9 smoke 打开 Note/Reader tab | 日常 profile 的人工体验验收仍未做 |
| topic 运行过程可直观看见，且不补造 auto-research 历史 | 已证明（隔离环境） | `Topic 与演化` 下的原生过程 Note；只消费 `graph.timeline`；Zotero smoke 验证 `process_note_created/refreshed` 和 7 条真实事件 | 还缺一个从全新 topic 开始、由 v2 workers 实际产出完整 timeline 的研究 run |
| 自上而下的知识体系逐步展开，知识节点能独立指向文献 | 已证明（有界样例） | v2 `knowledge-map` 严格契约与无环校验；6 个知识节点 Collection/Note 的父子与 source membership 被真实 Zotero smoke 验证 | 当前样例是有界学习图，不是 NLP/LLM/AI 完备 ontology；新 topic 的增量演化尚未实跑 |
| 从论文、技术材料、社区/现实信号形成现实世界张力，而非只做技术 gap | 已证明（契约与样例） | typed `opportunity-map` 要求两个独立 source function；现实张力 Note/Collection 映射；contextual source 不升级成 scholarly evidence | 尚未对一个全新 topic 完成真实多渠道检索、有效期刷新与人类品味审查 |
| 每个研究问题说明论文主观/客观提出、遗留、解决、挑战了什么 | 已证明（结构和 UI） | `problem_posture/resolves/leaves_unresolved/does_not_establish` 的 v2 校验；问题 Note 显示每篇论文角色且去重；真实 smoke 验证 | 历史记录缺失的 posture 保持“未记录”；需要真实阅读补定位，不能由系统猜补 |
| 论文讨论继续产生更细粒度问题节点 | 已证明 | typed `derived_questions`、显式父问题边和 source 限制；Zotero 中 3 个细粒度问题嵌套于当前问题卡 | 新问题仍必须由来源与最小判别器支撑，不能自动膨胀 |
| 人可以离线逐篇读、批注、写 Note，并明确支持/限定/反驳/不确定/提问 | 已证明（隔离环境） | Reader annotation 捕获；Item Pane 五种 typed stance；真实 smoke 捕获 `QUALIFIES`、highlight/comment/page/position | 需要用户在日常库中完成一次真实研究阅读，而非 smoke fixture |
| 从人的修改找到最靠近根/决策的受影响信息，回到 Codex 做认知更新 | 已证明到“待审查输入” | 只沿显式研究边的 BFS impact；Reader source → 最近问题距离 1；review queue 两阶段回显最近节点 | 尚未用一条用户真实反馈完成后续 scholarly re-review |
| 人的反馈不能自动改 lifecycle，旧节点、旧边和旧文献继续保留 | 已证明 | `REVIEW_INPUT_ONLY`、append-only packet/disposition、历史 projection snapshot；controller attachment 不改变 subject version/state | 无；后续任何自动 route 功能仍必须保持该不变量 |
| 人的处置能触发新的 claim/route review，并把新旧路线并排保留 | 部分完成（代码路径与隔离运行） | v2 已有 owner disposition → isolated `human-review-assessment`；repo-local Zotero 9 三阶段 smoke 验证「共创复核」Note、保留/重审 edge、真实 authority 不变、clone 仍为 `INTAKE`/v0 | 用真实人的 packet 运行 scholarly reviewer；生成新的 problem/collision/route artifact；执行合法 controller decision；重新投影并比较 current/history 链 |
| 插件与 auto-research harness 同时优化 | 部分完成 | harness 增加 knowledge/opportunity/problem-role/derived-question/human-review-assessment typed contracts；插件消费这些对象；105 项 harness tests 通过 | 还缺“全新 topic → worker artifacts → Zotero 阅读 → owner review → 新 route”的完整 v2 演示 run |
| 精确回到 Zotero 原始来源、PDF 与高亮 | 已证明（隔离环境） | 插件在事件发生时生成 user/group-aware `zotero://open-pdf/...page=...&annotation=...`；packet、queue、过程 Note 与 `review-links.md` 保留同一 URI；`Reader.open(..., {annotationID})` 内部重开也已验证 | 仍需在日常 profile 中点击一次真实 packet 链接做人工体验验收 |
| 新 GitHub repo 与本机目录配合 | 已证明 | 插件里程碑已推送到 `24kMengXin/atr-zotero-workbench`；harness 合同已推送到 `24kMengXin/multilingual-aaai`；本机 `.runtime/` 仅承载 gitignored 可丢弃验证态 | 后续每个新 topic 的学术产物仍应按 owner 选择形成独立、可审计的 commit，而不是提交 Zotero profile/data |
| 可安装候选 XPI | 已证明（隔离 profile） | `dist/atr-zotero-workbench.xpi`；静态/XPI 校验通过；隔离 Zotero 9.0.6 真实启动通过 | 日常 profile 尚未人工安装并验收；不得自动覆盖用户 profile |

## 当前最短的真实完成路径

1. 由用户在日常 Zotero 中选择一个当前问题/来源，完成一条真实 typed stance 或 Reader annotation。
2. Codex 运行 `review-human-input`，展示最近受影响节点；用户记录 owner disposition。
3. 对该 packet 另行执行 scoped collision/route review，生成新的 immutable artifact；controller 决定保持、分叉或停放。
4. 重建投影，在 Zotero 中验证旧问题/旧边仍在历史版本，新版本成为 current target。
5. 再从一个全新 topic 使用 v2 worker contract 走完至少 `INTAKE → LANDSCAPE → PROBLEM_CASE`，证明知识图、现实张力和问题森林不是只对迁移样例成立。
6. 审查本地 diff，提交并推送 GitHub；最后在日常 profile 安装候选 XPI 做人工体验验收。
