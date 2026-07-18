# 实现路线图

## P1：ATR v2 原生投影

- 从只读 `atr.sqlite` 和 artifact registry 读取 subject、events、typed artifacts。
- 按 v2 event 顺序显示 timeline；每个节点显示 worker envelope、artifact hash、review_mode 与 disposition。
- 将 v1 adapter 固化为 legacy importer，禁止它产生“事件已发生”的假象。

## P2：原生 Zotero 研究者共创循环

- topic 投影成 Collection；problem/claim/topic 投影成原生 Note；来源使用原生 Reader。
- 捕获带 ATR marker 的 Note 修改和已映射来源的 Reader annotation，保留原文、评论、页码、position、item/attachment key。
- 只沿显式 source↔decision relation 计算最近影响对象，禁止经 run/program/domain containment 污染其他分支。
- 生成 immutable review packet，再由 ATR owner 明确处置；不得覆写人的笔记或自动推进 lifecycle。

## P3：现实问题图谱

- 引入受控的 `inspiration-source` schema（论文 / 新闻 / 技术博客 / 产业报告 / 社媒）。
- 每条现实世界主张需标注来源类型、日期、适用范围与事实/观点状态。
- `research-problem` 必须连接两个 live worlds、一个 discriminator 和一个 falsifier，复用 ATR v2 的 problem-case 要求。

## P4：Zotero 9 companion plugin（已进入候选验证）

- 使用 manifest v2 + bootstrap，在 Tools 菜单提供显式 current/history topic 入口。
- 不创建自定义内容 Tab；使用 Collection、Reader、Note 与 Item Pane。
- 不在插件中实现 controller，不复制或直写 Zotero 数据库。
- 与 Better Notes 并存；ATR marker 只界定回流范围，不接管笔记编辑器。
- 候选包必须先通过结构测试，再在隔离 profile 验证菜单、Note tab、Reader tab 和 annotation bridge。
