# multilingual-aaai → ATR v2 历史归位矩阵

> 这是只读迁移判定，不改写历史 run。结构检查通过只说明旧契约自洽，不代表它已成为当前 ATR v2 研究链。

## 总体判定

- 覆盖 6 个 program、28 个历史 run；当前 checker 结构通过 28/28。
- 共 391 条来源记录、358 个唯一 source ID、326 个唯一 URL、352 个唯一标题；source ID 重复行 33 条，进入 Zotero 前必须去重。
- access status 已声明 0/391；带定位的全文已检查记录 0/391。因此这些来源目前只能按 metadata/abstract 历史输入处理，不能声称已经下载、阅读或核实全文。
- 28/28 个 run 的当前消费路径已有 manifest；其中逐项 sidecar 共 164 个。它们全部是 `LEGACY_MAPPED`，不能作为新 run 的 canonical 模板。
- 28 个 run 全部归为 `LEGACY_MAP_INPUT_ONLY`：没有发现需要物理删除的 JSON 损坏，但旧 stage、gate、claim 和 route 全部退出 current 权威；清退发生在当前投影与授权层，不破坏历史目录。

## 六个 program 的历史输入剩余限制

| Program | 历史 run | 来源记录 | 成为 current v2 链前必须补齐 |
| --- | ---: | ---: | --- |
| `multilingual-agent-action-attribution` | 7 | 124 | source access/fulltext re-verification with Zotero attachment state；fresh source-grounded semantic review for every reused historical interpretation；current claim/problem versions only after their independent gates |
| `multilingual-agent-state-continuity` | 5 | 32 | source access/fulltext re-verification with Zotero attachment state；fresh source-grounded semantic review for every reused historical interpretation；current claim/problem versions only after their independent gates |
| `multilingual-agent-authorization-safety` | 5 | 50 | source access/fulltext re-verification with Zotero attachment state；fresh source-grounded semantic review for every reused historical interpretation；current claim/problem versions only after their independent gates |
| `multilingual-representation-and-data-decisions` | 4 | 136 | source access/fulltext re-verification with Zotero attachment state；fresh source-grounded semantic review for every reused historical interpretation；current claim/problem versions only after their independent gates |
| `agent-infrastructure-and-evaluation-contracts` | 5 | 31 | source access/fulltext re-verification with Zotero attachment state；fresh source-grounded semantic review for every reused historical interpretation；current claim/problem versions only after their independent gates |
| `atr-research-governance` | 2 | 18 | source access/fulltext re-verification with Zotero attachment state；fresh source-grounded semantic review for every reused historical interpretation；current claim/problem versions only after their independent gates |

## 28 个 run 的逐项归位

| Program | 历史 run | 旧 stage | 来源 / claim | 可复用结构 | 归位动作 |
| --- | --- | --- | ---: | --- | --- |
| `multilingual-agent-action-attribution` | `2026-07-15-g1-reconstruction` | `R3_SEED_PORTFOLIO` | 13 / 4 | 仅基础 ledger | `RETAIN_BRANCH_AFTER_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-action-attribution` | `2026-07-16-action-evaluation-attribution` | `R2_FOCUSED_REVIEW` | 10 / 0 | 仅基础 ledger | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-action-attribution` | `2026-07-16-fks-multilingual-agent-action` | `R3_SEED_PORTFOLIO` | 56 / 0 | frontier, knowledge-context | `PRIORITY_REVIEW_INPUT`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-action-attribution` | `2026-07-17-controlled-multilingual-discovery` | `R2_FOCUSED_REVIEW` | 24 / 0 | frontier | `RETAIN_BRANCH_AFTER_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-action-attribution` | `2026-07-17-multilingual-agent-assurance` | `R3_SEED_PORTFOLIO` | 6 / 0 | frontier, knowledge-context | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-action-attribution` | `2026-07-17-multilingual-agent-evaluation-transport` | `R3_SEED_PORTFOLIO` | 7 / 0 | opportunity | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-action-attribution` | `2026-07-17-multilingual-evidence-provenance` | `R3_SEED_PORTFOLIO` | 8 / 0 | frontier | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-state-continuity` | `2026-07-17-code-switch-agent-control-plane` | `R3_SEED_PORTFOLIO` | 8 / 0 | frontier, knowledge-context, process-events | `PRIORITY_REVIEW_INPUT`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-state-continuity` | `2026-07-17-multilingual-agent-memory-continuity` | `R3_SEED_PORTFOLIO` | 9 / 0 | frontier, knowledge-context, process-events | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-state-continuity` | `2026-07-17-multilingual-agent-coordination` | `R2_FOCUSED_REVIEW` | 5 / 0 | 仅基础 ledger | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-state-continuity` | `2026-07-17-code-switched-speech-tool-grounding` | `R3_SEED_PORTFOLIO` | 6 / 0 | process-events | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-state-continuity` | `2026-07-17-multilingual-gui-locale-attribution` | `R3_SEED_PORTFOLIO` | 4 / 0 | 仅基础 ledger | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-authorization-safety` | `2026-07-17-multilingual-agent-abstention-calibration` | `R3_SEED_PORTFOLIO` | 9 / 0 | opportunity, process-events | `PRIORITY_REVIEW_INPUT`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-authorization-safety` | `2026-07-17-multilingual-agent-safety-boundary` | `R2_FOCUSED_REVIEW` | 9 / 0 | 仅基础 ledger | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-authorization-safety` | `2026-07-17-multilingual-tool-output-injection` | `R3_SEED_PORTFOLIO` | 8 / 3 | 仅基础 ledger | `RETAIN_BRANCH_AFTER_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-authorization-safety` | `2026-07-17-multilingual-pragmatic-action-authorization` | `R3_SEED_PORTFOLIO` | 9 / 0 | opportunity, process-events | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-agent-authorization-safety` | `2026-07-17-multilingual-adaptation-safety` | `R3_SEED_PORTFOLIO` | 15 / 0 | frontier | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-representation-and-data-decisions` | `2026-07-16-mt-reasoning` | `R2_SURVEY` | 102 / 0 | 仅基础 ledger | `RETAIN_BRANCH_AFTER_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-representation-and-data-decisions` | `2026-07-17-multilingual-reasoning-language-mixing` | `R2_FOCUSED_REVIEW` | 5 / 0 | process-events | `RETAIN_BRANCH_AFTER_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-representation-and-data-decisions` | `2026-07-17-fragmentation-assigned-compute-refresh` | `R3_SEED_PORTFOLIO` | 9 / 0 | frontier | `PRIORITY_REVIEW_INPUT`；`LEGACY_MAP_INPUT_ONLY` |
| `multilingual-representation-and-data-decisions` | `2026-07-17-multilingual-curation-decision` | `R2_SURVEY` | 20 / 0 | frontier | `RETAIN_BRANCH_AFTER_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `agent-infrastructure-and-evaluation-contracts` | `2026-07-17-agent-capability-registration` | `R3_SEED_PORTFOLIO` | 5 / 0 | opportunity | `PRIORITY_REVIEW_INPUT`；`LEGACY_MAP_INPUT_ONLY` |
| `agent-infrastructure-and-evaluation-contracts` | `2026-07-17-capability-contract-testbed` | `R3_SEED_PORTFOLIO` | 6 / 0 | opportunity | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `agent-infrastructure-and-evaluation-contracts` | `2026-07-17-agent-evaluation-drift-attribution` | `R3_SEED_PORTFOLIO` | 8 / 0 | opportunity, process-events | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `agent-infrastructure-and-evaluation-contracts` | `2026-07-17-programming-language-agent-affordances` | `R3_SEED_PORTFOLIO` | 6 / 0 | process-events | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `agent-infrastructure-and-evaluation-contracts` | `2026-07-17-skill-capability-containment` | `R3_SEED_PORTFOLIO` | 6 / 0 | opportunity, process-events | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |
| `atr-research-governance` | `2026-07-17-epistemic-route-calibration` | `R3_SEED_PORTFOLIO` | 7 / 0 | opportunity | `PRIORITY_REVIEW_INPUT`；`LEGACY_MAP_INPUT_ONLY` |
| `atr-research-governance` | `2026-07-17-evidence-conditioned-research-exploration` | `R3_SEED_PORTFOLIO` | 11 / 0 | opportunity, process-events | `MERGE_AFTER_DEDUP_AND_REVERIFY`；`LEGACY_MAP_INPUT_ONLY` |

## 清退与保留规则

- 来源 ledger：`REUSE_AFTER_SOURCE_REVERIFICATION`；先按 DOI/URL/标题去重，再补 Zotero attachment、access route、全文检查 locator。
- 旧 claim：`RETAIN_AS_CLAIM_HISTORY`；不得复制为 current claim。
- 旧 frontier/knowledge/opportunity：只作为新 program 综合的输入，必须重新绑定已核查来源和当前 cutoff。
- 旧 gate/route/run-state：只显示为历史过程，绝不迁移其 PASS 或 stage。
- v1.0 未配对 skill event：保留可视化时间线，但从精确 invocation/token 指标中隔离。
- 未分类 prose/code/result：默认 archive，只有获得 artifact-level manifest 和明确父子 lineage 后才进入新链。
