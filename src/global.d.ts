import type {
  ActivityEvent,
  AgentConfig,
  DeviceCodePrompt,
  IntegrationStatus,
  Settings,
} from "../shared/types";

declare global {
  interface Window {
    commandCenter: {
      listAgents(): Promise<AgentConfig[]>;
      createAgent(input: Omit<AgentConfig, "id" | "createdAt">): Promise<AgentConfig>;
      updateAgent(id: string, patch: Partial<AgentConfig>): Promise<AgentConfig | undefined>;
      deleteAgent(id: string): Promise<void>;
      isRunning(id: string): Promise<boolean>;
      runAgent(id: string, task: string): Promise<void>;
      stopAgent(id: string): Promise<void>;
      getIntegrationStatus(): Promise<IntegrationStatus>;
      connectClickUp(): Promise<IntegrationStatus>;
      connectMicrosoft(): Promise<IntegrationStatus>;
      onDeviceCode(handler: (prompt: DeviceCodePrompt) => void): () => void;
      openLoginWindow(url: string): Promise<void>;
      getSettings(): Promise<Settings>;
      saveSettings(settings: Settings): Promise<void>;
      onAgentEvent(handler: (event: ActivityEvent) => void): () => void;
    };
  }
}

export {};
