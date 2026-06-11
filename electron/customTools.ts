import { executeOutlookTool, OUTLOOK_TOOL_DEFINITIONS } from "./msgraph";
import { executeLocalWebTool, LOCALWEB_TOOL_DEFINITIONS } from "./localweb";
import { Store } from "./store";

const OUTLOOK_NAMES = new Set(OUTLOOK_TOOL_DEFINITIONS.map((t) => t.name));
const LOCALWEB_NAMES = new Set(LOCALWEB_TOOL_DEFINITIONS.map((t) => t.name));

/** Routes an agent's custom tool call to its host-side implementation. */
export async function executeCustomTool(
  store: Store,
  name: string,
  input: Record<string, unknown>,
): Promise<string> {
  if (OUTLOOK_NAMES.has(name)) return executeOutlookTool(store, name, input);
  if (LOCALWEB_NAMES.has(name)) return executeLocalWebTool(name, input);
  throw new Error(`Unknown tool: ${name}`);
}
