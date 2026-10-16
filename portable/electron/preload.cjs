// Minimal, read-only bridge so the web app knows it runs inside the desktop shell.
const { contextBridge } = require("electron");

const versionArg = process.argv.find((a) => a.startsWith("--arzepak-version="));

contextBridge.exposeInMainWorld("arzepak", {
  isElectron: true,
  platform: process.platform,
  version: versionArg ? versionArg.split("=")[1] : "1.0.0",
});
