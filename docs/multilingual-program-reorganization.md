# multilingual-aaai 的研究计划重组

历史目录不是 topic 清单。它们是短期探索、前沿刷新、评测分支、失败重构和控制器元研究的混合物；把每个目录当作独立研究主题会制造虚假的碎片化。

本重组以 [machine-readable program catalog](../programs/multilingual-programs.json) 为权威派生视图，将 28 个历史 run 组织为六个研究计划：

1. 多语言 Agent 行动归因与接口契约（7 个分支）
2. 多语言 Agent 状态、交互与连续性（5 个分支）
3. 多语言 Agent 授权与安全边界（5 个分支）
4. 多语言表示、推理与语料决策（4 个分支）
5. Agent 基础设施与评测契约（5 个分支）
6. ATR 自身的证据与路线治理（2 个分支）

## 首个计划：多语言 Agent 行动归因与接口契约

它的根问题不是“多语言 agent 好不好”，而是：当工具调用表现下降时，如何分开判断行动能力、语言条件化执行接口与评测/本地化伪差异？

```text
行动可靠性
├── 任务/语言/接口政策的归因
│   ├── action-evaluation-attribution
│   ├── FKS multilingual-agent-action（主前沿图）
│   └── evaluation-transport
├── 可验证的语言 contract 与评分
│   └── g1 reconstruction（历史 claim 谱系，保留而不复活旧结论）
├── 企业工作流与可恢复性
│   └── agent-assurance
├── 受控机制探索
│   └── controlled-multilingual-discovery
└── 读者侧跨语言证据可验证性
    └── multilingual-evidence-provenance
```

这七条不是七个待投稿题目：`fks-multilingual-agent-action` 是当前前沿/证据锚点；`g1-reconstruction` 是 claim history；其余是问题、机制、应用或读者验证分支。

## 处置规则

- `canonical_*`：该计划当前的根分支或前沿锚点；
- `merge_as_*`：纳入同一计划的子问题，不再作为独立根 topic；
- `retain_as_*`：保存探索或 claim 历史，显示其旧线但不将其自动升级为当前结论；
- 历史 run 一律只读。此重组不会删除、移动或修改 `multilingual-aaai` 的目录；新程序图只保存对它们的引用。

## 可核查依据

- `fks-multilingual-agent-action` 与 `action-evaluation-attribution` 共享 7 个 source ID；
- capability registration 与 capability contract testbed 共享 4/约 7 个 source ID（Jaccard 0.57），应合并为同一基础设施线；
- `g1-reconstruction` 是唯一有版本化 claim/supersedes 谱系的历史案例，应作为行动归因计划的历史上下文，而不是孤立 topic；
- 两个 ATR 元研究 run 不提供领域问题，应与 multilingual 领域树分开。
