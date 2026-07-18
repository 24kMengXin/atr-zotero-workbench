# Zotero 插件：构建、安装与验证

`zotero-plugin/` 是 Zotero 7+ bootstrapped extension，使用 manifest v2、`bootstrap.js` 生命周期钩子和 `Zotero.Notifier` 的 item 通知。当前发行包的已测范围以 Zotero 9.0.x 为基线；它没有、也不得直接写 Zotero SQLite。

## 验证层级

构建脚本会先执行 `scripts/validate_zotero_plugin.py`：检查官方要求的 manifest 字段、更新清单、bootstrapped 生命周期、Zotero 9 工具菜单 ID 与 XPI 根目录内容。这让大部分结构性错误在启动 Zotero 前失败。

真正的客户端验证仍应使用独立的开发 profile：通过与插件 ID 同名的 extension proxy file 从源码加载插件，并用 `-ZoteroDebugText`、Run JavaScript 与 Error Console 定位运行时错误。日常 Zotero profile 只用于候选版本的最终 smoke test。一次性配置命令为：

```bash
./scripts/link_zotero_dev.sh \
  /absolute/path/to/a-development-profile \
  /absolute/path/to/a-development-data-dir
```

完整流程、Run JavaScript 探针和日志证据要求见[插件开发守则](zotero-plugin-development.md)。

## 安装

1. 运行 `./scripts/build_zotero_plugin.sh`。
2. Zotero：工具 → 插件 → 齿轮 → **Install Add-on From File…**。
3. 选择 `dist/atr-zotero-workbench.xpi`，在插件列表确认 “ATR Research Workbench” 为启用状态。
4. 不要以覆盖 profile 中同名 `.xpi` 文件代替安装：Zotero 会继续注册旧版本。使用 `scripts/check_installed_plugin_version.py dist/atr-zotero-workbench.xpi <profile-dir>` 核对候选版本与注册版本相同，再完全重启 Zotero。
   该命令也会读取 `extensions.update.autoUpdateDefault` 与插件的 `applyBackgroundUpdates`。如果显示 `BACKGROUND_UPDATES_DISABLED_BY_PROFILE_DEFAULT`，说明更新清单并未失效，而是该插件正在跟随一个已关闭的全局自动更新设置；应通过 Zotero 的插件管理器安装/检查更新，不能修改 `extensions.json` 冒充升级。
5. 重启 Zotero 后，从「工具 → ATR Research」选择标记为“当前权威”的 topic。插件会创建/定位原生 Collection，并打开原生 Topic Note tab。

## 验证人工输入桥

1. 从 ATR topic Collection 打开 problem/claim/source review Note，写入判断并保存。
2. 为已映射来源添加 PDF/EPUB attachment，在原生 Reader 中高亮或评论。
3. 检查所选 topic workspace 的 `human-input/inbox.jsonl` 是否分别出现 `human_note_modified` 与 `human_annotation_modified`。
4. 运行 `review-human-input`，确认反馈只沿显式 source↔decision relation 映射到最近 problem/claim/question。

安装时遇到 UI 确认窗，需要由正在使用 Zotero 的人点击确认；开发者不应编辑 `extensions.json` 来伪造安装或启用状态。
