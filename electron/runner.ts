import Anthropic from "@anthropic-ai/sdk";
import * as crypto from "crypto";
import { ActivityEvent, AgentConfig, Settings } from "../shared/types";
import { Store } from "./store";

type Emit = (event: ActivityEvent) => void;

type AgentCreateParams = Anthropic.Beta.AgentCreateParams;
type RemoteAgentConfig = Pick<
  AgentCreateParams,
  "name" | "model" | "system" | "tools" | "mcp_servers"
>;

/**
 * Runs agents via Anthropic Managed Agents: the agent loop and sandbox are
 * hosted by Anthropic; this process creates sessions and relays the live
 * event stream to the dashboard.
 */
export class AgentRunner {
  private store: Store;
  private emit: Emit;
  /** agentId -> live session id, used by stop(). */
  private liveSessions = new Map<string, string>();

  constructor(store: Store, emit: Emit) {
    this.store = store;
    this.emit = emit;
  }

  isRunning(agentId: string): boolean {
    return this.liveSessions.has(agentId);
  }

  private client(settings: Settings): Anthropic {
    if (!settings.anthropicApiKey) {
      throw new Error("Anthropic API key is not set. Open Settings first.");
    }
    return new Anthropic({ apiKey: settings.anthropicApiKey });
  }

  private configHash(agent: AgentConfig, settings: Settings): string {
    const basis = JSON.stringify([
      agent.name,
      agent.instructions,
      agent.model,
      agent.integrations,
      settings.clickupMcpUrl,
    ]);
    return crypto.createHash("sha256").update(basis).digest("hex");
  }

  private buildRemoteConfig(agent: AgentConfig, settings: Settings): RemoteAgentConfig {
    const tools: NonNullable<AgentCreateParams["tools"]> = [
      { type: "agent_toolset_20260401", default_config: { enabled: true } },
    ];
    const mcpServers: NonNullable<AgentCreateParams["mcp_servers"]> = [];

    if (agent.integrations.includes("clickup")) {
      if (!settings.clickupMcpUrl) {
        throw new Error(
          "This agent uses ClickUp, but no ClickUp MCP URL is set in Settings.",
        );
      }
      mcpServers.push({ type: "url", name: "clickup", url: settings.clickupMcpUrl });
      tools.push({ type: "mcp_toolset", mcp_server_name: "clickup" });
    }

    return {
      name: agent.name,
      model: agent.model,
      system: agent.instructions,
      tools,
      mcp_servers: mcpServers,
    };
  }

  /** Create or sync the persistent remote agent + shared environment. */
  private async ensureRemote(agent: AgentConfig, settings: Settings): Promise<AgentConfig> {
    const client = this.client(settings);

    let environmentId = this.store.getEnvironmentId();
    if (!environmentId) {
      const env = await client.beta.environments.create({
        name: `command-center-${crypto.randomUUID().slice(0, 8)}`,
        config: { type: "cloud", networking: { type: "unrestricted" } },
      });
      environmentId = env.id;
      this.store.setEnvironmentId(environmentId);
    }

    const hash = this.configHash(agent, settings);
    const remoteConfig = this.buildRemoteConfig(agent, settings);

    if (!agent.remoteAgentId) {
      const created = await client.beta.agents.create(remoteConfig);
      return (
        this.store.updateAgent(agent.id, {
          remoteAgentId: created.id,
          remoteAgentVersion: Number(created.version),
          remoteConfigHash: hash,
        }) ?? agent
      );
    }

    if (agent.remoteConfigHash !== hash) {
      const updated = await client.beta.agents.update(agent.remoteAgentId, {
        version: agent.remoteAgentVersion!,
        ...remoteConfig,
      });
      return (
        this.store.updateAgent(agent.id, {
          remoteAgentVersion: Number(updated.version),
          remoteConfigHash: hash,
        }) ?? agent
      );
    }

    return agent;
  }

  async run(agentId: string, task: string): Promise<void> {
    const settings = this.store.getSettings();
    let agent = this.store.getAgent(agentId);
    if (!agent) throw new Error(`Unknown agent ${agentId}`);
    if (this.liveSessions.has(agentId)) {
      throw new Error(`${agent.name} is already running.`);
    }

    const runId = crypto.randomUUID();
    const log = (kind: ActivityEvent["kind"], text: string) =>
      this.emit({ agentId, runId, at: new Date().toISOString(), kind, text });

    try {
      agent = await this.ensureRemote(agent, settings);
      const client = this.client(settings);

      const session = await client.beta.sessions.create({
        agent: {
          type: "agent",
          id: agent.remoteAgentId!,
          version: agent.remoteAgentVersion!,
        },
        environment_id: this.store.getEnvironmentId()!,
        title: `${agent.name} — ${new Date().toLocaleString()}`,
      });

      this.liveSessions.set(agentId, session.id);
      log("run-started", `Session ${session.id} started.`);

      // Stream-first, then send the kickoff so no early events are missed.
      const stream = await client.beta.sessions.events.stream(session.id);
      await client.beta.sessions.events.send(session.id, {
        events: [{ type: "user.message", content: [{ type: "text", text: task }] }],
      });

      let summary = "";
      for await (const event of stream) {
        switch (event.type) {
          case "agent.message": {
            const text = event.content
              .filter((b) => b.type === "text")
              .map((b) => ("text" in b ? b.text : ""))
              .join("");
            if (text) {
              summary = text;
              log("agent-text", text);
            }
            break;
          }
          case "agent.tool_use":
          case "agent.mcp_tool_use":
            log("tool-use", event.name ?? "tool call");
            break;
          case "session.error":
            log("run-error", JSON.stringify(event.error ?? "Session error"));
            break;
        }

        if (event.type === "session.status_terminated") break;
        if (event.type === "session.status_idle") {
          if (event.stop_reason?.type === "requires_action") {
            // V1 has no client-side tools or approval gates, so nothing here
            // can resolve this — interrupt instead of deadlocking.
            await client.beta.sessions.events.send(session.id, {
              events: [{ type: "user.interrupt" }],
            });
            log("run-error", "Agent paused for an unsupported action; run was stopped.");
          }
          break;
        }
      }

      this.store.updateAgent(agentId, {
        lastRunAt: new Date().toISOString(),
        lastRunSummary: summary.slice(0, 280),
      });
      log("run-finished", "Run complete.");
    } catch (err) {
      log("run-error", err instanceof Error ? err.message : String(err));
      throw err;
    } finally {
      this.liveSessions.delete(agentId);
    }
  }

  async stop(agentId: string): Promise<void> {
    const sessionId = this.liveSessions.get(agentId);
    if (!sessionId) return;
    const client = this.client(this.store.getSettings());
    await client.beta.sessions.events.send(sessionId, {
      events: [{ type: "user.interrupt" }],
    });
  }
}
