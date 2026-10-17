/**
 * Lenient JSON parsing for agent step outputs.
 *
 * The agent engine stores each step's output as `json.dumps(value)[:480]`
 * (AGENTIC_CONFIG.summary_chars), so longer outputs arrive truncated mid-token.
 * `looseJson` first tries a strict parse, then repairs the tail: it closes an
 * open string, drops a dangling key/comma and closes every open bracket, backing
 * off one element at a time until the prefix parses.
 */
export interface LooseResult {
  value: unknown;
  /** True when the text was not valid JSON and had to be repaired. */
  truncated: boolean;
  /** True when the value is structured (object/array) JSON. */
  ok: boolean;
}

function closeJson(t: string): string {
  const stack: string[] = [];
  let inStr = false;
  let esc = false;
  for (let i = 0; i < t.length; i++) {
    const c = t[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === "\\") esc = true;
      else if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') inStr = true;
    else if (c === "{") stack.push("}");
    else if (c === "[") stack.push("]");
    else if (c === "}" || c === "]") stack.pop();
  }
  let out = t;
  if (inStr) {
    if (esc) out = out.slice(0, -1);
    out += '"';
  }
  out = out.replace(/[\s,:]+$/, "");
  return out + stack.reverse().join("");
}

function lastComma(t: string): number {
  let inStr = false;
  let esc = false;
  let last = -1;
  for (let i = 0; i < t.length; i++) {
    const c = t[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === "\\") esc = true;
      else if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') inStr = true;
    else if (c === ",") last = i;
  }
  return last;
}

export function looseJson(v: unknown): LooseResult {
  if (typeof v !== "string") return { value: v, truncated: false, ok: v !== null && typeof v === "object" };
  const s = v.trim();
  if (!s) return { value: v, truncated: false, ok: false };
  try {
    const parsed = JSON.parse(s);
    return { value: parsed, truncated: false, ok: parsed !== null && typeof parsed === "object" };
  } catch {
    /* fall through to repair */
  }
  if (s[0] !== "{" && s[0] !== "[") return { value: v, truncated: false, ok: false };
  let cut = s;
  for (let i = 0; i < 60 && cut.length > 1; i++) {
    try {
      const parsed = JSON.parse(closeJson(cut));
      return { value: parsed, truncated: true, ok: true };
    } catch {
      const idx = lastComma(cut);
      if (idx < 0) break;
      cut = cut.slice(0, idx);
    }
  }
  return { value: v, truncated: false, ok: false };
}
