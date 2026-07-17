var ATRZoteroWorkbench;

function install() { Zotero.debug("ATR Workbench: installed"); }
async function startup({ id, version, rootURI }) {
  Services.scriptloader.loadSubScript(rootURI + "atr-zotero-workbench.js");
  ATRZoteroWorkbench.init({ id, version, rootURI });
  ATRZoteroWorkbench.addToAllWindows();
  ATRZoteroWorkbench.startObserving();
}
function onMainWindowLoad({ window }) { ATRZoteroWorkbench.addToWindow(window); }
function onMainWindowUnload({ window }) { ATRZoteroWorkbench.removeFromWindow(window); }
function shutdown() {
  ATRZoteroWorkbench.stopObserving();
  ATRZoteroWorkbench.removeFromAllWindows();
  ATRZoteroWorkbench = undefined;
}
function uninstall() { Zotero.debug("ATR Workbench: uninstalled"); }
