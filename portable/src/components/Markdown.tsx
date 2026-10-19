import type { ReactNode } from "react";
import { safeHref } from "@/lib/utils";

/** Tiny markdown renderer for assistant replies: headings, bullets, **bold**, `code`, links. */
export function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r/g, "").split("\n");
  const out: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (!list.length) return;
    out.push(
      <ul key={`ul-${out.length}`} className="my-1.5 list-disc space-y-1 ps-5">
        {list.map((l, i) => (
          <li key={i}>{inline(l)}</li>
        ))}
      </ul>,
    );
    list = [];
  };
  lines.forEach((raw, i) => {
    const l = raw.trimEnd();
    const bullet = l.match(/^\s*[-*•]\s+(.*)$/) ?? l.match(/^\s*\d+\.\s+(.*)$/);
    if (bullet) {
      list.push(bullet[1]!);
      return;
    }
    flush();
    if (!l.trim()) return;
    const h = l.match(/^(#{1,3})\s+(.*)$/);
    if (h) out.push(<p key={i} className="mt-2 font-display font-semibold">{inline(h[2]!)}</p>);
    else out.push(<p key={i} className="my-1">{inline(l)}</p>);
  });
  flush();
  return <div className="text-sm leading-relaxed">{out}</div>;
}

function inline(s: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    if (m.index > last) parts.push(s.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) parts.push(<strong key={m.index}>{t.slice(2, -2)}</strong>);
    else if (t.startsWith("`")) parts.push(<code key={m.index} className="rounded bg-black/5 px-1 font-mono text-[12px] dark:bg-white/10">{t.slice(1, -1)}</code>);
    else {
      const lm = t.match(/^\[([^\]]+)\]\(([^)]+)\)$/)!;
      // Only http(s) / mailto / tel / relative links; javascript:, data: etc. render as plain text.
      const href = safeHref(lm[2]);
      parts.push(
        href ? (
          <a key={m.index} href={href} target="_blank" rel="noreferrer" className="link">
            {lm[1]}
          </a>
        ) : (
          <span key={m.index}>{lm[1]}</span>
        ),
      );
    }
    last = m.index + t.length;
  }
  if (last < s.length) parts.push(s.slice(last));
  return parts;
}
