# Agentic Control Center (A.C.C.)

Read this first — it is the memory between Claude sessions. Update it whenever
project state, decisions, or open threads change.

## Who / what

- **Owner:** Jason Turner (GitHub `JT4416`, chat email alligatorair@gmail.com),
  Field Services at Blue Frontier (HVAC / liquid-desiccant units). Practical,
  non-developer; explain commands step by step (e.g. he once ran `npm start`
  from his home dir — always say `cd` into the project folder first).
- **Project:** a Windows Electron desktop dashboard ("Jarvis-style command
  center") where independent AI agents live: ClickUp Expert, Fleet Manager,
  receipts agent (pending), trading-bot dev agent (pending). Built entirely in
  this repo across phases 1–4 plus polish, all on branch
  `claude/modest-keller-j9470n` (NEVER push elsewhere without permission).

## Architecture (all shipped & pushed)

- **Stack:** Electron + React + TypeScript + Vite. `npm run typecheck`,
  `npm run build`, `npm start` (build+launch), `npm run dist` (Windows
  installer → `release/`).
- `electron/` main process:
  - `store.ts` — JSON store in userData (`command-center.json`): settings,
    agents, environmentId, vaultId, clickup + microsoft connections.
  - `runner.ts` — Anthropic **Managed Agents** (`client.beta.*`): lazily
    creates one cloud environment + one remote agent per local agent (synced
    by config hash via `agents.update`), `sessions.create` per run
    (vault_ids when ClickUp; `github_repository` resource when agent.repoUrl),
    streams events, resolves `agent.custom_tool_use` host-side via
    `customTools.ts`, `continue`s on idle `requires_action`. After success,
    **hand-off**: runs `agent.handoffAgentId` with full summary (one hop max).
  - `oauth.ts` — generic MCP OAuth (discovery, DCR, PKCE, loopback) used by
    ClickUp connect; tokens stored in an Anthropic **vault** credential with
    refresh (`integrations.ts`).
  - `msgraph.ts` — Microsoft 365 device-code flow + host-side Outlook tools
    (search_emails / get_email / forward_email) for receipts→Expensify.
  - `localweb.ts` — "Local browser" tools: `read_page` loads URLs in hidden
    BrowserWindow (partition `persist:localweb`) on the user's PC (his
    network + saved logins) for internal dashboards; `openLoginWindow` for
    one-time sign-in; Settings has a **Test read** diagnostic (IPC
    `localweb:test`).
  - `scheduler.ts` — minute tick; Auto agents with scheduleMinutes+autoTask
    run on interval; failure backoff = one full interval.
  - `main.ts` — tray (runtime-drawn blue dot icon, close-to-tray, Quit menu),
    single-instance lock, `--hidden` start, launch-at-login (packaged only),
    right-click edit menu, all IPC.
- `src/` renderer: `App.tsx` (roster, statuses incl. "done" green light,
  Broadcast mode = fan-out to all idle agents w/ combined named feed, TTS:
  agents speak lastResult in per-agent Windows voice, mute toggle in topbar),
  `components/` (AgentCard w/ scanner bar while running, ActivityFeed w/ mic
  button — SpeechRecognition w/ Win+H fallback hint, AgentForm w/ model/
  integrations/voice/handoff/repo/schedule, SettingsModal), `theme.css` =
  ALL look & feel ("Command HUD": near-black, dotted drifting grid, glowing
  blue borders, scanline animations — styled from a reference image he loved).
- `shared/types.ts` — single source of shared types.

## ClickUp context (his workspace)

- Workspace "Blue Frontier" (id 9013489610 in URLs). His space:
  **F.S. OPERATIONS** id `901313838822` (folders: TECH TOOLS, FIELD
  COMMISSIONING, INSTALLATION, WARRANTY / PARTS, TRAINING CENTER, MANAGEMENT
  REVIEW). Goal: ClickUp as XOi replacement; earlier review recommended a
  Units/asset list + field consolidation (F.S.Cx Report list has 185+ fields).
- Daily fleet report target list: `901327448848`.
- Fleet Manager prompt uses ACT→LEARN→REUSE: read
  https://status.bluefrontierac.com via read_page, compare with previous
  DAILY STATUS REPORT tasks in that list (ClickUp = his memory), post
  "DAILY STATUS REPORT - [YYYY-MM-DD]" incl. recurrence tracker. Full
  rewritten prompt is in chat history; he has it in the agent.

## Open threads (next session: ask where these stand)

1. **Fleet Manager slow/broken** — debugging in progress. He was told to:
   run Settings → Test read (isolates local browser vs agent), switch Fleet
   Manager to Sonnet 4.6, give him ONLY Local browser integration, and hand
   off to ClickUp Expert (instruction posts report to list 901327448848).
   Awaiting his Test read result + feed errors. Known runner weakness: no SSE
   reconnect — a dropped stream mid-run can end a run silently; consider
   adding reconnect/dedupe (events.list + stream) if "doesn't work" persists.
2. **ClickUp OAuth connect** — built (mcp.clickup.com/mcp default) but NEVER
   confirmed working by him. If it errors, get exact message; flow may need
   adapting to ClickUp's OAuth quirks.
3. **Microsoft 365 / receipts agent** — blocked on his company IT admin
   approval (device-code flow hit "need admin approval"). Once approved:
   Settings → client ID (he has one) → Connect → create Receipt Collector
   (Outlook integration, forward receipts/invoices to receipts@expensify.com,
   Auto daily).
4. **Trading bots** — Python scripts in repo `JT4416/Tragent2`, unrefined,
   not running. Plan: he adds a fine-grained PAT (Contents R/W on Tragent2)
   in Settings, creates "Trading Bot Developer" agent with that repoUrl;
   first task = state-of-the-union report. This chat session could not access
   that repo (scope limited to JT4416/clickup).
5. **Voice input** — mic button may fail in Electron (Chromium speech service);
   Win+H is the reliable path. Could add real STT (e.g. local whisper) later.
6. Possible future: percent-true progress, coordinator/multi-agent, cloud
   scheduler for true always-on, installer auto-update.

## Conventions / gotchas

- Commit style: imperative summary + body; push with
  `git push -u origin claude/modest-keller-j9470n`.
- README.md was once UTF-16 (Windows); keep files UTF-8.
- electron-builder output is `release/` (gitignored); vite renderer → `dist/`,
  main → `dist-electron/` (package.json main =
  `dist-electron/electron/main.js`).
- His machine: Windows, repo cloned at `C:\Users\JasonTurner\clickup`.
- Model guidance: Opus 4.8 default for smart agents; Sonnet 4.6 for fast
  monitoring agents. Never put credentials in prompts — vault / host-side
  custom tools / local browser session are the sanctioned paths.
