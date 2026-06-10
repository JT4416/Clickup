import { useEffect, useState } from "react";
import { DeviceCodePrompt, IntegrationStatus, Settings } from "../../shared/types";

export function SettingsModal(props: { onClose: () => void }) {
  const [settings, setSettings] = useState<Settings>({
    anthropicApiKey: "",
    clickupMcpUrl: "",
    microsoftClientId: "",
    githubPat: "",
    launchAtLogin: false,
  });
  const [loginUrl, setLoginUrl] = useState("https://status.bluefrontierac.com");
  const [testResult, setTestResult] = useState("");
  const [testing, setTesting] = useState(false);

  const testRead = async () => {
    setTesting(true);
    setTestResult("");
    const r = await window.commandCenter.testLocalWeb(loginUrl);
    setTestResult(
      `${r.ok ? "OK" : "FAILED"} in ${(r.ms / 1000).toFixed(1)}s — ${r.result.slice(0, 500)}`,
    );
    setTesting(false);
  };
  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState("");
  const [msConnecting, setMsConnecting] = useState(false);
  const [msError, setMsError] = useState("");
  const [deviceCode, setDeviceCode] = useState<DeviceCodePrompt | null>(null);

  useEffect(() => {
    window.commandCenter.getSettings().then(setSettings);
    window.commandCenter.getIntegrationStatus().then(setStatus);
    return window.commandCenter.onDeviceCode(setDeviceCode);
  }, []);

  const save = async () => {
    await window.commandCenter.saveSettings(settings);
    props.onClose();
  };

  const connect = async () => {
    setConnecting(true);
    setConnectError("");
    try {
      // Persist current fields first so the connect flow uses them.
      await window.commandCenter.saveSettings(settings);
      const result = await window.commandCenter.connectClickUp();
      setStatus(result);
      setSettings(await window.commandCenter.getSettings());
    } catch (err) {
      setConnectError(err instanceof Error ? err.message : String(err));
    } finally {
      setConnecting(false);
    }
  };

  const connectMicrosoft = async () => {
    setMsConnecting(true);
    setMsError("");
    setDeviceCode(null);
    try {
      await window.commandCenter.saveSettings(settings);
      const result = await window.commandCenter.connectMicrosoft();
      setStatus(result);
      setDeviceCode(null);
    } catch (err) {
      setMsError(err instanceof Error ? err.message : String(err));
    } finally {
      setMsConnecting(false);
    }
  };

  const clickup = status?.clickup;
  const microsoft = status?.microsoft;

  return (
    <div className="modal-backdrop" onClick={props.onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Settings</h2>
        <p className="hint">Stored locally on this machine only.</p>

        <label>Anthropic API key</label>
        <input
          type="password"
          value={settings.anthropicApiKey}
          onChange={(e) =>
            setSettings({ ...settings, anthropicApiKey: e.target.value })
          }
          placeholder="sk-ant-…"
        />
        <p className="hint">
          From platform.claude.com → API keys. Powers every agent in the dashboard.
        </p>

        <label>ClickUp</label>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            margin: "4px 0 6px",
          }}
        >
          <span className={`status ${clickup?.connected ? "running" : ""}`}>
            <span className="dot" />
            {clickup?.connected
              ? `Connected${
                  clickup.connectedAt
                    ? ` · ${new Date(clickup.connectedAt).toLocaleDateString()}`
                    : ""
                }`
              : "Not connected"}
          </span>
          <button
            className="primary"
            onClick={connect}
            disabled={connecting || !settings.anthropicApiKey}
          >
            {connecting
              ? "Waiting for browser…"
              : clickup?.connected
                ? "Reconnect"
                : "Connect ClickUp"}
          </button>
        </div>
        <p className="hint">
          Opens your browser to authorize, then stores the credential in a secure
          Anthropic vault. Requires the API key above.
        </p>
        {connectError && (
          <p className="hint" style={{ color: "var(--danger)" }}>
            {connectError}
          </p>
        )}

        <label>Microsoft 365 (Outlook)</label>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            margin: "4px 0 6px",
          }}
        >
          <span className={`status ${microsoft?.connected ? "running" : ""}`}>
            <span className="dot" />
            {microsoft?.connected
              ? `Connected${microsoft.account ? ` · ${microsoft.account}` : ""}`
              : "Not connected"}
          </span>
          <button
            className="primary"
            onClick={connectMicrosoft}
            disabled={msConnecting || !settings.microsoftClientId.trim()}
          >
            {msConnecting
              ? "Waiting for sign-in…"
              : microsoft?.connected
                ? "Reconnect"
                : "Connect Microsoft 365"}
          </button>
        </div>
        {msConnecting && deviceCode && (
          <p className="hint" style={{ color: "var(--text)" }}>
            Your browser opened <strong>{deviceCode.verificationUri}</strong> — enter
            code <strong style={{ fontFamily: "var(--mono)" }}>{deviceCode.userCode}</strong>{" "}
            and sign in with your work account.
          </p>
        )}
        {msError && (
          <p className="hint" style={{ color: "var(--danger)" }}>
            {msError}
          </p>
        )}

        <label>Microsoft client ID</label>
        <input
          value={settings.microsoftClientId}
          onChange={(e) =>
            setSettings({ ...settings, microsoftClientId: e.target.value })
          }
          placeholder="00000000-0000-0000-0000-000000000000"
        />
        <p className="hint">
          One-time setup: portal.azure.com → Microsoft Entra ID → App registrations →
          New (any name, "Accounts in any organizational directory and personal"),
          then under Authentication enable "Allow public client flows". Paste the
          Application (client) ID here.
        </p>

        <label>GitHub personal access token</label>
        <input
          type="password"
          value={settings.githubPat}
          onChange={(e) => setSettings({ ...settings, githubPat: e.target.value })}
          placeholder="github_pat_… (optional)"
        />
        <p className="hint">
          Lets agents work on a GitHub repo (set the repo URL on the agent). Needs
          Contents read/write on that repo.
        </p>

        <label>Internal site login (local browser)</label>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            value={loginUrl}
            onChange={(e) => setLoginUrl(e.target.value)}
            placeholder="https://status.bluefrontierac.com"
          />
          <button
            onClick={() => void window.commandCenter.openLoginWindow(loginUrl)}
            disabled={!loginUrl.trim()}
            style={{ whiteSpace: "nowrap" }}
          >
            Open &amp; sign in
          </button>
          <button
            onClick={testRead}
            disabled={!loginUrl.trim() || testing}
            style={{ whiteSpace: "nowrap" }}
          >
            {testing ? "Testing…" : "Test read"}
          </button>
        </div>
        {testResult && (
          <p
            className="hint"
            style={{
              color: testResult.startsWith("OK") ? "var(--ok)" : "var(--danger)",
              fontFamily: "var(--mono)",
              whiteSpace: "pre-wrap",
            }}
          >
            {testResult}
          </p>
        )}
        <p className="hint">
          Opens the site in an app browser window. Sign in once — the session is
          saved, and agents with the "Local browser" integration can then read the
          page from your PC.
        </p>

        <label>Startup</label>
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            textTransform: "none",
            fontSize: 14,
            color: "var(--text)",
            margin: 0,
            letterSpacing: "normal",
            fontWeight: 400,
          }}
        >
          <input
            type="checkbox"
            style={{ width: "auto" }}
            checked={settings.launchAtLogin}
            onChange={(e) =>
              setSettings({ ...settings, launchAtLogin: e.target.checked })
            }
          />
          Launch at Windows startup (starts hidden in the tray)
        </label>
        <p className="hint">
          Applies to the installed app (run "npm run dist" and install it) — not to
          dev launches via npm start.
        </p>

        <label>ClickUp MCP server URL (advanced)</label>
        <input
          value={settings.clickupMcpUrl}
          onChange={(e) =>
            setSettings({ ...settings, clickupMcpUrl: e.target.value })
          }
          placeholder="https://mcp.clickup.com/mcp"
        />
        <p className="hint">Leave blank to use the default ClickUp MCP server.</p>

        <div className="row">
          <button onClick={props.onClose}>Cancel</button>
          <button className="primary" onClick={save}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
