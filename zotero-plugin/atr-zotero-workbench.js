/* global IOUtils, PathUtils */
var ATRZoteroWorkbench = {
  id: null, rootURI: null, observerID: null, addedElementIDs: [], overlayID: "atr-zotero-workbench-overlay", workspaceOverride: null,
  // This path deliberately matches the repo's generated workbench output. It is a user-visible pref.
  defaultWorkspace: "/Users/zone/Documents/research assistant/atr-zotero-workbench/output/multilingual",
  defaultRegistry: "/Users/zone/Documents/research assistant/atr-zotero-workbench/output/runs.json",
  init({ id, rootURI }) { this.id = id; this.rootURI = rootURI; },
  log(message) { Zotero.debug("ATR Workbench: " + message); },
  get workspace() { return this.workspaceOverride || Zotero.Prefs.get("extensions.atr-zotero-workbench.workspace", true) || this.defaultWorkspace; },
  get registryPath() { return Zotero.Prefs.get("extensions.atr-zotero-workbench.registry", true) || this.defaultRegistry; },
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
  async readJsonLines(path) {
    try {
      return (await Zotero.File.getContentsAsync(path)).split("\n")
        .filter(line => line.trim()).map(line => JSON.parse(line));
    } catch (_) { return []; }
  },
  async loadRunRegistry() {
    try {
      let registry = JSON.parse(await Zotero.File.getContentsAsync(this.registryPath));
      return (registry.runs || []).filter(run => run.key && run.workspace);
    } catch (_) { return []; }
  },
  plainNote(html) { return String(html || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim(); },
  htmlEscape(value) { return String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]); },
  async sourceItem(source) {
    let sourceID = source.data?.source_id;
    let search = new Zotero.Search();
    search.libraryID = Zotero.Libraries.userLibraryID;
    search.addCondition("tag", "is", "atr-source-id:" + sourceID);
    let ids = await search.search();
    let existing = ids.length ? Zotero.Items.get(ids[0]) : null;
    if (existing) return existing;
    let item = new Zotero.Item(source.data?.source_layer === "scholarly_evidence" ? "journalArticle" : "webpage");
    item.setField("title", source.label); item.setField("url", source.data?.url || "");
    item.setField("extra", "ATR source ID: " + sourceID);
    item.addTag("ATR"); item.addTag("atr-source-id:" + sourceID);
    await item.saveTx();
    return item;
  },
  async openReviewNote(source, window) {
    let sourceID = source.data?.source_id, item = await this.sourceItem(source);
    let marker = "ATR Review Source ID: " + sourceID;
    let existing = (item.getNotes?.() || []).map(id => Zotero.Items.get(id))
      .find(note => note?.getNote().includes(marker));
    if (existing) { window.ZoteroPane.selectItem(existing.id); return existing; }
    let note = new Zotero.Item("note"); note.parentItemID = item.id;
    note.setNote("<h1>我的 ATR 阅读反馈</h1><p>" + marker + "</p>"
      + "<p>ATR Review Stance: PENDING</p>"
      + "<p>ATR Source Locator: 请填写页码、章节、高亮或段落定位</p>"
      + "<h2>来源支持的内容</h2><p>" + this.htmlEscape(source.data?.supports) + "</p>"
      + "<h2>来源不支持 / 不能推出的内容</h2><p>" + this.htmlEscape(source.data?.does_not_support) + "</p>"
      + "<h2>我的阅读与反驳</h2><p>请在这里写下你核对原文后的判断。</p>");
    await note.saveTx(); window.ZoteroPane.selectItem(note.id); return note;
  },
  async openClaimReviewNote(claim, window) {
    let claimID = claim.data?.claim_id;
    if (!claimID) throw new Error("claim node has no stable claim_id");
    let marker = "ATR Claim ID: " + claimID;
    let search = new Zotero.Search();
    search.libraryID = Zotero.Libraries.userLibraryID;
    search.addCondition("note", "contains", marker);
    let ids = await search.search();
    let existing = ids.map(id => Zotero.Items.get(id)).find(item => item?.isNote?.() && item.getNote().includes(marker));
    if (existing) { window.ZoteroPane.selectItem(existing.id); return existing; }
    let note = new Zotero.Item("note");
    note.setNote("<h1>我的 ATR 断言审查</h1><p>" + marker + "</p>"
      + "<p>ATR Review Stance: PENDING</p>"
      + "<p>ATR Source Locator: 请填写你核对的原文页码、章节、高亮或段落定位</p>"
      + "<h2>AI 提出的可核查断言</h2><p>" + this.htmlEscape(claim.label) + "</p>"
      + "<h2>适用条件</h2><p>" + this.htmlEscape(JSON.stringify(claim.data?.conditions || {})) + "</p>"
      + "<h2>我的原文定位与判断</h2><p>请将 PENDING 改为 SUPPORTS / QUALIFIES / CHALLENGES / UNSURE / NEW_QUESTION，并写下原文位置、摘录与理由。</p>");
    await note.saveTx(); window.ZoteroPane.selectItem(note.id); return note;
  },
  async setClaimReviewStance(claim, stance, window) {
    let note = await this.openClaimReviewNote(claim, window);
    let html = note.getNote();
    let replacement = "ATR Review Stance: " + stance;
    if (/ATR Review Stance:\s*(SUPPORTS|QUALIFIES|CHALLENGES|UNSURE|NEW_QUESTION|PENDING)/.test(this.plainNote(html))) {
      html = html.replace(/ATR Review Stance:\s*(SUPPORTS|QUALIFIES|CHALLENGES|UNSURE|NEW_QUESTION|PENDING)/, replacement);
    } else {
      html = "<p>" + replacement + "</p>" + html;
    }
    note.setNote(html); await note.saveTx(); window.ZoteroPane.selectItem(note.id);
    return note;
  },
  async noteChanged(ids, extraData) {
    for (let id of ids) {
      let item = Zotero.Items.get(id);
      if (!item || !item.isNote()) continue;
      let parent = item.parentItemID ? Zotero.Items.get(item.parentItemID) : null;
      let parentExtra = parent ? parent.getField("extra") : "";
      let noteHTML = item.getNote(), noteText = this.plainNote(noteHTML);
      let source = /ATR source ID:\s*([^\s<]+)/.exec(parentExtra)?.[1]
        || /ATR Source ID:\s*([^\s<]+)/.exec(noteText)?.[1] || null;
      let claim = /ATR Claim ID:\s*([^\s<]+)/.exec(noteText)?.[1] || null;
      let stance = /ATR Review Stance:\s*(SUPPORTS|QUALIFIES|CHALLENGES|UNSURE|NEW_QUESTION|PENDING)/.exec(noteText)?.[1] || "UNSPECIFIED";
      let locator = /ATR Source Locator:\s*([^<]+)/.exec(noteText)?.[1]?.trim() || null;
      // Never copy arbitrary Zotero notes into an ATR workspace. A feedback
      // event exists only when the researcher explicitly works in a marked
      // source/claim review note created or adopted for this purpose.
      if (!source && !claim) continue;
      await this.appendHumanInput({
        schema_version: "0.1", event: "human_note_modified", at: new Date().toISOString(),
        zotero_note_key: item.key, zotero_parent_key: parent?.key || null, atr_source_id: source,
        atr_claim_id: claim, review_stance: stance, source_locator: locator, note_html: noteHTML, notifier: extraData?.[id] || null
      });
    }
  },
  startObserving() {
    if (this.observerID) return;
    this.observerID = Zotero.Notifier.registerObserver({
      notify: (event, type, ids, extraData) => {
        if (type === "item" && event === "modify") this.noteChanged(ids, extraData);
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
  renderRelationshipMap(doc, nodes, edges, onNode) {
    const ns = "http://www.w3.org/2000/svg", create = name => doc.createElementNS(ns, name);
    let svg = create("svg"); svg.setAttribute("viewBox", "0 0 960 330"); svg.setAttribute("width", "100%"); svg.setAttribute("height", "330");
    svg.setAttribute("style", "background:#fff;border:1px solid #d9e2ec;border-radius:8px;margin:8px 0");
    let by = Object.fromEntries(nodes.map(node => [node.id, node]));
    let lanes = [
      ["research_question", 150, "前沿问题", "#bc5b12"], ["claim", 365, "可审查断言", "#28796c"],
      ["real_world_tension", 600, "现实张力", "#d38418"], ["research_problem", 810, "问题卡", "#9b4f96"],
    ];
    let selected = [], positions = new Map();
    let root = nodes.find(node => node.kind === "research_program") || nodes.find(node => node.kind === "run");
    let isProgram = root?.kind === "research_program";
    if (root) { selected.push(root); positions.set(root.id, [480, 34]); }
    if (isProgram) {
      let branchRuns = nodes.filter(node => node.kind === "run").slice(0, 7);
      branchRuns.forEach((node, index) => { selected.push(node); positions.set(node.id, [100 + index * 126, 94]); });
      for (let branch of branchRuns) {
        let prefix = branch.id.slice(0, branch.id.lastIndexOf(":run:"));
        let domain = nodes.find(node => node.kind === "concept" && node.id === prefix + ":concept:domain");
        if (domain) { selected.push(domain); positions.set(domain.id, positions.get(branch.id).map((value, i) => i ? value + 45 : value)); }
      }
    } else {
      let domain = nodes.find(node => node.id === "concept:domain");
      if (domain) { selected.push(domain); positions.set(domain.id, [480, 106]); }
    }
    for (let [kind, x, heading] of lanes) {
      let title = create("text"); title.setAttribute("x", x); title.setAttribute("y", "78"); title.setAttribute("text-anchor", "middle"); title.setAttribute("font-size", "12"); title.setAttribute("fill", "#64748b"); title.textContent = heading; svg.append(title);
      let items = nodes.filter(node => node.kind === kind).slice(0, 4);
      items.forEach((node, index) => { selected.push(node); positions.set(node.id, [x, (isProgram ? 185 : 150) + index * 48]); });
    }
    let selectedIDs = new Set(selected.map(node => node.id));
    for (let edge of edges) {
      if (!selectedIDs.has(edge.source) || !selectedIDs.has(edge.target)) continue;
      let [x1, y1] = positions.get(edge.source), [x2, y2] = positions.get(edge.target), line = create("line");
      line.setAttribute("x1", x1); line.setAttribute("y1", y1); line.setAttribute("x2", x2); line.setAttribute("y2", y2); line.setAttribute("stroke", "#bac7d4"); line.setAttribute("stroke-width", "1.4"); svg.append(line);
    }
    for (let node of selected) {
      let [x, y] = positions.get(node.id), lane = lanes.find(row => row[0] === node.kind), color = lane ? lane[3] : (node.kind === "concept" ? "#7858a6" : "#374151");
      let group = create("g"), circle = create("circle"), text = create("text"); circle.setAttribute("cx", x); circle.setAttribute("cy", y); circle.setAttribute("r", node.kind === "run" ? "12" : "10"); circle.setAttribute("fill", color); circle.setAttribute("stroke", "#fff"); circle.setAttribute("stroke-width", "2");
      text.setAttribute("x", x); text.setAttribute("y", y + 22); text.setAttribute("text-anchor", "middle"); text.setAttribute("font-size", "10"); text.setAttribute("fill", "#172033"); text.textContent = String(node.label || "").slice(0, 18) + (String(node.label || "").length > 18 ? "…" : "");
      group.setAttribute("style", "cursor:pointer"); group.append(circle, text); group.addEventListener("click", () => onNode(node)); svg.append(group);
    }
    if (!selected.some(node => node.kind !== "run")) { let empty = create("text"); empty.setAttribute("x", "480"); empty.setAttribute("y", "180"); empty.setAttribute("text-anchor", "middle"); empty.setAttribute("fill", "#64748b"); empty.textContent = "当前 run 尚无可画出的研究对象；不会补造节点。"; svg.append(empty); }
    return svg;
  },
  async openWorkbench(window) {
    let doc = window.document;
    doc.getElementById(this.overlayID)?.remove();
    let registeredRuns = await this.loadRunRegistry();
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
    if (registeredRuns.length > 1) {
      let picker = xul("menulist"), choices = xul("menupopup");
      let current = registeredRuns.find(run => run.workspace === this.workspace) || registeredRuns[0];
      picker.setAttribute("label", current.label || current.key);
      for (let run of registeredRuns) {
        let choice = xul("menuitem"); choice.setAttribute("label", run.label || run.key); choice.setAttribute("value", run.workspace);
        choice.addEventListener("command", async () => {
          this.workspaceOverride = run.workspace;
          await this.appendRuntimeStatus("run_selected", { run_key: run.key, workspace: run.workspace });
          await this.openWorkbench(window);
        });
        choices.append(choice);
      }
      picker.append(choices); header.append(picker);
    }
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
      let claims = nodes.filter(node => node.kind === "claim");
      let knowledgeContexts = nodes.filter(node => node.kind === "knowledge_context");
      let knowledgeSteps = nodes.filter(node => node.kind === "knowledge_step");
      let conceptMaps = nodes.filter(node => node.kind === "concept_map");
      let knowledgeConcepts = nodes.filter(node => node.kind === "knowledge_concept");
      let landscapeBriefs = nodes.filter(node => node.kind === "landscape_brief");
      let realWorldTensions = nodes.filter(node => node.kind === "real_world_tension");
      let researchProblems = nodes.filter(node => node.kind === "research_problem");
      let gateNodes = nodes.filter(node => node.kind === "gate");
      let skillEvents = nodes.filter(node => node.kind === "skill_event").sort((a, b) => String(a.data?.timestamp || "").localeCompare(String(b.data?.timestamp || "")));
      let timeline = Array.isArray(graph.timeline) ? graph.timeline : [];
      let runNode = nodes.find(node => node.kind === "run");
      let scholarly = papers.filter(node => node.data?.source_layer === "scholarly_evidence").length;
      let contextual = papers.filter(node => node.data?.source_layer === "contextual_inspiration").length;
      let reviewEvents = await this.readJsonLines(this.inboxPath());
      let latestReviews = new Map();
      for (let event of reviewEvents) if (event.event === "human_note_modified") latestReviews.set(event.zotero_note_key, event);
      meta.setAttribute("value", `${graph.run || "unknown run"} · 派生只读投影`);
      let metrics = xul("hbox"); metrics.setAttribute("style", "margin-bottom:16px");
      for (let [count, title] of [[questions.length,"前沿问题"],[claims.length,"可审查断言"],[realWorldTensions.length,"现实张力"],[researchProblems.length,"问题卡"],[(graph.history?.snapshots || []).length,"历史快照"]]) {
        let card = xul("vbox"); card.setAttribute("style", "background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:12px;margin-right:10px;min-width:130px");
        card.append(label(count, "font-size:24px;font-weight:bold"), label(title)); metrics.append(card);
      }
      body.append(metrics, label("从问题向知识展开", "font-size:20px;font-weight:bold;margin-bottom:10px"));
      let mapBox = xul("vbox"); mapBox.setAttribute("style", "background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:14px;margin-bottom:16px");
      mapBox.append(label("研究关系图", "font-size:18px;font-weight:bold"), label("只绘制当前投影中存在的节点与显式关系；点击节点可在下方查看其边界。", "white-space:normal;color:#64748b;margin-top:4px"));
      mapBox.append(this.renderRelationshipMap(doc, nodes, edges, node => {
        meta.setAttribute("value", node.kind + " · " + node.label);
      }));
      body.append(mapBox);
      let lifecycleBox = xul("vbox"); lifecycleBox.setAttribute("style", "background:#eaf2fb;border:1px solid #8baed1;border-radius:8px;padding:14px;margin-bottom:16px");
      lifecycleBox.append(label("ATR 运行过程", "font-size:18px;font-weight:bold"));
      lifecycleBox.append(label("当前阶段：" + (runNode?.data?.stage || "未记录") + " · 状态：" + (runNode?.data?.status || "未记录"), "white-space:normal"));
      lifecycleBox.append(label("下一步：" + (runNode?.data?.next_action || "未记录"), "white-space:normal;color:#365b7b;margin:4px 0"));
      if (gateNodes.length) lifecycleBox.append(label("质量门：" + gateNodes.map(gate => gate.label).join(" · "), "white-space:normal;color:#365b7b"));
      else lifecycleBox.append(label("该 legacy run 未提供 gate ledger。", "white-space:normal;color:#64748b"));
      if (skillEvents.length) lifecycleBox.append(label("最近已记录的研究动作：" + skillEvents.slice(-6).map(event => event.label).join(" · "), "white-space:normal;color:#365b7b;margin-top:4px"));
      else lifecycleBox.append(label("当前 run 未记录 skill events。", "white-space:normal;color:#64748b;margin-top:4px"));
      body.append(lifecycleBox);
      let timelineBox = xul("vbox"); timelineBox.setAttribute("style", "background:#f8fafc;border:1px solid #cbd5e1;border-radius:8px;padding:14px;margin-bottom:16px");
      timelineBox.append(label("研究演化时间线", "font-size:18px;font-weight:bold"));
      timelineBox.append(label("只包含 ATR artifact 自身带时间戳的动作、断言与地图；没有记录时间的对象不会被伪装成过程事件。", "white-space:normal;color:#475569;margin:5px 0"));
      if (!timeline.length) timelineBox.append(label("当前 run 未提供可排序的时间戳 artifact。", "white-space:normal;color:#64748b"));
      for (let item of timeline) {
        let row = xul("vbox"); row.setAttribute("style", "border-left:3px solid #64748b;padding:4px 8px;margin:4px 0;background:#fff");
        row.append(label(String(item.at || "未记录时间") + " · " + String(item.kind || "artifact"), "font-size:12px;color:#64748b"), label(item.label || item.id || "未命名 artifact", "white-space:normal"));
        timelineBox.append(row);
      }
      body.append(timelineBox);
      let briefBox = xul("vbox"); briefBox.setAttribute("style", "background:#eef4ff;border:1px solid #90add6;border-radius:8px;padding:14px;margin-bottom:16px");
      briefBox.append(label("已读证据的景观简报", "font-size:18px;font-weight:bold"));
      briefBox.append(label("这是 AI 对已检查来源的暂时综合，不是 claim；请逐篇打开来源阅读，再通过阅读笔记反馈。它会同时显示未证实边界与最小下一判别。", "white-space:normal;color:#365b7b;margin:5px 0"));
      if (!landscapeBriefs.length) briefBox.append(label("尚无 landscape brief；插件不会把来源清单伪装成综合结论。", "white-space:normal;color:#64748b"));
      for (let brief of landscapeBriefs) {
        let row = xul("vbox"); row.setAttribute("style", "background:#fff;border-radius:6px;padding:9px;margin-top:8px");
        let sources = edges.filter(edge => edge.source === brief.id && edge.relation === "inspects_explicit_source").map(edge => by[edge.target]).filter(Boolean);
        row.append(label(brief.label, "font-weight:bold;white-space:normal"));
        row.append(label("状态：" + (brief.data?.disposition || "UNSPECIFIED") + " · " + (brief.data?.immutable ? "immutable artifact" : "非 immutable artifact"), "white-space:normal;color:#365b7b"));
        row.append(label("张力：" + (brief.data?.observed_tension || "未记录"), "white-space:normal;color:#365b7b;margin-top:3px"));
        row.append(label("还不能证明：" + (brief.data?.sources_do_not_establish || []).join(" · "), "white-space:normal;color:#64748b;margin-top:3px"));
        row.append(label("最小下一判别：" + (brief.data?.smallest_next_discriminator || "未记录"), "white-space:normal;color:#365b7b;margin-top:3px"));
        for (let source of sources) {
          let review = xul("button"); review.setAttribute("label", "阅读来源：" + source.label);
          review.addEventListener("command", async () => {
            let note = await this.openReviewNote(source, window);
            meta.setAttribute("value", "已定位景观简报的来源笔记 · " + note.key);
          });
          row.append(review);
        }
        briefBox.append(row);
      }
      body.append(briefBox);
      let claimBox = xul("vbox"); claimBox.setAttribute("style", "background:#f8f1e7;border:1px solid #d7ae73;border-radius:8px;padding:14px;margin-bottom:16px");
      claimBox.append(label("等待你审查的 ATR 断言", "font-size:18px;font-weight:bold"));
      claimBox.append(label("断言不是论文结论。请先核对原始材料，再在专属笔记中选择支持、限定、反驳、不确定或提出问题。你的判断只会生成待审查输入，不会自动修改 ATR 路线。", "white-space:normal;color:#765526;margin:5px 0"));
      if (!claims.length) claimBox.append(label("当前 run 没有可用的 claim ledger；插件不会把论文标题或 AI 摘要伪造为断言。", "white-space:normal;color:#64748b"));
      for (let claim of claims) {
        let row = xul("vbox"); row.setAttribute("style", "background:#fff;border-radius:6px;padding:9px;margin-top:8px");
        row.append(label(claim.label, "font-weight:bold;white-space:normal"));
        row.append(label("状态：" + (claim.data?.status || "未记录") + " · 版本：" + (claim.data?.version ?? "未记录"), "white-space:normal;color:#765526;margin-top:3px"));
        let restrictions = claim.data?.forbidden_claims || [];
        if (restrictions.length) row.append(label("不能声称：" + restrictions.join(" · "), "white-space:normal;color:#64748b;margin-top:3px"));
        let review = xul("button"); review.setAttribute("label", "建立 / 打开我的断言审查");
        review.addEventListener("command", async () => {
          try {
            let note = await this.openClaimReviewNote(claim, window);
            meta.setAttribute("value", "已定位断言审查笔记 · " + note.key);
            await this.appendRuntimeStatus("claim_review_note_opened", { claim_id: claim.data?.claim_id, note_key: note.key });
          } catch (error) {
            this.log("could not open claim review note: " + error);
            meta.setAttribute("value", "无法建立断言审查笔记：" + error);
            await this.appendRuntimeStatus("claim_review_note_failed", { claim_id: claim.data?.claim_id, error: String(error) });
          }
        });
        let stancePicker = xul("menulist"), stanceChoices = xul("menupopup");
        stancePicker.setAttribute("value", "PENDING"); stancePicker.setAttribute("label", "选择我的立场");
        for (let [value, title] of [["PENDING", "尚未判断"], ["SUPPORTS", "支持"], ["QUALIFIES", "需要限定"], ["CHALLENGES", "反驳 / 挑战"], ["UNSURE", "证据不足"], ["NEW_QUESTION", "提出新问题"]]) {
          let choice = xul("menuitem"); choice.setAttribute("value", value); choice.setAttribute("label", title); stanceChoices.append(choice);
        }
        stancePicker.append(stanceChoices);
        let record = xul("button"); record.setAttribute("label", "记录我的立场并打开笔记");
        record.addEventListener("command", async () => {
          let stance = stancePicker.value || "PENDING";
          try {
            let note = await this.setClaimReviewStance(claim, stance, window);
            meta.setAttribute("value", "已记录 " + stance + " · 请补充原文定位与理由");
            await this.appendRuntimeStatus("claim_review_stance_recorded", { claim_id: claim.data?.claim_id, note_key: note.key, stance });
          } catch (error) {
            this.log("could not record claim review stance: " + error);
            meta.setAttribute("value", "无法记录立场：" + error);
            await this.appendRuntimeStatus("claim_review_stance_failed", { claim_id: claim.data?.claim_id, error: String(error) });
          }
        });
        row.append(review, stancePicker, record); claimBox.append(row);
      }
      body.append(claimBox);
      let reviewBox = xul("vbox"); reviewBox.setAttribute("style", "background:#edf7f2;border:1px solid #8ac7ad;border-radius:8px;padding:14px;margin-bottom:16px");
      reviewBox.append(label("你的阅读反馈", "font-size:18px;font-weight:bold"));
      reviewBox.append(label("在 Zotero 的 ATR 阅读卡（子笔记）中写下判断；这里只展示事件副本，不会自动改写研究路线或删除旧线。", "white-space:normal;color:#365b47;margin:5px 0"));
      if (!latestReviews.size) {
        reviewBox.append(label("尚无已捕获的批注。先导入/同步 ATR 阅读卡，再在对应子笔记保存你的判断。", "white-space:normal"));
      } else {
        for (let event of latestReviews.values()) {
          let paper = papers.find(node => node.data?.source_id === event.atr_source_id);
          let nearest = paper ? edges.filter(edge => edge.target === paper.id && edge.relation === "anchored_by")
            .map(edge => by[edge.source]).filter(node => node?.kind === "research_question") : [];
          let review = xul("vbox"); review.setAttribute("style", "background:#fff;border-radius:6px;padding:9px;margin-top:8px");
          let claim = claims.find(node => node.data?.claim_id === event.atr_claim_id);
          review.append(label(claim?.label || paper?.label || event.atr_claim_id || event.atr_source_id || "未映射反馈目标", "font-weight:bold;white-space:normal"));
          review.append(label("立场：" + (event.review_stance || "UNSPECIFIED") + " · 原文定位：" + (event.source_locator || "未填写"), "white-space:normal;color:#365b47"));
          review.append(label("最近研究问题：" + (nearest.map(node => node.label).join(" · ") || "尚未在当前投影中找到"), "white-space:normal;color:#365b47"));
          review.append(label(this.plainNote(event.note_html).slice(0, 420) || "（笔记内容为空）", "white-space:normal;color:#475569;margin-top:4px"));
          reviewBox.append(review);
        }
      }
      body.append(reviewBox);
      let conceptMapBox = xul("vbox"); conceptMapBox.setAttribute("style", "background:#f7f3fb;border:1px solid #b8a5d5;border-radius:8px;padding:14px;margin-bottom:16px");
      conceptMapBox.append(label("可展开的来源知识树", "font-size:18px;font-weight:bold"));
      conceptMapBox.append(label("概念必须有来源、定义和边界；层级只帮助你从领域到具体机制阅读，绝不自动表示因果或共识。", "white-space:normal;color:#594578;margin:5px 0"));
      if (!conceptMaps.length) conceptMapBox.append(label("尚无 source-grounded concept map。", "white-space:normal;color:#64748b"));
      for (let map of conceptMaps) {
        let mapRow = xul("vbox"); mapRow.setAttribute("style", "background:#fff;border-radius:6px;padding:9px;margin-top:8px");
        mapRow.append(label(map.label, "font-weight:bold;white-space:normal"), label("边界：" + (map.data?.does_not_establish || "未记录"), "white-space:normal;color:#594578"));
        let appendConcept = (concept, level) => {
          let row = xul("vbox"); row.setAttribute("style", "margin-left:" + (level * 18) + "px;margin-top:6px;border-left:2px solid #b8a5d5;padding-left:8px");
          row.append(label(concept.label, "font-weight:bold;white-space:normal"), label(concept.data?.definition || "未记录定义", "white-space:normal"), label("来源：" + (concept.data?.source_ids || []).join(" · "), "white-space:normal;color:#594578"), label("不能说明：" + (concept.data?.does_not_establish || "未记录"), "white-space:normal;color:#64748b"));
          for (let sourceId of concept.data?.source_ids || []) {
            let source = papers.find(item => item.data?.source_id === sourceId);
            if (!source) continue;
            let review = xul("button"); review.setAttribute("label", "阅读：" + source.label);
            review.addEventListener("command", async () => { let note = await this.openReviewNote(source, window); meta.setAttribute("value", "已定位概念来源笔记 · " + note.key); });
            row.append(review);
          }
          mapRow.append(row);
          for (let child of edges.filter(edge => edge.source === concept.id && edge.relation === "specializes_concept").map(edge => by[edge.target]).filter(Boolean)) appendConcept(child, level + 1);
        };
        for (let root of edges.filter(edge => edge.source === map.id && edge.relation === "roots_concept").map(edge => by[edge.target]).filter(Boolean)) appendConcept(root, 0);
        conceptMapBox.append(mapRow);
      }
      body.append(conceptMapBox);
      let knowledgeBox = xul("vbox"); knowledgeBox.setAttribute("style", "background:#f3effa;border:1px solid #b8a5d5;border-radius:8px;padding:14px;margin-bottom:16px");
      let domain = by["concept:domain"];
      knowledgeBox.append(label("知识体系：" + (domain?.label || "未定义领域"), "font-size:18px;font-weight:bold;white-space:normal"));
      knowledgeBox.append(label("概念与文献的连线来自当前 frontier 问题的锚定上下文，不等同于‘文献证明该概念’；具体可推出与不可推出内容仍以下方证据边界为准。", "white-space:normal;color:#594578;margin:5px 0"));
      let concepts = nodes.filter(node => node.kind === "concept" && node.id !== "concept:domain");
      for (let concept of concepts) {
        let linkedPapers = edges.filter(edge => edge.source === concept.id && edge.relation === "illustrated_by_question_anchor")
          .map(edge => by[edge.target]).filter(Boolean);
        let conceptRow = xul("vbox"); conceptRow.setAttribute("style", "background:#fff;border-radius:6px;padding:8px;margin-top:7px");
        conceptRow.append(label(concept.label, "font-weight:bold;white-space:normal"));
        conceptRow.append(label("关联阅读：" + (linkedPapers.map(paper => paper.label).join(" · ") || "当前 run 未提供可追溯锚定来源"), "white-space:normal;color:#594578"));
        knowledgeBox.append(conceptRow);
      }
      if (!concepts.length) knowledgeBox.append(label("当前 run 尚未显式记录概念维度，插件不会补造知识节点。", "white-space:normal"));
      body.append(knowledgeBox);
      let contractionBox = xul("vbox"); contractionBox.setAttribute("style", "background:#eef4ff;border:1px solid #90add6;border-radius:8px;padding:14px;margin-bottom:16px");
      contractionBox.append(label("知识如何从前沿收缩到可审查断言", "font-size:18px;font-weight:bold"));
      contractionBox.append(label("每一步保留不变量、排除的解释与明确引用；这不是模型自动生成的知识树。", "white-space:normal;color:#365b7b;margin:5px 0"));
      if (!knowledgeContexts.length) contractionBox.append(label("尚无 knowledge-context artifact；当前只可查看 frontier 问题，不能声称已形成可审计的知识收缩路径。", "white-space:normal;color:#64748b"));
      for (let context of knowledgeContexts) {
        let row = xul("vbox"); row.setAttribute("style", "background:#fff;border-radius:6px;padding:9px;margin-top:8px");
        row.append(label("决策节点：" + (context.data?.decision_node || "未记录"), "font-weight:bold"));
        let steps = edges.filter(edge => edge.source === context.id && edge.relation === "contracts_to").map(edge => by[edge.target]).filter(Boolean);
        while (steps.length) {
          let step = steps.shift();
          row.append(label((step.data?.layer || "步骤") + " · " + step.label, "white-space:normal;margin-top:5px"));
          row.append(label("保留：" + (step.data?.invariant_preserved || "未记录") + "；排除：" + (step.data?.excluded_explanations || []).join(" · "), "white-space:normal;color:#365b7b"));
          steps.push(...edges.filter(edge => edge.source === step.id && edge.relation === "contracts_to").map(edge => by[edge.target]).filter(Boolean));
        }
        contractionBox.append(row);
      }
      body.append(contractionBox);
      for (let question of questions) {
        let concepts = edges.filter(edge => edge.source === question.id && edge.relation === "requires_concept").map(edge => by[edge.target]).filter(Boolean);
        let anchors = edges.filter(edge => edge.source === question.id && edge.relation === "anchored_by").map(edge => by[edge.target]).filter(Boolean);
        let inspirations = edges.filter(edge => edge.source === question.id && edge.relation === "inspired_by_context").map(edge => by[edge.target]).filter(Boolean);
        let card = xul("vbox"); card.setAttribute("style", "background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:14px;margin-bottom:12px");
        card.append(label(question.label, "font-size:17px;font-weight:bold;white-space:normal"), label("ATR frontier map 提出的问题，不是论文自身结论。", "color:#64748b;margin:6px 0"), label("所需概念", "font-size:13px;font-weight:bold;margin-top:8px"), label(concepts.map(node => node.label).join(" · ") || "未记录", "white-space:normal"), label("锚定来源", "font-size:13px;font-weight:bold;margin-top:8px"));
        for (let source of anchors) {
          let details = xul("vbox"); details.setAttribute("style", "margin:5px 0;padding:7px;background:#f7fafc;border-radius:5px");
          details.append(label(source.label, "font-weight:bold;white-space:normal"), label("支持：" + (source.data?.supports || "未记录"), "white-space:normal"), label("不能推出：" + (source.data?.does_not_support || "未记录"), "white-space:normal;color:#64748b"));
          let review = xul("button"); review.setAttribute("label", "建立 / 打开我的阅读笔记");
          review.addEventListener("command", async () => {
            try {
              let note = await this.openReviewNote(source, window);
              meta.setAttribute("value", "已定位你的阅读笔记 · " + note.key);
              await this.appendRuntimeStatus("review_note_opened", { source_id: source.data?.source_id, note_key: note.key });
            } catch (error) {
              this.log("could not open review note: " + error);
              meta.setAttribute("value", "无法建立阅读笔记：" + error);
              await this.appendRuntimeStatus("review_note_failed", { source_id: source.data?.source_id, error: String(error) });
            }
          });
          details.append(review);
          card.append(details);
        }
        card.append(label("现实世界启发（不是学术证据）", "font-size:13px;font-weight:bold;margin-top:8px"));
        if (!inspirations.length) card.append(label("当前 run 未记录与此问题关联的新闻、报告、博客或社媒材料。", "white-space:normal;color:#64748b"));
        for (let source of inspirations) {
          let inspiration = xul("vbox"); inspiration.setAttribute("style", "margin:5px 0;padding:7px;background:#fff7e6;border-radius:5px");
          inspiration.append(label(source.label, "font-weight:bold;white-space:normal"), label("为什么值得作为启发：" + (source.data?.why_it_matters || source.data?.supports || "未记录"), "white-space:normal"), label("不能推出：" + (source.data?.does_not_support || "未记录"), "white-space:normal;color:#64748b"));
          card.append(inspiration);
        }
        body.append(card);
      }
      let worldBox = xul("vbox"); worldBox.setAttribute("style", "background:#fff7e6;border:1px solid #e3b76a;border-radius:8px;padding:14px;margin-bottom:16px");
      worldBox.append(label("现实世界张力与研究问题", "font-size:18px;font-weight:bold"));
      worldBox.append(label("现实材料只能提出值得解释的摩擦，不能替代学术证据或直接认证研究缺口。", "white-space:normal;color:#7a5620;margin:5px 0"));
      if (!realWorldTensions.length) worldBox.append(label("尚无 opportunity-map artifact；当前 run 不能展示受控的现实问题链路。", "white-space:normal;color:#64748b"));
      for (let tension of realWorldTensions) {
        let row = xul("vbox"); row.setAttribute("style", "background:#fff;border-radius:6px;padding:9px;margin-top:8px");
        row.append(label(tension.label, "font-weight:bold;white-space:normal"));
        row.append(label("主体：" + (tension.data?.actor || "未记录") + " · 后果：" + (tension.data?.material_consequence || "未记录"), "white-space:normal"));
        row.append(label("不能说明：" + (tension.data?.does_not_establish || "未记录"), "white-space:normal;color:#7a5620"));
        worldBox.append(row);
      }
      if (researchProblems.length) worldBox.append(label("可审查研究问题卡", "font-size:16px;font-weight:bold;margin-top:12px"));
      for (let problem of researchProblems) {
        let row = xul("vbox"); row.setAttribute("style", "background:#fff;border-radius:6px;padding:9px;margin-top:8px");
        row.append(label(problem.label, "font-weight:bold;white-space:normal"));
        let worlds = (problem.data?.counterfactual_worlds || []).map(world => (world.label || "世界") + "：" + (world.explanation || "未记录")).join(" · ");
        row.append(label("竞争解释：" + (worlds || "未记录"), "white-space:normal"));
        row.append(label("最小证伪条件：" + (problem.data?.minimum_falsifier || "未记录"), "white-space:normal;color:#7a5620"));
        worldBox.append(row);
      }
      body.append(worldBox);
      if (!questions.length) body.append(label("当前 run 尚未产生 frontier tensions；插件不会凭空生成研究问题。", "white-space:normal"));
      if (graph.diagnostics?.length) {
        let warning = xul("vbox"); warning.setAttribute("style", "background:#fff7e6;border:1px solid #f0c36d;border-radius:8px;padding:12px");
        warning.append(label("数据完整性提示", "font-weight:bold"), label(graph.diagnostics.join("；"), "white-space:normal")); body.append(warning);
      }
      await this.appendRuntimeStatus("render_completed", { question_count: questions.length, source_count: papers.length, claim_count: claims.length, concept_map_count: conceptMaps.length, knowledge_concept_count: knowledgeConcepts.length, knowledge_context_count: knowledgeContexts.length, landscape_brief_count: landscapeBriefs.length, real_world_tension_count: realWorldTensions.length, research_problem_count: researchProblems.length, human_review_count: latestReviews.size });
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
