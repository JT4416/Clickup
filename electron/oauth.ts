import * as crypto from "crypto";
import * as http from "http";
import { shell } from "electron";

/**
 * Generic OAuth 2.0 client for MCP servers: metadata discovery, dynamic
 * client registration, PKCE authorization-code flow via the system browser,
 * and token exchange. Returns everything needed to store the credential in
 * an Anthropic vault with auto-refresh.
 */

export interface OAuthTokens {
  accessToken: string;
  refreshToken?: string;
  /** RFC 3339 expiry, when the server reported expires_in. */
  expiresAt?: string;
  clientId: string;
  tokenEndpoint: string;
}

interface AuthServerMetadata {
  authorization_endpoint: string;
  token_endpoint: string;
  registration_endpoint?: string;
}

const TIMEOUT_MS = 5 * 60 * 1000;

async function fetchJson(url: string): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) return null;
    return (await res.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/** MCP auth discovery: protected-resource metadata first, then AS metadata. */
async function discover(mcpServerUrl: string): Promise<AuthServerMetadata> {
  const origin = new URL(mcpServerUrl).origin;

  let authServer = origin;
  const resource = await fetchJson(`${origin}/.well-known/oauth-protected-resource`);
  const servers = resource?.authorization_servers;
  if (Array.isArray(servers) && typeof servers[0] === "string") {
    authServer = servers[0].replace(/\/$/, "");
  }

  const metadata =
    (await fetchJson(`${authServer}/.well-known/oauth-authorization-server`)) ??
    (await fetchJson(`${authServer}/.well-known/openid-configuration`));

  if (
    !metadata ||
    typeof metadata.authorization_endpoint !== "string" ||
    typeof metadata.token_endpoint !== "string"
  ) {
    throw new Error(
      `Could not discover OAuth endpoints for ${mcpServerUrl}. ` +
        "The server may not support OAuth, or the URL may be wrong.",
    );
  }

  return {
    authorization_endpoint: metadata.authorization_endpoint,
    token_endpoint: metadata.token_endpoint,
    registration_endpoint:
      typeof metadata.registration_endpoint === "string"
        ? metadata.registration_endpoint
        : undefined,
  };
}

async function registerClient(
  registrationEndpoint: string,
  appName: string,
  redirectUri: string,
): Promise<string> {
  const res = await fetch(registrationEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_name: appName,
      redirect_uris: [redirectUri],
      grant_types: ["authorization_code", "refresh_token"],
      response_types: ["code"],
      token_endpoint_auth_method: "none",
    }),
  });
  if (!res.ok) {
    throw new Error(`Client registration failed (${res.status}): ${await res.text()}`);
  }
  const body = (await res.json()) as { client_id?: string };
  if (!body.client_id) throw new Error("Client registration returned no client_id.");
  return body.client_id;
}

/** Waits for the browser redirect on a local loopback server. */
function waitForCallback(
  server: http.Server,
  expectedState: string,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error("Timed out waiting for authorization (5 minutes)."));
      server.close();
    }, TIMEOUT_MS);

    server.on("request", (req, res) => {
      const url = new URL(req.url ?? "/", "http://127.0.0.1");
      if (url.pathname !== "/callback") {
        res.writeHead(404).end();
        return;
      }
      const finish = (html: string) => {
        res.writeHead(200, { "Content-Type": "text/html" }).end(html);
        clearTimeout(timer);
        setTimeout(() => server.close(), 500);
      };

      const error = url.searchParams.get("error");
      if (error) {
        finish("<h3>Authorization failed — you can close this tab.</h3>");
        reject(new Error(`Authorization failed: ${error}`));
        return;
      }
      if (url.searchParams.get("state") !== expectedState) {
        finish("<h3>State mismatch — you can close this tab.</h3>");
        reject(new Error("OAuth state mismatch; aborting for safety."));
        return;
      }
      const code = url.searchParams.get("code");
      if (!code) {
        finish("<h3>No authorization code — you can close this tab.</h3>");
        reject(new Error("Callback contained no authorization code."));
        return;
      }
      finish(
        "<h3>Connected! You can close this tab and return to Agent Command Center.</h3>",
      );
      resolve(code);
    });
  });
}

export async function runMcpOAuth(
  mcpServerUrl: string,
  appName: string,
): Promise<OAuthTokens> {
  const metadata = await discover(mcpServerUrl);

  // Loopback server first so the redirect URI (with port) is known before
  // client registration.
  const server = http.createServer();
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const address = server.address();
  if (!address || typeof address === "string") {
    server.close();
    throw new Error("Could not start local callback server.");
  }
  const redirectUri = `http://127.0.0.1:${address.port}/callback`;

  try {
    if (!metadata.registration_endpoint) {
      throw new Error(
        "This MCP server does not support automatic client registration. " +
          "A pre-registered OAuth client ID would be required.",
      );
    }
    const clientId = await registerClient(
      metadata.registration_endpoint,
      appName,
      redirectUri,
    );

    const verifier = crypto.randomBytes(32).toString("base64url");
    const challenge = crypto.createHash("sha256").update(verifier).digest("base64url");
    const state = crypto.randomBytes(16).toString("base64url");

    const authUrl = new URL(metadata.authorization_endpoint);
    authUrl.searchParams.set("response_type", "code");
    authUrl.searchParams.set("client_id", clientId);
    authUrl.searchParams.set("redirect_uri", redirectUri);
    authUrl.searchParams.set("code_challenge", challenge);
    authUrl.searchParams.set("code_challenge_method", "S256");
    authUrl.searchParams.set("state", state);
    authUrl.searchParams.set("resource", mcpServerUrl);

    const callback = waitForCallback(server, state);
    await shell.openExternal(authUrl.toString());
    const code = await callback;

    const tokenRes = await fetch(metadata.token_endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        code,
        redirect_uri: redirectUri,
        client_id: clientId,
        code_verifier: verifier,
        resource: mcpServerUrl,
      }),
    });
    if (!tokenRes.ok) {
      throw new Error(`Token exchange failed (${tokenRes.status}): ${await tokenRes.text()}`);
    }
    const tokens = (await tokenRes.json()) as {
      access_token?: string;
      refresh_token?: string;
      expires_in?: number;
    };
    if (!tokens.access_token) throw new Error("Token response contained no access token.");

    return {
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      expiresAt: tokens.expires_in
        ? new Date(Date.now() + tokens.expires_in * 1000).toISOString()
        : undefined,
      clientId,
      tokenEndpoint: metadata.token_endpoint,
    };
  } finally {
    if (server.listening) server.close();
  }
}
