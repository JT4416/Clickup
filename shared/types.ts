// Shared between the Electron main process and the renderer.

export type AgentMode = "auto" | "manual";

export type AgentStatus = "idle" | "running" | "error";

/** An integration the agent can be granted. */
export type IntegrationId = "clickup" | "web" | "outlook";

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
  /** GitHub repo (https URL) mounted into this agent's sessions. */
  repoUrl?: string;
  /** Remote (Anthropic) identifiers — created lazily on first run. */
  remoteAgentId?: string;
  remoteAgentVersion?: number;
  /** Hash of the config last pushed remotely, so edits sync before the next run. */
  remoteConfigHash?: string;
}

export interface Settings {
  anthropicApiKey: string;
  /** Streamable-HTTP MCP endpoint for ClickUp; blank = default server. */
  clickupMcpUrl: string;
  /** Azure app registration (public client) used for Microsoft 365 sign-in. */
  microsoftClientId: string;
  /** GitHub personal access token used to mount repos into agent sessions. */
  githubPat: string;
}

export interface MicrosoftConnection {
  clientId: string;
  accessToken: string;
  refreshToken: string;
  /** RFC 3339 expiry of the access token. */
  expiresAt: string;
  connectedAt: string;
  account?: string;
}

export interface DeviceCodePrompt {
  userCode: string;
  verificationUri: string;
}

export interface ClickUpConnection {
  credentialId: string;
  connectedAt: string;
}

export interface IntegrationStatus {
  clickup: { connected: boolean; connectedAt?: string };
  microsoft: { connected: boolean; connectedAt?: string; account?: string };
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
