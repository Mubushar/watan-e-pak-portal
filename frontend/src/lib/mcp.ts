/**
 * Minimal Model Context Protocol client for the portal's Streamable-HTTP MCP
 * endpoint (`/mcp`, stateless by default). Speaks JSON-RPC 2.0 and accepts
 * either a JSON body or an SSE stream (`event: message / data: {...}`).
 */
import { API_BASE } from "./api";
import { useAuth } from "@/store/auth";

export interface McpTool {
  name: string;
  description?: string;
  inputSchema?: { properties?: Record<string, McpSchemaProp>; required?: string[] };
}
export interface McpSchemaProp {
  type?: string;
  anyOf?: { type?: string }[];
  default?: unknown;
  title?: string;
  description?: string;
  enum?: unknown[];
  items?: unknown;
}
export interface McpCallResult {
  content?: { type: string; text?: string }[];
  structuredContent?: unknown;
  isError?: boolean;
}

let seq = 0;

/** The MCP endpoint exposes every portal tool, so the server only admits administrators. */
export const MCP_ROLES = ["super_admin", "admin"];
export function isMcpAdmin(u: { role?: string; roles?: string[] } | null | undefined): boolean {
  return !!u && MCP_ROLES.some((r) => u.roles?.includes(r) || u.role === r);
}

export class McpError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function rpc<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  // The signed-in session token authorises the call (the server requires an administrator's).
  const token = useAuth.getState().token;
  const res = await fetch(`${API_BASE}/mcp`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ jsonrpc: "2.0", id: ++seq, method, params }),
  });
  if (res.status === 401 || res.status === 403)
    throw new McpError(token ? "The MCP console is for administrators only." : "Sign in with an administrator account to use the MCP console.", res.status);
  if (!res.ok) throw new McpError(`MCP ${method} failed: ${res.status} ${res.statusText}`, res.status);
  const ct = res.headers.get("content-type") ?? "";
  let msg: { result?: T; error?: { message: string } } | undefined;
  if (ct.includes("text/event-stream")) {
    const text = await res.text();
    for (const line of text.split(/\r?\n/)) {
      if (line.startsWith("data:")) {
        const data = line.slice(5).trim();
        if (data) msg = JSON.parse(data);
      }
    }
  } else {
    msg = await res.json();
  }
  if (!msg) throw new Error(`MCP ${method}: empty response`);
  if (msg.error) throw new Error(msg.error.message);
  return msg.result as T;
}

export const mcp = {
  initialize: () =>
    rpc<{ serverInfo: { name: string; version: string }; capabilities: unknown; protocolVersion: string }>("initialize", {
      protocolVersion: "2025-06-18",
      capabilities: {},
      clientInfo: { name: "arzepak-web", version: "1.0.0" },
    }),
  listTools: () => rpc<{ tools: McpTool[] }>("tools/list"),
  listResources: () => rpc<{ resources: { uri: string; name: string; description?: string; mimeType?: string }[] }>("resources/list"),
  listResourceTemplates: () => rpc<{ resourceTemplates: { uriTemplate: string; name: string; description?: string }[] }>("resources/templates/list"),
  readResource: (uri: string) => rpc<{ contents: { uri: string; text?: string; mimeType?: string }[] }>("resources/read", { uri }),
  listPrompts: () => rpc<{ prompts: { name: string; description?: string; arguments?: { name: string; required?: boolean; description?: string }[] }[] }>("prompts/list"),
  getPrompt: (name: string, args: Record<string, string>) =>
    rpc<{ messages: { role: string; content: { type: string; text?: string } }[] }>("prompts/get", { name, arguments: args }),
  callTool: (name: string, args: Record<string, unknown>) => rpc<McpCallResult>("tools/call", { name, arguments: args }),
};

/** Tool results arrive as a JSON string inside a text block; parse it when possible. */
export function parseToolResult(r: McpCallResult): unknown {
  if (r.structuredContent && typeof r.structuredContent === "object") {
    const sc = r.structuredContent as { result?: unknown };
    if (typeof sc.result === "string") {
      try {
        return JSON.parse(sc.result);
      } catch {
        return sc.result;
      }
    }
    return sc;
  }
  const text = r.content?.map((c) => c.text ?? "").join("\n") ?? "";
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
