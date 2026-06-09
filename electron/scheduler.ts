import { Store } from "./store";
import { AgentRunner } from "./runner";

const TICK_MS = 60_000;

/**
 * Fires scheduled runs for agents in "auto" mode. An auto agent needs both a
 * scheduleMinutes interval and an autoTask (the standing instruction sent on
 * every run). Runs continue while the window is hidden in the tray.
 */
export class Scheduler {
  private store: Store;
  private runner: AgentRunner;
  private timer?: NodeJS.Timeout;
  /** Last attempt per agent — covers failed runs, which don't set lastRunAt. */
  private lastAttempt = new Map<string, number>();

  constructor(store: Store, runner: AgentRunner) {
    this.store = store;
    this.runner = runner;
  }

  start(): void {
    this.timer = setInterval(() => this.tick(), TICK_MS);
    this.tick();
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
  }

  private tick(): void {
    const now = Date.now();
    for (const agent of this.store.listAgents()) {
      if (agent.mode !== "auto") continue;
      if (!agent.scheduleMinutes || !agent.autoTask) continue;
      if (this.runner.isRunning(agent.id)) continue;

      const lastRun = agent.lastRunAt ? Date.parse(agent.lastRunAt) : 0;
      const last = Math.max(lastRun, this.lastAttempt.get(agent.id) ?? 0);
      if (now - last < agent.scheduleMinutes * 60_000) continue;

      this.lastAttempt.set(agent.id, now);
      void this.runner.run(agent.id, agent.autoTask).catch(() => {
        // Failure is already in the activity feed; lastAttempt prevents
        // retry-hammering until the next full interval.
      });
    }
  }
}
