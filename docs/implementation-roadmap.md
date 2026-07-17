# 后续实现路线图

## P1：ATR v2 原生投影

- 从只读 `atr.sqlite` 和 artifact registry 读取 subject、events、typed artifacts。
- 按 v2 event 顺序显示 timeline；每个节点显示 worker envelope、artifact hash、review_mode 与 disposition。
- 将 v1 adapter 固化为 legacy importer，禁止它产生“事件已发生”的假象。

## P2：研究者共创循环

- 导入 Zotero 注释和 Better Notes 导出的 Markdown（用户选择的 collection）。
- 将人的注释标为 `human_annotation`，保留原文位置、修改时间和 Zotero item key。
- 让 ATR worker 把人的问题作为明确输入 artifact，而不是覆写人的笔记。

## P3：现实问题图谱

- 引入受控的 `inspiration-source` schema（论文 / 新闻 / 技术博客 / 产业报告 / 社媒）。
- 每条现实世界主张需标注来源类型、日期、适用范围与事实/观点状态。
- `research-problem` 必须连接两个 live worlds、一个 discriminator 和一个 falsifier，复用 ATR v2 的 problem-case 要求。

## P4：Zotero companion plugin

- 基于 Zotero 7 manifest + bootstrap 创建只负责启动/深链的 Tab。
- 不在插件中实现 controller 或复制 Zotero 数据库；通过 loopback 只读连接到 workbench。
- 与 Better Notes 并存：把阅读卡作为模板/链接，不接管用户笔记。
