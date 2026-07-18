var ATRZoteroWorkbench;

function install() {}

// Follow the lifecycle used by Zotero's Make It Red example and current
// production plugins: wait for Zotero, then run plugin code in an explicit
// sandbox context. This also makes errors show up in Zotero's debug output.
async function startup({ id, version, resourceURI, rootURI }) {
  await Zotero.initializationPromise;
  if (!rootURI) rootURI = resourceURI.spec;

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
}

function uninstall() {}
