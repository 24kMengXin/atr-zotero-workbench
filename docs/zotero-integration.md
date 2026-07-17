# Zotero 集成决策记录

调研于 2026-07-18：中文社区的开发指南说明该指南面向 Zotero 7，且仍在重写；其 `Zotero_Tabs` 接口可用于将来制作嵌入式图谱标签页。Better Notes 提供双链、模板及 Markdown 导出，是人的阅读注解层。官方 Zotero 文档说明客户端插件运行于内部 JavaScript API；也明确建议外部工具考虑 Web API，或仅只读客户端 SQLite。

## 采用的分层

- **现在：外部 workbench + CSL-JSON + Markdown cards。** 零账户配置即可导入书目并建立阅读工作流。
- **可选：Zotero Web API。** 使用写权限 API key 创建 collection、论文条目和 child note。写操作有显式命令和审计日志。
- **以后：Zotero 7 companion plugin。** 仅提供当前图谱的 Tab/命令入口和 deep link，不复制图计算或研究状态机。

这能复用 Better Notes 的人类批注能力，同时避免插件 API 的版本耦合。不得直接写 `zotero.sqlite`；即使读取亦不作为 MVP 依赖。

参考：<https://zotero-chinese.com/plugin-dev-guide/>、<https://zotero-chinese.com/user-guide/plugins/better-notes>、<https://www.zotero.org/support/dev/client_coding/plugin_development>、<https://www.zotero.org/support/dev/web_api/v3/write_requests>。
