import { useEffect, useState } from "react";
import { IntegrationStatus, Settings } from "../../shared/types";

export function SettingsModal(props: { onClose: () => void }) {
  const [settings, setSettings] = useState<Settings>({
    anthropicApiKey: "",
    clickupMcpUrl: "",
  });
  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState("");

  useEffect(() => {
    window.commandCenter.getSettings().then(setSettings);
    window.commandCenter.getIntegrationStatus().then(setStatus);
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

  const clickup = status?.clickup;

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
