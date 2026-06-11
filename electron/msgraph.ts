import { shell } from "electron";
import { DeviceCodePrompt, MicrosoftConnection } from "../shared/types";
import { Store } from "./store";

/**
 * Microsoft 365 via the Graph API. Sign-in uses the OAuth device-code flow
 * (user enters a short code at microsoft.com/devicelogin), and mailbox tools
 * run HERE in the main process — the agent calls them as custom tools, so
 * tokens never leave this machine or enter the agent's sandbox.
 */

const AUTHORITY = "https://login.microsoftonline.com/common/oauth2/v2.0";
const GRAPH = "https://graph.microsoft.com/v1.0";
const SCOPES = "offline_access User.Read Mail.Read Mail.Send";

interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
  error?: string;
  error_description?: string;
}

export async function connectMicrosoft(
  store: Store,
  onPrompt: (prompt: DeviceCodePrompt) => void,
): Promise<MicrosoftConnection> {
  const clientId = store.getSettings().microsoftClientId.trim();
  if (!clientId) {
    throw new Error(
      "Microsoft client ID is not set. Create a (free) app registration at " +
        "portal.azure.com → Microsoft Entra ID → App registrations, enable " +
        '"Allow public client flows", and paste its Application (client) ID here.',
    );
  }

  const codeRes = await fetch(`${AUTHORITY}/devicecode`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: clientId, scope: SCOPES }),
  });
  const code = (await codeRes.json()) as {
    device_code?: string;
    user_code?: string;
    verification_uri?: string;
    interval?: number;
    expires_in?: number;
    error_description?: string;
  };
  if (!codeRes.ok || !code.device_code) {
    throw new Error(code.error_description ?? "Could not start Microsoft sign-in.");
  }

  onPrompt({ userCode: code.user_code!, verificationUri: code.verification_uri! });
  void shell.openExternal(code.verification_uri!);

  const deadline = Date.now() + (code.expires_in ?? 900) * 1000;
  const intervalMs = (code.interval ?? 5) * 1000;

  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, intervalMs));
    const res = await fetch(`${AUTHORITY}/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "urn:ietf:params:oauth:grant-type:device_code",
        client_id: clientId,
        device_code: code.device_code,
      }),
    });
    const token = (await res.json()) as TokenResponse;
    if (token.access_token) {
      const connection: MicrosoftConnection = {
        clientId,
        accessToken: token.access_token,
        refreshToken: token.refresh_token ?? "",
        expiresAt: new Date(Date.now() + token.expires_in * 1000).toISOString(),
        connectedAt: new Date().toISOString(),
      };
      // Best-effort: label the connection with the signed-in address.
      try {
        const me = (await graphGet(connection, "/me")) as {
          mail?: string;
          userPrincipalName?: string;
        };
        connection.account = me.mail ?? me.userPrincipalName;
      } catch {
        /* non-fatal */
      }
      store.setMicrosoft(connection);
      return connection;
    }
    if (token.error && token.error !== "authorization_pending") {
      throw new Error(token.error_description ?? `Sign-in failed: ${token.error}`);
    }
  }
  throw new Error("Microsoft sign-in timed out.");
}

async function refreshIfNeeded(store: Store): Promise<MicrosoftConnection> {
  const conn = store.getMicrosoft();
  if (!conn) {
    throw new Error("Microsoft 365 is not connected. Connect it in Settings.");
  }
  if (Date.parse(conn.expiresAt) - Date.now() > 2 * 60 * 1000) return conn;

  if (!conn.refreshToken) {
    throw new Error("Microsoft session expired. Reconnect in Settings.");
  }
  const res = await fetch(`${AUTHORITY}/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: conn.clientId,
      refresh_token: conn.refreshToken,
      scope: SCOPES,
    }),
  });
  const token = (await res.json()) as TokenResponse;
  if (!token.access_token) {
    throw new Error(
      `Microsoft token refresh failed: ${token.error_description ?? token.error}`,
    );
  }
  const updated: MicrosoftConnection = {
    ...conn,
    accessToken: token.access_token,
    refreshToken: token.refresh_token ?? conn.refreshToken,
    expiresAt: new Date(Date.now() + token.expires_in * 1000).toISOString(),
  };
  store.setMicrosoft(updated);
  return updated;
}

async function graphGet(conn: MicrosoftConnection, path: string): Promise<unknown> {
  const res = await fetch(`${GRAPH}${path}`, {
    headers: { Authorization: `Bearer ${conn.accessToken}` },
  });
  if (!res.ok) throw new Error(`Graph ${path} failed (${res.status}): ${await res.text()}`);
  return res.json();
}

/* ---------- Mailbox tools (exposed to agents as custom tools) ---------- */

export const OUTLOOK_TOOL_DEFINITIONS = [
  {
    type: "custom" as const,
    name: "search_emails",
    description:
      "Search the connected Outlook mailbox. Call this to find receipts, " +
      "invoices, payment confirmations, or any other emails. Returns id, " +
      "subject, sender, date, and a preview for each match.",
    input_schema: {
      type: "object" as const,
      properties: {
        query: {
          type: "string",
          description: 'Search terms, e.g. "receipt OR invoice OR payment confirmation"',
        },
        top: { type: "number", description: "Max results (default 20, max 50)" },
      },
      required: ["query"],
    },
  },
  {
    type: "custom" as const,
    name: "get_email",
    description: "Read the full body of one email by its id (from search_emails).",
    input_schema: {
      type: "object" as const,
      properties: { id: { type: "string", description: "Email id" } },
      required: ["id"],
    },
  },
  {
    type: "custom" as const,
    name: "forward_email",
    description:
      "Forward an email (with its attachments) to a recipient. Use this to " +
      "send receipts to receipts@expensify.com.",
    input_schema: {
      type: "object" as const,
      properties: {
        id: { type: "string", description: "Email id to forward" },
        to: { type: "string", description: "Recipient email address" },
        comment: { type: "string", description: "Optional note added above the email" },
      },
      required: ["id", "to"],
    },
  },
];

interface GraphMessage {
  id: string;
  subject?: string;
  from?: { emailAddress?: { address?: string; name?: string } };
  receivedDateTime?: string;
  bodyPreview?: string;
  hasAttachments?: boolean;
  body?: { content?: string };
}

export async function executeOutlookTool(
  store: Store,
  name: string,
  input: Record<string, unknown>,
): Promise<string> {
  const conn = await refreshIfNeeded(store);

  if (name === "search_emails") {
    const top = Math.min(Number(input.top) || 20, 50);
    const query = encodeURIComponent(String(input.query ?? ""));
    const data = (await graphGet(
      conn,
      `/me/messages?$top=${top}&$search="${query}"&$select=id,subject,from,receivedDateTime,bodyPreview,hasAttachments`,
    )) as { value?: GraphMessage[] };
    const rows = (data.value ?? []).map((m) => ({
      id: m.id,
      subject: m.subject,
      from: m.from?.emailAddress?.address,
      received: m.receivedDateTime,
      preview: m.bodyPreview?.slice(0, 160),
      hasAttachments: m.hasAttachments,
    }));
    return JSON.stringify(rows, null, 1);
  }

  if (name === "get_email") {
    const m = (await graphGet(
      conn,
      `/me/messages/${encodeURIComponent(String(input.id))}` +
        `?$select=id,subject,from,receivedDateTime,hasAttachments,body`,
    )) as GraphMessage;
    return JSON.stringify(
      {
        id: m.id,
        subject: m.subject,
        from: m.from?.emailAddress?.address,
        received: m.receivedDateTime,
        hasAttachments: m.hasAttachments,
        body: (m.body?.content ?? "").replace(/<[^>]+>/g, " ").slice(0, 8000),
      },
      null,
      1,
    );
  }

  if (name === "forward_email") {
    const res = await fetch(
      `${GRAPH}/me/messages/${encodeURIComponent(String(input.id))}/forward`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${conn.accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          comment: String(input.comment ?? ""),
          toRecipients: [{ emailAddress: { address: String(input.to) } }],
        }),
      },
    );
    if (!res.ok) throw new Error(`Forward failed (${res.status}): ${await res.text()}`);
    return `Forwarded email ${input.id} to ${input.to}.`;
  }

  throw new Error(`Unknown tool: ${name}`);
}
