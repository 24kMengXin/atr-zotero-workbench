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

## 新 continuation 的可验证状态

`2026-07-18-multilingual-agent-action-continuation` 是新的 continuation，而不是被伪装成历史阶段的合并 run。其当前记录阶段为 `R2_FOCUSED_REVIEW`：

- 111 个去重的历史来源；
- 4 条历史 claim，保存在 `migration/historical-claims.jsonl`，未进入当前 `evidence/claims.jsonl`；
- 采用有明确出处的 FKS frontier map；
- `G2C-CONSTRUCTION` 与所有 claim/proposal gate 仍为 `PENDING`；
- 已记录未晋升的 opportunity-map、topic-routing package、knowledge-context、版本化 research-problem card、item-contract audit、source-grounded concept map 与 contextual inspiration ledger；它们都不替代 claim review。
- 当前 claim ledger 为空，item contract 不足，且尚无真实 Zotero source locator/review packet 或 controller 后续路由决定；这些是继续 R2 而非进入 G3Q 的明确原因。

下一项 system change 只能在新的 source-grounded artifact 或人类阅读反馈显示需要它时实施。
