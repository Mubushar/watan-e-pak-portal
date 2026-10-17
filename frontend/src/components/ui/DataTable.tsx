import { useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { EmptyState } from "./layout";

export interface Column<T> {
  key: string;
  header: ReactNode;
  /** Cell renderer; defaults to row[key]. */
  render?: (row: T) => ReactNode;
  /** Value used for sorting / searching; defaults to row[key]. */
  value?: (row: T) => string | number | null | undefined;
  align?: "left" | "right" | "center";
  className?: string;
  sortable?: boolean;
}

/**
 * Lightweight sortable, searchable table.
 *   <DataTable rows={leads} columns={[{ key: "name", header: "Name" }, …]} search onRowClick={…} />
 */
export function DataTable<T extends Record<string, any>>({
  rows,
  columns,
  search,
  onRowClick,
  pageSize = 12,
  empty,
  rowKey = (r: T, i: number) => (r.id as string) ?? String(i),
  dense,
  toolbar,
}: {
  rows: T[];
  columns: Column<T>[];
  search?: boolean;
  onRowClick?: (row: T) => void;
  pageSize?: number;
  empty?: ReactNode;
  rowKey?: (r: T, i: number) => string;
  dense?: boolean;
  toolbar?: ReactNode;
}) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const [page, setPage] = useState(0);

  const val = (c: Column<T>, r: T) => (c.value ? c.value(r) : (r[c.key] as string | number | null | undefined));

  const filtered = useMemo(() => {
    let out = rows;
    if (q.trim()) {
      const s = q.toLowerCase();
      out = out.filter((r) => columns.some((c) => String(val(c, r) ?? "").toLowerCase().includes(s)));
    }
    if (sort) {
      const c = columns.find((x) => x.key === sort.key);
      if (c)
        out = [...out].sort((a, b) => {
          const va = val(c, a), vb = val(c, b);
          if (va === vb) return 0;
          if (va === null || va === undefined) return 1;
          if (vb === null || vb === undefined) return -1;
          return (va > vb ? 1 : -1) * sort.dir;
        });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, q, sort, columns]);

  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const view = filtered.slice(page * pageSize, page * pageSize + pageSize);

  return (
    <div>
      {(search || toolbar) && (
        <div className="flex flex-wrap items-center gap-3 border-b border-black/5 px-4 py-3 dark:border-white/10">
          {search && (
            <div className="relative w-full max-w-xs">
              <Search className="absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-mute" />
              <input
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setPage(0);
                }}
                placeholder="Search…"
                className="input py-2 ps-9"
              />
            </div>
          )}
          <div className="ms-auto flex items-center gap-2">{toolbar}</div>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-black/5 bg-brand-50/50 text-left text-[11px] font-bold uppercase tracking-wider text-ink-mute dark:border-white/10 dark:bg-white/5 dark:text-slate-400">
              {columns.map((c) => {
                const sortable = c.sortable !== false;
                const active = sort?.key === c.key;
                return (
                  <th
                    key={c.key}
                    className={cn("whitespace-nowrap px-4 py-3", c.align === "right" && "text-right", c.align === "center" && "text-center", sortable && "cursor-pointer select-none", c.className)}
                    onClick={() => sortable && setSort((s) => (s?.key === c.key ? (s.dir === 1 ? { key: c.key, dir: -1 } : null) : { key: c.key, dir: 1 }))}
                  >
                    <span className="inline-flex items-center gap-1">
                      {c.header}
                      {sortable && (active ? sort!.dir === 1 ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" /> : <ChevronsUpDown className="h-3 w-3 opacity-40" />)}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {view.map((r, i) => (
              <tr
                key={rowKey(r, i)}
                onClick={onRowClick ? () => onRowClick(r) : undefined}
                className={cn("border-b border-black/5 transition-colors last:border-0 dark:border-white/5", onRowClick && "cursor-pointer hover:bg-brand-50/60 dark:hover:bg-white/5")}
              >
                {columns.map((c) => (
                  <td key={c.key} className={cn("px-4", dense ? "py-2" : "py-3", c.align === "right" && "text-right tabular-nums", c.align === "center" && "text-center", c.className)}>
                    {c.render ? c.render(r) : (r[c.key] as ReactNode) ?? "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {view.length === 0 && <div className="p-6">{empty ?? <EmptyState title="No records" />}</div>}
      </div>
      {pages > 1 && (
        <div className="flex items-center justify-between gap-2 border-t border-black/5 px-4 py-3 text-xs text-ink-mute dark:border-white/10">
          <span>
            {page * pageSize + 1}–{Math.min(filtered.length, (page + 1) * pageSize)} of {filtered.length}
          </span>
          <div className="flex gap-1">
            <button className="btn btn-outline btn-sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
              Prev
            </button>
            <button className="btn btn-outline btn-sm" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)}>
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
