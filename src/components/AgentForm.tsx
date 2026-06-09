import { useState } from "react";
import { AgentConfig, AgentMode, IntegrationId } from "../../shared/types";

const MODELS = [
  { id: "claude-opus-4-8", label: "Claude Opus 4.8 (most capable)" },
  { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6 (fast + smart)" },
  { id: "claude-haiku-4-5", label: "Claude Haiku 4.5 (fastest)" },
];

const INTEGRATIONS: { id: IntegrationId; label: string; hint: string }[] = [
  { id: "clickup", label: "ClickUp", hint: "Read and manage your ClickUp workspace" },
  { id: "web", label: "Web research", hint: "Search and read the web (built-in)" },
];

const INTERVALS = [
  { minutes: 15, label: "Every 15 minutes" },
  { minutes: 30, label: "Every 30 minutes" },
  { minutes: 60, label: "Every hour" },
  { minutes: 240, label: "Every 4 hours" },
  { minutes: 1440, label: "Once a day" },
];

export function AgentForm(props: {
  agent: AgentConfig | null;
  onSave: (input: Omit<AgentConfig, "id" | "createdAt">, existingId?: string) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}) {
  const existing = props.agent;
  const [name, setName] = useState(existing?.name ?? "");
  const [instructions, setInstructions] = useState(existing?.instructions ?? "");
  const [model, setModel] = useState(existing?.model ?? "claude-opus-4-8");
  const [mode, setMode] = useState<AgentMode>(existing?.mode ?? "manual");
  const [scheduleMinutes, setScheduleMinutes] = useState(
    existing?.scheduleMinutes ?? 60,
  );
  const [autoTask, setAutoTask] = useState(existing?.autoTask ?? "");
  const [integrations, setIntegrations] = useState<IntegrationId[]>(
    existing?.integrations ?? [],
  );

  const toggleIntegration = (id: IntegrationId) =>
    setIntegrations((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );

  const autoIncomplete = mode === "auto" && !autoTask.trim();

  const save = () => {
    if (!name.trim() || !instructions.trim() || autoIncomplete) return;
    props.onSave(
      {
        name: name.trim(),
        instructions: instructions.trim(),
        model,
        mode,
        scheduleMinutes,
        autoTask: autoTask.trim() || undefined,
        integrations,
        // Preserve run history + remote linkage on edit.
        ...(existing
          ? {
              lastRunAt: existing.lastRunAt,
              lastRunSummary: existing.lastRunSummary,
              remoteAgentId: existing.remoteAgentId,
              remoteAgentVersion: existing.remoteAgentVersion,
              remoteConfigHash: existing.remoteConfigHash,
            }
          : {}),
      },
      existing?.id,
    );
  };

  return (
    <div className="modal-backdrop" onClick={props.onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>{existing ? `Edit ${existing.name}` : "New Agent"}</h2>
        <p className="hint">
          Describe the job in plain English — this becomes the agent's standing
          instructions.
        </p>

        <label>Name</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Receipt Collector"
        />

        <label>Instructions</label>
        <textarea
          rows={6}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          placeholder="What is this agent's job? What should it always / never do?"
        />

        <label>Model</label>
        <select value={model} onChange={(e) => setModel(e.target.value)}>
          {MODELS.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>

        <label>Integrations</label>
        {INTEGRATIONS.map((integ) => (
          <div key={integ.id} style={{ margin: "6px 0" }}>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                textTransform: "none",
                fontSize: 14,
                color: "var(--text)",
                margin: 0,
              }}
            >
              <input
                type="checkbox"
                style={{ width: "auto" }}
                checked={integrations.includes(integ.id)}
                onChange={() => toggleIntegration(integ.id)}
              />
              {integ.label}
              <span className="hint">— {integ.hint}</span>
            </label>
          </div>
        ))}

        <label>Mode</label>
        <div className="toggle" style={{ marginLeft: 0 }}>
          <button className={mode === "auto" ? "active" : ""} onClick={() => setMode("auto")}>
            Auto
          </button>
          <button
            className={mode === "manual" ? "active" : ""}
            onClick={() => setMode("manual")}
          >
            Manual
          </button>
        </div>
        {mode === "auto" && (
          <>
            <label>Runs</label>
            <select
              value={scheduleMinutes}
              onChange={(e) => setScheduleMinutes(Number(e.target.value))}
            >
              {INTERVALS.map((i) => (
                <option key={i.minutes} value={i.minutes}>
                  {i.label}
                </option>
              ))}
            </select>

            <label>Standing task (sent on every scheduled run)</label>
            <textarea
              rows={3}
              value={autoTask}
              onChange={(e) => setAutoTask(e.target.value)}
              placeholder="e.g. Check for new form submissions since your last run and summarize them."
            />
            <p className="hint">
              Runs fire while the app is open or minimized to the tray. Closing the
              window keeps it running; use Quit in the tray menu to stop fully.
            </p>
          </>
        )}

        <div className="row">
          {existing && (
            <button
              className="danger"
              style={{ marginRight: "auto" }}
              onClick={() => props.onDelete(existing.id)}
            >
              Delete
            </button>
          )}
          <button onClick={props.onClose}>Cancel</button>
          <button
            className="primary"
            onClick={save}
            disabled={!name.trim() || !instructions.trim() || autoIncomplete}
          >
            {existing ? "Save" : "Create Agent"}
          </button>
        </div>
      </div>
    </div>
  );
}
