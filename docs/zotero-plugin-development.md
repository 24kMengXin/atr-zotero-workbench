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

1. 运行静态契约并构建候选 XPI；
2. 在开发 profile 的 `extensions/atr-zotero-workbench@24kmengxin.github.io` 写入 `zotero-plugin/` 的绝对路径；
3. 在该 profile 的 `user.js` 固定独立 data directory；
4. 仅在该 disposable 开发 profile 中关闭“自动禁用外部侧载”策略，使源码 proxy 首次启动即可启用；
5. 不安装 XPI、不修改日常 profile，也不碰日常 Zotero SQLite。

重启使用该 profile 的 Zotero 后，插件会直接从 `zotero-plugin/` 加载。改动 JS、bootstrap、manifest 或 Fluent 资源后，重启**开发实例**即可。ATR graph 由 registry 指向的 workspace 在运行时读取，不再复制进 XPI。

## 每次改动的验证顺序

1. 先做不启动 Zotero 的检查：

   ```bash
   PYTHONPATH=src python3 -m unittest discover -s tests -v
   ./scripts/build_zotero_plugin.sh
   ```

   后者验证 manifest、更新清单、全部生命周期 hook、菜单 ID、Fluent 资源、XPI 内容和原生交互契约。它还显式禁止 `zotero-pane-stack` overlay、自定义 dashboard 页面或缺失 Reader/Note/Item Pane API 的构建。构建插件不会重写任何 ATR graph 或历史快照。

2. 只在开发 profile 重新加载插件/重启 Zotero，并从「工具 → 开发者 → Run JavaScript」执行小而可观察的探针；异步代码应 `return` 结果。每次只验证一个断言，例如：

   若环境没有 GUI 自动化权限，可只在 disposable 开发 profile 的 `user.js` 设置
   `user_pref("extensions.atr-zotero-workbench.devSmokeTestOnStartup", true);`。插件会在启动时自动执行一次“当前权威 topic → Collection → Topic Note tab”的同一路径，并把结果写入 `plugin-runtime.jsonl`；该偏好默认关闭，不能用于日常 profile。

   要连带验证 problem Note 的 Notifier 回流，可再设置
   `user_pref("extensions.atr-zotero-workbench.devSmokeFeedbackOnStartup", true);`，但必须同时把 registry 指向本仓库 `.runtime/zotero-smoke/workspace/` 下的测试 workspace，禁止向真实 run 写入合成反馈。

   ```js
   // 菜单是否被当前插件注入
   return !!Zotero.getMainWindows()[0]
     .document.getElementById("atr-zotero-workbench-menu");
   ```

   从「工具 → ATR Research」打开一个 topic 后，用第二个探针确认结果是原生 Note tab，而不是插件自建页面：

   ```js
   return Zotero.getMainWindows()[0].Zotero_Tabs._tabs
     .filter(tab => tab.type === "note")
     .map(tab => ({ id: tab.id, title: tab.title, itemID: tab.data.itemID }));
   ```

   打开来源后验证 Reader tab：

   ```js
   return Zotero.getMainWindows()[0].Zotero_Tabs._tabs
     .filter(tab => tab.type === "reader")
     .map(tab => ({ id: tab.id, title: tab.title, itemID: tab.data.itemID }));
   ```

3. 为运行时路径加 `Zotero.debug("ATR Workbench: ...")`，在「帮助 → 输出日志排错 → 查看输出文件」查看；异常用 `Zotero.log` 并在「工具 → 开发者 → Error Console」检查。不要用 `console.log` 作为插件日志。

   插件还会把结构化运行轨迹追加到 `output/<run>/plugin-runtime.jsonl`：一次正常打开应包含 `startup_complete`、`projection_loaded`、`native_topic_synced`、`native_note_tab_opened`；打开有附件的来源后还应出现 `native_reader_tab_opened`。这是运行时诊断文件，不提交版本库。

4. 在提交说明或 PR 描述中记录本次探针的返回值、相关日志时间段和是否有 Error Console 错误。没有这三项时，状态只能是“未验证”，不能写“已修复”。

5. 只有一个完整用户流程在开发 profile 中通过后，才构建 XPI，并在日常 profile 中做一次安装/启用/菜单可见/核心 UI 可见的烟测。

6. 每个 UI 缺陷都先保留 Error Console 与 debug 日志，再从资源 URL、生命周期、DOM/XUL API 三层定位。不得用复制 XPI 或编辑 profile 数据库来掩盖错误。

## 生命周期与状态约束

- `startup` 负责一次性初始化 Item Pane、菜单和 Notifier；`shutdown` 必须撤销相应资源。
- 对每个 `Zotero.Notifier.registerObserver` 都必须有对应的 `unregisterObserver`；窗口注入的元素也必须在 unload/shutdown 移除。
- `rootURI` 对 XPI 是 `jar:file:///.../`，它以 `/` 结束；仅用于加载插件脚本。插件不再把 HTML 页面作为主界面载入 Zotero。
- 偏好项只保存短小的用户设置；不能用作大数据或临时日志，并且不要引导用户手改 profile 的 `prefs.js`。
- 插件不直接读写 Zotero 本地 SQLite。对条目和笔记的更改使用 Zotero API 与 Notifier。

## 发布前门禁

发布包必须同时满足：

- `manifest.json` 的 ID、版本、兼容范围和 `update_url` 正确；
- `update.json` 的 add-on ID 与 manifest 一致；
- XPI 可解压且只包含启动脚本、manifest、偏好和 Fluent 资源；
- 新建/干净 profile 可安装、启用、显示 topic 菜单和 ATR Item Pane section；
- 用一条实际 Zotero Note 修改和一条 Reader annotation 验证 `human-input/inbox.jsonl` 事件桥；
- 验证 Collection 归属等 Note 元数据变化不会进入认知反馈；每条接受事件携带 `input_origin=ZOTERO_NOTIFIER`；
- 验证 annotation 事件中的 `zotero_open_uri` 同时包含 attachment key、PDF page 和 annotation key，且 user/group scope 在事件发生时解析；

Deep-link 形状以 Zotero 当前
[`ZoteroProtocolHandler.mjs`](https://github.com/zotero/zotero/blob/main/chrome/content/zotero/ZoteroProtocolHandler.mjs)
的 `open-pdf` router 为准：user library 使用 `library/items/:objectKey`，group
library 使用 `groups/:groupID/items/:objectKey`，`annotation` query 被解析为
Reader `annotationID`。不要从论坛示例或文献标题反推 attachment key。
- topic/source 分别在原生 Note/Reader tab 打开，没有 `zotero-pane-stack` overlay；
- 日常 profile 的最终烟测没有新增 Error Console 报错。

## 调试启动命令

仓库内的可重复 smoke harness 使用 `.runtime/zotero-smoke/`，不再把 profile、fixture 或日志散落在系统 `/tmp`：

```bash
python3 scripts/prepare_zotero_smoke.py --reset
./scripts/run_zotero_smoke.sh
# 自动路径完成后退出该 Zotero 实例
python3 scripts/verify_zotero_smoke.py
```

要单独验证 DOI-only 条目经过 Zotero 原生 available-file resolver，而不是回退到
artifact 的 `pdf_url`，使用
`python3 scripts/prepare_zotero_smoke.py --reset --native-resolver --run-key human-ai-scholarly-coreading`，
再运行同一启动与 verifier 命令。该模式只在 repo-local graph 副本中移除候选
`pdf_url`，不会改写权威 artifact 或日常 Zotero 库。

第一阶段 verifier 会从真实 Note/Reader 事件物化 repo-local `review-queue.json`。要验证该队列重新进入 Zotero 后能显示最近受影响节点，使用同一隔离 profile 再启动一次，等待 topic 同步完成后退出，再运行：

```bash
./scripts/run_zotero_smoke.sh
# 自动路径完成后退出该 Zotero 实例
python3 scripts/verify_zotero_review_queue_roundtrip.py
```

第二阶段必须出现 `review_queue_loaded` 与 `process_note_refreshed`；过程 Note 显示 pending 数量、最近受影响节点和“不自动改变 lifecycle”边界。

第三阶段验证 owner disposition 与独立 assessment 返回 Zotero。它只克隆真实 v2
authority 到 `.runtime/zotero-smoke/review-v2-run`，不会修改真实研究 run：

```bash
PYTHONPATH=src python3 scripts/prepare_zotero_review_assessment_roundtrip.py --reset
bash scripts/run_zotero_smoke.sh
# 等待 native_topic_synced 后退出隔离 Zotero
PYTHONPATH=src python3 scripts/verify_zotero_review_assessment_roundtrip.py
```

通过条件包括：`05 · 共创复核` 中恰有一条原生 assessment Note；过程 Note
显示该 attachment；Note 可见证据边界、保留对象、待重审对象和后续 artifact
类型；clone 与真实 authority 均未发生 lifecycle 变化。

要覆盖复杂的历史森林而不改变 registry 的 active run，可显式选择已登记 run：

```bash
python3 scripts/prepare_zotero_smoke.py --reset --run-key multilingual-agent-action-continuation
./scripts/run_zotero_smoke.sh
python3 scripts/verify_zotero_smoke.py
```

`.runtime/` 被 Git 忽略，因为其中包含 Zotero SQLite、translator/style cache 等可再生大文件；准备脚本、验证逻辑和所选 authority 元数据均由 repo 管理。它不会使用或修改日常 profile/data directory。

旧的迁移产物中若出现 `/private/tmp/atr-v2-migration-inputs/...`，它只是已经写入不可变 ATR artifact metadata 的历史来源路径，不代表当前代码仍依赖或写入该目录。不得为了美化路径重写既有 provenance；新的迁移输入必须放在仓库 `.runtime/migration-inputs/`，可复现的迁移脚本和摘要则保留在仓库中。

需要检查 DOM、网络和断点时，也可以显式指定其他隔离开发 profile 启动 Zotero并启用文本日志：

```bash
/Applications/Zotero.app/Contents/MacOS/zotero -ZoteroDebugText -profile /absolute/path/to/a-development-profile
```

Firefox 开发者工具可用于更深入的 UI 调试；优先在单独的 Zotero Beta/开发实例使用它，不替代上述静态检查与运行日志。
