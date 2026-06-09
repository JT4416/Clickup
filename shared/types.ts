// Shared between the Electron main process and the renderer.

export type AgentMode = "auto" | "manual";

export type AgentStatus = "idle" | "running" | "error";

/** An integration the agent can be granted. Each maps to an MCP server. */
export type IntegrationId = "clickup" | "web";

export interface AgentConfig {
  id: string;
  name: string;
  /** Plain-English standing instructions — becomes the agent's system prompt. */
  instructions: string;
  model: string;
  integrations: IntegrationId[];
  /** "auto" = scheduler starts runs on an interval; "manual" = only Run Now. */
  mode: AgentMode;
  /** Minutes between automatic runs (auto mode). */
  scheduleMinutes?: number;
  /** The standing task given to the agent on every scheduled run (auto mode). */
  autoTask?: string;
  /** Legacy free-text schedule note (pre-phase-3); superseded by scheduleMinutes. */
  schedule?: string;
  createdAt: string;
  lastRunAt?: string;
  lastRunSummary?: string;
  /** Remote (Anthropic) identifiers — created lazily on first run. */
  remoteAgentId?: string;
  remoteAgentVersion?: number;
  /** Hash of the config last pushed remotely, so edits sync before the next run. */
  remoteConfigHash?: string;
}

export interface Settings {
  anthropicApiKey: string;
  /** Streamable-HTTP MCP endpoint for ClickUp, e.g. from the ClickUp MCP docs. */
  clickupMcpUrl: string;
}

export interface ClickUpConnection {
  credentialId: string;
  connectedAt: string;
}

export interface IntegrationStatus {
  clickup: { connected: boolean; connectedAt?: string };
}

/** A single line in an agent's activity feed. */
export interface ActivityEvent {
  agentId: string;
  runId: string;
  at: string;
  kind:
    | "run-started"
    | "agent-text"
    | "agent-thinking"
    | "tool-use"
    | "tool-result"
    | "run-finished"
    | "run-error";
  text: string;
}

export interface RunState {
  agentId: string;
  runId: string;
  status: AgentStatus;
}
