# Harness × Zotero 对齐发现

这份记录只收录在真实 continuation migration、结构检查或 Zotero 映射中复现的问题；它不是预先设想的重构愿望清单。

| ID | 复现证据 | 判定 | 修复/处置 |
| --- | --- | --- | --- |
| HZ-001 | `init_run.py` 生成 `harness_release: 0.8.0`，而仓库 README/registry 是 0.9.0 | 初始化元数据错误，会误导迁移政策 | 初始化器改为 0.9.0；新 continuation 已验证 |
| HZ-002 | 0.9 schema 要求 `G2C-CONSTRUCTION`，初始化器未写入；旧 `check_run.py` 仍返回 pass | 新 run 不符合自身 schema，审计漏检 | 初始化器补 gate；checker 对 0.9+ run 强制检查，旧 0.6–0.8 run 保持历史兼容 |
| HZ-003 | direction run 要求 frontier map，但初始化器不创建 `knowledge/` | 新 run 的首个必需 artifact 没有明确落点 | 初始化器创建 `knowledge/`；continuation 已验证 |
| HZ-004 | 历史 run 大多只有 sources/frontier，缺 current claim、knowledge-context、opportunity-map、problem-card、source locator | 不能把“有论文”误判为“有完整研究链” | continuation 将来源与历史 claim 放入 migration baseline；当前 claim ledger 留空，并写 `MISSING_ARTIFACTS.md` |
| HZ-005 | Zotero 的核心单元是阅读定位与人的判断，旧 ATR source ledger 只记录 source-level supports/does-not-support | source 不能直接等价为 claim review unit | 工作台采用 claim review note、locator、stance 与 immutable human-review-packet；当前仍需真实 Zotero 阅读来填充 |

## 新 continuation 的可验证状态

`2026-07-18-multilingual-agent-action-continuation` 是新的 `R0_INTAKE`，而不是被伪装成历史阶段的合并 run：

- 111 个去重的历史来源；
- 4 条历史 claim，保存在 `migration/historical-claims.jsonl`，未进入当前 `evidence/claims.jsonl`；
- 采用有明确出处的 FKS frontier map；
- `G2C-CONSTRUCTION` 为 `PENDING`；
- 仍缺 topic-routing、knowledge-context、opportunity-map、problem cards、当前 claims、来源定位和人的 review packets。

下一项 system change 只能在新的 source-grounded artifact 或人类阅读反馈显示需要它时实施。
