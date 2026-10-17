import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowDownLeft,
  ArrowUpRight,
  BookOpen,
  CalendarRange,
  CheckCircle2,
  CircleDollarSign,
  FileSpreadsheet,
  FileText,
  Hourglass,
  Landmark,
  LayoutDashboard,
  ListTree,
  PiggyBank,
  Plus,
  Receipt,
  Scale,
  Send,
  Target,
  Trash2,
  Wallet,
} from "lucide-react";
import { post } from "@/lib/api";
import { useApi, useMutate } from "@/hooks/useApi";
import { compact, date, num, pct, pkr, pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  Badge,
  Bars,
  Button,
  Card,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  Field,
  Input,
  KeyValue,
  Modal,
  PageHeader,
  Progress,
  QueryState,
  Segmented,
  Select,
  Skeleton,
  StatCard,
  StatusBadge,
  Tabs,
  Textarea,
  Toggle,
  type Column,
} from "@/components/ui";
import { FormGrid, MiniStat, Panel, SkeletonGrid, crShort, ensure, isoDay, numOr, useFormState, rs } from "@/components/biz/ops-kit";

// ------------------------------------------------------------------ types
interface Ratios {
  current_ratio: number;
  quick_ratio: number;
  debt_to_equity: number;
  net_profit_margin: number;
  return_on_equity: number;
  return_on_assets: number;
  working_capital: number;
}
interface Dashboard {
  as_of: string;
  total_assets: number;
  total_liabilities: number;
  total_equity: number;
  cash_and_bank: number;
  accounts_receivable: number;
  accounts_payable: number;
  revenue: number;
  expenses: number;
  net_profit: number;
  overdue_invoices: number;
  overdue_amount: number;
  journal_entries: number;
  accounts: number;
  ratios: Ratios;
}
interface Line {
  code: string;
  name: string;
  subtype?: string;
  amount: number;
}
interface Pnl {
  income: Line[];
  expenses: Line[];
  total_income: number;
  total_expenses: number;
  net_profit: number;
  net_margin: number;
}
interface CashFlow {
  opening_cash: number;
  operating: number;
  investing: number;
  financing: number;
  net_change: number;
  closing_cash: number;
}
interface BalanceSheet {
  as_of: string;
  assets: Line[];
  liabilities: Line[];
  equity: Line[];
  total_assets: number;
  total_liabilities: number;
  total_equity: number;
  balanced: boolean;
}
interface InvoiceLine {
  description: string;
  quantity: number;
  unit_price: number;
  amount: number;
  tax_rate: number;
}
interface Invoice {
  id: string;
  number: string;
  invoice_type: "receivable" | "payable";
  counterparty: string;
  issue_date: string;
  due_date: string;
  lines: InvoiceLine[];
  subtotal: number;
  tax_amount: number;
  total: number;
  amount_paid: number;
  balance: number;
  status: string;
  notes?: string | null;
  days_overdue: number;
  is_overdue: boolean;
  payments?: { id: string; date: string; amount: number; method: string; reference?: string | null }[];
}
interface Account {
  code: string;
  name: string;
  type: string;
  subtype: string;
  normal_side: string;
  is_bank: boolean;
  is_cash: boolean;
  active: boolean;
  balance: number;
}
interface JournalEntry {
  id: string;
  entry_no: number;
  date: string;
  reference?: string | null;
  memo?: string | null;
  source: string;
  lines: { account: string; debit: number; credit: number; description?: string | null }[];
  status: string;
  void_reason?: string | null;
  total_debit: number;
  total_credit: number;
}
interface Budget {
  id: string;
  name: string;
  fiscal_year: string;
  scope: string;
  lines: Record<string, number>;
  notes?: string | null;
}
interface Variance {
  budget: string;
  fiscal_year: string;
  rows: { code: string; name: string; budget: number; actual: number; variance: number; variance_pct: number; favorable: boolean }[];
  total_budget: number;
  total_actual: number;
  total_variance: number;
}

type TabKey = "overview" | "invoices" | "aging" | "rentroll" | "journal" | "chart" | "trial" | "budgets";
const INVALIDATE = ["/accounting", "/portal", "/leasing"];
const METHODS = ["bank_transfer", "cash", "cheque", "online", "card", "adjustment"];

export default function Accounting() {
  const [tab, setTab] = useState<TabKey>("overview");
  const [newInvoice, setNewInvoice] = useState(false);
  const [payFor, setPayFor] = useState<Invoice | null | "new">(null);
  const dash = useApi<Dashboard>("/accounting/dashboard");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Accounting"
        subtitle={dash.data ? `Double-entry books as of ${date(dash.data.as_of)}` : "Ledger, invoices, rent roll and budgets"}
        actions={
          <>
            <Button variant="outline" size="sm" icon={<Wallet className="h-4 w-4" />} onClick={() => setPayFor("new")}>
              Record payment
            </Button>
            <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setNewInvoice(true)}>
              New invoice
            </Button>
          </>
        }
      />

      <QueryState q={dash} skeleton={<SkeletonGrid n={4} />}>
        {(d) => (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Cash & bank" value={rs(d.cash_and_bank)} icon={<Landmark className="h-5 w-5" />} hint={`${pkrShort(d.total_assets, false)} total assets`} />
              <StatCard
                label="Receivables"
                value={rs(d.accounts_receivable)}
                icon={<ArrowDownLeft className="h-5 w-5" />}
                hint={d.overdue_invoices ? `${d.overdue_invoices} overdue · ${pkrShort(d.overdue_amount, false)}` : "nothing overdue"}
                tone={d.overdue_invoices ? "red" : "blue"}
              />
              <StatCard label="Revenue" value={rs(d.revenue)} icon={<CircleDollarSign className="h-5 w-5" />} hint={`${pkrShort(d.expenses, false)} expenses`} tone="gold" />
              <StatCard
                label="Net profit"
                value={rs(d.net_profit)}
                icon={<PiggyBank className="h-5 w-5" />}
                delta={d.ratios.net_profit_margin * 100}
                hint="net margin"
                tone={d.net_profit >= 0 ? "green" : "red"}
              />
            </div>
            <Card className="p-3">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
                <MiniStat label="Current ratio" value={d.ratios.current_ratio.toFixed(2)} tone={d.ratios.current_ratio >= 1 ? "green" : "red"} />
                <MiniStat label="Quick ratio" value={d.ratios.quick_ratio.toFixed(2)} tone={d.ratios.quick_ratio >= 1 ? "green" : "red"} />
                <MiniStat label="Debt / equity" value={d.ratios.debt_to_equity.toFixed(2)} tone={d.ratios.debt_to_equity <= 1 ? "green" : "gold"} />
                <MiniStat label="Net margin" value={pct(d.ratios.net_profit_margin)} />
                <MiniStat label="ROE" value={pct(d.ratios.return_on_equity)} />
                <MiniStat label="ROA" value={pct(d.ratios.return_on_assets)} />
                <MiniStat label="Working capital" value={pkrShort(d.ratios.working_capital, false)} tone="blue" />
              </div>
            </Card>
          </div>
        )}
      </QueryState>

      <Card className="overflow-hidden">
        <Tabs<TabKey>
          className="px-2"
          value={tab}
          onChange={setTab}
          tabs={[
            { value: "overview", label: "Overview", icon: <LayoutDashboard className="h-4 w-4" /> },
            { value: "invoices", label: "Invoices", icon: <FileText className="h-4 w-4" />, count: dash.data?.overdue_invoices || undefined },
            { value: "aging", label: "Ageing", icon: <Hourglass className="h-4 w-4" /> },
            { value: "rentroll", label: "Rent roll", icon: <CalendarRange className="h-4 w-4" /> },
            { value: "journal", label: "Journal", icon: <BookOpen className="h-4 w-4" /> },
            { value: "chart", label: "Chart of accounts", icon: <ListTree className="h-4 w-4" /> },
            { value: "trial", label: "Trial balance", icon: <Scale className="h-4 w-4" /> },
            { value: "budgets", label: "Budgets", icon: <Target className="h-4 w-4" /> },
          ]}
        />
        <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
          {tab === "overview" && <OverviewTab />}
          {tab === "invoices" && <InvoicesTab onPay={(i) => setPayFor(i)} />}
          {tab === "aging" && <AgingTab />}
          {tab === "rentroll" && <RentRollTab />}
          {tab === "journal" && <JournalTab />}
          {tab === "chart" && <ChartTab />}
          {tab === "trial" && <TrialTab />}
          {tab === "budgets" && <BudgetsTab />}
        </motion.div>
      </Card>

      <NewInvoiceModal open={newInvoice} onClose={() => setNewInvoice(false)} />
      <PaymentModal open={payFor !== null} invoice={payFor && payFor !== "new" ? payFor : null} onClose={() => setPayFor(null)} />
    </div>
  );
}

// ================================================================== Overview
/** "Parking & Ancillary Income" -> "Parking & Ancillary" (keeps chart axes readable). */
function shortName(n: string) {
  const t = n.replace(/ (Income|Expense|Expenses)$/, "");
  return t.length > 20 ? `${t.slice(0, 19)}…` : t;
}

function OverviewTab() {
  const pnl = useApi<Pnl>("/accounting/profit-and-loss");
  const cf = useApi<CashFlow>("/accounting/cash-flow");
  const bs = useApi<BalanceSheet>("/accounting/balance-sheet");
  return (
    <div className="grid gap-5 p-4 sm:p-5 lg:grid-cols-5">
      <Panel title="Profit & loss" subtitle="Income vs expenses by account" icon={<Receipt className="h-4 w-4" />} className="lg:col-span-3">
        <QueryState q={pnl} skeleton={<Skeleton className="h-80" />}>
          {(p) => {
            const rows = [
              ...p.income.map((l) => ({ name: shortName(l.name), income: l.amount, expenses: 0 })),
              ...p.expenses.map((l) => ({ name: shortName(l.name), income: 0, expenses: l.amount })),
            ];
            return (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-2">
                  <MiniStat label="Income" value={pkrShort(p.total_income, false)} tone="green" />
                  <MiniStat label="Expenses" value={pkrShort(p.total_expenses, false)} tone="gold" />
                  <MiniStat label="Net profit" value={pkrShort(p.net_profit, false)} hint={`${pct(p.net_margin)} margin`} tone={p.net_profit >= 0 ? "green" : "red"} />
                </div>
                {rows.length ? (
                  <Bars
                    data={rows}
                    x="name"
                    horizontal
                    stacked
                    height={Math.max(300, rows.length * 34)}
                    series={[
                      { key: "income", label: "Income", color: "#146f45" },
                      { key: "expenses", label: "Expenses", color: "#c99a22" },
                    ]}
                    format={crShort}
                  />
                ) : (
                  <EmptyState title="No postings yet" />
                )}
              </div>
            );
          }}
        </QueryState>
      </Panel>

      <div className="space-y-5 lg:col-span-2">
        <Panel title="Cash flow" subtitle="Sources and uses of cash" icon={<Wallet className="h-4 w-4" />}>
          <QueryState q={cf} skeleton={<Skeleton className="h-56" />}>
            {(c) => (
              <div className="space-y-3">
                <Bars
                  data={[
                    { name: "Operating", value: c.operating },
                    { name: "Investing", value: c.investing },
                    { name: "Financing", value: c.financing },
                    { name: "Net", value: c.net_change },
                  ]}
                  x="name"
                  series={[{ key: "value", label: "Cash flow" }]}
                  colorByIndex
                  height={180}
                  format={crShort}
                />
                <div className="flex items-center justify-between rounded-xl bg-brand-50/60 px-3 py-2 text-sm dark:bg-white/5">
                  <span className="text-ink-mute">Opening {pkrShort(c.opening_cash, false)}</span>
                  <ArrowUpRight className="h-4 w-4 text-brand-600 rtl:-scale-x-100" />
                  <span className="font-semibold">Closing {pkrShort(c.closing_cash, false)}</span>
                </div>
              </div>
            )}
          </QueryState>
        </Panel>

        <Panel
          title="Balance sheet"
          subtitle={bs.data ? `As of ${date(bs.data.as_of)}` : undefined}
          icon={<Scale className="h-4 w-4" />}
          action={bs.data && <Badge tone={bs.data.balanced ? "green" : "red"}>{bs.data.balanced ? "Balanced" : "Out of balance"}</Badge>}
        >
          <QueryState q={bs} skeleton={<Skeleton className="h-64" />}>
            {(b) => (
              <div className="space-y-4">
                <div className="flex h-3 overflow-hidden rounded-full">
                  <div className="bg-gold-500" style={{ width: `${(b.total_liabilities / Math.max(1, b.total_assets)) * 100}%` }} title="Liabilities" />
                  <div className="bg-brand-600" style={{ width: `${(b.total_equity / Math.max(1, b.total_assets)) * 100}%` }} title="Equity" />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <MiniStat label="Assets" value={crShort(b.total_assets)} />
                  <MiniStat label="Liabilities" value={crShort(b.total_liabilities)} tone="gold" />
                  <MiniStat label="Equity" value={crShort(b.total_equity)} tone="green" />
                </div>
                {(
                  [
                    ["Assets", b.assets],
                    ["Liabilities", b.liabilities],
                    ["Equity", b.equity],
                  ] as const
                ).map(([label, rows]) => (
                  <div key={label}>
                    <p className="mb-1 text-[11px] font-bold uppercase tracking-wider text-ink-mute">{label}</p>
                    <ul className="divide-y divide-black/5 text-sm dark:divide-white/5">
                      {rows.map((r) => (
                        <li key={r.code} className="flex justify-between gap-3 py-1.5">
                          <span className="min-w-0 truncate">
                            <span className="me-2 font-mono text-[11px] text-ink-mute">{r.code}</span>
                            {r.name}
                          </span>
                          <span className={cn("shrink-0 tabular-nums", r.amount < 0 && "text-red-600")}>{num(r.amount)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </QueryState>
        </Panel>
      </div>
    </div>
  );
}

// ================================================================== Invoices
function InvoicesTab({ onPay }: { onPay: (i: Invoice) => void }) {
  const [type, setType] = useState<"all" | "receivable" | "payable">("all");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const q = useApi<{ count: number; invoices: Invoice[] }>("/accounting/invoices", {
    invoice_type: type === "all" ? undefined : type,
    overdue_only: overdueOnly || undefined,
    limit: 500,
  });

  const columns: Column<Invoice>[] = [
    {
      key: "number",
      header: "Invoice",
      render: (i) => (
        <div className="min-w-[150px]">
          <p className="font-mono text-xs font-semibold text-brand-800 dark:text-brand-200">{i.number}</p>
          <p className="truncate text-sm font-medium">{i.counterparty}</p>
        </div>
      ),
      value: (i) => `${i.number} ${i.counterparty}`,
    },
    {
      key: "invoice_type",
      header: "Type",
      render: (i) => (
        <Badge tone={i.invoice_type === "receivable" ? "blue" : "purple"} icon={i.invoice_type === "receivable" ? <ArrowDownLeft className="h-3 w-3" /> : <ArrowUpRight className="h-3 w-3" />}>
          {i.invoice_type === "receivable" ? "AR" : "AP"}
        </Badge>
      ),
    },
    { key: "issue_date", header: "Issued", render: (i) => <span className="whitespace-nowrap text-xs">{date(i.issue_date)}</span> },
    { key: "due_date", header: "Due", render: (i) => <span className="whitespace-nowrap text-xs">{date(i.due_date)}</span> },
    { key: "total", header: "Total", align: "right", render: (i) => <span className="whitespace-nowrap">{num(i.total)}</span> },
    { key: "balance", header: "Balance", align: "right", render: (i) => <span className={cn("whitespace-nowrap font-semibold", i.balance > 0 ? "text-ink dark:text-white" : "text-ink-mute")}>{num(i.balance)}</span> },
    {
      key: "status",
      header: "Status",
      value: (i) => (i.is_overdue ? `overdue ${i.days_overdue}` : i.status),
      render: (i) => (
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge status={i.status} />
          {i.is_overdue && <Badge tone="red">{i.days_overdue}d overdue</Badge>}
        </div>
      ),
    },
    {
      key: "act",
      header: "",
      sortable: false,
      render: (i) =>
        i.balance > 0 && i.status !== "void" ? (
          <Button
            size="sm"
            variant="soft"
            onClick={(e) => {
              e.stopPropagation();
              onPay(i);
            }}
          >
            {i.invoice_type === "receivable" ? "Receive" : "Pay"}
          </Button>
        ) : null,
    },
  ];

  return (
    <>
      <QueryState q={q} skeleton={<div className="p-5"><Skeleton className="h-80" /></div>}>
        {(d) => {
          const outstanding = d.invoices.reduce((s, i) => s + i.balance, 0);
          return (
            <DataTable
              rows={d.invoices}
              columns={columns}
              search
              onRowClick={(i) => setOpenId(i.id)}
              toolbar={
                <div className="flex flex-wrap items-center gap-3">
                  <span className="hidden text-xs text-ink-mute md:inline">Outstanding {pkrShort(outstanding)}</span>
                  <Toggle checked={overdueOnly} onChange={setOverdueOnly} label={<span className="text-xs font-semibold">Overdue only</span>} />
                  <Segmented
                    size="sm"
                    value={type}
                    onChange={setType}
                    options={[
                      { value: "all", label: "All" },
                      { value: "receivable", label: "AR" },
                      { value: "payable", label: "AP" },
                    ]}
                  />
                </div>
              }
              empty={<EmptyState title="No invoices" hint="Create one with “New invoice”." />}
            />
          );
        }}
      </QueryState>
      <InvoiceDrawer id={openId} onClose={() => setOpenId(null)} onPay={onPay} />
    </>
  );
}

function InvoiceDrawer({ id, onClose, onPay }: { id: string | null; onClose: () => void; onPay: (i: Invoice) => void }) {
  const q = useApi<Invoice>(id ? `/accounting/invoices/${id}` : null);
  const postIt = useMutate(() => post(`/accounting/invoices/${id}/post`).then(ensure), { invalidate: INVALIDATE, success: "Invoice posted to the ledger" });
  return (
    <Drawer open={!!id} onClose={onClose} title={q.data?.number ?? "Invoice"} width="max-w-lg">
      <div className="p-5">
        <QueryState q={q} skeleton={<Skeleton className="h-96" />}>
          {(i) => (
            <div className="space-y-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-ink-mute">{i.invoice_type === "receivable" ? "Bill to" : "Supplier"}</p>
                  <p className="font-display text-lg font-semibold">{i.counterparty}</p>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <StatusBadge status={i.status} />
                  {i.is_overdue && <Badge tone="red">{i.days_overdue} days overdue</Badge>}
                </div>
              </div>
              <KeyValue
                items={[
                  { label: "Issued", value: date(i.issue_date) },
                  { label: "Due", value: date(i.due_date) },
                  { label: "Total", value: pkr(i.total) },
                  { label: "Balance", value: <span className={i.balance > 0 ? "text-red-600" : "text-brand-700"}>{pkr(i.balance)}</span> },
                ]}
              />
              <div>
                <p className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-mute">Lines</p>
                <div className="overflow-hidden rounded-xl border border-black/5 dark:border-white/10">
                  <table className="w-full text-sm">
                    <tbody>
                      {i.lines.map((l, k) => (
                        <tr key={k} className="border-b border-black/5 last:border-0 dark:border-white/5">
                          <td className="px-3 py-2">
                            {l.description}
                            <span className="block text-xs text-ink-mute">
                              {l.quantity} × {num(l.unit_price)}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-end tabular-nums">{num(l.amount)}</td>
                        </tr>
                      ))}
                      <tr className="bg-black/[.02] text-xs dark:bg-white/5">
                        <td className="px-3 py-1.5 text-ink-mute">Subtotal · Tax</td>
                        <td className="px-3 py-1.5 text-end tabular-nums">
                          {num(i.subtotal)} · {num(i.tax_amount)}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              <div>
                <p className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-mute">Payments</p>
                {i.payments?.length ? (
                  <ul className="space-y-1.5 text-sm">
                    {i.payments.map((p) => (
                      <li key={p.id} className="flex justify-between rounded-lg bg-brand-50/50 px-3 py-2 dark:bg-white/5">
                        <span>
                          {date(p.date)} · {titleCase(p.method)}
                        </span>
                        <span className="font-semibold tabular-nums">{num(p.amount)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-ink-mute">No payments recorded.</p>
                )}
                <Progress value={i.total ? (i.amount_paid / i.total) * 100 : 0} className="mt-3" />
              </div>
              {i.notes && <p className="rounded-xl bg-gold-50/70 px-3 py-2 text-xs text-gold-800 dark:bg-gold-500/10 dark:text-gold-100">{i.notes}</p>}
              <div className="flex flex-wrap gap-2">
                {i.status === "draft" && (
                  <Button variant="outline" icon={<Send className="h-4 w-4" />} loading={postIt.isPending} onClick={() => postIt.mutate()}>
                    Post to ledger
                  </Button>
                )}
                {i.balance > 0 && i.status !== "void" && (
                  <Button icon={<Wallet className="h-4 w-4" />} onClick={() => onPay(i)}>
                    Record payment
                  </Button>
                )}
              </div>
            </div>
          )}
        </QueryState>
      </div>
    </Drawer>
  );
}

// ================================================================== Ageing
function AgingTab() {
  const [type, setType] = useState<"all" | "receivable" | "payable">("all");
  const q = useApi<{ as_of: string; buckets: Record<string, number>; total: number; invoices: { number: string; counterparty: string; type: string; due_date: string; days_overdue: number; balance: number; bucket: string }[] }>(
    "/accounting/aging",
    { invoice_type: type === "all" ? undefined : type },
  );
  return (
    <div className="p-4 sm:p-5">
      <QueryState q={q} skeleton={<Skeleton className="h-80" />}>
        {(a) => (
          <div className="grid gap-5 lg:grid-cols-5">
            <Panel
              title="Ageing buckets"
              subtitle={`${pkrShort(a.total)} outstanding`}
              icon={<Hourglass className="h-4 w-4" />}
              className="lg:col-span-2"
              action={
                <Segmented
                  size="sm"
                  value={type}
                  onChange={setType}
                  options={[
                    { value: "all", label: "All" },
                    { value: "receivable", label: "AR" },
                    { value: "payable", label: "AP" },
                  ]}
                />
              }
            >
              <Bars data={Object.entries(a.buckets).map(([b, v]) => ({ bucket: b === "current" ? "Current" : `${b} d`, value: v }))} x="bucket" series={[{ key: "value", label: "Balance" }]} colorByIndex height={240} format={crShort} />
              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {Object.entries(a.buckets).map(([b, v]) => (
                  <MiniStat key={b} label={b === "current" ? "Current" : `${b} days`} value={pkrShort(v, false)} tone={b === "90+" && v > 0 ? "red" : "default"} />
                ))}
              </div>
            </Panel>
            <Card className="overflow-hidden lg:col-span-3">
              <DataTable
                rows={a.invoices}
                rowKey={(r) => r.number}
                columns={[
                  { key: "number", header: "Invoice", render: (r) => <span className="font-mono text-xs font-semibold">{r.number}</span> },
                  { key: "counterparty", header: "Counterparty" },
                  { key: "type", header: "Type", render: (r) => <Badge tone={r.type === "receivable" ? "blue" : "purple"}>{r.type === "receivable" ? "AR" : "AP"}</Badge> },
                  { key: "days_overdue", header: "Days", align: "right", render: (r) => <span className={cn("font-semibold", r.days_overdue > 90 ? "text-red-600" : r.days_overdue > 30 ? "text-gold-700" : "")}>{r.days_overdue}</span> },
                  { key: "bucket", header: "Bucket", render: (r) => <Badge tone={r.bucket === "90+" ? "red" : r.bucket === "61-90" ? "orange" : "gold"}>{r.bucket}</Badge> },
                  { key: "balance", header: "Balance", align: "right", render: (r) => num(r.balance) },
                ]}
                search
                empty={<EmptyState title="Nothing overdue" icon={<CheckCircle2 className="h-6 w-6" />} />}
              />
            </Card>
          </div>
        )}
      </QueryState>
    </div>
  );
}

// ================================================================== Rent roll
function RentRollTab() {
  const q = useApi<{
    leases: number;
    monthly_rent: number;
    annual_rent: number;
    security_deposits: number;
    by_cycle: Record<string, number>;
    tenants: { id: string; tenant: string; unit_label?: string | null; start_date: string; end_date: string; rent_amount: number; billing_cycle: string; escalation_rate?: number | null; security_deposit: number; status: string; monthly_rent: number; annual_rent: number }[];
  }>("/accounting/rent-roll");
  return (
    <div className="p-4 sm:p-5">
      <QueryState q={q} skeleton={<Skeleton className="h-80" />}>
        {(r) => (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <MiniStat label="Active leases" value={r.leases} />
              <MiniStat label="Monthly rent" value={pkrShort(r.monthly_rent, false)} tone="green" />
              <MiniStat label="Annual rent" value={pkrShort(r.annual_rent, false)} tone="gold" />
              <MiniStat label="Deposits held" value={pkrShort(r.security_deposits, false)} tone="blue" />
            </div>
            <Card className="overflow-hidden">
              <DataTable
                rows={r.tenants}
                search
                columns={[
                  {
                    key: "tenant",
                    header: "Tenant",
                    render: (t) => (
                      <div className="min-w-[150px]">
                        <p className="font-semibold">{t.tenant}</p>
                        <p className="text-xs text-ink-mute">{t.unit_label ?? "—"}</p>
                      </div>
                    ),
                  },
                  { key: "billing_cycle", header: "Cycle", render: (t) => <Badge tone="gray">{titleCase(t.billing_cycle)}</Badge> },
                  { key: "rent_amount", header: "Rent / cycle", align: "right", render: (t) => num(t.rent_amount) },
                  { key: "monthly_rent", header: "Monthly", align: "right", render: (t) => <span className="font-semibold">{num(t.monthly_rent)}</span> },
                  { key: "escalation_rate", header: "Escalation", align: "right", render: (t) => (t.escalation_rate ? pct(t.escalation_rate, 0) : "—") },
                  { key: "security_deposit", header: "Deposit", align: "right", render: (t) => num(t.security_deposit) },
                  { key: "end_date", header: "Term", render: (t) => <span className="whitespace-nowrap text-xs">{date(t.start_date, { month: "short", year: "numeric" })} – {date(t.end_date, { month: "short", year: "numeric" })}</span> },
                  { key: "status", header: "Status", render: (t) => <StatusBadge status={t.status} /> },
                ]}
                empty={<EmptyState title="No leases" />}
              />
            </Card>
          </div>
        )}
      </QueryState>
    </div>
  );
}

// ================================================================== Journal
function useAccountNames() {
  const chart = useApi<{ accounts: Account[] }>("/accounting/chart");
  return useMemo(() => Object.fromEntries((chart.data?.accounts ?? []).map((a) => [a.code, a.name])), [chart.data]);
}

function JournalTab() {
  const [source, setSource] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const q = useApi<{ count: number; entries: JournalEntry[] }>("/accounting/journal", { limit: 500 });
  const sources = useMemo(() => Array.from(new Set((q.data?.entries ?? []).map((e) => e.source))).sort(), [q.data]);
  return (
    <>
      <QueryState q={q} skeleton={<div className="p-5"><Skeleton className="h-80" /></div>}>
        {(d) => (
          <DataTable
            rows={source ? d.entries.filter((e) => e.source === source) : d.entries}
            search
            onRowClick={(e) => setOpenId(e.id)}
            toolbar={
              <Select className="w-40 py-2" value={source} onChange={(e) => setSource(e.target.value)}>
                <option value="">All sources</option>
                {sources.map((s) => (
                  <option key={s} value={s}>
                    {titleCase(s)}
                  </option>
                ))}
              </Select>
            }
            columns={[
              { key: "entry_no", header: "#", align: "right", render: (e) => <span className="font-mono text-xs">{e.entry_no}</span> },
              { key: "date", header: "Date", render: (e) => <span className="whitespace-nowrap text-xs">{date(e.date)}</span> },
              { key: "reference", header: "Reference", render: (e) => <span className="font-mono text-xs">{e.reference ?? "—"}</span> },
              { key: "memo", header: "Memo", render: (e) => <span className="line-clamp-1 min-w-[160px] text-sm">{e.memo ?? "—"}</span> },
              { key: "source", header: "Source", render: (e) => <Badge tone="gray">{titleCase(e.source)}</Badge> },
              { key: "total_debit", header: "Amount", align: "right", render: (e) => <span className="font-semibold">{num(e.total_debit)}</span> },
              { key: "status", header: "Status", render: (e) => <StatusBadge status={e.status} /> },
            ]}
            empty={<EmptyState title="No journal entries" />}
          />
        )}
      </QueryState>
      <JournalDrawer id={openId} onClose={() => setOpenId(null)} />
    </>
  );
}

function JournalDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const q = useApi<JournalEntry>(id ? `/accounting/journal/${id}` : null);
  const names = useAccountNames();
  return (
    <Drawer open={!!id} onClose={onClose} title={q.data ? `Journal entry #${q.data.entry_no}` : "Journal entry"} width="max-w-lg">
      <div className="p-5">
        <QueryState q={q} skeleton={<Skeleton className="h-72" />}>
          {(e) => (
            <div className="space-y-5">
              <KeyValue
                items={[
                  { label: "Date", value: date(e.date) },
                  { label: "Reference", value: e.reference ?? "—" },
                  { label: "Source", value: titleCase(e.source) },
                  { label: "Status", value: <StatusBadge status={e.status} /> },
                ]}
              />
              {e.memo && <p className="text-sm text-ink-soft dark:text-slate-300">{e.memo}</p>}
              <div className="overflow-x-auto rounded-xl border border-black/5 dark:border-white/10">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-brand-50/50 text-[11px] font-bold uppercase tracking-wider text-ink-mute dark:bg-white/5">
                      <th className="px-3 py-2 text-start">Account</th>
                      <th className="px-3 py-2 text-end">Debit</th>
                      <th className="px-3 py-2 text-end">Credit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {e.lines.map((l, i) => (
                      <tr key={i} className="border-t border-black/5 dark:border-white/5">
                        <td className="px-3 py-2">
                          <span className="font-mono text-xs text-ink-mute">{l.account}</span> {names[l.account] ?? ""}
                          {l.description && <span className="block text-xs text-ink-mute">{l.description}</span>}
                        </td>
                        <td className="px-3 py-2 text-end tabular-nums">{l.debit ? num(l.debit) : ""}</td>
                        <td className="px-3 py-2 text-end tabular-nums">{l.credit ? num(l.credit) : ""}</td>
                      </tr>
                    ))}
                    <tr className="border-t-2 border-black/10 font-semibold dark:border-white/15">
                      <td className="px-3 py-2">Total</td>
                      <td className="px-3 py-2 text-end tabular-nums">{num(e.total_debit)}</td>
                      <td className="px-3 py-2 text-end tabular-nums">{num(e.total_credit)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              {e.void_reason && <ErrorState error={`Voided: ${e.void_reason}`} />}
            </div>
          )}
        </QueryState>
      </div>
    </Drawer>
  );
}

// ================================================================== Chart of accounts
const TYPE_TONE: Record<string, "green" | "gold" | "blue" | "purple" | "red" | "gray"> = { asset: "blue", liability: "gold", equity: "purple", income: "green", expense: "red" };

function ChartTab() {
  const [type, setType] = useState("");
  const q = useApi<{ count: number; accounts: Account[] }>("/accounting/chart");
  return (
    <QueryState q={q} skeleton={<div className="p-5"><Skeleton className="h-80" /></div>}>
      {(d) => {
        const types = Array.from(new Set(d.accounts.map((a) => a.type)));
        const rows = type ? d.accounts.filter((a) => a.type === type) : d.accounts;
        return (
          <DataTable
            rows={rows}
            rowKey={(a) => a.code}
            search
            pageSize={20}
            toolbar={
              <Select className="w-36 py-2" value={type} onChange={(e) => setType(e.target.value)}>
                <option value="">All types</option>
                {types.map((t) => (
                  <option key={t} value={t}>
                    {titleCase(t)}
                  </option>
                ))}
              </Select>
            }
            columns={[
              { key: "code", header: "Code", render: (a) => <span className="font-mono text-xs font-semibold">{a.code}</span> },
              {
                key: "name",
                header: "Account",
                render: (a) => (
                  <span className="inline-flex items-center gap-2">
                    {a.name}
                    {(a.is_bank || a.is_cash) && <Badge tone="blue">{a.is_bank ? "Bank" : "Cash"}</Badge>}
                  </span>
                ),
              },
              { key: "type", header: "Type", render: (a) => <Badge tone={TYPE_TONE[a.type] ?? "gray"}>{titleCase(a.type)}</Badge> },
              { key: "subtype", header: "Subtype", render: (a) => <span className="text-xs text-ink-mute">{titleCase(a.subtype)}</span> },
              { key: "normal_side", header: "Normal", render: (a) => <span className="text-xs uppercase">{a.normal_side === "debit" ? "Dr" : "Cr"}</span> },
              { key: "balance", header: "Balance", align: "right", render: (a) => <span className={cn("font-semibold", a.balance === 0 && "text-ink-mute font-normal", a.balance < 0 && "text-red-600")}>{num(a.balance)}</span> },
            ]}
          />
        );
      }}
    </QueryState>
  );
}

// ================================================================== Trial balance
function TrialTab() {
  const q = useApi<{ as_of: string; rows: { code: string; name: string; type: string; debit: number; credit: number }[]; total_debit: number; total_credit: number; balanced: boolean }>("/accounting/trial-balance");
  return (
    <div className="p-4 sm:p-5">
      <QueryState q={q} skeleton={<Skeleton className="h-96" />}>
        {(t) => (
          <Card className="overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-black/5 px-4 py-3 dark:border-white/10">
              <p className="text-sm font-semibold">As of {date(t.as_of)}</p>
              <Badge tone={t.balanced ? "green" : "red"} icon={t.balanced ? <CheckCircle2 className="h-3 w-3" /> : undefined}>
                {t.balanced ? "Debits = credits" : "Out of balance"}
              </Badge>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-brand-50/50 text-[11px] font-bold uppercase tracking-wider text-ink-mute dark:bg-white/5">
                    <th className="px-4 py-2.5 text-start">Account</th>
                    <th className="px-4 py-2.5 text-start">Type</th>
                    <th className="px-4 py-2.5 text-end">Debit</th>
                    <th className="px-4 py-2.5 text-end">Credit</th>
                  </tr>
                </thead>
                <tbody>
                  {t.rows.map((r) => (
                    <tr key={r.code} className="border-t border-black/5 dark:border-white/5">
                      <td className="px-4 py-2">
                        <span className="me-2 font-mono text-xs text-ink-mute">{r.code}</span>
                        {r.name}
                      </td>
                      <td className="px-4 py-2">
                        <Badge tone={TYPE_TONE[r.type] ?? "gray"}>{titleCase(r.type)}</Badge>
                      </td>
                      <td className="px-4 py-2 text-end tabular-nums">{r.debit ? num(r.debit) : ""}</td>
                      <td className="px-4 py-2 text-end tabular-nums">{r.credit ? num(r.credit) : ""}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 border-black/10 bg-brand-50/40 font-display font-bold dark:border-white/15 dark:bg-white/5">
                    <td className="px-4 py-3" colSpan={2}>
                      Totals
                    </td>
                    <td className="px-4 py-3 text-end tabular-nums">{num(t.total_debit)}</td>
                    <td className="px-4 py-3 text-end tabular-nums">{num(t.total_credit)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Card>
        )}
      </QueryState>
    </div>
  );
}

// ================================================================== Budgets
function BudgetsTab() {
  const q = useApi<{ count: number; budgets: Budget[] }>("/accounting/budgets");
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => {
    if (!sel && q.data?.budgets.length) setSel(q.data.budgets[0].id);
  }, [q.data, sel]);
  const v = useApi<Variance>(sel ? `/accounting/budgets/${sel}/variance` : null);
  return (
    <div className="p-4 sm:p-5">
      <QueryState q={q} skeleton={<Skeleton className="h-80" />}>
        {(d) =>
          d.budgets.length ? (
            <div className="grid gap-5 lg:grid-cols-4">
              <div className="space-y-2">
                {d.budgets.map((b) => (
                  <button
                    key={b.id}
                    onClick={() => setSel(b.id)}
                    className={cn(
                      "w-full rounded-2xl border p-4 text-start transition-all",
                      sel === b.id ? "border-brand-400 bg-brand-50/70 shadow-soft dark:border-brand-500/50 dark:bg-brand-500/10" : "border-black/5 hover:border-brand-200 dark:border-white/10",
                    )}
                  >
                    <p className="font-semibold">{b.name}</p>
                    <p className="mt-0.5 text-xs text-ink-mute">
                      FY {b.fiscal_year || "—"} · {titleCase(b.scope)}
                    </p>
                    <p className="mt-2 font-display text-lg font-bold text-brand-800 dark:text-brand-200">{pkrShort(Object.values(b.lines).reduce((s, x) => s + x, 0), false)}</p>
                  </button>
                ))}
              </div>
              <div className="min-w-0 lg:col-span-3">
                <QueryState q={v} skeleton={<Skeleton className="h-80" />}>
                  {(x) => {
                    const used = x.total_budget ? (x.total_actual / x.total_budget) * 100 : 0;
                    return (
                      <div className="space-y-5">
                        <div className="grid grid-cols-3 gap-2">
                          <MiniStat label="Budget" value={pkrShort(x.total_budget, false)} />
                          <MiniStat label="Actual" value={pkrShort(x.total_actual, false)} tone="gold" hint={`${used.toFixed(0)}% used`} />
                          <MiniStat label="Variance" value={pkrShort(x.total_variance, false)} tone={x.total_variance >= 0 ? "green" : "red"} hint={x.total_variance >= 0 ? "under budget" : "over budget"} />
                        </div>
                        <Bars
                          data={x.rows.map((r) => ({ name: r.name, budget: r.budget, actual: r.actual }))}
                          x="name"
                          series={[
                            { key: "budget", label: "Budget", color: "#a6dcbf" },
                            { key: "actual", label: "Actual", color: "#146f45" },
                          ]}
                          height={260}
                          format={crShort}
                        />
                        <div className="overflow-x-auto rounded-xl border border-black/5 dark:border-white/10">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="bg-brand-50/50 text-[11px] font-bold uppercase tracking-wider text-ink-mute dark:bg-white/5">
                                <th className="px-3 py-2 text-start">Account</th>
                                <th className="px-3 py-2 text-end">Budget</th>
                                <th className="px-3 py-2 text-end">Actual</th>
                                <th className="px-3 py-2 text-end">Variance</th>
                                <th className="px-3 py-2">Used</th>
                              </tr>
                            </thead>
                            <tbody>
                              {x.rows.map((r) => {
                                const u = r.budget ? (r.actual / r.budget) * 100 : 0;
                                return (
                                  <tr key={r.code} className="border-t border-black/5 dark:border-white/5">
                                    <td className="px-3 py-2">
                                      <span className="me-2 font-mono text-xs text-ink-mute">{r.code}</span>
                                      {r.name}
                                    </td>
                                    <td className="px-3 py-2 text-end tabular-nums">{num(r.budget)}</td>
                                    <td className="px-3 py-2 text-end tabular-nums">{num(r.actual)}</td>
                                    <td className={cn("px-3 py-2 text-end font-semibold tabular-nums", r.favorable ? "text-brand-700 dark:text-brand-300" : "text-red-600")}>
                                      {num(r.variance)} <span className="text-xs font-normal">({pct(r.variance_pct, 0)})</span>
                                    </td>
                                    <td className="w-32 px-3 py-2">
                                      <Progress value={u} tone={u > 100 ? "red" : u > 85 ? "gold" : "green"} className="h-1.5" />
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    );
                  }}
                </QueryState>
              </div>
            </div>
          ) : (
            <EmptyState title="No budgets yet" icon={<FileSpreadsheet className="h-6 w-6" />} />
          )
        }
      </QueryState>
    </div>
  );
}

// ================================================================== New invoice
type DraftLine = { description: string; quantity: string; unit_price: string };

function NewInvoiceModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [f, set, reset] = useFormState({ counterparty: "", invoice_type: "receivable", issue_date: isoDay(0), due_date: isoDay(14), tax_rate: "0", notes: "", auto_post: true });
  const [lines, setLines] = useState<DraftLine[]>([{ description: "", quantity: "1", unit_price: "" }]);
  const subtotal = lines.reduce((s, l) => s + (numOr(l.quantity, 0) ?? 0) * (numOr(l.unit_price, 0) ?? 0), 0);
  const tax = subtotal * ((numOr(f.tax_rate, 0) ?? 0) / 100);
  const valid = f.counterparty.trim() && lines.some((l) => l.description.trim() && (numOr(l.unit_price, 0) ?? 0) > 0);

  const create = useMutate(
    () =>
      post<Invoice>("/accounting/invoices", {
        counterparty: f.counterparty.trim(),
        invoice_type: f.invoice_type,
        issue_date: f.issue_date || undefined,
        due_date: f.due_date || undefined,
        tax_rate: (numOr(f.tax_rate, 0) ?? 0) / 100,
        notes: f.notes || undefined,
        auto_post: f.auto_post,
        lines: lines
          .filter((l) => l.description.trim())
          .map((l) => ({ description: l.description.trim(), quantity: numOr(l.quantity, 1), unit_price: numOr(l.unit_price, 0) })),
      }).then(ensure),
    {
      invalidate: INVALIDATE,
      success: (r) => `Invoice ${r?.number ?? ""} created`,
      onSuccess: () => {
        reset();
        setLines([{ description: "", quantity: "1", unit_price: "" }]);
        onClose();
      },
    },
  );

  const upd = (i: number, k: keyof DraftLine, v: string) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, [k]: v } : l)));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New invoice"
      subtitle="Bill a tenant or customer, or record a supplier bill"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={create.isPending} disabled={!valid} onClick={() => create.mutate()}>
            Create invoice
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <FormGrid>
          <Field label="Counterparty *">
            <Input value={f.counterparty} onChange={(e) => set("counterparty")(e.target.value)} placeholder="e.g. Metro Mart (Pvt) Ltd" autoFocus />
          </Field>
          <Field label="Type">
            <Select
              value={f.invoice_type}
              onChange={(e) => set("invoice_type")(e.target.value)}
              options={[
                { value: "receivable", label: "Receivable (we bill)" },
                { value: "payable", label: "Payable (supplier bill)" },
              ]}
            />
          </Field>
          <Field label="Issue date">
            <Input type="date" value={f.issue_date} onChange={(e) => set("issue_date")(e.target.value)} />
          </Field>
          <Field label="Due date">
            <Input type="date" value={f.due_date} onChange={(e) => set("due_date")(e.target.value)} />
          </Field>
        </FormGrid>

        <div>
          <p className="label">Line items</p>
          <div className="space-y-2">
            {lines.map((l, i) => (
              <div key={i} className="grid grid-cols-12 gap-2">
                <Input className="col-span-12 sm:col-span-6" placeholder="Description" value={l.description} onChange={(e) => upd(i, "description", e.target.value)} />
                <Input className="col-span-3 sm:col-span-2" type="number" min={0} placeholder="Qty" value={l.quantity} onChange={(e) => upd(i, "quantity", e.target.value)} />
                <Input className="col-span-7 sm:col-span-3" type="number" min={0} placeholder="Unit price" value={l.unit_price} onChange={(e) => upd(i, "unit_price", e.target.value)} />
                <Button
                  size="icon"
                  variant="ghost"
                  className="col-span-2 h-[42px] w-full sm:col-span-1"
                  aria-label="Remove line"
                  disabled={lines.length === 1}
                  onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
          <Button size="sm" variant="soft" className="mt-2" icon={<Plus className="h-4 w-4" />} onClick={() => setLines((ls) => [...ls, { description: "", quantity: "1", unit_price: "" }])}>
            Add line
          </Button>
        </div>

        <FormGrid>
          <Field label="Tax rate (%)">
            <Input type="number" min={0} step="0.5" value={f.tax_rate} onChange={(e) => set("tax_rate")(e.target.value)} />
          </Field>
          <div className="flex items-end">
            <Toggle checked={f.auto_post} onChange={set("auto_post")} label={<span className="text-sm">Post to the ledger now</span>} />
          </div>
          <Field label="Notes" className="sm:col-span-2">
            <Textarea className="min-h-[64px]" value={f.notes} onChange={(e) => set("notes")(e.target.value)} />
          </Field>
        </FormGrid>

        <div className="rounded-2xl bg-brand-50/60 p-4 text-sm dark:bg-white/5">
          <div className="flex justify-between">
            <span className="text-ink-mute">Subtotal</span>
            <span className="tabular-nums">{pkr(subtotal)}</span>
          </div>
          <div className="mt-1 flex justify-between">
            <span className="text-ink-mute">Tax</span>
            <span className="tabular-nums">{pkr(tax)}</span>
          </div>
          <div className="mt-2 flex justify-between border-t border-black/5 pt-2 font-display text-base font-bold dark:border-white/10">
            <span>Total</span>
            <span className="tabular-nums">{pkr(subtotal + tax)}</span>
          </div>
        </div>
      </div>
    </Modal>
  );
}

// ================================================================== Payment
function PaymentModal({ open, invoice, onClose }: { open: boolean; invoice: Invoice | null; onClose: () => void }) {
  const invoices = useApi<{ invoices: Invoice[] }>(open ? "/accounting/invoices" : null, { limit: 500 });
  const chart = useApi<{ accounts: Account[] }>(open ? "/accounting/chart" : null);
  const banks = (chart.data?.accounts ?? []).filter((a) => a.is_bank || a.is_cash);
  const openInvoices = (invoices.data?.invoices ?? []).filter((i) => i.balance > 0 && i.status !== "void");

  const [f, set, , setF] = useFormState({ invoice_id: "", amount: "", direction: "in", method: "bank_transfer", account_code: "1010", date: isoDay(0), counterparty: "", reference: "", notes: "" });

  useEffect(() => {
    if (!open) return;
    setF((s) => ({
      ...s,
      invoice_id: invoice?.id ?? "",
      amount: invoice ? String(invoice.balance) : "",
      direction: invoice?.invoice_type === "payable" ? "out" : "in",
      counterparty: invoice?.counterparty ?? "",
      date: isoDay(0),
      reference: "",
      notes: "",
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, invoice]);

  const pickInvoice = (id: string) => {
    const inv = openInvoices.find((i) => i.id === id);
    setF((s) => ({
      ...s,
      invoice_id: id,
      amount: inv ? String(inv.balance) : s.amount,
      direction: inv ? (inv.invoice_type === "payable" ? "out" : "in") : s.direction,
      counterparty: inv?.counterparty ?? s.counterparty,
    }));
  };
  const selected = openInvoices.find((i) => i.id === f.invoice_id) ?? (invoice?.id === f.invoice_id ? invoice : null);
  const amt = numOr(f.amount, 0) ?? 0;

  const pay = useMutate(
    () =>
      post("/accounting/payments", {
        amount: amt,
        invoice_id: f.invoice_id || undefined,
        direction: f.direction,
        method: f.method,
        account_code: f.account_code,
        date: f.date || undefined,
        counterparty: f.counterparty || undefined,
        reference: f.reference || undefined,
        notes: f.notes || undefined,
      }).then(ensure),
    { invalidate: INVALIDATE, success: "Payment recorded", onSuccess: onClose },
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Record payment"
      subtitle="Receipts and disbursements post straight to the ledger"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={pay.isPending} disabled={amt <= 0} onClick={() => pay.mutate()}>
            Record {amt > 0 ? pkrShort(amt) : "payment"}
          </Button>
        </>
      }
    >
      <FormGrid>
        <Field label="Invoice" className="sm:col-span-2" hint={selected ? `Balance ${pkr(selected.balance)} · due ${date(selected.due_date)}` : "Leave empty for an unallocated receipt / payment"}>
          <Select value={f.invoice_id} onChange={(e) => pickInvoice(e.target.value)}>
            <option value="">No invoice (on account)</option>
            {invoice && !openInvoices.some((i) => i.id === invoice.id) && (
              <option value={invoice.id}>
                {invoice.number} · {invoice.counterparty}
              </option>
            )}
            {openInvoices.map((i) => (
              <option key={i.id} value={i.id}>
                {i.number} · {i.counterparty} · {num(i.balance)}
                {i.is_overdue ? " · overdue" : ""}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Amount (PKR)">
          <Input type="number" min={0} value={f.amount} onChange={(e) => set("amount")(e.target.value)} />
        </Field>
        <Field label="Direction">
          <Select
            value={f.direction}
            onChange={(e) => set("direction")(e.target.value)}
            options={[
              { value: "in", label: "Money in (receipt)" },
              { value: "out", label: "Money out (payment)" },
            ]}
          />
        </Field>
        <Field label="Method">
          <Select value={f.method} onChange={(e) => set("method")(e.target.value)} options={METHODS.map((m) => ({ value: m, label: titleCase(m) }))} />
        </Field>
        <Field label="Cash / bank account">
          <Select value={f.account_code} onChange={(e) => set("account_code")(e.target.value)}>
            {(banks.length ? banks : [{ code: "1010", name: "Bank — Operating" } as Account]).map((a) => (
              <option key={a.code} value={a.code}>
                {a.code} · {a.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Date">
          <Input type="date" value={f.date} onChange={(e) => set("date")(e.target.value)} />
        </Field>
        <Field label="Reference">
          <Input value={f.reference} onChange={(e) => set("reference")(e.target.value)} placeholder="Cheque / transfer #" />
        </Field>
        {!f.invoice_id && (
          <Field label="Counterparty" className="sm:col-span-2">
            <Input value={f.counterparty} onChange={(e) => set("counterparty")(e.target.value)} />
          </Field>
        )}
      </FormGrid>
    </Modal>
  );
}
