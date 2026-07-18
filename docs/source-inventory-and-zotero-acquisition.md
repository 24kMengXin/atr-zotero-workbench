# multilingual 来源归并与 Zotero 获取队列

历史归位之后，`scripts/build_multilingual_source_inventory.py` 对 28 个 run 的来源做**书目身份归并**，但不合并或覆盖历史解释：

- 391 个 legacy occurrence 归并为 344 个 canonical source；
- 47 个重复 occurrence 保留在 `source-occurrences.jsonl`，各自继续携带原 run、program、`supports` 与 `does_not_support`；
- 16 个 canonical source 存在标题/URL/legacy ID 冲突，需要 Zotero/原文复核；
- 两个不同的 AutoResearchBench 记录曾复用 `SRC-AUTORESEARCHBENCH-2026`，现以稳定 digest 后缀分开，避免一个 Zotero item 覆盖另一个；
- 344/344 当前均为 `METADATA_ONLY`，0 个已声明附件，0 个已声明全文检查。

权威派生文件位于 `programs/source-inventory/`：

- `canonical-sources.jsonl`：一个可能的书目对象一行；
- `source-occurrences.jsonl`：每次历史使用一行，绝不因去重丢失；
- `zotero-acquisition-queue.json`：按 canonical/重复频次排序的 Zotero 获取与检查队列。

重建命令：

```bash
python3 scripts/build_multilingual_source_inventory.py \
  programs/multilingual-programs.json \
  --out programs/source-inventory
```

## 进入六条 v2 child 链

`scripts/attach_source_inventory_to_v2.py` 为每个 program 生成独立的 `program-source-inventory`，并以 `SOURCE_REVERIFICATION_QUEUE` 绑定在 child version 0。它不触发 transition。当前规模为：

| Program | Canonical source |
| --- | ---: |
| multilingual agent action attribution | 105 |
| multilingual agent state continuity | 30 |
| multilingual agent authorization/safety | 45 |
| multilingual representation/data decisions | 135 |
| agent infrastructure/evaluation contracts | 27 |
| ATR research governance | 17 |

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
