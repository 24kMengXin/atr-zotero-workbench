/* global IOUtils, PathUtils */
var ATRZoteroWorkbench = {
  id: null, rootURI: null, observerID: null, addedElementIDs: [], overlayID: "atr-zotero-workbench-overlay",
  // This path deliberately matches the repo's generated workbench output. It is a user-visible pref.
  defaultWorkspace: "/Users/zone/Documents/research assistant/atr-zotero-workbench/output/multilingual",
  init({ id, rootURI }) { this.id = id; this.rootURI = rootURI; },
  log(message) { Zotero.debug("ATR Workbench: " + message); },
  get workspace() { return Zotero.Prefs.get("extensions.atr-zotero-workbench.workspace", true) || this.defaultWorkspace; },
  inboxPath() { return PathUtils.join(this.workspace, "human-input", "inbox.jsonl"); },
  // Keep the trace beside graph.json: that directory is created by the ATR
  // build, so a diagnostic must not depend on an extra directory API call.
  runtimeLogPath() { return PathUtils.join(this.workspace, "plugin-runtime.jsonl"); },
  async appendWorkspaceLine(path, line) {
    await Zotero.File.createDirectoryIfMissingAsync(PathUtils.parent(path), { ignoreExisting: true });
    let existing = "";
    try { existing = await Zotero.File.getContentsAsync(path); } catch (_) { /* new audit file */ }
    await Zotero.File.putContentsAsync(path, existing + line + "\n");
  },
  async appendRuntimeStatus(stage, details = {}) {
    let record = { schema_version: "0.1", component: "zotero_plugin", stage, at: new Date().toISOString(), ...details };
    this.log(stage + ": " + JSON.stringify(details));
    try {
      await this.appendWorkspaceLine(this.runtimeLogPath(), JSON.stringify(record));
    } catch (error) { this.log("could not write runtime status: " + error); }
  },
  async appendHumanInput(record) {
    try {
      await this.appendWorkspaceLine(this.inboxPath(), JSON.stringify(record));
    } catch (error) { this.log("could not write human input: " + error); }
  },
  async noteChanged(ids, extraData) {
    for (let id of ids) {
      let item = Zotero.Items.get(id);
      if (!item || !item.isNote()) continue;
      let parent = item.parentItemID ? Zotero.Items.get(item.parentItemID) : null;
      let parentExtra = parent ? parent.getField("extra") : "";
      let source = /ATR source ID:\s*([^\n]+)/.exec(parentExtra)?.[1] || null;
      await this.appendHumanInput({
        schema_version: "0.1", event: "human_note_modified", at: new Date().toISOString(),
        zotero_note_key: item.key, zotero_parent_key: parent?.key || null, atr_source_id: source,
        note_html: item.getNote(), notifier: extraData?.[id] || null
      });
    }
  },
  startObserving() {
    if (this.observerID) return;
    this.observerID = Zotero.Notifier.registerObserver({
      notify: (event, type, ids, extraData) => {
        if (type === "item" && (event === "modify" || event === "add")) this.noteChanged(ids, extraData);
      }
    }, ["item"], "atr-zotero-workbench");
    this.log("annotation observer started");
  },
  stopObserving() { if (this.observerID) Zotero.Notifier.unregisterObserver(this.observerID); this.observerID = null; },
  addToWindow(window) {
    let doc = window.document;
    if (doc.getElementById("atr-zotero-workbench-open")) return;
    // Zotero 9 uses this exact, case-sensitive ID. `menu_toolsPopup` is from
    // older examples and is not present in the current client.
    let toolsPopup = doc.getElementById("menu_ToolsPopup");
    if (!toolsPopup) {
      this.log("Tools menu is not ready yet; skipping this window");
      return;
    }
    let item = doc.createXULElement("menuitem");
    item.id = "atr-zotero-workbench-open"; item.setAttribute("label", "打开 ATR Research Workbench");
    item.addEventListener("command", () => this.openWorkbench(window));
    toolsPopup.appendChild(item); this.addedElementIDs.push(item.id);
    this.log("Tools menu item added");
  },
  addToAllWindows() { for (let win of Zotero.getMainWindows()) if (win.ZoteroPane) this.addToWindow(win); },
  removeFromWindow(window) {
    for (let id of this.addedElementIDs) window.document.getElementById(id)?.remove();
    window.document.getElementById(this.overlayID)?.remove();
  },
  removeFromAllWindows() { for (let win of Zotero.getMainWindows()) if (win.ZoteroPane) this.removeFromWindow(win); },
  async openWorkbench(window) {
    let doc = window.document;
    doc.getElementById(this.overlayID)?.remove();
    await this.appendRuntimeStatus("open_requested", { window_uri: String(window.location) });
    let xul = name => doc.createXULElement(name);
    let label = (value, style = "") => {
      let node = xul("label"); node.setAttribute("value", String(value ?? ""));
      if (style) node.setAttribute("style", style);
      return node;
    };
    let host = xul("vbox");
    host.id = this.overlayID;
    host.setAttribute("flex", "1");
    host.setAttribute("style", "background:#f5f7fb;color:#172033;border:1px solid #8093aa;border-radius:10px;box-shadow:0 12px 40px rgba(0,0,0,.28)");
    let header = xul("hbox");
    header.setAttribute("align", "center");
    header.setAttribute("style", "background:#122a43;color:#fff;padding:14px 18px");
    header.append(label("ATR × Zotero Research Workbench", "font-size:16px;font-weight:bold"));
    let meta = label("正在读取研究投影…", "opacity:.8;margin-left:12px");
    meta.setAttribute("flex", "1"); header.append(meta);
    let close = xul("button"); close.setAttribute("label", "关闭");
    header.append(close); host.append(header);
    let body = xul("scrollbox");
    body.setAttribute("orient", "vertical"); body.setAttribute("flex", "1");
    body.setAttribute("style", "padding:18px;overflow:auto"); host.append(body);
    // Zotero's own transient views live in this stack. Appending to the
    // document root creates an out-of-layout XUL node and can appear blank.
    let stack = doc.getElementById("zotero-pane-stack");
    if (!stack) {
      let error = new Error("Zotero pane stack is unavailable");
      await this.appendRuntimeStatus("mount_failed", { error: String(error) });
      throw error;
    }
    stack.appendChild(host);
    await this.appendRuntimeStatus("overlay_mounted", {
      mount_id: stack.id, overlay_present: !!doc.getElementById(this.overlayID)
    });
    close.addEventListener("command", () => host.remove());
    try {
      let graph = JSON.parse(await IOUtils.readUTF8(PathUtils.join(this.workspace, "graph.json")));
      let nodes = graph.nodes || [], edges = graph.edges || [];
      await this.appendRuntimeStatus("projection_loaded", {
        run: graph.run || null, node_count: nodes.length, edge_count: edges.length
      });
      let by = Object.fromEntries(nodes.map(node => [node.id, node]));
      let questions = nodes.filter(node => node.kind === "research_question");
      let papers = nodes.filter(node => node.kind === "paper");
      let scholarly = papers.filter(node => node.data?.source_layer === "scholarly_evidence").length;
      let contextual = papers.filter(node => node.data?.source_layer === "contextual_inspiration").length;
      meta.setAttribute("value", `${graph.run || "unknown run"} · 派生只读投影`);
      let metrics = xul("hbox"); metrics.setAttribute("style", "margin-bottom:16px");
      for (let [count, title] of [[questions.length,"研究问题"],[scholarly,"学术证据"],[contextual,"现实灵感"],[(graph.history?.snapshots || []).length,"历史快照"]]) {
        let card = xul("vbox"); card.setAttribute("style", "background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:12px;margin-right:10px;min-width:130px");
        card.append(label(count, "font-size:24px;font-weight:bold"), label(title)); metrics.append(card);
      }
      body.append(metrics, label("从问题向知识展开", "font-size:20px;font-weight:bold;margin-bottom:10px"));
      for (let question of questions) {
        let concepts = edges.filter(edge => edge.source === question.id && edge.relation === "requires_concept").map(edge => by[edge.target]).filter(Boolean);
        let anchors = edges.filter(edge => edge.source === question.id && edge.relation === "anchored_by").map(edge => by[edge.target]).filter(Boolean);
        let card = xul("vbox"); card.setAttribute("style", "background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:14px;margin-bottom:12px");
        card.append(label(question.label, "font-size:17px;font-weight:bold;white-space:normal"), label("ATR frontier map 提出的问题，不是论文自身结论。", "color:#64748b;margin:6px 0"), label("所需概念", "font-size:13px;font-weight:bold;margin-top:8px"), label(concepts.map(node => node.label).join(" · ") || "未记录", "white-space:normal"), label("锚定来源", "font-size:13px;font-weight:bold;margin-top:8px"));
        for (let source of anchors) {
          let details = xul("vbox"); details.setAttribute("style", "margin:5px 0;padding:7px;background:#f7fafc;border-radius:5px");
          details.append(label(source.label, "font-weight:bold;white-space:normal"), label("支持：" + (source.data?.supports || "未记录"), "white-space:normal"), label("不能推出：" + (source.data?.does_not_support || "未记录"), "white-space:normal;color:#64748b"));
          card.append(details);
        }
        body.append(card);
      }
      if (!questions.length) body.append(label("当前 run 尚未产生 frontier tensions；插件不会凭空生成研究问题。", "white-space:normal"));
      if (graph.diagnostics?.length) {
        let warning = xul("vbox"); warning.setAttribute("style", "background:#fff7e6;border:1px solid #f0c36d;border-radius:8px;padding:12px");
        warning.append(label("数据完整性提示", "font-weight:bold"), label(graph.diagnostics.join("；"), "white-space:normal")); body.append(warning);
      }
      await this.appendRuntimeStatus("render_completed", { question_count: questions.length, source_count: papers.length });
    } catch (error) {
      this.log("could not render workbench overlay: " + error);
      await this.appendRuntimeStatus("render_failed", { error: String(error) });
      body.append(label("无法读取工作台投影：" + error, "white-space:normal;color:#b42318"));
    }
  },
  hooks: {
    async onStartup({ id, rootURI }) {
      ATRZoteroWorkbench.init({ id, rootURI });
      await ATRZoteroWorkbench.appendRuntimeStatus("startup_complete", { addon_id: id, root_uri: rootURI });
      ATRZoteroWorkbench.addToAllWindows();
      ATRZoteroWorkbench.startObserving();
    },
    async onMainWindowLoad(window) { ATRZoteroWorkbench.addToWindow(window); },
    async onMainWindowUnload(window) { ATRZoteroWorkbench.removeFromWindow(window); },
    async onShutdown() {
      ATRZoteroWorkbench.stopObserving();
      ATRZoteroWorkbench.removeFromAllWindows();
    }
  }
};
