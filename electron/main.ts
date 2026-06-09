import { app, BrowserWindow, ipcMain, Menu } from "electron";
import * as path from "path";
import { Store } from "./store";
import { AgentRunner } from "./runner";
import { ActivityEvent, AgentConfig, Settings } from "../shared/types";

let win: BrowserWindow | null = null;
const store = new Store();

const runner = new AgentRunner(store, (event: ActivityEvent) => {
  win?.webContents.send("agent-event", event);
});

function createWindow(): void {
  win = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#0f1115",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Standard right-click edit menu on text fields (Electron has none by default).
  win.webContents.on("context-menu", (_event, params) => {
    if (!params.isEditable && !params.selectionText) return;
    Menu.buildFromTemplate([
      { role: "cut", enabled: params.editFlags.canCut },
      { role: "copy", enabled: params.editFlags.canCopy },
      { role: "paste", enabled: params.editFlags.canPaste },
      { type: "separator" },
      { role: "selectAll" },
    ]).popup();
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    win.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    win.loadFile(path.join(__dirname, "..", "..", "dist", "index.html"));
  }
}

app.whenReady().then(() => {
  ipcMain.handle("agents:list", () => store.listAgents());
  ipcMain.handle("agents:create", (_e, input: Omit<AgentConfig, "id" | "createdAt">) =>
    store.createAgent(input),
  );
  ipcMain.handle("agents:update", (_e, id: string, patch: Partial<AgentConfig>) =>
    store.updateAgent(id, patch),
  );
  ipcMain.handle("agents:delete", (_e, id: string) => store.deleteAgent(id));
  ipcMain.handle("agents:isRunning", (_e, id: string) => runner.isRunning(id));

  ipcMain.handle("agents:run", async (_e, id: string, task: string) => {
    // Errors are already emitted to the activity feed; swallow here so the
    // renderer promise resolves either way.
    await runner.run(id, task).catch(() => undefined);
  });
  ipcMain.handle("agents:stop", (_e, id: string) => runner.stop(id));

  ipcMain.handle("settings:get", () => store.getSettings());
  ipcMain.handle("settings:save", (_e, settings: Settings) => store.saveSettings(settings));

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
