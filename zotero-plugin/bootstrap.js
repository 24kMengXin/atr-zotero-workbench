var ATRZoteroWorkbench;
var chromeHandle;

function install() {}

// Follow the lifecycle used by Zotero's Make It Red example and current
// production plugins: wait for Zotero, then run plugin code in an explicit
// sandbox context. This also makes errors show up in Zotero's debug output.
async function startup({ id, version, resourceURI, rootURI }) {
  await Zotero.initializationPromise;
  if (!rootURI) rootURI = resourceURI.spec;

  const aomStartup = Components.classes[
    "@mozilla.org/addons/addon-manager-startup;1"
  ].getService(Components.interfaces.amIAddonManagerStartup);
  const manifestURI = Services.io.newURI(rootURI + "manifest.json");
  chromeHandle = aomStartup.registerChrome(manifestURI, [
    ["content", "atr-zotero-workbench", rootURI],
  ]);

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
  if (chromeHandle) {
    chromeHandle.destruct();
    chromeHandle = undefined;
  }
}

function uninstall() {}
