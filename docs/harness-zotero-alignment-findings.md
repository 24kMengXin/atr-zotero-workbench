# Harness × Zotero 对齐发现

这份记录只收录在真实 continuation migration、结构检查或 Zotero 映射中复现的问题；它不是预先设想的重构愿望清单。

| ID | 复现证据 | 判定 | 修复/处置 |
| --- | --- | --- | --- |
| HZ-001 | `init_run.py` 生成 `harness_release: 0.8.0`，而仓库 README/registry 是 0.9.0 | 初始化元数据错误，会误导迁移政策 | 初始化器改为 0.9.0；新 continuation 已验证 |
| HZ-002 | 0.9 schema 要求 `G2C-CONSTRUCTION`，初始化器未写入；旧 `check_run.py` 仍返回 pass | 新 run 不符合自身 schema，审计漏检 | 初始化器补 gate；checker 对 0.9+ run 强制检查，旧 0.6–0.8 run 保持历史兼容 |
| HZ-003 | direction run 要求 frontier map，但初始化器不创建 `knowledge/` | 新 run 的首个必需 artifact 没有明确落点 | 初始化器创建 `knowledge/`；continuation 已验证 |
| HZ-004 | 历史 run 大多只有 sources/frontier，缺 current claim、knowledge-context、opportunity-map、problem-card、source locator | 不能把“有论文”误判为“有完整研究链” | continuation 将来源与历史 claim 放入 migration baseline；当前 claim ledger 留空，并写 `MISSING_ARTIFACTS.md` |
| HZ-005 | Zotero 的核心单元是阅读定位与人的判断，旧 ATR source ledger 只记录 source-level supports/does-not-support | source 不能直接等价为 claim review unit | 工作台采用 claim review note、locator、stance 与 immutable human-review-packet；当前仍需真实 Zotero 阅读来填充 |
| HZ-006 | 真实 continuation 的 `opportunity-map` 能通过 harness validator，但工作台投影得到空标题、空后果、空证据边界：validator 只检查 signal 数量，插件依赖另一组字段 | 跨系统 artifact 契约不完整；“可验证”不等于“可读、可审查” | validator 现在要求 actor、incumbent practice、observed tension、material consequence、candidate construct、does-not-establish、rival explanations 与 required academic evidence；新增回归测试，并以真实 artifact 重投影验证 |
| HZ-007 | workbench 已能把 Zotero 的 review packet 记录为 append-only owner disposition，但旧 `check_run.py` 不读取该账本；首次接入又把不存在的新账本当成旧 run 的必需文件 | 人类反馈缺少 controller 侧结构约束；反向强制新文件又会让真实历史 run 失效 | checker 对**存在的** `decisions/human-review-dispositions.jsonl` 验证唯一 decision/packet、允许处置、明确 target 与 non-authorizing boundary；账本缺席代表“尚无处置”，保持旧 run 可读。87 项 harness 回归和 continuation structural/referential check 已通过。 |
| HZ-008 | 用户级 auto-research skill 已使用 v2 SQLite controller，但维护仓库只保留 v0.9 JSON harness；workbench 无法把已批准的人类 packet 交给 v2 | 已安装运行时与受版本控制源码漂移，且“写入 disposition”没有形成 controller 可消费证据 | v2 controller、worker contract 与回归测试已纳入 harness 源码；workbench 只在 disposition hash 匹配后执行 `ingest → attach`，返回最近受影响节点。临时端到端 run 已验证 attachment 出现在导出 ledger，而 subject 保持 `INTAKE`/version 0；后续 transition 仍需要独立 review artifact。 |
| HZ-009 | 历史 multilingual continuation 是 v0.9 `R2_FOCUSED_REVIEW`，不能把其旧 stage 直接写入 v2 SQLite；但其中的 baseline、source-grounded concept map 与问题卡有复用价值 | 若直接“迁移阶段”，会伪造 v2 的 transition 和 current claim；若完全不带历史材料，新 controller 又失去可阅读的起点 | 新建 `2026-07-18-multilingual-agent-action-v2-intake`：注册历史 baseline、两条明确来源支撑的 knowledge-map，及一个含 3 个 source span、3 种竞争解释、判别器和证伪条件的 problem-case；后二者均只是 attachment。subject 停在 `INTAKE`/version 0；controller check 通过，workbench 从 SQLite 投影 3 个来源、6 个概念、1 张问题卡和 2 个非授权 attachment。 |
| HZ-010 | v2 最初允许宽松 knowledge/problem JSON，不能保证 knowledge 边界、现实信号独立性、论文问题姿态或派生问题来源 | 插件可以“显示一个节点”，却无法证明节点有足够信息供人阅读审查 | v2 新增严格 `knowledge-map`、`opportunity-map`、`problem-case` 契约；从 continuation 可复现生成并追加 3 类新 artifact。所有 attachment 均绑定 subject version 0 且不改变 `INTAKE`；旧 digest 原样保留。 |
| HZ-011 | 同一 `map_id/problem_id` 追加严格版本后，workbench 把新旧 artifact 投影为相同 graph node ID，native validator 报 duplicate marker/object | append-only authority 与“当前对象唯一”之间缺少版本映射；删除旧 artifact 会破坏审计 | 最新 artifact 保持 canonical node ID，旧 artifact 使用 `@<digest-prefix>` 稳定 ID；knowledge/problem/derived-question 建立显式 supersession，旧 Note 进入「历史版本」。真实 v2 Zotero 9 smoke 验证 12 个知识 Note（6 旧+6 新）、4 个问题版本、9 个派生问题版本、1 个当前张力，current/historical 不混淆。 |
| HZ-012 | packet 和 owner disposition 已能进入 v2，但过程只显示“待审查”；没有结构化位置记录 reviewer 的认知更新、保留对象和另写版本请求 | 若直接改 problem/claim 会抹掉人的输入到系统判断之间的审计层；若只保留 pending queue，又无法形成真正共创 | v2 新增隔离 `human-review-assessment`：强制 owner/reviewer 分离、证据与非证据边界、保留/重审对象互斥、outcome→follow-up kind 一致；它只作为 attachment。插件新增原生「05 · 共创复核」Collection/Note，可跳回来源和问题。repo-local Zotero 9 三阶段 smoke 验证真实 authority 哈希不变、clone 仍为 `INTAKE`/v0、assessment Note 唯一可见。 |
| HZ-013 | 第一轮 claim-scoped review 发现：action 与 infra 的宽泛问题已被相邻工作实质覆盖，state 只有可疑的剩余边界；若插件只显示 problem-case 与 opaque attachment，人无法看出“碰撞了什么、还剩什么、下一证据是什么” | problem-case 不是 topic 终点，worker review 也不是 gate；必须把负面/收窄判断作为问题的子级历史对象，而不是悄悄改写问题或新建 topic | 三个真实 authority 追加 `collision-review` attachment，均保持 `INTAKE`/v0；action/infra=`REFRAME`，state=`NEEDS_EVIDENCE`。workbench 投影五类 collision、coverage limits、surviving boundary、alternatives 与 next evidence；Zotero 将其作为问题卡子 Collection/Note，并把受检论文放入同一阅读上下文。 |
| HZ-014 | 获取 UniToolCall 时，第一次 arXiv PDF 下载得到可读但标题完全无关的论文；URL 成功、PDF 可解析和 SHA-256 都不能证明 bibliographic identity | acquisition/inspection/Zotero-state 四元组仍缺“文件是不是目标论文”这一独立状态；若不校验，错误全文也会被标成 `FULLTEXT_INSPECTED` | 错误文件被隔离并删除，重新解析正确 arXiv identity 后才进入 review；新增 `HCH-source-identity-before-fulltext-inspected-v1` SHADOW card，要求候选 DOI/arXiv ID、landing title、PDF metadata/first-page title 至少两种信号核对，并分开记录 VERIFIED/AMBIGUOUS/MISMATCH。 |
| HZ-015 | 六条 collision review 的 7 篇全文已在 repo cache 完成书目身份和摘要核验，但 Zotero 仍只有 metadata item；若插件静默把 repo path 当附件，人的离线阅读、同步和 attachment key 都不成立 | `IDENTITY_VERIFIED`、repo cache、Zotero stored attachment 与 human inspection 是四个不同状态；artifact 创建时不能预填未来的 Zotero item/attachment key | 六个 child 各追加 immutable `SOURCE_ACQUISITION_TO_ZOTERO_HANDOFF`，均保持 `INTAKE`/v0；明确点击阅读时，插件重新校验 SHA-256 后才调用 `importFromFile` 复制进 Zotero 管理。隔离 Zotero 9 已验证 UniToolCall 的 stored attachment、Reader annotation、source Note 和精确 deep link。 |
| HZ-016 | UniToolCall annotation 已精确映射到 source，但回流算法找不到研究问题；图中真实链是 `paper → collision review → research problem`，旧传播白名单只允许 paper 直接连 decision object | collision review 是显式的 claim-scoped 中介，不应因不是 claim/problem 节点而截断；同时不能放开 artifact/run/collection containment 造成无边界传播 | 反馈传播白名单只新增 `inspects_for_collision` 与 `is_claim_scoped_reviewed_by`；回归测试证明最近问题距离为 2，旁支 `contains` problem 不会进入 affected set。 |
| HZ-017 | 六条 R0 knowledge scaffold 各有 6 个概念和 `source_ids`，但全部是 metadata-only；v2 validator 不要求 locator、定义与来源的关系或逐节点核验状态，插件因而只能显示一棵“看起来有引用”的树 | citation membership 不是 source review；若没有 `DEFINES/DISTINGUISHES/CHALLENGES/LIMITS` 和原文跨度，人无法从概念回到原文核对，也无法区分已支撑、部分支撑、被挑战和待补证据 | v2 保留 1.0 历史兼容，新增 knowledge-map 1.1 强制 source inspection spans、逐概念 review status 和 located evidence spans；六个 child 各追加一张新版本。36 个 current 概念分为 12 bounded、12 partial、6 challenged、6 pending；旧 36 节点进入 Zotero 历史版本，authority 仍为 `INTAKE`/v0。 |
| HZ-018 | collision-review Note 有 graph marker，但人的修改未被 notifier 识别 | worker 内容只读不等于人不能围绕它追加 owner review；原实现会丢失关键科研判断 | 插件与 impact contract 增加精确 collision-review target、理由必填的折叠 owner input，以及到父问题的唯一显式传播；隔离 smoke 证明形成独立 review packet且 lifecycle effect 仍为 NONE |
| HZ-019 | 3 条 `NO_ADMISSIBLE_SIGNAL` 在 harness 中是明确的负面裁决，工作台却只诊断 `missing opportunity_map` | “没有合格现实信号”不是漏跑，也不能被补成张力；隐藏该裁决会让用户无法审查科研品味和停止理由 | 新增 `reality_signal_gap` 只读投影与原生 Zotero Note；列出 bounded search、缺失来源功能、下一合法工作和非结论边界，链接受检来源；人的 Note 反馈只命中该负面证据对象，不凭空连接研究问题 |

## 新 continuation 的可验证状态

`2026-07-18-multilingual-agent-action-continuation` 是新的 continuation，而不是被伪装成历史阶段的合并 run。其当前记录阶段为 `R2_FOCUSED_REVIEW`：

- 111 个去重的历史来源；
- 4 条历史 claim，保存在 `migration/historical-claims.jsonl`，未进入当前 `evidence/claims.jsonl`；
- 采用有明确出处的 FKS frontier map；
- `G2C-CONSTRUCTION` 与所有 claim/proposal gate 仍为 `PENDING`；
- 已记录未晋升的 opportunity-map、topic-routing package、knowledge-context、版本化 research-problem card、item-contract audit、source-grounded concept map 与 contextual inspiration ledger；它们都不替代 claim review。
- 当前 claim ledger 为空，item contract 不足，且尚无真实 Zotero source locator/review packet 或 controller 后续路由决定；这些是继续 R2 而非进入 G3Q 的明确原因。

下一项 system change 只能在新的 source-grounded artifact 或人类阅读反馈显示需要它时实施。
## HZ-018 · collision-review Note 曾经可见但不可作为精确反馈目标

- 现象：collision-review 已投影为 Zotero Note，并有 `ATR Graph Node` marker；但 `markerFromNote()` 与 `noteChanged()` 没有识别 `ATR Collision Review`，所以人在该 Note 中写的 owner 判断可能不会进入 Codex inbox。
- 根因：native mapping 把 collision review 当作只读 worker 输出，却没有区分“worker 内容不可被覆盖”和“人必须能围绕该对象追加独立 review input”。
- 修正：feedback target priority 增加 `collision_review`；插件识别精确 marker，提供需要非空理由的 `ACCEPT_REFRAME / REQUEST_MORE_EVIDENCE / PARK_TOPIC / RETIRE_CANDIDATE` 人类输入，并保持 `REVIEW_INPUT_ONLY`；impact BFS 只沿 `is_claim_scoped_reviewed_by` 到父问题，不沿 run/collection containment 扩散。
- 证据：新增单元测试证明 collision-review Note 是距离 0 的显式决策对象、父问题距离 1；隔离 Zotero 9 smoke 证明 typed input、rationale、exact graph node 均进入第三个 immutable review packet，authority 未变。
