/**
 * Arz-e-Pak desktop shell (Windows / macOS / Linux).
 *
 * Production: serves the built web app (dist/) from a privileged `app://arzepak/`
 * scheme so fetch, media and storage behave like a normal secure origin.
 * Development: `npm run desktop:dev` points ELECTRON_DEV_URL at the Vite server.
 */
const { app, BrowserWindow, protocol, net, session, shell, systemPreferences } = require("electron");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const DIST = path.join(__dirname, "..", "dist");
const DEV_URL = process.env.ELECTRON_DEV_URL;

protocol.registerSchemesAsPrivileged([
  { scheme: "app", privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true } },
]);

function serveDist() {
  protocol.handle("app", (req) => {
    const { pathname } = new URL(req.url);
    const rel = decodeURIComponent(pathname).replace(/^\/+/, "") || "index.html";
    const file = path.normalize(path.join(DIST, rel));
    // Never serve anything outside dist/.
    if (!file.startsWith(DIST)) return new Response("Not found", { status: 404 });
    return net.fetch(pathToFileURL(file).toString());
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 380,
    minHeight: 640,
    title: "Arz-e-Pak",
    backgroundColor: "#07130d",
    icon: path.join(__dirname, "..", "build-resources", "icon.png"),
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: true,
      // app:// is a secure origin; this lets it reach a backend on plain http:// over the
      // LAN (localhost is already allowed). Safe here: the window only ever runs the
      // bundled app — navigation elsewhere is blocked below.
      allowRunningInsecureContent: true,
      additionalArguments: [`--arzepak-version=${app.getVersion()}`],
    },
  });
  win.once("ready-to-show", () => win.show());

  // External links (maps, docs) open in the system browser, never inside the app.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/i.test(url)) void shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => {
    const internal = DEV_URL ? url.startsWith(DEV_URL) : url.startsWith("app://");
    if (!internal) {
      e.preventDefault();
      if (/^https?:/i.test(url)) void shell.openExternal(url);
    }
  });

  void win.loadURL(DEV_URL || "app://arzepak/index.html");
}

app.whenReady().then(async () => {
  serveDist();
  // Allow the microphone (voice assistant); deny every other permission request.
  session.defaultSession.setPermissionRequestHandler((_wc, permission, cb) => cb(permission === "media" || permission === "clipboard-sanitized-write"));
  if (process.platform === "darwin") await systemPreferences.askForMediaAccess("microphone").catch(() => false);
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
