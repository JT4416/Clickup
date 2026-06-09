import { useEffect, useState } from "react";
import { Settings } from "../../shared/types";

export function SettingsModal(props: { onClose: () => void }) {
  const [settings, setSettings] = useState<Settings>({
    anthropicApiKey: "",
    clickupMcpUrl: "",
  });
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    window.commandCenter.getSettings().then((s) => {
      setSettings(s);
      setLoaded(true);
    });
  }, []);

  const save = async () => {
    await window.commandCenter.saveSettings(settings);
    props.onClose();
  };

  return (
    <div className="modal-backdrop" onClick={props.onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Settings</h2>
        <p className="hint">
          Stored locally on this machine only ({loaded ? "loaded" : "loading…"}).
        </p>

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

        <label>ClickUp MCP server URL</label>
        <input
          value={settings.clickupMcpUrl}
          onChange={(e) =>
            setSettings({ ...settings, clickupMcpUrl: e.target.value })
          }
          placeholder="https://mcp.clickup.com/mcp"
        />
        <p className="hint">
          Required for agents with the ClickUp integration enabled.
        </p>

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
