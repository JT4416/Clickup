import { BrowserWindow } from "electron";

/**
 * "Local browser" tools: load pages in a real (hidden) Chromium window ON THE
 * USER'S MACHINE — with the user's network access (VPN/intranet) and any
 * logins saved in the persistent "localweb" session. This is what lets agents
 * read internal dashboards (e.g. status.bluefrontierac.com) that cloud-side
 * web_fetch cannot reach or render.
 */

export const LOCALWEB_PARTITION = "persist:localweb";
const MAX_TEXT = 14000;

export const LOCALWEB_TOOL_DEFINITIONS = [
  {
    type: "custom" as const,
    name: "read_page",
    description:
      "Load a web page in a real browser on the user's computer (with the " +
      "user's network access and saved logins) and return the page's visible " +
      "text after JavaScript renders. Use this for internal/company " +
      "dashboards and status pages that normal web fetch cannot access. If " +
      "the text looks like a login page, tell the user to open Settings → " +
      "Internal site login and sign in once.",
    input_schema: {
      type: "object" as const,
      properties: {
        url: { type: "string", description: "Full URL, e.g. https://status.example.com" },
        wait_seconds: {
          type: "number",
          description: "Extra seconds to wait for scripts/charts to render (default 5, max 20)",
        },
      },
      required: ["url"],
    },
  },
];

export async function executeLocalWebTool(
  name: string,
  input: Record<string, unknown>,
): Promise<string> {
  if (name !== "read_page") throw new Error(`Unknown tool: ${name}`);

  const url = String(input.url ?? "");
  if (!/^https?:\/\//i.test(url)) {
    throw new Error("read_page needs a full http(s) URL.");
  }
  const waitSeconds = Math.min(Math.max(Number(input.wait_seconds) || 5, 0), 20);

  const win = new BrowserWindow({
    show: false,
    width: 1600,
    height: 1000,
    webPreferences: {
      partition: LOCALWEB_PARTITION,
      sandbox: true,
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  try {
    await win.loadURL(url);
    // Dashboards render after load — give scripts time to paint.
    await new Promise((r) => setTimeout(r, waitSeconds * 1000));
    const page = (await win.webContents.executeJavaScript(
      `({
        title: document.title,
        url: location.href,
        text: document.body ? document.body.innerText : "",
      })`,
      true,
    )) as { title: string; url: string; text: string };

    return JSON.stringify(
      {
        requested: url,
        landed_on: page.url,
        title: page.title,
        text: page.text.replace(/\n{3,}/g, "\n\n").slice(0, MAX_TEXT),
      },
      null,
      1,
    );
  } finally {
    win.destroy();
  }
}

/** Visible window (same session) where the user signs in to internal sites. */
export function openLoginWindow(url: string): void {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    title: "Sign in — your login is saved for agents",
    webPreferences: {
      partition: LOCALWEB_PARTITION,
      sandbox: true,
      nodeIntegration: false,
      contextIsolation: true,
    },
  });
  void win.loadURL(/^https?:\/\//i.test(url) ? url : `https://${url}`);
}
