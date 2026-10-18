/**
 * Financing calculators: mortgage, installment, rental yield, appreciation, rent-vs-buy.
 * NB: every rate the backend accepts is a FRACTION (0.21 = 21%) — the sliders show
 * percents and divide by 100 before sending.
 */
import { useMemo, useState } from "react";
import { Banknote, CalendarClock, Coins, Home, Landmark, Percent, PiggyBank, Repeat, Scale, TrendingUp, Wallet } from "lucide-react";
import { num, pkr, pkrShort } from "@/lib/format";
import { Card, CardBody, CardHeader, ScoreRing, StatCard } from "@/components/ui";
import { AreaTrend, Bars, Donut, Legendish, PALETTE } from "@/components/ui/charts";
import { CalcShell, ChoiceChips, NumField, StatGrid, useCalc } from "./CalcKit";

const money = (v: number) => pkrShort(v, false);
const crore = (v: number) => pkrShort(v);

// ================================================================== mortgage
interface MortgageRes {
  loan_amount: number;
  down_payment: number;
  down_payment_pct: number;
  annual_rate: number;
  years: number;
  payments_per_year: number;
  monthly_payment: number;
  periodic_payment: number;
  total_paid: number;
  total_interest: number;
  interest_share: number;
  total_cost: number;
  schedule: { period: number; payment: number; interest: number; principal: number; balance: number }[];
}

export function MortgageCalc() {
  const [price, setPrice] = useState(25_000_000);
  const [downPct, setDownPct] = useState(20);
  const [rate, setRate] = useState(18);
  const [years, setYears] = useState(20);
  const [ppy, setPpy] = useState(12);
  const body = { price, down_payment: Math.round((price * downPct) / 100), annual_rate: rate / 100, years, payments_per_year: ppy };
  const q = useCalc<MortgageRes>("/tools/calculators/mortgage", body);
  const d = q.data;

  const yearly = useMemo(() => {
    if (!d?.schedule) return [];
    const per = d.payments_per_year || 12;
    const out: { year: string; balance: number; principal: number; interest: number; cumPrincipal: number; cumInterest: number }[] = [];
    let cp = 0;
    let ci = 0;
    for (const r of d.schedule) {
      const y = Math.ceil(r.period / per);
      cp += r.principal;
      ci += r.interest;
      let row = out[y - 1];
      if (!row) row = out[y - 1] = { year: `Y${y}`, balance: 0, principal: 0, interest: 0, cumPrincipal: 0, cumInterest: 0 };
      row.principal += r.principal;
      row.interest += r.interest;
      row.balance = r.balance;
      row.cumPrincipal = cp;
      row.cumInterest = ci;
    }
    return out.map((r) => ({ ...r, principal: Math.round(r.principal), interest: Math.round(r.interest), cumPrincipal: Math.round(r.cumPrincipal), cumInterest: Math.round(r.cumInterest) }));
  }, [d]);

  const donut = d
    ? [
        { name: "Down payment", value: Math.round(d.down_payment), color: PALETTE[1] },
        { name: "Principal", value: Math.round(d.loan_amount), color: PALETTE[0] },
        { name: "Interest", value: Math.round(d.total_interest), color: PALETTE[4] },
      ]
    : [];

  return (
    <CalcShell
      q={q}
      save={{ tool: "mortgage", inputs: body, outputs: d && { ...d, schedule: undefined }, name: `${pkrShort(price)} home loan · ${rate}% · ${years}y` }}
      form={
        <>
          <NumField label="Property price" value={price} onChange={setPrice} min={1_000_000} max={500_000_000} step={500_000} display={crore} />
          <NumField label="Down payment" value={downPct} onChange={setDownPct} min={0} max={90} step={1} suffix="%" hint={pkr(Math.round((price * downPct) / 100))} />
          <NumField label="Annual markup rate" value={rate} onChange={setRate} min={1} max={35} step={0.25} suffix="%" hint="KIBOR + bank spread; sent to the backend as a fraction." />
          <NumField label="Tenure" value={years} onChange={setYears} min={1} max={30} suffix=" yrs" />
          <div>
            <span className="label">Payment frequency</span>
            <ChoiceChips value={ppy} onChange={setPpy} options={[{ value: 12, label: "Monthly" }, { value: 4, label: "Quarterly" }, { value: 2, label: "Half-yearly" }]} />
          </div>
        </>
      }
    >
      {d && (
        <>
          <StatGrid>
            <StatCard label={ppy === 12 ? "Monthly payment" : "Per installment"} value={pkrShort(d.periodic_payment)} icon={<CalendarClock className="h-5 w-5" />} hint={pkr(d.periodic_payment)} />
            <StatCard label="Loan amount" value={pkrShort(d.loan_amount)} icon={<Landmark className="h-5 w-5" />} tone="blue" hint={`${num(d.down_payment_pct, 1)}% down`} />
            <StatCard label="Total interest" value={pkrShort(d.total_interest)} icon={<Percent className="h-5 w-5" />} tone="red" hint={`${num(d.interest_share * 100, 1)}% of repayments`} />
            <StatCard label="All-in cost" value={pkrShort(d.total_cost)} icon={<Wallet className="h-5 w-5" />} tone="gold" hint="Down payment + repayments" />
          </StatGrid>
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
            <Card>
              <CardHeader title="Amortisation" subtitle="Outstanding balance vs cumulative principal and interest" icon={<TrendingUp className="h-4 w-4" />} />
              <CardBody>
                <AreaTrend
                  data={yearly}
                  x="year"
                  format={money}
                  series={[
                    { key: "balance", label: "Balance", color: PALETTE[2] },
                    { key: "cumPrincipal", label: "Principal paid", color: PALETTE[0] },
                    { key: "cumInterest", label: "Interest paid", color: PALETTE[4] },
                  ]}
                  height={280}
                />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Where the money goes" icon={<Coins className="h-4 w-4" />} />
              <CardBody>
                <Donut
                  data={donut}
                  format={money}
                  height={200}
                  center={
                    <>
                      <span className="text-[10px] font-semibold uppercase text-ink-mute">Total</span>
                      <span className="font-display text-lg font-bold">{pkrShort(d.total_cost, false)}</span>
                    </>
                  }
                />
                <div className="mt-3">
                  <Legendish data={donut.map((x) => ({ ...x, value: Math.round((x.value / d.total_cost) * 100) }))} />
                  <p className="mt-1 text-[11px] text-ink-mute">Shares in % of the all-in cost.</p>
                </div>
              </CardBody>
            </Card>
          </div>
          <Card>
            <CardHeader title="Yearly split" subtitle="Principal vs interest paid each year" />
            <CardBody>
              <Bars data={yearly} x="year" stacked format={money} series={[{ key: "principal", label: "Principal", color: PALETTE[0] }, { key: "interest", label: "Interest", color: PALETTE[4] }]} height={240} />
            </CardBody>
          </Card>
        </>
      )}
    </CalcShell>
  );
}

// ================================================================== installment
interface InstallmentRes {
  down_payment: number;
  down_payment_pct: number;
  financed: number;
  months: number;
  markup: number;
  total_payable: number;
  monthly_installment: number;
}

export function InstallmentCalc() {
  const [price, setPrice] = useState(12_000_000);
  const [downPct, setDownPct] = useState(25);
  const [months, setMonths] = useState(36);
  const [markup, setMarkup] = useState(8);
  const body = { price, down_payment: Math.round((price * downPct) / 100), months, annual_markup: markup / 100 };
  const q = useCalc<InstallmentRes>("/tools/calculators/installment", body);
  const d = q.data;
  const plan = useMemo(() => {
    if (!d) return [];
    const out: { label: string; paid: number }[] = [{ label: "Booking", paid: Math.round(d.down_payment) }];
    let cum = d.down_payment;
    for (let m = 1; m <= d.months; m++) {
      cum += d.monthly_installment;
      if (m % 6 === 0 || m === d.months) out.push({ label: `M${m}`, paid: Math.round(cum) });
    }
    return out;
  }, [d]);
  const donut = d
    ? [
        { name: "Down payment", value: Math.round(d.down_payment), color: PALETTE[1] },
        { name: "Financed", value: Math.round(d.financed), color: PALETTE[0] },
        { name: "Markup", value: Math.round(d.markup), color: PALETTE[4] },
      ]
    : [];
  return (
    <CalcShell
      q={q}
      save={{ tool: "installment", inputs: body, outputs: d, name: `${pkrShort(price)} · ${months} month plan` }}
      form={
        <>
          <NumField label="Property price" value={price} onChange={setPrice} min={500_000} max={300_000_000} step={250_000} display={crore} />
          <NumField label="Down payment" value={downPct} onChange={setDownPct} min={0} max={90} suffix="%" hint={pkr(Math.round((price * downPct) / 100))} />
          <NumField label="Plan length" value={months} onChange={setMonths} min={3} max={120} suffix=" months" />
          <NumField label="Developer markup (annual)" value={markup} onChange={setMarkup} min={0} max={30} step={0.5} suffix="%" />
        </>
      }
    >
      {d && (
        <>
          <StatGrid>
            <StatCard label="Monthly installment" value={pkrShort(d.monthly_installment)} icon={<CalendarClock className="h-5 w-5" />} hint={pkr(d.monthly_installment)} />
            <StatCard label="Down payment" value={pkrShort(d.down_payment)} icon={<Wallet className="h-5 w-5" />} tone="gold" hint={`${num(d.down_payment_pct, 1)}% at booking`} />
            <StatCard label="Markup" value={pkrShort(d.markup)} icon={<Percent className="h-5 w-5" />} tone="red" />
            <StatCard label="Total payable" value={pkrShort(d.total_payable)} icon={<Banknote className="h-5 w-5" />} tone="blue" />
          </StatGrid>
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
            <Card>
              <CardHeader title="Cumulative payments" subtitle="Booking, then every 6 months" />
              <CardBody>
                <AreaTrend data={plan} x="label" series={[{ key: "paid", label: "Paid to date" }]} format={money} height={260} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Breakdown" />
              <CardBody>
                <Donut data={donut} format={money} height={200} />
                <div className="mt-3">
                  <Legendish data={donut.map((x) => ({ ...x, value: Math.round((x.value / d.total_payable) * 100) }))} />
                </div>
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </CalcShell>
  );
}

// ================================================================== rental yield
interface YieldRes {
  gross_annual_rent: number;
  effective_annual_rent: number;
  annual_costs: number;
  net_annual_income: number;
  gross_yield_pct: number;
  net_yield_pct: number;
  payback_years: number | null;
  cap_rate_pct: number;
}

export function RentalYieldCalc() {
  const [price, setPrice] = useState(20_000_000);
  const [rent, setRent] = useState(90_000);
  const [costs, setCosts] = useState(120_000);
  const [vacancy, setVacancy] = useState(5);
  const body = { price, monthly_rent: rent, annual_costs: costs, vacancy_rate: vacancy / 100 };
  const q = useCalc<YieldRes>("/tools/calculators/rental-yield", body);
  const d = q.data;
  const flow = d
    ? [
        { step: "Gross rent", value: Math.round(d.gross_annual_rent) },
        { step: "Vacancy loss", value: Math.round(d.gross_annual_rent - d.effective_annual_rent) },
        { step: "Costs", value: Math.round(d.annual_costs) },
        { step: "Net income", value: Math.round(d.net_annual_income) },
      ]
    : [];
  return (
    <CalcShell
      q={q}
      save={{ tool: "rental_yield", inputs: body, outputs: d, name: `Yield · ${pkrShort(price)} @ ${pkrShort(rent)}/mo` }}
      form={
        <>
          <NumField label="Purchase price" value={price} onChange={setPrice} min={1_000_000} max={300_000_000} step={500_000} display={crore} />
          <NumField label="Monthly rent" value={rent} onChange={setRent} min={5_000} max={2_000_000} step={5_000} display={crore} />
          <NumField label="Annual costs" value={costs} onChange={setCosts} min={0} max={5_000_000} step={10_000} display={crore} hint="Maintenance, tax, management, insurance" />
          <NumField label="Vacancy" value={vacancy} onChange={setVacancy} min={0} max={50} suffix="%" />
        </>
      }
    >
      {d && (
        <>
          <div className="grid gap-5 md:grid-cols-[220px_minmax(0,1fr)]">
            <Card className="flex flex-col items-center justify-center gap-2 bg-gradient-to-br from-brand-50 to-white p-6 text-center dark:from-brand-500/10 dark:to-transparent">
              <ScoreRing value={Math.min(100, (d.net_yield_pct / 12) * 100)} size={120} stroke={10} label="net" />
              <p className="font-display text-3xl font-bold text-brand-800 dark:text-white">{num(d.net_yield_pct, 2)}%</p>
              <p className="text-xs text-ink-mute">Net yield · 12% = full ring</p>
            </Card>
            <StatGrid cols={2}>
              <StatCard label="Gross yield" value={`${num(d.gross_yield_pct, 2)}%`} icon={<Percent className="h-5 w-5" />} />
              <StatCard label="Cap rate" value={`${num(d.cap_rate_pct, 2)}%`} icon={<TrendingUp className="h-5 w-5" />} tone="blue" />
              <StatCard label="Net annual income" value={pkrShort(d.net_annual_income)} icon={<PiggyBank className="h-5 w-5" />} tone="gold" />
              <StatCard label="Payback" value={d.payback_years ? `${num(d.payback_years, 1)} yrs` : "—"} icon={<Repeat className="h-5 w-5" />} tone="purple" />
            </StatGrid>
          </div>
          <Card>
            <CardHeader title="From rent to net income" subtitle="Annual figures" />
            <CardBody>
              <Bars data={flow} x="step" series={[{ key: "value", label: "PKR" }]} colorByIndex format={money} height={240} />
            </CardBody>
          </Card>
        </>
      )}
    </CalcShell>
  );
}

// ================================================================== appreciation
interface ApprRes {
  final_value: number;
  total_gain: number;
  cumulative_rent: number;
  series: { year: number; value: number; low: number; high: number; annual_rent: number; cumulative_rent: number; total_return: number }[];
}

export function AppreciationCalc() {
  const [value, setValue] = useState(20_000_000);
  const [cagr, setCagr] = useState(9);
  const [years, setYears] = useState(10);
  const [rent, setRent] = useState(70_000);
  const [rentGrowth, setRentGrowth] = useState(6);
  const body = { current_value: value, cagr: cagr / 100, years, monthly_rent: rent, rent_growth: rentGrowth / 100 };
  const q = useCalc<ApprRes>("/tools/calculators/appreciation", body);
  const d = q.data;
  return (
    <CalcShell
      q={q}
      save={{ tool: "appreciation", inputs: body, outputs: d, name: `${pkrShort(value)} · ${cagr}% CAGR · ${years}y` }}
      form={
        <>
          <NumField label="Current value" value={value} onChange={setValue} min={1_000_000} max={500_000_000} step={500_000} display={crore} />
          <NumField label="Expected growth (CAGR)" value={cagr} onChange={setCagr} min={0} max={30} step={0.5} suffix="%" />
          <NumField label="Horizon" value={years} onChange={setYears} min={1} max={30} suffix=" yrs" />
          <NumField label="Monthly rent (optional)" value={rent} onChange={setRent} min={0} max={2_000_000} step={5_000} display={crore} />
          <NumField label="Rent growth" value={rentGrowth} onChange={setRentGrowth} min={0} max={20} step={0.5} suffix="%" />
        </>
      }
    >
      {d && (
        <>
          <StatGrid cols={3}>
            <StatCard label={`Value in ${years} yrs`} value={pkrShort(d.final_value)} icon={<Home className="h-5 w-5" />} delta={(d.total_gain / value) * 100} hint="capital growth" />
            <StatCard label="Capital gain" value={pkrShort(d.total_gain)} icon={<TrendingUp className="h-5 w-5" />} tone="gold" />
            <StatCard label="Rent collected" value={pkrShort(d.cumulative_rent)} icon={<Coins className="h-5 w-5" />} tone="blue" />
          </StatGrid>
          <Card>
            <CardHeader title="Projected value with scenario band" subtitle="Low / base / high growth paths" icon={<TrendingUp className="h-4 w-4" />} />
            <CardBody>
              <AreaTrend
                data={d.series.map((r) => ({ ...r, year: String(r.year) }))}
                x="year"
                format={money}
                series={[
                  { key: "high", label: "High", color: PALETTE[1] },
                  { key: "value", label: "Base", color: PALETTE[0] },
                  { key: "low", label: "Low", color: PALETTE[7] },
                ]}
                height={300}
              />
            </CardBody>
          </Card>
          {rent > 0 && (
            <Card>
              <CardHeader title="Total return (value + rent)" />
              <CardBody>
                <Bars data={d.series.map((r) => ({ year: String(r.year), value: Math.round(r.value), rent: Math.round(r.cumulative_rent) }))} x="year" stacked format={money} series={[{ key: "value", label: "Property value" }, { key: "rent", label: "Cumulative rent" }]} height={240} />
              </CardBody>
            </Card>
          )}
        </>
      )}
    </CalcShell>
  );
}

// ================================================================== rent vs buy
interface RvbRes {
  hold_years: number;
  annual_rate: number;
  monthly_payment: number;
  down_payment: number;
  projected_value: number;
  total_rent_paid: number;
  mortgage_total_interest: number;
  message: string;
}

export function RentVsBuyCalc() {
  const [price, setPrice] = useState(25_000_000);
  const [rent, setRent] = useState(90_000);
  const [downPct, setDownPct] = useState(20);
  const [rate, setRate] = useState(18);
  const [loanYears, setLoanYears] = useState(20);
  const [cagr, setCagr] = useState(8);
  const [rentGrowth, setRentGrowth] = useState(5);
  const [hold, setHold] = useState(10);
  const body = { price, monthly_rent: rent, down_payment_pct: downPct / 100, annual_rate: rate / 100, years: loanYears, cagr: cagr / 100, rent_growth: rentGrowth / 100, hold_years: hold };
  const q = useCalc<RvbRes>("/tools/calculators/rent-vs-buy", body);
  const d = q.data;
  const compare = d
    ? [
        { item: "Rent paid", value: Math.round(d.total_rent_paid) },
        { item: "Down payment", value: Math.round(d.down_payment) },
        { item: "Loan interest (full term)", value: Math.round(d.mortgage_total_interest) },
        { item: "Home value at exit", value: Math.round(d.projected_value) },
      ]
    : [];
  const gainVsRent = d ? d.projected_value - price : 0;
  return (
    <CalcShell
      q={q}
      save={{ tool: "rent_vs_buy", inputs: body, outputs: d, name: `Rent vs buy · ${pkrShort(price)}` }}
      form={
        <>
          <NumField label="Home price" value={price} onChange={setPrice} min={2_000_000} max={300_000_000} step={500_000} display={crore} />
          <NumField label="Monthly rent (same home)" value={rent} onChange={setRent} min={5_000} max={2_000_000} step={5_000} display={crore} />
          <NumField label="Down payment" value={downPct} onChange={setDownPct} min={0} max={90} suffix="%" />
          <NumField label="Markup rate" value={rate} onChange={setRate} min={1} max={35} step={0.25} suffix="%" />
          <NumField label="Loan tenure" value={loanYears} onChange={setLoanYears} min={1} max={30} suffix=" yrs" />
          <NumField label="Price growth" value={cagr} onChange={setCagr} min={0} max={25} step={0.5} suffix="%" />
          <NumField label="Rent growth" value={rentGrowth} onChange={setRentGrowth} min={0} max={20} step={0.5} suffix="%" />
          <NumField label="Holding period" value={hold} onChange={setHold} min={1} max={30} suffix=" yrs" />
        </>
      }
    >
      {d && (
        <>
          <StatGrid>
            <StatCard label="Mortgage / month" value={pkrShort(d.monthly_payment)} icon={<Landmark className="h-5 w-5" />} hint={`vs ${pkrShort(rent)} rent`} />
            <StatCard label={`Rent over ${d.hold_years} yrs`} value={pkrShort(d.total_rent_paid)} icon={<Repeat className="h-5 w-5" />} tone="red" />
            <StatCard label="Home value at exit" value={pkrShort(d.projected_value)} icon={<Home className="h-5 w-5" />} tone="gold" delta={(gainVsRent / price) * 100} />
            <StatCard label="Loan interest (term)" value={pkrShort(d.mortgage_total_interest)} icon={<Percent className="h-5 w-5" />} tone="purple" />
          </StatGrid>
          <Card>
            <CardHeader title="Side by side" icon={<Scale className="h-4 w-4" />} />
            <CardBody>
              <Bars data={compare} x="item" series={[{ key: "value", label: "PKR" }]} colorByIndex horizontal format={money} height={240} />
              <p className="mt-4 rounded-xl bg-gold-50 px-4 py-3 text-sm text-gold-800 dark:bg-gold-500/10 dark:text-gold-200">{d.message}</p>
            </CardBody>
          </Card>
        </>
      )}
    </CalcShell>
  );
}
