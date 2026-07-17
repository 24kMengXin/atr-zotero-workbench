# Zotero 插件开发守则

本仓库遵循 **源码侧载优先、发布包后验** 的工作流。不要把日常调试变成反复安装 XPI、重启日常 Zotero 的循环；XPI 仅用于候选版本最终验证。

## 两类环境

| 环境 | 用途 | 不可做的事 |
| --- | --- | --- |
| 独立开发 profile | 源码侧载、功能调试、开发者工具 | 不导入或修改日常文献库 |
| 日常 profile | 已构建 XPI 的一次最终烟测 | 不用于逐次调试，不手改 `extensions.json` |

开发 profile 应是专用的空 profile，路径可在 Zotero Profile Manager 中确认。不要把本机的主 profile 传给下面脚本。

## 一次性配置：源码 proxy file

Zotero 对 bootstrapped extension 支持以“插件 ID 同名的 proxy file”侧载源码。执行：

```bash
./scripts/link_zotero_dev.sh /absolute/path/to/a-development-profile
```

该命令会：

1. 构建派生仪表盘，保证 `chrome/content/workbench/` 有当前页面；
2. 在开发 profile 的 `extensions/atr-zotero-workbench@24kmengxin.github.io` 写入 `zotero-plugin/` 的绝对路径；
3. 不安装 XPI、不修改日常 profile，也不碰 Zotero SQLite。

重启使用该 profile 的 Zotero 后，插件会直接从 `zotero-plugin/` 加载。改动 JS、bootstrap、manifest 或 XUL/chrome 资源后，重启**开发实例**即可；只有仪表盘生成逻辑或输入数据变化时，需要重新运行该脚本（或 `./scripts/build_zotero_plugin.sh`）以更新打包的派生 HTML。

## 每次改动的验证顺序

1. 先做不启动 Zotero 的检查：

   ```bash
   PYTHONPATH=src python3 -m unittest discover -s tests -v
   ./scripts/build_zotero_plugin.sh
   ```

   后者会验证 manifest、更新清单、全部生命周期 hook、菜单 ID、chrome 注册和 XPI 内容。

2. 只在开发 profile 重启 Zotero，并从「工具 → 开发者 → Run JavaScript」执行小而可观察的探针；异步代码应 `return` 结果。

3. 为运行时路径加 `Zotero.debug("ATR Workbench: ...")`，在「帮助 → 输出日志排错 → 查看输出文件」查看；异常用 `Zotero.log` 并在「工具 → 开发者 → Error Console」检查。不要用 `console.log` 作为插件日志。

4. 只有一个完整用户流程在开发 profile 中通过后，才构建 XPI，并在日常 profile 中做一次安装/启用/菜单可见/核心 UI 可见的烟测。

5. 每个 UI 缺陷都先保留 Error Console 与 debug 日志，再从资源 URL、生命周期、DOM/XUL API 三层定位。不得用复制 XPI 或编辑 profile 数据库来掩盖错误。

## 生命周期与状态约束

- `startup` 负责一次性初始化和 chrome 注册；`shutdown` 必须撤销相应资源。
- 对每个 `Zotero.Notifier.registerObserver` 都必须有对应的 `unregisterObserver`；窗口注入的元素也必须在 unload/shutdown 移除。
- `rootURI` 对 XPI 是 `jar:file:///.../`，它以 `/` 结束；仅用于拼接插件自带资源，不能假定普通 `file://` 页面可在 Zotero UI 中加载。
- 偏好项只保存短小的用户设置；不能用作大数据或临时日志，并且不要引导用户手改 profile 的 `prefs.js`。
- 插件不直接读写 Zotero 本地 SQLite。对条目和笔记的更改使用 Zotero API 与 Notifier。

## 发布前门禁

发布包必须同时满足：

- `manifest.json` 的 ID、版本、兼容范围和 `update_url` 正确；
- `update.json` 的 add-on ID 与 manifest 一致；
- XPI 可解压且包含启动所需脚本、chrome 页面与生成仪表盘；
- 新建/干净 profile 可安装、启用、显示菜单；
- 用一条实际 Zotero 笔记修改验证 `human-input/inbox.jsonl` 事件桥；
- 日常 profile 的最终烟测没有新增 Error Console 报错。

## 调试启动命令

需要检查 DOM、网络和断点时，以开发 profile 启动 Zotero 并启用文本日志：

```bash
/Applications/Zotero.app/Contents/MacOS/zotero -ZoteroDebugText -profile /absolute/path/to/a-development-profile
```

Firefox 开发者工具可用于更深入的 UI 调试；优先在单独的 Zotero Beta/开发实例使用它，不替代上述静态检查与运行日志。
