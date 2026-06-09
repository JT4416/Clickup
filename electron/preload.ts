import { contextBridge, ipcRenderer, IpcRendererEvent } from "electron";
import { ActivityEvent, AgentConfig, Settings } from "../shared/types";

const api = {
  listAgents: (): Promise<AgentConfig[]> => ipcRenderer.invoke("agents:list"),
  createAgent: (input: Omit<AgentConfig, "id" | "createdAt">): Promise<AgentConfig> =>
    ipcRenderer.invoke("agents:create", input),
  updateAgent: (id: string, patch: Partial<AgentConfig>): Promise<AgentConfig | undefined> =>
    ipcRenderer.invoke("agents:update", id, patch),
  deleteAgent: (id: string): Promise<void> => ipcRenderer.invoke("agents:delete", id),
  isRunning: (id: string): Promise<boolean> => ipcRenderer.invoke("agents:isRunning", id),
  runAgent: (id: string, task: string): Promise<void> =>
    ipcRenderer.invoke("agents:run", id, task),
  stopAgent: (id: string): Promise<void> => ipcRenderer.invoke("agents:stop", id),
  getSettings: (): Promise<Settings> => ipcRenderer.invoke("settings:get"),
  saveSettings: (settings: Settings): Promise<void> =>
    ipcRenderer.invoke("settings:save", settings),
  onAgentEvent: (handler: (event: ActivityEvent) => void): (() => void) => {
    const listener = (_e: IpcRendererEvent, event: ActivityEvent) => handler(event);
    ipcRenderer.on("agent-event", listener);
    return () => ipcRenderer.removeListener("agent-event", listener);
  },
};

export type CommandCenterApi = typeof api;

contextBridge.exposeInMainWorld("commandCenter", api);
