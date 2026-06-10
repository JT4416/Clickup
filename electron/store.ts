import { app } from "electron";
import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";
import {
  AgentConfig,
  ClickUpConnection,
  MicrosoftConnection,
  Settings,
} from "../shared/types";

interface StoreShape {
  settings: Settings;
  agents: AgentConfig[];
  /** Shared Anthropic environment id, created once on first run. */
  environmentId?: string;
  /** Shared Anthropic vault id holding MCP credentials. */
  vaultId?: string;
  clickup?: ClickUpConnection;
  microsoft?: MicrosoftConnection;
}

const DEFAULTS: StoreShape = {
  settings: {
    anthropicApiKey: "",
    clickupMcpUrl: "",
    microsoftClientId: "",
    githubPat: "",
  },
  agents: [],
};

/** Seeded on first launch so the dashboard never opens empty. */
function seedAgents(): AgentConfig[] {
  return [
    {
      id: crypto.randomUUID(),
      name: "ClickUp Expert",
      instructions: [
        "You are a ClickUp operations specialist for the F.S. OPERATIONS workspace.",
        "You know the workspace layout: TECH TOOLS (workflow forms), FIELD COMMISSIONING,",
        "INSTALLATION, WARRANTY / PARTS, TRAINING CENTER, and MANAGEMENT REVIEW.",
        "When given a task, use your ClickUp tools to read and update tasks, lists,",
        "and comments exactly as asked. Summarize what you changed when you finish.",
        "Never delete anything unless the instruction explicitly says to delete.",
      ].join(" "),
      model: "claude-opus-4-8",
      integrations: ["clickup"],
      mode: "manual",
      createdAt: new Date().toISOString(),
    },
  ];
}

export class Store {
  private file: string;
  private data: StoreShape;

  constructor() {
    this.file = path.join(app.getPath("userData"), "command-center.json");
    this.data = this.load();
  }

  private load(): StoreShape {
    try {
      const raw = fs.readFileSync(this.file, "utf-8");
      const parsed = JSON.parse(raw) as StoreShape;
      // Merge settings so fields added in later versions get defaults.
      return {
        ...DEFAULTS,
        ...parsed,
        settings: { ...DEFAULTS.settings, ...parsed.settings },
      };
    } catch {
      const fresh = { ...DEFAULTS, agents: seedAgents() };
      this.persist(fresh);
      return fresh;
    }
  }

  private persist(data: StoreShape = this.data): void {
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    fs.writeFileSync(this.file, JSON.stringify(data, null, 2), "utf-8");
  }

  getSettings(): Settings {
    return this.data.settings;
  }

  saveSettings(settings: Settings): void {
    this.data.settings = settings;
    this.persist();
  }

  getEnvironmentId(): string | undefined {
    return this.data.environmentId;
  }

  setEnvironmentId(id: string): void {
    this.data.environmentId = id;
    this.persist();
  }

  getVaultId(): string | undefined {
    return this.data.vaultId;
  }

  setVaultId(id: string): void {
    this.data.vaultId = id;
    this.persist();
  }

  getClickUp(): ClickUpConnection | undefined {
    return this.data.clickup;
  }

  setClickUp(connection: ClickUpConnection | undefined): void {
    this.data.clickup = connection;
    this.persist();
  }

  getMicrosoft(): MicrosoftConnection | undefined {
    return this.data.microsoft;
  }

  setMicrosoft(connection: MicrosoftConnection | undefined): void {
    this.data.microsoft = connection;
    this.persist();
  }

  listAgents(): AgentConfig[] {
    return this.data.agents;
  }

  getAgent(id: string): AgentConfig | undefined {
    return this.data.agents.find((a) => a.id === id);
  }

  createAgent(input: Omit<AgentConfig, "id" | "createdAt">): AgentConfig {
    const agent: AgentConfig = {
      ...input,
      id: crypto.randomUUID(),
      createdAt: new Date().toISOString(),
    };
    this.data.agents.push(agent);
    this.persist();
    return agent;
  }

  updateAgent(id: string, patch: Partial<AgentConfig>): AgentConfig | undefined {
    const agent = this.getAgent(id);
    if (!agent) return undefined;
    Object.assign(agent, patch);
    this.persist();
    return agent;
  }

  deleteAgent(id: string): void {
    this.data.agents = this.data.agents.filter((a) => a.id !== id);
    this.persist();
  }
}
