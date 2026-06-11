import { app, BrowserWindow, ipcMain, Menu, nativeImage, Tray } from "electron";
import * as path from "path";
import { Store } from "./store";
import { AgentRunner } from "./runner";
import { Scheduler } from "./scheduler";
import { connectClickUp, connectMicrosoft365, integrationStatus } from "./integrations";
import { executeLocalWebTool, openLoginWindow } from "./localweb";
import { ActivityEvent, AgentConfig, DeviceCodePrompt, Settings } from "../shared/types";

let win: BrowserWindow | null = null;
let tray: Tray | null = null;
let isQuitting = false;

const store = new Store();

const runner = new AgentRunner(store, (event: ActivityEvent) => {
  win?.webContents.send("agent-event", event);
});

const scheduler = new Scheduler(store, runner);

/** Simple solid-dot tray icon drawn at runtime (no asset file needed). */
function trayIcon() {
  const size = 16;
  const buf = Buffer.alloc(size * size * 4);
  const cx = size / 2 - 0.5;
  const radius = 6.5;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      const inside = (x - cx) ** 2 + (y - cx) ** 2 <= radius ** 2;
      // BGRA — accent blue #4f8cff
      buf[i] = 0xff;
      buf[i + 1] = 0x8c;
      buf[i + 2] = 0x4f;
      buf[i + 3] = inside ? 0xff : 0x00;
    }
  }
  return nativeImage.createFromBitmap(buf, { width: size, height: size });
}

function showWindow(): void {
  if (win) {
    win.show();
    win.focus();
  } else {
    createWindow();
  }
}

function createTray(): void {
  tray = new Tray(trayIcon());
  tray.setToolTip("Agent Command Center");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Open Agent Command Center", click: showWindow },
      { type: "separator" },
      {
        label: "Quit",
        click: () => {
          isQuitting = true;
          app.quit();
        },
      },
    ]),
  );
  tray.on("double-click", showWindow);
}

/** Registers/unregisters the app as a Windows startup item (installed app only). */
function applyLaunchAtLogin(): void {
  if (!app.isPackaged) return; // in dev this would register electron.exe
  app.setLoginItemSettings({
    openAtLogin: store.getSettings().launchAtLogin,
    args: ["--hidden"],
  });
}

function createWindow(show = true): void {
  win = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 960,
    minHeight: 640,
    show,
    backgroundColor: "#04070e",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Closing hides to the tray; agents and the scheduler keep running.
  win.on("close", (e) => {
    if (!isQuitting) {
      e.preventDefault();
      win?.hide();
    }
  });
  win.on("closed", () => {
    win = null;
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

// Single instance: launching the app again focuses the existing window.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", showWindow);

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

    ipcMain.handle("integrations:status", () => integrationStatus(store));
    ipcMain.handle("integrations:connectClickUp", () => connectClickUp(store));
    ipcMain.handle("integrations:connectMicrosoft", () =>
      connectMicrosoft365(store, (prompt: DeviceCodePrompt) => {
        win?.webContents.send("ms-device-code", prompt);
      }),
    );

    ipcMain.handle("settings:get", () => store.getSettings());
    ipcMain.handle("settings:save", (_e, settings: Settings) => {
      store.saveSettings(settings);
      applyLaunchAtLogin();
    });

    ipcMain.handle("localweb:openLogin", (_e, url: string) => openLoginWindow(url));
    ipcMain.handle("localweb:test", async (_e, url: string) => {
      const started = Date.now();
      try {
        const result = await executeLocalWebTool("read_page", {
          url,
          wait_seconds: 8,
        });
        return { ok: true, ms: Date.now() - started, result };
      } catch (err) {
        return {
          ok: false,
          ms: Date.now() - started,
          result: err instanceof Error ? err.message : String(err),
        };
      }
    });

    createTray();
    // Started by Windows at login → stay hidden in the tray.
    createWindow(!process.argv.includes("--hidden"));
    applyLaunchAtLogin();
    scheduler.start();

    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });

  app.on("before-quit", () => {
    isQuitting = true;
    scheduler.stop();
  });

  // Keep running in the tray when the window closes (all platforms but macOS
  // would normally quit here).
  app.on("window-all-closed", () => {
    /* stay alive in tray */
  });
}
