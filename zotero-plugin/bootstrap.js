var ATRZoteroWorkbench;
var ATRZoteroWorkbenchChromeHandle;

function install() {}

// Follow the lifecycle used by Zotero's Make It Red example and current
// production plugins: wait for Zotero, then run plugin code in an explicit
// sandbox context. This also makes errors show up in Zotero's debug output.
async function startup({ id, version, resourceURI, rootURI }) {
  await Zotero.initializationPromise;
  if (!rootURI) rootURI = resourceURI.spec;

  // Register bundled HTML as chrome content. A content browser in Zotero does
  // not reliably load arbitrary add-on-root URIs, while chrome:// is the
  // supported route used by established Zotero 9 extensions.
  const aomStartup = Components.classes[
    "@mozilla.org/addons/addon-manager-startup;1"
  ].getService(Components.interfaces.amIAddonManagerStartup);
  ATRZoteroWorkbenchChromeHandle = aomStartup.registerChrome(
    Services.io.newURI(rootURI + "manifest.json"),
    [["content", "atr-zotero-workbench", rootURI + "chrome/content/"]]
  );

  const ctx = { Zotero, Services, IOUtils, PathUtils, Components, rootURI };
  ctx._globalThis = ctx;
  Services.scriptloader.loadSubScript(rootURI + "atr-zotero-workbench.js", ctx);
  ATRZoteroWorkbench = ctx.ATRZoteroWorkbench;
  await ATRZoteroWorkbench.hooks.onStartup({ id, version, rootURI });
}

async function onMainWindowLoad({ window }) {
  await ATRZoteroWorkbench?.hooks.onMainWindowLoad(window);
}

async function onMainWindowUnload({ window }) {
  await ATRZoteroWorkbench?.hooks.onMainWindowUnload(window);
}

async function shutdown() {
  await ATRZoteroWorkbench?.hooks.onShutdown();
  ATRZoteroWorkbench = undefined;
  ATRZoteroWorkbenchChromeHandle?.destruct();
  ATRZoteroWorkbenchChromeHandle = undefined;
}

function uninstall() {}
