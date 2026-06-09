import { useCallback, useEffect, useState } from "react";
import { ActivityEvent, AgentConfig, AgentStatus } from "../shared/types";
import { AgentCard } from "./components/AgentCard";
import { ActivityFeed } from "./components/ActivityFeed";
import { AgentForm } from "./components/AgentForm";
import { SettingsModal } from "./components/SettingsModal";

export function App() {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
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

  const runAgent = (id: string, task: string) => {
    setSelectedId(id);
    void window.commandCenter.runAgent(id, task);
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
          <h1>Agent Command Center</h1>
          <span className="sub">
            {agents.length} agent{agents.length === 1 ? "" : "s"}
          </span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
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

        {selected && (
          <ActivityFeed
            agent={selected}
            status={statuses[selected.id] ?? "idle"}
            events={events.filter((e) => e.agentId === selected.id)}
            onSend={(task) => runAgent(selected.id, task)}
            onClose={() => setSelectedId(null)}
          />
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
