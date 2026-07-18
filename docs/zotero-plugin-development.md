# Zotero 插件开发守则

本仓库遵循 **源码侧载优先、发布包后验** 的工作流。不要把日常调试变成反复安装 XPI、重启日常 Zotero 的循环；XPI 仅用于候选版本最终验证。

这不是口号，而是仓库的开发门禁：任何 UI 或事件桥改动，先在源代码、静态契约和独立开发 profile 中留下可观察的证据，再允许生成候选 XPI。

## 依据与版本边界

本守则吸收了 Zotero 中文社区指南的完整导航：Make It Red 的目录/生命周期模型、代理文件侧载、Run JavaScript、`Zotero.debug`/`Zotero.log`、Preference 和 Notifier 的成对注册/释放规则。

- 中文指南首页明确说明其面向 Zotero 7，且部分页面仍待重写；因此它用来规定**开发方法**，不用来猜测当前版本的 DOM ID 或内部 UI API。
- 本项目以 Zotero 9.0.x 为实际兼容基线。所有易变 API（菜单 ID、挂载点、XPI 结构、兼容范围）必须由 `scripts/validate_zotero_plugin.py` 和独立 profile 的运行日志共同确认。
- `manifest.json`/`bootstrap.js` 是扩展不可缺失的入口文件；`rootURI` 可指向解压源码或 XPI 内的 `jar:` 资源，故资源路径必须通过它构造，不能把本地 `file://` 当作应用 UI 的通用途径。

参考： [中文指南首页](https://zotero-chinese.com/plugin-dev-guide/)、[调试代码](https://zotero-chinese.com/plugin-dev-guide/development/debug)、[侧载插件](https://zotero-chinese.com/plugin-dev-guide/development/sideloading)、[引导脚本](https://zotero-chinese.com/plugin-dev-guide/reference/bootstrap)、[事件机制](https://zotero-chinese.com/plugin-dev-guide/reference/notify)。

## 两类环境

| 环境 | 用途 | 不可做的事 |
| --- | --- | --- |
| 独立开发 profile | 源码侧载、功能调试、开发者工具 | 不导入或修改日常文献库 |
| 日常 profile | 已构建 XPI 的一次最终烟测 | 不用于逐次调试，不手改 `extensions.json` |

开发 profile 应是专用的空 profile，路径可在 Zotero Profile Manager 中确认；它还必须对应一个**独立的空 data directory**。Zotero 可能沿用主 profile 的数据目录偏好，因此只隔离 profile 不足以保护日常文献库。不要把本机的主 profile 或日常 data directory 传给下面脚本。

## 一次性配置：源码 proxy file

Zotero 对 bootstrapped extension 支持以“插件 ID 同名的 proxy file”侧载源码。执行：

```bash
./scripts/link_zotero_dev.sh \
  /absolute/path/to/a-development-profile \
  /absolute/path/to/a-development-data-dir
```

该命令会：

1. 构建派生仪表盘，保证 `chrome/content/workbench/` 有当前页面；
2. 在开发 profile 的 `extensions/atr-zotero-workbench@24kmengxin.github.io` 写入 `zotero-plugin/` 的绝对路径；
3. 在该 profile 的 `user.js` 固定独立 data directory；
4. 不安装 XPI、不修改日常 profile，也不碰日常 Zotero SQLite。

重启使用该 profile 的 Zotero 后，插件会直接从 `zotero-plugin/` 加载。改动 JS、bootstrap、manifest 或 XUL/chrome 资源后，重启**开发实例**即可；只有仪表盘生成逻辑或输入数据变化时，需要重新运行该脚本（或 `./scripts/build_zotero_plugin.sh`）以更新打包的派生 HTML。

## 每次改动的验证顺序

1. 先做不启动 Zotero 的检查：

   ```bash
   PYTHONPATH=src python3 -m unittest discover -s tests -v
   ./scripts/build_zotero_plugin.sh
   ```

   后者会验证 manifest、更新清单、全部生命周期 hook、菜单 ID、chrome 注册和 XPI 内容。

2. 只在开发 profile 重新加载插件/重启 Zotero，并从「工具 → 开发者 → Run JavaScript」执行小而可观察的探针；异步代码应 `return` 结果。每次只验证一个断言，例如：

   ```js
   // 菜单是否被当前插件注入
   return !!Zotero.getMainWindows()[0]
     .document.getElementById("atr-zotero-workbench-menuitem");
   ```

   点击「打开 ATR Research Workbench」后，使用第二个探针确认实际 DOM 挂载，而不是只凭“没有报错”判断：

   ```js
   return !!Zotero.getMainWindows()[0]
     .document.getElementById("atr-zotero-workbench-overlay");
   ```

3. 为运行时路径加 `Zotero.debug("ATR Workbench: ...")`，在「帮助 → 输出日志排错 → 查看输出文件」查看；异常用 `Zotero.log` 并在「工具 → 开发者 → Error Console」检查。不要用 `console.log` 作为插件日志。

   工作台还会把结构化运行轨迹追加到 `output/<run>/plugin-runtime.jsonl`：一次正常打开应依次有 `startup_complete`、`open_requested`、`overlay_mounted`、`projection_loaded`、`render_completed`。这是运行时诊断文件，不提交版本库；它既能证明实际 DOM 挂载和投影读取，也不会写入 Zotero 的本地数据库。

4. 在提交说明或 PR 描述中记录本次探针的返回值、相关日志时间段和是否有 Error Console 错误。没有这三项时，状态只能是“未验证”，不能写“已修复”。

5. 只有一个完整用户流程在开发 profile 中通过后，才构建 XPI，并在日常 profile 中做一次安装/启用/菜单可见/核心 UI 可见的烟测。

6. 每个 UI 缺陷都先保留 Error Console 与 debug 日志，再从资源 URL、生命周期、DOM/XUL API 三层定位。不得用复制 XPI 或编辑 profile 数据库来掩盖错误。

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
