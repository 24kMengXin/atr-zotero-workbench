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
      let gateNodes = nodes.filter(node => node.kind === "gate");
      let skillEvents = nodes.filter(node => node.kind === "skill_event").sort((a, b) => String(a.data?.timestamp || "").localeCompare(String(b.data?.timestamp || "")));
      let runNode = nodes.find(node => node.kind === "run");
      let scholarly = papers.filter(node => node.data?.source_layer === "scholarly_evidence").length;
      let contextual = papers.filter(node => node.data?.source_layer === "contextual_inspiration").length;
      let reviewEvents = await this.readJsonLines(this.inboxPath());
      let latestReviews = new Map();
      for (let event of reviewEvents) if (event.event === "human_note_modified") latestReviews.set(event.zotero_note_key, event);
      meta.setAttribute("value", `${graph.run || "unknown run"} · 派生只读投影`);
      let metrics = xul("hbox"); metrics.setAttribute("style", "margin-bottom:16px");
      for (let [count, title] of [[questions.length,"研究问题"],[scholarly,"学术证据"],[contextual,"现实灵感"],[(graph.history?.snapshots || []).length,"历史快照"]]) {
        let card = xul("vbox"); card.setAttribute("style", "background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:12px;margin-right:10px;min-width:130px");
        card.append(label(count, "font-size:24px;font-weight:bold"), label(title)); metrics.append(card);
      }
      body.append(metrics, label("从问题向知识展开", "font-size:20px;font-weight:bold;margin-bottom:10px"));
      let lifecycleBox = xul("vbox"); lifecycleBox.setAttribute("style", "background:#eaf2fb;border:1px solid #8baed1;border-radius:8px;padding:14px;margin-bottom:16px");
      lifecycleBox.append(label("ATR 运行过程", "font-size:18px;font-weight:bold"));
      lifecycleBox.append(label("当前阶段：" + (runNode?.data?.stage || "未记录") + " · 状态：" + (runNode?.data?.status || "未记录"), "white-space:normal"));
      lifecycleBox.append(label("下一步：" + (runNode?.data?.next_action || "未记录"), "white-space:normal;color:#365b7b;margin:4px 0"));
      if (gateNodes.length) lifecycleBox.append(label("质量门：" + gateNodes.map(gate => gate.label).join(" · "), "white-space:normal;color:#365b7b"));
      else lifecycleBox.append(label("该 legacy run 未提供 gate ledger。", "white-space:normal;color:#64748b"));
      if (skillEvents.length) lifecycleBox.append(label("最近已记录的研究动作：" + skillEvents.slice(-6).map(event => event.label).join(" · "), "white-space:normal;color:#365b7b;margin-top:4px"));
      else lifecycleBox.append(label("当前 run 未记录 skill events。", "white-space:normal;color:#64748b;margin-top:4px"));
      body.append(lifecycleBox);
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
          review.append(label(paper?.label || event.atr_source_id || "未映射来源", "font-weight:bold;white-space:normal"));
          review.append(label("最近研究问题：" + (nearest.map(node => node.label).join(" · ") || "尚未在当前投影中找到"), "white-space:normal;color:#365b47"));
          review.append(label(this.plainNote(event.note_html).slice(0, 420) || "（笔记内容为空）", "white-space:normal;color:#475569;margin-top:4px"));
          reviewBox.append(review);
        }
      }
      body.append(reviewBox);
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
      if (!questions.length) body.append(label("当前 run 尚未产生 frontier tensions；插件不会凭空生成研究问题。", "white-space:normal"));
      if (graph.diagnostics?.length) {
        let warning = xul("vbox"); warning.setAttribute("style", "background:#fff7e6;border:1px solid #f0c36d;border-radius:8px;padding:12px");
        warning.append(label("数据完整性提示", "font-weight:bold"), label(graph.diagnostics.join("；"), "white-space:normal")); body.append(warning);
      }
      await this.appendRuntimeStatus("render_completed", { question_count: questions.length, source_count: papers.length, human_review_count: latestReviews.size });
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
