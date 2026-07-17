# Zotero 插件：构建、安装与验证

`zotero-plugin/` 是 Zotero 7+ bootstrapped extension，使用 manifest v2、`bootstrap.js` 生命周期钩子和 `Zotero.Notifier` 的 item 通知。兼容范围为 6.999–100.*，以覆盖本机当前 Zotero 9。它没有、也不得直接写 Zotero SQLite。

## 安装

1. 运行 `./scripts/build_zotero_plugin.sh`。
2. Zotero：工具 → 插件 → 齿轮 → **Install Add-on From File…**。
3. 选择 `dist/atr-zotero-workbench.xpi`，在插件列表确认 “ATR Research Workbench” 为启用状态。
4. 重启 Zotero 后，从工具菜单选择“打开 ATR Research Workbench”。

## 验证人工输入桥

1. 导入 `output/multilingual/zotero/items.csl.json`，或通过 `sync` 创建带 `ATR source ID` 的论文和笔记。
2. 在任一子笔记写入自己的判断并保存。
3. 检查 `output/multilingual/human-input/inbox.jsonl` 是否多出 `human_note_modified` 事件。
4. 运行 `review-human-input`，检查 `affected_research_questions` 与该文献的 source ID 对应。

安装时遇到 UI 确认窗，需要由正在使用 Zotero 的人点击确认；开发者不应编辑 `extensions.json` 来伪造安装或启用状态。
