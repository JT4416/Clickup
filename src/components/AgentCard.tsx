import { useState } from "react";
import { AgentConfig, AgentMode, AgentStatus } from "../../shared/types";

const INTEGRATION_LABELS: Record<string, string> = {
  clickup: "ClickUp",
  web: "Web",
};

function formatInterval(minutes: number): string {
  if (minutes >= 1440) return "daily";
  if (minutes >= 60) return `every ${minutes / 60}h`;
  return `every ${minutes}m`;
}

export function AgentCard(props: {
  agent: AgentConfig;
  status: AgentStatus;
  selected: boolean;
  onSelect: () => void;
  onRun: (task: string) => void;
  onStop: () => void;
  onEdit: () => void;
  onModeChange: (mode: AgentMode) => void;
}) {
  const { agent, status } = props;
  const [askTask, setAskTask] = useState(false);
  const [task, setTask] = useState("");

  const running = status === "running";
  const integrations = agent.integrations
    .map((i) => INTEGRATION_LABELS[i] ?? i)
    .join(" · ");

  return (
    <div
      className={`card${props.selected ? " selected" : ""}`}
      onClick={props.onSelect}
    >
      <div className="head">
        <span className="name">{agent.name}</span>
        <span className={`status ${status}`}>
          <span className="dot" />
          {running ? "running" : status === "error" ? "error" : "idle"}
        </span>
      </div>

      <div className="meta">
        {integrations || "No integrations"}
        {agent.mode === "auto" &&
          agent.scheduleMinutes &&
          ` · auto ${formatInterval(agent.scheduleMinutes)}`}
        {agent.lastRunAt &&
          ` · last run ${new Date(agent.lastRunAt).toLocaleString()}`}
      </div>
      <div className="summary">{agent.lastRunSummary ?? "No runs yet."}</div>

      {askTask ? (
        <div className="actions" onClick={(e) => e.stopPropagation()}>
          <input
            autoFocus
            placeholder="What should it do?"
            value={task}
            onChange={(e) => setTask(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && task.trim()) {
                props.onRun(task.trim());
                setTask("");
                setAskTask(false);
              }
              if (e.key === "Escape") setAskTask(false);
            }}
          />
        </div>
      ) : (
        <div className="actions" onClick={(e) => e.stopPropagation()}>
          {running ? (
            <button className="danger" onClick={props.onStop}>
              Stop
            </button>
          ) : (
            <button className="primary" onClick={() => setAskTask(true)}>
              Run Now
            </button>
          )}
          <button onClick={props.onEdit}>Edit</button>
          <div className="toggle" title="Auto-run on a schedule (phase 3) or manual only">
            <button
              className={agent.mode === "auto" ? "active" : ""}
              onClick={() => props.onModeChange("auto")}
            >
              Auto
            </button>
            <button
              className={agent.mode === "manual" ? "active" : ""}
              onClick={() => props.onModeChange("manual")}
            >
              Manual
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
