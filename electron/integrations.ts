import Anthropic from "@anthropic-ai/sdk";
import { DeviceCodePrompt, IntegrationStatus } from "../shared/types";
import { connectMicrosoft } from "./msgraph";
import { runMcpOAuth } from "./oauth";
import { Store } from "./store";

const APP_NAME = "Agent Command Center";
export const DEFAULT_CLICKUP_MCP_URL = "https://mcp.clickup.com/mcp";

export function integrationStatus(store: Store): IntegrationStatus {
  const clickup = store.getClickUp();
  const microsoft = store.getMicrosoft();
  return {
    clickup: { connected: Boolean(clickup), connectedAt: clickup?.connectedAt },
    microsoft: {
      connected: Boolean(microsoft),
      connectedAt: microsoft?.connectedAt,
      account: microsoft?.account,
    },
  };
}

export async function connectMicrosoft365(
  store: Store,
  onPrompt: (prompt: DeviceCodePrompt) => void,
): Promise<IntegrationStatus> {
  await connectMicrosoft(store, onPrompt);
  return integrationStatus(store);
}

/**
 * Full ClickUp connect flow: OAuth in the system browser, then store the
 * tokens in the shared Anthropic vault so sessions can authenticate the
 * ClickUp MCP server (Anthropic auto-refreshes from there).
 */
export async function connectClickUp(store: Store): Promise<IntegrationStatus> {
  const settings = store.getSettings();
  if (!settings.anthropicApiKey) {
    throw new Error("Set your Anthropic API key before connecting ClickUp.");
  }

  const mcpUrl = settings.clickupMcpUrl.trim() || DEFAULT_CLICKUP_MCP_URL;
  const tokens = await runMcpOAuth(mcpUrl, APP_NAME);

  const client = new Anthropic({ apiKey: settings.anthropicApiKey });

  let vaultId = store.getVaultId();
  if (!vaultId) {
    const vault = await client.beta.vaults.create({ display_name: APP_NAME });
    vaultId = vault.id;
    store.setVaultId(vaultId);
  }

  // Replace any previous credential so the vault holds exactly one ClickUp entry.
  const previous = store.getClickUp();
  if (previous) {
    await client.beta.vaults.credentials
      .delete(previous.credentialId, { vault_id: vaultId })
      .catch(() => undefined);
  }

  const credential = await client.beta.vaults.credentials.create(vaultId, {
    display_name: "ClickUp",
    auth: {
      type: "mcp_oauth",
      mcp_server_url: mcpUrl,
      access_token: tokens.accessToken,
      expires_at: tokens.expiresAt ?? null,
      refresh: tokens.refreshToken
        ? {
            refresh_token: tokens.refreshToken,
            client_id: tokens.clientId,
            token_endpoint: tokens.tokenEndpoint,
            token_endpoint_auth: { type: "none" },
          }
        : null,
    },
  });

  store.setClickUp({
    credentialId: credential.id,
    connectedAt: new Date().toISOString(),
  });
  store.saveSettings({ ...settings, clickupMcpUrl: mcpUrl });

  return integrationStatus(store);
}
