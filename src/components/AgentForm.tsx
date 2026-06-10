import { useEffect, useState } from "react";
import { AgentConfig, AgentMode, IntegrationId } from "../../shared/types";

const MODELS = [
  { id: "claude-opus-4-8", label: "Claude Opus 4.8 (most capable)" },
  { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6 (fast + smart)" },
  { id: "claude-haiku-4-5", label: "Claude Haiku 4.5 (fastest)" },
];

const INTEGRATIONS: { id: IntegrationId; label: string; hint: string }[] = [
  { id: "clickup", label: "ClickUp", hint: "Read and manage your ClickUp workspace" },
  { id: "web", label: "Web research", hint: "Search and read the web (built-in)" },
  {
    id: "outlook",
    label: "Outlook email",
    hint: "Search, read, and forward email (requires Microsoft 365 in Settings)",
  },
  {
    id: "localweb",
    label: "Local browser",
    hint: "Read internal dashboards using your PC's network and saved logins",
  },
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
  /** Full roster, used for the hand-off picker. */
  agents: AgentConfig[];
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
  const [repoUrl, setRepoUrl] = useState(existing?.repoUrl ?? "");
  const [voice, setVoice] = useState(existing?.voice ?? "");
  const [handoffAgentId, setHandoffAgentId] = useState(existing?.handoffAgentId ?? "");
  const [handoffTask, setHandoffTask] = useState(existing?.handoffTask ?? "");
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);

  useEffect(() => {
    const load = () => setVoices(window.speechSynthesis?.getVoices() ?? []);
    load();
    window.speechSynthesis?.addEventListener("voiceschanged", load);
    return () => window.speechSynthesis?.removeEventListener("voiceschanged", load);
  }, []);

  const previewVoice = (name: string) => {
    if (!name || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance("Online and ready for orders.");
    const v = window.speechSynthesis.getVoices().find((x) => x.name === name);
    if (v) u.voice = v;
    window.speechSynthesis.speak(u);
  };

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
        repoUrl: repoUrl.trim() || undefined,
        voice: voice || undefined,
        handoffAgentId: handoffAgentId || undefined,
        handoffTask: handoffTask.trim() || undefined,
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

        <label>Voice</label>
        <select
          value={voice}
          onChange={(e) => {
            setVoice(e.target.value);
            previewVoice(e.target.value);
          }}
        >
          <option value="">Silent (no voice)</option>
          {voices.map((v) => (
            <option key={v.name} value={v.name}>
              {v.name.replace("Microsoft ", "")} ({v.lang})
            </option>
          ))}
        </select>
        <p className="hint">
          The agent announces its result in this voice when a run completes.
          Picking one plays a preview.
        </p>

        <label>Hand off result to (optional)</label>
        <select
          value={handoffAgentId}
          onChange={(e) => setHandoffAgentId(e.target.value)}
        >
          <option value="">No hand-off</option>
          {props.agents
            .filter((a) => a.id !== existing?.id)
            .map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
        </select>
        {handoffAgentId && (
          <>
            <label>Hand-off instruction</label>
            <textarea
              rows={2}
              value={handoffTask}
              onChange={(e) => setHandoffTask(e.target.value)}
              placeholder="e.g. Post this report to ClickUp list 901327448848 as a task titled DAILY STATUS REPORT - [today's date]."
            />
            <p className="hint">
              When this agent finishes, its result is sent to the chosen agent with
              this instruction — an automatic pipeline.
            </p>
          </>
        )}

        <label>GitHub repo (optional)</label>
        <input
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          placeholder="https://github.com/you/your-repo"
        />
        <p className="hint">
          The repo is mounted into every run so the agent can read and edit its
          code. Requires a GitHub token in Settings.
        </p>

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
