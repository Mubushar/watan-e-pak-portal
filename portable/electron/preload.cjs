// Minimal, read-only bridge so the web app knows it runs inside the desktop shell.
const { contextBridge } = require("electron");

const versionArg = process.argv.find((a) => a.startsWith("--watanepak-version="));

contextBridge.exposeInMainWorld("watanepak", {
  isElectron: true,
  platform: process.platform,
  version: versionArg ? versionArg.split("=")[1] : "1.0.0",
});
