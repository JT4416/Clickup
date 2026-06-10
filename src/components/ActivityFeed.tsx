import { useEffect, useRef, useState } from "react";
import { ActivityEvent, AgentStatus } from "../../shared/types";

export function ActivityFeed(props: {
  title: string;
  status: AgentStatus;
  events: ActivityEvent[];
  /** When provided, each event line is prefixed with its agent's name. */
  agentNames?: Record<string, string>;
  /** Broadcast mode keeps the composer open while agents are running. */
  lockWhileRunning?: boolean;
  placeholder?: string;
  onSend: (task: string) => void;
  onClose: () => void;
}) {
  const [task, setTask] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [props.events.length]);

  const locked = (props.lockWhileRunning ?? true) && props.status === "running";

  const send = () => {
    if (!task.trim() || locked) return;
    props.onSend(task.trim());
    setTask("");
  };

  return (
    <aside className="feed">
      <div className="feed-head">
        <div>
          <strong>{props.title}</strong>
          <span className={`status ${props.status}`} style={{ marginLeft: 10 }}>
            <span className="dot" /> {props.status}
          </span>
        </div>
        <button onClick={props.onClose}>Close</button>
      </div>

      <div className="events">
        {props.events.length === 0 && (
          <div className="event run-started">
            Activity will appear here when agents run.
          </div>
        )}
        {props.events.map((e, i) => (
          <div className={`event ${e.kind}`} key={i}>
            <div className="when">
              {props.agentNames && (
                <span className="who">{props.agentNames[e.agentId] ?? "?"}</span>
              )}
              {new Date(e.at).toLocaleTimeString()}
            </div>
            {e.kind === "tool-use" ? `→ ${e.text}` : e.text}
          </div>
        ))}
        <div ref={bottom} />
      </div>

      <div className="composer">
        <input
          placeholder={
            locked
              ? "Agent is working…"
              : (props.placeholder ?? "Give this agent a task…")
          }
          value={task}
          disabled={locked}
          onChange={(e) => setTask(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        <button className="primary" onClick={send} disabled={locked}>
          Run
        </button>
      </div>
    </aside>
  );
}
