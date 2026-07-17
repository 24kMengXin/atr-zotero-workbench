/* global IOUtils, PathUtils */
var ATRZoteroWorkbench = {
  id: null, rootURI: null, observerID: null, addedElementIDs: [],
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
  removeFromWindow(window) { for (let id of this.addedElementIDs) window.document.getElementById(id)?.remove(); },
  removeFromAllWindows() { for (let win of Zotero.getMainWindows()) if (win.ZoteroPane) this.removeFromWindow(win); },
  openWorkbench(window) {
    let tab = window.Zotero_Tabs.add({ type: "atr-zotero-workbench", title: "ATR Research Workbench", data: {}, select: true });
    // A Zotero tab is XUL chrome, not a regular web document.  Use the same
    // native content-browser pattern as Zotero's own reader instead of an
    // HTML iframe: iframe content can be silently blocked here and produces a
    // blank tab.  The page is bundled in the XPI, so it also avoids file://
    // permissions for a workspace outside the add-on.
    let browser = window.document.createXULElement("browser");
    browser.id = "atr-zotero-workbench-browser-" + tab.id;
    browser.setAttribute("type", "content");
    browser.setAttribute("flex", "1");
    browser.setAttribute("remote", "false");
    browser.setAttribute("disableglobalhistory", "true");
    browser.setAttribute("src", this.rootURI + "workbench/index.html");
    tab.container.appendChild(browser);
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
