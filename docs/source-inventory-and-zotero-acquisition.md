# multilingual 来源归并与 Zotero 获取队列

历史归位之后，`scripts/build_multilingual_source_inventory.py` 对 28 个 run 的来源做**书目身份归并**，并从六个 current child 的 content-addressed、source-reviewed knowledge-map artifact 补齐后来新增的来源；它不读取 Zotero/graph 投影作为 authority，也不合并或覆盖历史解释：

- 391 个 legacy occurrence 归并为 344 个 canonical source；current v2 审阅层另外补入 8 个历史账本没有的来源，因此统一账本现为 399 个 occurrence / 352 个 canonical source；
- 47 个重复 occurrence 保留在 `source-occurrences.jsonl`，各自继续携带原 run、program、`supports` 与 `does_not_support`；
- 16 个 canonical source 存在标题/URL/legacy ID 冲突，需要 Zotero/原文复核；
- 两个不同的 AutoResearchBench 记录曾复用 `SRC-AUTORESEARCHBENCH-2026`，现以稳定 digest 后缀分开，避免一个 Zotero item 覆盖另一个；
- 8 个新增 occurrence 明确标记 `CURRENT_V2_REVIEWED_SOURCE`、不可变 artifact digest、locator 和 `FULLTEXT_INSPECTED`；这是 worker 检查状态，不等于人的阅读，也不等于 Zotero attachment。其余历史来源仍不从 URL 推断全文状态。

权威派生文件位于 `programs/source-inventory/`：

- `canonical-sources.jsonl`：一个可能的书目对象一行；
- `source-occurrences.jsonl`：每次历史使用一行，绝不因去重丢失；
- `zotero-acquisition-queue.json`：按 canonical/重复频次排序的 Zotero 获取与检查队列。
- `zotero-local-reconciliation.json`：只读 local API 对账快照；严格身份匹配、本地 PDF 摘要、Zotero item/attachment key 与 annotation 数分开记录。

2026-07-19 对日常 Zotero 的实查现覆盖全部 352 个 canonical source：148 个顶层条目中，9 个严格匹配；其中 7 个确认存在本地 PDF，2 个只有书目；另有 3 个仅标题相同，保持 `IDENTITY_REVIEW_REQUIRED`；340 个未找到。7 个 PDF 均记录 SHA-256，但全部仍是 `ATTACHED_NOT_INSPECTED`，不能据此宣称 worker 或人已读全文。current v2 的 8 个 worker-inspected 来源全部尚未在日常 Zotero 找到，状态边界没有被合并。第一次实现曾错误删除 OpenReview `?id=` 并造成四篇论文碰撞，已清退该结果、改为站点感知归一化并加入回归门禁。详见 [Zotero 本地对账](source-inventory-zotero-reconciliation.md)。

重建命令：

```bash
python3 scripts/build_multilingual_source_inventory.py \
  programs/multilingual-programs.json \
  --current-registry programs/v2-intakes/program-registry.json \
  --runs-root /path/to/multilingual-aaai/research-runs \
  --out programs/source-inventory
```

## 进入六条 v2 child 链

`scripts/attach_source_inventory_to_v2.py` 为每个 program 生成独立的 `program-source-inventory`，并以 `SOURCE_REVERIFICATION_QUEUE` 绑定在 child version 0。它不触发 transition。当前规模为：

| Program | Canonical source |
| --- | ---: |
| multilingual agent action attribution | 106 |
| multilingual agent state continuity | 31 |
| multilingual agent authorization/safety | 46 |
| multilingual representation/data decisions | 137 |
| agent infrastructure/evaluation contracts | 29 |
| ATR research governance | 18 |

跨 program 的同一 canonical source 使用同一稳定 source ID，因此 Zotero 同步必须复用既有 item，而不是复制条目。

## 获取与阅读状态机

```text
METADATA_ONLY
  → 在现有 Zotero 库中按 DOI / URL / 精确标题解析
  → RESOLVER_CANDIDATE 或 ACCESS_REQUIRED
  → Zotero 原生 resolver / OA / 机构访问 / 用户提供文件
  → FULLTEXT_ATTACHED（有可读 attachment 与 Zotero key）
  → FULLTEXT_INSPECTED（有页码/章节/annotation locator）
  → 才可复核历史 supports / does_not_support
```

URL、DOI、候选 PDF URL、插件导入尝试都不等于附件成功；附件成功也不等于内容已经阅读。插件必须分别展示和回传这几个状态。

## 不可越过的边界

- canonicalization 只判断“可能是同一书目对象”，不证明引用版本相同；
- 历史 occurrence 的不同解释不得合并成一条新 claim；
- identity conflict 未解决前不得自动创建 Zotero duplicate 或当前知识边；
- 来源只有在真实 attachment 存在后才显示“全文已获取”；
- 只有带 locator 的人工/worker 阅读记录才显示“全文已检查”。
