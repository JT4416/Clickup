import { useCallback, useEffect, useState } from "react";
import { ActivityEvent, AgentConfig, AgentStatus } from "../shared/types";
import { AgentCard } from "./components/AgentCard";
import { ActivityFeed } from "./components/ActivityFeed";
import { AgentForm } from "./components/AgentForm";
import { SettingsModal } from "./components/SettingsModal";

export function App() {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  /** Selected agent id, "ALL" for the broadcast feed, or null (closed). */
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [statuses, setStatuses] = useState<Record<string, AgentStatus>>({});
  const [showSettings, setShowSettings] = useState(false);
  const [editing, setEditing] = useState<AgentConfig | "new" | null>(null);

  const refresh = useCallback(async () => {
    setAgents(await window.commandCenter.listAgents());
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    return window.commandCenter.onAgentEvent((event) => {
      setEvents((prev) => [...prev.slice(-499), event]);
      if (event.kind === "run-started") {
        setStatuses((s) => ({ ...s, [event.agentId]: "running" }));
      } else if (event.kind === "run-finished") {
        setStatuses((s) => ({ ...s, [event.agentId]: "idle" }));
        refresh();
      } else if (event.kind === "run-error") {
        setStatuses((s) => ({ ...s, [event.agentId]: "error" }));
        refresh();
      }
    });
  }, [refresh]);

  const selected = agents.find((a) => a.id === selectedId) ?? null;
  const broadcast = selectedId === "ALL";
  const anyRunning = agents.some((a) => statuses[a.id] === "running");
  const agentNames = Object.fromEntries(agents.map((a) => [a.id, a.name]));

  const runAgent = (id: string, task: string) => {
    setSelectedId(id);
    void window.commandCenter.runAgent(id, task);
  };

  /** Send one instruction to every agent that isn't already busy. */
  const runAll = (task: string) => {
    for (const agent of agents) {
      if (statuses[agent.id] === "running") continue;
      void window.commandCenter.runAgent(agent.id, task);
    }
  };

  const saveAgent = async (
    input: Omit<AgentConfig, "id" | "createdAt">,
    existingId?: string,
  ) => {
    if (existingId) {
      await window.commandCenter.updateAgent(existingId, input);
    } else {
      await window.commandCenter.createAgent(input);
    }
    setEditing(null);
    refresh();
  };

  return (
    <div className="app">
      <header className="topbar">
        <div style={{ display: "flex", alignItems: "baseline" }}>
          <h1>Agentic Control Center</h1>
          <span className="sub">
            {agents.length} agent{agents.length === 1 ? "" : "s"}
          </span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setSelectedId(broadcast ? null : "ALL")}>
            Broadcast
          </button>
          <button className="primary" onClick={() => setEditing("new")}>
            + New Agent
          </button>
          <button onClick={() => setShowSettings(true)}>Settings</button>
        </div>
      </header>

      <div className="content">
        <main className="roster">
          {agents.length === 0 && (
            <div className="empty">No agents yet — create your first one.</div>
          )}
          {agents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              status={statuses[agent.id] ?? "idle"}
              selected={agent.id === selectedId}
              onSelect={() => setSelectedId(agent.id)}
              onRun={(task) => runAgent(agent.id, task)}
              onStop={() => void window.commandCenter.stopAgent(agent.id)}
              onEdit={() => setEditing(agent)}
              onModeChange={async (mode) => {
                await window.commandCenter.updateAgent(agent.id, { mode });
                refresh();
              }}
            />
          ))}
        </main>

        {broadcast ? (
          <ActivityFeed
            title="All Agents"
            status={anyRunning ? "running" : "idle"}
            events={events}
            agentNames={agentNames}
            lockWhileRunning={false}
            placeholder="Command every agent at once…"
            onSend={runAll}
            onClose={() => setSelectedId(null)}
          />
        ) : (
          selected && (
            <ActivityFeed
              title={selected.name}
              status={statuses[selected.id] ?? "idle"}
              events={events.filter((e) => e.agentId === selected.id)}
              onSend={(task) => runAgent(selected.id, task)}
              onClose={() => setSelectedId(null)}
            />
          )
        )}
      </div>

      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
      {editing && (
        <AgentForm
          agent={editing === "new" ? null : editing}
          onSave={saveAgent}
          onDelete={async (id) => {
            await window.commandCenter.deleteAgent(id);
            setEditing(null);
            if (selectedId === id) setSelectedId(null);
            refresh();
          }}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
