import { useEffect, useRef, useState } from "react";
import { ActivityEvent, AgentConfig, AgentStatus } from "../../shared/types";

export function ActivityFeed(props: {
  agent: AgentConfig;
  status: AgentStatus;
  events: ActivityEvent[];
  onSend: (task: string) => void;
  onClose: () => void;
}) {
  const [task, setTask] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [props.events.length]);

  const send = () => {
    if (!task.trim() || props.status === "running") return;
    props.onSend(task.trim());
    setTask("");
  };

  return (
    <aside className="feed">
      <div className="feed-head">
        <div>
          <strong>{props.agent.name}</strong>
          <span className={`status ${props.status}`} style={{ marginLeft: 10 }}>
            <span className="dot" /> {props.status}
          </span>
        </div>
        <button onClick={props.onClose}>Close</button>
      </div>

      <div className="events">
        {props.events.length === 0 && (
          <div className="event run-started">
            Activity will appear here when this agent runs.
          </div>
        )}
        {props.events.map((e, i) => (
          <div className={`event ${e.kind}`} key={i}>
            <div className="when">{new Date(e.at).toLocaleTimeString()}</div>
            {e.kind === "tool-use" ? `→ ${e.text}` : e.text}
          </div>
        ))}
        <div ref={bottom} />
      </div>

      <div className="composer">
        <input
          placeholder={
            props.status === "running" ? "Agent is working…" : "Give this agent a task…"
          }
          value={task}
          disabled={props.status === "running"}
          onChange={(e) => setTask(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        <button className="primary" onClick={send} disabled={props.status === "running"}>
          Run
        </button>
      </div>
    </aside>
  );
}
