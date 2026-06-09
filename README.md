# Agent Command Center

A Windows desktop dashboard where your AI agents live. Each agent is an
independent worker with its own instructions, integrations, and run history —
launch them manually or flip them to Auto and let them run on a schedule.

Built with Electron + React + TypeScript. Agents run on Anthropic's Managed
Agents platform: the agent loop and sandbox are hosted by Anthropic, and this
app creates sessions and streams live activity into the dashboard.

## Status

- [x] Dashboard shell with agent roster (cards: status, last run, summary)
- [x] Run Now with a task prompt + Stop
- [x] Live per-agent activity feed (messages, tool calls, errors)
- [x] Agent Builder (create / edit / delete agents from the UI)
- [x] Auto / Manual toggle (persisted; scheduler lands in phase 3)
- [x] Settings (Anthropic API key) stored locally
- [x] Seeded "ClickUp Expert" agent
- [x] Phase 2: Connect ClickUp via OAuth — tokens stored in an Anthropic
      credential vault (auto-refreshed) and attached to every ClickUp session
- [x] Phase 3: system tray + scheduler — Auto agents run on their interval
      with a standing task; closing the window keeps everything running
- [ ] Phase 4: receipts agent (Gmail + Expensify), trading-agent monitoring lane

## Getting started

```bash
npm install
npm start          # build + launch the desktop app
```

First run:

1. Open **Settings** and paste your Anthropic API key
   (platform.claude.com -> API keys).
2. Click **Connect ClickUp** — your browser opens to authorize, and the
   credential lands in a secure Anthropic vault.
3. Click **Run Now** on the ClickUp Expert card and give it a task.

`npm run dist` produces a Windows installer via electron-builder.

## Layout

```
electron/   Main process: window, IPC, local store, OAuth, Managed Agents runner
shared/     Types shared between main process and renderer
src/        React renderer: roster, activity feed, agent builder, settings
src/theme.css   All colors/fonts/spacing — restyle the whole app here
```
