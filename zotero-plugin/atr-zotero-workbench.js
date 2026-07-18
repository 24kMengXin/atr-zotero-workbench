/* global IOUtils, PathUtils */
var ATRZoteroWorkbench = {
  id: null, rootURI: null, observerID: null, addedElementIDs: [], overlayID: "atr-zotero-workbench-overlay",
  // This path deliberately matches the repo's generated workbench output. It is a user-visible pref.
  defaultWorkspace: "/Users/zone/Documents/research assistant/atr-zotero-workbench/output/multilingual",
  init({ id, rootURI }) { this.id = id; this.rootURI = rootURI; },
  log(message) { Zotero.debug("ATR Workbench: " + message); },
  get workspace() { return Zotero.Prefs.get("extensions.atr-zotero-workbench.workspace", true) || this.defaultWorkspace; },
  inboxPath() { return PathUtils.join(this.workspace, "human-input", "inbox.jsonl"); },
  async appendHumanInput(record) {
    try {
      await IOUtils.makeDirectory(PathUtils.parent(this.inboxPath()), { ignoreExisting: true });
      await IOUtils.writeUTF8(this.inboxPath(), JSON.stringify(record) + "\n", { mode: "append" });
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
  escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
  },
  async openWorkbench(window) {
    let doc = window.document;
    doc.getElementById(this.overlayID)?.remove();
    let host = doc.createElement("div");
    host.id = this.overlayID;
    host.style.cssText = "position:fixed;inset:58px 18px 18px 220px;z-index:100000;background:#f5f7fb;color:#172033;border:1px solid #8093aa;border-radius:10px;box-shadow:0 12px 40px rgba(0,0,0,.28);font:14px system-ui,-apple-system,sans-serif;overflow:auto";
    host.innerHTML = "<div style='position:sticky;top:0;display:flex;align-items:center;gap:12px;padding:14px 18px;background:#122a43;color:#fff;z-index:1'><b style='font-size:16px'>ATR × Zotero Research Workbench</b><span id='atr-workbench-meta' style='opacity:.8;flex:1'></span><button id='atr-workbench-close' style='padding:5px 10px'>关闭</button></div><div id='atr-workbench-body' style='padding:18px'></div>";
    doc.documentElement.appendChild(host);
    doc.getElementById("atr-workbench-close").addEventListener("click", () => host.remove());
    let body = doc.getElementById("atr-workbench-body");
    try {
      let graph = JSON.parse(await IOUtils.readUTF8(PathUtils.join(this.workspace, "graph.json")));
      let nodes = graph.nodes || [], edges = graph.edges || [];
      let by = Object.fromEntries(nodes.map(node => [node.id, node]));
      let questions = nodes.filter(node => node.kind === "research_question");
      let papers = nodes.filter(node => node.kind === "paper");
      let scholarly = papers.filter(node => node.data?.source_layer === "scholarly_evidence").length;
      let contextual = papers.filter(node => node.data?.source_layer === "contextual_inspiration").length;
      doc.getElementById("atr-workbench-meta").textContent = `${graph.run || "unknown run"} · 派生只读投影`;
      let cards = `<div style='display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:16px'>${[[questions.length,"研究问题"],[scholarly,"学术证据"],[contextual,"现实灵感"],[(graph.history?.snapshots || []).length,"历史快照"]].map(([n,label]) => `<div style='background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:12px'><b style='display:block;font-size:24px'>${n}</b><span>${label}</span></div>`).join("")}</div>`;
      let questionCards = questions.map(question => {
        let concepts = edges.filter(edge => edge.source === question.id && edge.relation === "requires_concept").map(edge => by[edge.target]).filter(Boolean);
        let anchors = edges.filter(edge => edge.source === question.id && edge.relation === "anchored_by").map(edge => by[edge.target]).filter(Boolean);
        return `<section style='background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:14px;margin-bottom:12px'><h2 style='margin:0 0 8px;font-size:17px'>${this.escapeHTML(question.label)}</h2><p style='color:#64748b'>ATR frontier map 提出的问题，不是论文自身结论。</p><h3 style='font-size:13px;margin:12px 0 4px'>所需概念</h3><p>${concepts.map(node => `<span style='display:inline-block;background:#edf2f7;border-radius:12px;padding:3px 8px;margin:2px'>${this.escapeHTML(node.label)}</span>`).join("") || "未记录"}</p><h3 style='font-size:13px;margin:12px 0 4px'>锚定来源</h3>${anchors.map(node => `<details style='margin:6px 0'><summary>${this.escapeHTML(node.label)}</summary><p><b>支持：</b>${this.escapeHTML(node.data?.supports || "未记录")}</p><p><b>不能推出：</b>${this.escapeHTML(node.data?.does_not_support || "未记录")}</p></details>`).join("") || "未记录"}</section>`;
      }).join("");
      let diagnostics = (graph.diagnostics || []).map(item => `<li>${this.escapeHTML(item)}</li>`).join("");
      body.innerHTML = cards + "<h1 style='font-size:20px'>从问题向知识展开</h1>" + (questionCards || "<p>当前 run 尚未产生 frontier tensions；插件不会凭空生成研究问题。</p>") + (diagnostics ? `<section style='background:#fff7e6;border:1px solid #f0c36d;border-radius:8px;padding:12px'><b>数据完整性提示</b><ul>${diagnostics}</ul></section>` : "");
    } catch (error) {
      this.log("could not render workbench overlay: " + error);
      body.textContent = "无法读取工作台投影：" + error;
    }
  },
  hooks: {
    async onStartup({ id, rootURI }) {
      ATRZoteroWorkbench.init({ id, rootURI });
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
