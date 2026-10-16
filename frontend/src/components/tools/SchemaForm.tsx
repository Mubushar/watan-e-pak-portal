/**
 * Auto-generated form for an MCP tool's JSON `inputSchema`.
 * string / number / integer / boolean inputs; `anyOf [.., null]` = optional;
 * `enum` → Select; array / object → JSON textarea.
 */
import type { McpSchemaProp, McpTool } from "@/lib/mcp";
import { titleCase } from "@/lib/format";
import { Field, Input, Select, Textarea, Toggle } from "@/components/ui";

export type FormValues = Record<string, string | boolean>;
type Kind = "string" | "number" | "integer" | "boolean" | "array" | "object" | "unknown";

export function propKind(p: McpSchemaProp): { kind: Kind; nullable: boolean } {
  if (p.type) return { kind: (p.type as Kind) ?? "unknown", nullable: false };
  const opts = p.anyOf ?? [];
  const nonNull = opts.filter((o) => o.type && o.type !== "null");
  return { kind: ((nonNull[0]?.type as Kind) ?? "unknown"), nullable: opts.some((o) => o.type === "null") };
}

type Schema = NonNullable<McpTool["inputSchema"]>;

export function initialValues(schema?: Schema): FormValues {
  const out: FormValues = {};
  for (const [k, p] of Object.entries(schema?.properties ?? {})) {
    const { kind } = propKind(p);
    if (kind === "boolean") out[k] = p.default === true;
    else if (p.default === null || p.default === undefined) out[k] = "";
    else if (kind === "array" || kind === "object") out[k] = JSON.stringify(p.default);
    else out[k] = String(p.default);
  }
  return out;
}

/** Turn the string-y form state into typed arguments (or field errors). */
export function buildArgs(schema: Schema | undefined, values: FormValues): { args: Record<string, unknown>; errors: Record<string, string> } {
  const args: Record<string, unknown> = {};
  const errors: Record<string, string> = {};
  const required = new Set(schema?.required ?? []);
  for (const [k, p] of Object.entries(schema?.properties ?? {})) {
    const { kind } = propKind(p);
    const v = values[k];
    if (kind === "boolean") {
      args[k] = !!v;
      continue;
    }
    if (v === undefined || v === "") {
      if (required.has(k)) errors[k] = "Required";
      continue;
    }
    const sv = String(v);
    if (kind === "number" || kind === "integer") {
      const n = Number(sv);
      if (!Number.isFinite(n)) errors[k] = "Must be a number";
      else if (kind === "integer" && !Number.isInteger(n)) errors[k] = "Must be a whole number";
      else args[k] = n;
    } else if (kind === "array" || kind === "object") {
      try {
        args[k] = JSON.parse(sv);
      } catch {
        errors[k] = "Invalid JSON";
      }
    } else args[k] = sv;
  }
  return { args, errors };
}

export function SchemaForm({ schema, values, onChange, errors = {}, compact }: { schema?: Schema; values: FormValues; onChange: (v: FormValues) => void; errors?: Record<string, string>; compact?: boolean }) {
  const props = Object.entries(schema?.properties ?? {});
  const required = new Set(schema?.required ?? []);
  if (!props.length) return <p className="rounded-xl bg-brand-50/60 px-3 py-2 text-sm text-ink-mute dark:bg-white/5">This tool takes no arguments.</p>;
  const set = (k: string, v: string | boolean) => onChange({ ...values, [k]: v });
  return (
    <div className={compact ? "grid gap-3 sm:grid-cols-2" : "space-y-4"}>
      {props.map(([k, p]) => {
        const { kind, nullable } = propKind(p);
        const label = (
          <span className="inline-flex flex-wrap items-center gap-1.5 normal-case tracking-normal">
            <span className="uppercase tracking-wider">{p.title ?? titleCase(k)}</span>
            <code className="rounded bg-black/5 px-1 text-[10px] font-medium lowercase text-ink-mute dark:bg-white/10">{kind}</code>
            {required.has(k) ? <span className="text-red-500">*</span> : nullable ? <span className="text-[10px] font-normal lowercase text-ink-mute">optional</span> : null}
          </span>
        );
        const hint = p.description;
        if (kind === "boolean")
          return (
            <Field key={k} label={label} hint={hint} error={errors[k]}>
              <Toggle checked={!!values[k]} onChange={(v) => set(k, v)} label={values[k] ? "true" : "false"} />
            </Field>
          );
        if (p.enum?.length)
          return (
            <Field key={k} label={label} hint={hint} error={errors[k]}>
              <Select value={String(values[k] ?? "")} onChange={(e) => set(k, e.target.value)}>
                {!required.has(k) && <option value="">—</option>}
                {p.enum.map((o) => (
                  <option key={String(o)} value={String(o)}>
                    {String(o)}
                  </option>
                ))}
              </Select>
            </Field>
          );
        if (kind === "array" || kind === "object")
          return (
            <Field key={k} label={label} hint={hint ?? (kind === "array" ? 'JSON array, e.g. ["a", "b"] or [[31.5, 74.3]]' : 'JSON object, e.g. {"key": "value"}')} error={errors[k]} className={compact ? "sm:col-span-2" : undefined}>
              <Textarea value={String(values[k] ?? "")} onChange={(e) => set(k, e.target.value)} className="min-h-[80px] font-mono text-xs" placeholder={kind === "array" ? "[]" : "{}"} spellCheck={false} />
            </Field>
          );
        return (
          <Field key={k} label={label} hint={hint} error={errors[k]}>
            <Input
              type={kind === "number" || kind === "integer" ? "number" : "text"}
              step={kind === "integer" ? 1 : "any"}
              value={String(values[k] ?? "")}
              onChange={(e) => set(k, e.target.value)}
              placeholder={p.default !== undefined && p.default !== null ? String(p.default) : nullable ? "null" : ""}
            />
          </Field>
        );
      })}
    </div>
  );
}
