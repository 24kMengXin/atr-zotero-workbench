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

## 新 continuation 的可验证状态

`2026-07-18-multilingual-agent-action-continuation` 是新的 continuation，而不是被伪装成历史阶段的合并 run。其当前记录阶段为 `R2_FOCUSED_REVIEW`：

- 111 个去重的历史来源；
- 4 条历史 claim，保存在 `migration/historical-claims.jsonl`，未进入当前 `evidence/claims.jsonl`；
- 采用有明确出处的 FKS frontier map；
- `G2C-CONSTRUCTION` 与所有 claim/proposal gate 仍为 `PENDING`；
- 已记录未晋升的 opportunity-map、topic-routing package、knowledge-context、版本化 research-problem card、item-contract audit、source-grounded concept map 与 contextual inspiration ledger；它们都不替代 claim review。
- 当前 claim ledger 为空，item contract 不足，且尚无真实 Zotero source locator/review packet 或 controller 后续路由决定；这些是继续 R2 而非进入 G3Q 的明确原因。

下一项 system change 只能在新的 source-grounded artifact 或人类阅读反馈显示需要它时实施。
