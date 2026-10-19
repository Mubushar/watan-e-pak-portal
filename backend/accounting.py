"""
Accounting & property-finance engine for the Real Estate Portal
==============================================================

A complete, dependency-free **double-entry accounting core** plus the investment
maths a real-estate portal needs (ROI, IRR, NPV, payback, cap rate, mortgage
amortisation, rent roll).

* **Ledger** — chart of accounts, balanced journal entries, trial balance,
  general ledger, profit & loss, balance sheet, cash-flow statement, ratios.
* **Billing** — receivable/payable invoices with tax, payments + allocation,
  ageing buckets, expenses, budgets with variance, and a lease-driven rent roll.
* **Property-aware** — every journal line and invoice can carry ``property_id`` /
  ``scheme_id`` / ``city_id``, so every statement and every ROI figure can be
  produced for a single property, a scheme, a city or the whole portfolio.
* **Investments** — :func:`investment_metrics` (NPV/IRR/payback/PI/equity
  multiple), :func:`mortgage_schedule`, :func:`cap_rate`, :func:`roi_analysis`
  with pessimistic/base/optimistic scenarios.

No MCP or FastAPI code lives here: ``server.py`` exposes these functions over MCP
and ``api.py`` reuses the very same functions over REST.
"""

import math
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

# Alias so model fields may legitimately be named ``date`` without shadowing the type.
DateType = date

# ============================================================
# CONFIGURATION
# ============================================================

ACCOUNTING_CONFIG: Dict[str, Any] = {
    "currency": "PKR",
    "currency_symbol": "Rs",
    "fiscal_year_start_month": 7,          # Pakistan: July–June
    "fiscal_year_start_day": 1,
    "default_sales_tax_rate": 0.17,        # GST on commercial rent/lettings
    "default_income_tax_rate": 0.15,       # withholding on rent
    "default_commission_rate": 0.02,
    "default_rent_escalation": 0.10,       # annual
    "default_discount_rate": 0.12,         # NPV discount rate
    "default_mortgage_rate": 0.21,         # KIBOR + spread, Pakistan 2025-26
    "default_mortgage_years": 20,
    "default_hold_years": 5,
    "default_cap_rate": 0.07,
    "depreciation_years_buildings": 40,
    "depreciation_years_equipment": 8,
    "aging_buckets": [30, 60, 90],         # current, 1-30, 31-60, 61-90, 90+
}

ACCOUNT_TYPES = ["asset", "liability", "equity", "income", "expense"]

# name -> default normal side per account type
_NORMAL_SIDE = {
    "asset": "debit",
    "expense": "debit",
    "liability": "credit",
    "equity": "credit",
    "income": "credit",
}

ACCOUNT_SUBTYPES = [
    "cash", "bank", "receivable", "inventory", "ppe", "contra_asset", "prepaid",
    "payable", "accrued", "deposit", "tax", "loan", "capital", "retained", "contra_equity",
    "operating_income", "other_income",
    "operating_expense", "payroll", "finance_cost", "contra_expense",
]

INVOICE_TYPES = ["receivable", "payable"]
INVOICE_STATUSES = ["draft", "sent", "part_paid", "paid", "overdue", "void"]
PAYMENT_METHODS = ["cash", "bank_transfer", "cheque", "online", "card", "adjustment"]
LEASE_STATUSES = ["draft", "active", "expired", "terminated"]
BILLING_CYCLES = {"monthly": 1, "quarterly": 3, "semi_annual": 6, "annual": 12}


def _round(value: Any, places: int = 2) -> float:
    try:
        return round(float(value or 0.0), places)
    except (TypeError, ValueError):
        return 0.0


def _m(model: BaseModel) -> Dict[str, Any]:
    return model.model_dump(mode="json")


def _today() -> date:
    return date.today()


def _as_date(value: Any, default: Optional[date] = None) -> Optional[date]:
    if value in (None, ""):
        return default
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return default


def _iso(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


# ============================================================
# MODELS
# ============================================================


class Account(BaseModel):
    code: str                                  # primary key, e.g. "4000"
    name: str
    type: str = "asset"                        # asset | liability | equity | income | expense
    subtype: Optional[str] = None
    normal_side: str = "debit"                 # debit | credit
    parent_code: Optional[str] = None
    description: Optional[str] = None
    is_bank: bool = False
    is_cash: bool = False
    currency: str = "PKR"
    opening_balance: float = 0.0               # on the normal side
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)


class JournalLine(BaseModel):
    account: str
    debit: float = 0.0
    credit: float = 0.0
    description: Optional[str] = None
    property_id: Optional[str] = None
    scheme_id: Optional[str] = None
    city_id: Optional[str] = None
    cost_center: Optional[str] = None


class JournalEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entry_no: int = 0
    date: DateType = Field(default_factory=_today)
    reference: Optional[str] = None
    memo: Optional[str] = None
    source: str = "manual"                     # manual | invoice | payment | expense | lease | depreciation | opening
    source_id: Optional[str] = None
    lines: List[JournalLine] = Field(default_factory=list)
    status: str = "posted"                     # posted | void
    void_reason: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

    def totals(self) -> Tuple[float, float]:
        return _round(sum(l.debit for l in self.lines)), _round(sum(l.credit for l in self.lines))


class InvoiceLine(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float = 0.0
    amount: float = 0.0
    tax_rate: Optional[float] = None


class Invoice(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    number: str = ""
    invoice_type: str = "receivable"           # receivable (we bill) | payable (we are billed)
    counterparty: str = ""
    counterparty_id: Optional[str] = None
    issue_date: date = Field(default_factory=_today)
    due_date: Optional[date] = None
    currency: str = "PKR"
    lines: List[InvoiceLine] = Field(default_factory=list)
    subtotal: float = 0.0
    tax_rate: float = 0.0
    tax_amount: float = 0.0
    total: float = 0.0
    amount_paid: float = 0.0
    balance: float = 0.0
    status: str = "draft"
    property_id: Optional[str] = None
    scheme_id: Optional[str] = None
    city_id: Optional[str] = None
    lease_id: Optional[str] = None
    notes: Optional[str] = None
    journal_entry_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Payment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    date: DateType = Field(default_factory=_today)
    amount: float = 0.0
    direction: str = "in"                      # in (receipt) | out (disbursement)
    method: str = "bank_transfer"
    account_code: str = "1010"                 # cash/bank account
    invoice_id: Optional[str] = None
    counterparty: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None
    journal_entry_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class Expense(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    date: DateType = Field(default_factory=_today)
    category: str = "misc"
    account_code: str = "5900"
    vendor: Optional[str] = None
    description: Optional[str] = None
    amount: float = 0.0
    tax_amount: float = 0.0
    total: float = 0.0
    paid: bool = True
    property_id: Optional[str] = None
    scheme_id: Optional[str] = None
    city_id: Optional[str] = None
    journal_entry_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class Lease(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant: str
    tenant_id: Optional[str] = None
    property_id: Optional[str] = None
    unit_label: Optional[str] = None
    start_date: date = Field(default_factory=_today)
    end_date: Optional[date] = None
    rent_amount: float = 0.0                   # per billing cycle
    billing_cycle: str = "monthly"
    escalation_rate: float = 0.10              # annual
    security_deposit: float = 0.0
    status: str = "active"
    property_id_scope: Optional[str] = None
    city_id: Optional[str] = None
    scheme_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class Budget(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    fiscal_year: str = ""
    scope: str = "portfolio"                   # portfolio | city | scheme | property
    scope_id: Optional[str] = None
    lines: Dict[str, float] = Field(default_factory=dict)   # account_code -> budgeted amount
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# STORES
# ============================================================

accounts_db: Dict[str, Account] = {}
journal_db: List[JournalEntry] = []
invoices_db: List[Invoice] = []
payments_db: List[Payment] = []
expenses_db: List[Expense] = []
leases_db: List[Lease] = []
budgets_db: List[Budget] = []


def reset() -> None:
    """Clear every store (used by tests and seeders)."""
    accounts_db.clear()
    journal_db.clear()
    invoices_db.clear()
    payments_db.clear()
    expenses_db.clear()
    leases_db.clear()
    budgets_db.clear()


# ============================================================
# CHART OF ACCOUNTS
# ============================================================

CHART_OF_ACCOUNTS: List[Dict[str, Any]] = [
    # ---- Assets ----
    {"code": "1000", "name": "Cash on Hand", "type": "asset", "subtype": "cash", "is_cash": True},
    {"code": "1010", "name": "Bank — Operating", "type": "asset", "subtype": "bank", "is_bank": True},
    {"code": "1020", "name": "Bank — Project Escrow", "type": "asset", "subtype": "bank", "is_bank": True},
    {"code": "1100", "name": "Accounts Receivable", "type": "asset", "subtype": "receivable"},
    {"code": "1200", "name": "Land & Plots", "type": "asset", "subtype": "inventory"},
    {"code": "1210", "name": "Construction Work in Progress", "type": "asset", "subtype": "inventory"},
    {"code": "1300", "name": "Buildings & Improvements", "type": "asset", "subtype": "ppe"},
    {"code": "1310", "name": "Furniture, Fixtures & Equipment", "type": "asset", "subtype": "ppe"},
    {"code": "1350", "name": "Accumulated Depreciation", "type": "asset", "subtype": "contra_asset",
     "normal_side": "credit"},
    {"code": "1400", "name": "Prepaid Expenses", "type": "asset", "subtype": "prepaid"},
    # ---- Liabilities ----
    {"code": "2000", "name": "Accounts Payable", "type": "liability", "subtype": "payable"},
    {"code": "2010", "name": "Security Deposits Held", "type": "liability", "subtype": "deposit"},
    {"code": "2020", "name": "Advance Rent Received", "type": "liability", "subtype": "deposit"},
    {"code": "2050", "name": "Accrued Expenses", "type": "liability", "subtype": "accrued"},
    {"code": "2100", "name": "Sales Tax Payable", "type": "liability", "subtype": "tax"},
    {"code": "2110", "name": "Income Tax Payable", "type": "liability", "subtype": "tax"},
    {"code": "2200", "name": "Long-Term Bank Loan", "type": "liability", "subtype": "loan"},
    {"code": "2210", "name": "Mortgage Payable", "type": "liability", "subtype": "loan"},
    # ---- Equity ----
    {"code": "3000", "name": "Share Capital", "type": "equity", "subtype": "capital"},
    {"code": "3100", "name": "Retained Earnings", "type": "equity", "subtype": "retained"},
    {"code": "3200", "name": "Owner's Drawings", "type": "equity", "subtype": "contra_equity",
     "normal_side": "debit"},
    # ---- Income ----
    {"code": "4000", "name": "Rental Income", "type": "income", "subtype": "operating_income"},
    {"code": "4010", "name": "Sale of Property", "type": "income", "subtype": "operating_income"},
    {"code": "4020", "name": "Service Charges Income", "type": "income", "subtype": "operating_income"},
    {"code": "4030", "name": "Commission Income", "type": "income", "subtype": "operating_income"},
    {"code": "4040", "name": "Parking & Ancillary Income", "type": "income", "subtype": "operating_income"},
    {"code": "4050", "name": "Interest Income", "type": "income", "subtype": "other_income"},
    {"code": "4900", "name": "Other Income", "type": "income", "subtype": "other_income"},
    # ---- Expenses ----
    {"code": "5000", "name": "Salaries & Wages", "type": "expense", "subtype": "payroll"},
    {"code": "5010", "name": "Utilities", "type": "expense", "subtype": "operating_expense"},
    {"code": "5020", "name": "Repairs & Maintenance", "type": "expense", "subtype": "operating_expense"},
    {"code": "5030", "name": "Property Management Fees", "type": "expense", "subtype": "operating_expense"},
    {"code": "5040", "name": "Marketing & Advertising", "type": "expense", "subtype": "operating_expense"},
    {"code": "5050", "name": "Government Rates & Taxes", "type": "expense", "subtype": "operating_expense"},
    {"code": "5060", "name": "Insurance", "type": "expense", "subtype": "operating_expense"},
    {"code": "5070", "name": "Depreciation Expense", "type": "expense", "subtype": "operating_expense"},
    {"code": "5080", "name": "Professional & Legal Fees", "type": "expense", "subtype": "operating_expense"},
    {"code": "5090", "name": "Bank Charges & Interest", "type": "expense", "subtype": "finance_cost"},
    {"code": "5900", "name": "Miscellaneous Expense", "type": "expense", "subtype": "operating_expense"},
]

# convenience aliases used across the module
ACC_CASH = "1000"
ACC_BANK = "1010"
ACC_ESCROW = "1020"
ACC_AR = "1100"
ACC_LAND = "1200"
ACC_PAYABLE = "2000"
ACC_DEPOSITS = "2010"
ACC_SALES_TAX = "2100"
ACC_RETAINED = "3100"
ACC_RENT = "4000"


def seed_chart_of_accounts() -> int:
    """Install the standard chart of accounts (idempotent). Returns accounts created."""
    created = 0
    for row in CHART_OF_ACCOUNTS:
        if row["code"] in accounts_db:
            continue
        create_account(**row)
        created += 1
    return created


def create_account(
    code: str,
    name: str,
    type: str = "asset",                      # noqa: A002 - matches the public API
    subtype: Optional[str] = None,
    parent_code: Optional[str] = None,
    normal_side: Optional[str] = None,
    description: Optional[str] = None,
    is_bank: bool = False,
    is_cash: bool = False,
    opening_balance: float = 0.0,
) -> Dict[str, Any]:
    """Create a ledger account. ``code`` is the primary key."""
    code = str(code).strip()
    if not code:
        return {"error": "Account code is required"}
    if code in accounts_db:
        return {"error": f"Account {code} already exists"}
    if type not in ACCOUNT_TYPES:
        return {"error": f"type must be one of {ACCOUNT_TYPES}"}
    if parent_code and parent_code not in accounts_db:
        return {"error": f"Unknown parent account: {parent_code}"}
    acct = Account(
        code=code, name=name, type=type, subtype=subtype, parent_code=parent_code,
        normal_side=normal_side or _NORMAL_SIDE[type], description=description,
        is_bank=is_bank, is_cash=is_cash, currency=ACCOUNTING_CONFIG["currency"],
        opening_balance=_round(opening_balance),
    )
    accounts_db[code] = acct
    return _m(acct)


def update_account(code: str, **fields: Any) -> Dict[str, Any]:
    acct = accounts_db.get(str(code))
    if not acct:
        return {"error": f"Account not found: {code}"}
    for key, value in fields.items():
        if value is None or not hasattr(acct, key):
            continue
        if key == "type" and value not in ACCOUNT_TYPES:
            return {"error": f"type must be one of {ACCOUNT_TYPES}"}
        if key == "normal_side" and value not in ("debit", "credit"):
            return {"error": "normal_side must be debit or credit"}
        setattr(acct, key, value)
    return _m(acct)


def get_account(code: str) -> Optional[Account]:
    return accounts_db.get(str(code))


def list_accounts(type: Optional[str] = None, subtype: Optional[str] = None,  # noqa: A002
                  active_only: bool = False) -> List[Dict[str, Any]]:
    rows = sorted(accounts_db.values(), key=lambda a: a.code)
    if type:
        rows = [a for a in rows if a.type == type]
    if subtype:
        rows = [a for a in rows if a.subtype == subtype]
    if active_only:
        rows = [a for a in rows if a.active]
    return [account_with_balance(a) for a in rows]


def _account_movement(code: str, upto: Optional[date] = None) -> Tuple[float, float]:
    """Total (debit, credit) posted to an account, up to and including ``upto``."""
    debit = credit = 0.0
    for entry in journal_db:
        if entry.status != "posted":
            continue
        if upto and entry.date > upto:
            continue
        for line in entry.lines:
            if line.account == code:
                debit += line.debit or 0.0
                credit += line.credit or 0.0
    return _round(debit), _round(credit)


def account_balance(code: str, as_of: Any = None) -> Dict[str, Any]:
    """Signed balance on the account's normal side, plus the raw debit/credit totals."""
    acct = accounts_db.get(str(code))
    if not acct:
        return {"error": f"Account not found: {code}"}
    as_of_date = _as_date(as_of)
    debit, credit = _account_movement(acct.code, as_of_date)
    if acct.normal_side == "debit":
        balance = acct.opening_balance + debit - credit
    else:
        balance = acct.opening_balance + credit - debit
    return {
        "code": acct.code, "name": acct.name, "type": acct.type, "subtype": acct.subtype,
        "normal_side": acct.normal_side,
        "opening_balance": _round(acct.opening_balance),
        "debit_total": debit, "credit_total": credit,
        "raw_balance": _round(debit - credit),
        "balance": _round(balance),
    }


def account_with_balance(acct: Account) -> Dict[str, Any]:
    data = _m(acct)
    data["balance"] = account_balance(acct.code)["balance"]
    return data


# ============================================================
# JOURNAL  (double entry)
# ============================================================


def _next_entry_no() -> int:
    # max + 1, not count + 1: numbers stay unique after an entry is removed
    return max((getattr(e, "entry_no", 0) or 0 for e in journal_db), default=0) + 1


def post_journal_entry(
    lines: List[Dict[str, Any]],
    date: Any = None,                          # noqa: A002 - public API name
    memo: Optional[str] = None,
    reference: Optional[str] = None,
    source: str = "manual",
    source_id: Optional[str] = None,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Post a balanced journal entry.

    ``lines`` is a list of ``{account, debit, credit, description?, property_id?,
    scheme_id?, city_id?, cost_center?}``. Debits must equal credits.
    """
    if not lines:
        return {"error": "At least one journal line is required"}
    parsed: List[JournalLine] = []
    total_debit = total_credit = 0.0
    for raw in lines:
        acct_code = str(raw.get("account", "")).strip()
        if acct_code not in accounts_db:
            return {"error": f"Unknown account: {acct_code or '(blank)'}"}
        debit = _round(raw.get("debit", 0.0))
        credit = _round(raw.get("credit", 0.0))
        if debit < 0 or credit < 0:
            return {"error": "Debit and credit amounts cannot be negative"}
        if debit and credit:
            return {"error": "A line cannot have both a debit and a credit"}
        if not debit and not credit:
            continue
        parsed.append(
            JournalLine(
                account=acct_code, debit=debit, credit=credit,
                description=raw.get("description"),
                property_id=raw.get("property_id"), scheme_id=raw.get("scheme_id"),
                city_id=raw.get("city_id"), cost_center=raw.get("cost_center"),
            )
        )
        total_debit += debit
        total_credit += credit
    if not parsed:
        return {"error": "No non-zero journal lines supplied"}
    if abs(total_debit - total_credit) > 0.009:
        return {
            "error": "Journal entry is not balanced",
            "total_debit": _round(total_debit),
            "total_credit": _round(total_credit),
            "difference": _round(total_debit - total_credit),
        }
    entry = JournalEntry(
        entry_no=_next_entry_no(), date=_as_date(date, _today()), reference=reference,
        memo=memo, source=source, source_id=source_id, lines=parsed, created_by=created_by,
    )
    journal_db.append(entry)
    return _m(entry)


def get_journal_entry(entry_id: str) -> Dict[str, Any]:
    entry = next((e for e in journal_db if e.id == entry_id), None)
    if not entry:
        return {"error": f"Journal entry not found: {entry_id}"}
    data = _m(entry)
    data["total_debit"], data["total_credit"] = entry.totals()
    return data


def list_journal_entries(
    from_date: Any = None,
    to_date: Any = None,
    source: Optional[str] = None,
    account: Optional[str] = None,
    property_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    start, end = _as_date(from_date), _as_date(to_date)
    rows = []
    for entry in journal_db:
        if start and entry.date < start:
            continue
        if end and entry.date > end:
            continue
        if source and entry.source != source:
            continue
        if status and entry.status != status:
            continue
        if account and not any(l.account == account for l in entry.lines):
            continue
        if property_id and not any(l.property_id == property_id for l in entry.lines):
            continue
        rows.append(entry)
    rows.sort(key=lambda e: (e.date, e.entry_no), reverse=True)
    out = []
    for entry in rows[:limit]:
        data = _m(entry)
        data["total_debit"], data["total_credit"] = entry.totals()
        out.append(data)
    return out


def void_journal_entry(entry_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
    entry = next((e for e in journal_db if e.id == entry_id), None)
    if not entry:
        return {"error": f"Journal entry not found: {entry_id}"}
    if entry.status == "void":
        return {"error": "Journal entry is already void"}
    entry.status = "void"
    entry.void_reason = reason
    return _m(entry)


# ============================================================
# STATEMENTS
# ============================================================


def trial_balance(as_of: Any = None) -> Dict[str, Any]:
    """Debit/credit columns per account plus totals (must agree)."""
    as_of_date = _as_date(as_of)
    rows, total_debit, total_credit = [], 0.0, 0.0
    for acct in sorted(accounts_db.values(), key=lambda a: a.code):
        debit, credit = _account_movement(acct.code, as_of_date)
        # the opening balance sits on the account's normal side
        opening_debit = acct.opening_balance if acct.normal_side == "debit" else 0.0
        opening_credit = acct.opening_balance if acct.normal_side == "credit" else 0.0
        net = (opening_debit + debit) - (opening_credit + credit)
        row_debit = _round(net) if net > 0 else 0.0
        row_credit = _round(-net) if net < 0 else 0.0
        if not row_debit and not row_credit:
            continue
        rows.append({"code": acct.code, "name": acct.name, "type": acct.type,
                     "debit": row_debit, "credit": row_credit})
        total_debit += row_debit
        total_credit += row_credit
    return {
        "as_of": _iso(as_of_date) or _iso(_today()),
        "rows": rows,
        "total_debit": _round(total_debit),
        "total_credit": _round(total_credit),
        "balanced": abs(total_debit - total_credit) < 0.01,
    }


def general_ledger(account_code: str, from_date: Any = None, to_date: Any = None) -> Dict[str, Any]:
    """Chronological postings for one account with a running balance."""
    acct = accounts_db.get(str(account_code))
    if not acct:
        return {"error": f"Account not found: {account_code}"}
    start, end = _as_date(from_date), _as_date(to_date)
    postings = []
    for entry in sorted(journal_db, key=lambda e: (e.date, e.entry_no)):
        if entry.status != "posted":
            continue
        if start and entry.date < start:
            continue
        if end and entry.date > end:
            continue
        for line in entry.lines:
            if line.account != acct.code:
                continue
            postings.append({
                "entry_id": entry.id, "entry_no": entry.entry_no, "date": _iso(entry.date),
                "reference": entry.reference, "memo": entry.memo, "source": entry.source,
                "debit": _round(line.debit), "credit": _round(line.credit),
                "description": line.description,
            })
    running = acct.opening_balance
    for row in postings:
        delta = row["debit"] - row["credit"]
        running += delta if acct.normal_side == "debit" else -delta
        row["balance"] = _round(running)
    return {
        "account": acct.code, "name": acct.name, "type": acct.type,
        "opening_balance": _round(acct.opening_balance),
        "closing_balance": _round(running),
        "postings": postings,
        "count": len(postings),
    }


def _filtered_lines(from_date: Any = None, to_date: Any = None, **scope: Any) -> List[JournalLine]:
    start, end = _as_date(from_date), _as_date(to_date)
    out = []
    for entry in journal_db:
        if entry.status != "posted":
            continue
        if start and entry.date < start:
            continue
        if end and entry.date > end:
            continue
        for line in entry.lines:
            if scope.get("property_id") and line.property_id != scope["property_id"]:
                continue
            if scope.get("scheme_id") and line.scheme_id != scope["scheme_id"]:
                continue
            if scope.get("city_id") and line.city_id != scope["city_id"]:
                continue
            out.append(line)
    return out


def _balance_by_type(acct_type: str, from_date: Any = None, to_date: Any = None, **scope: Any) -> List[Dict[str, Any]]:
    lines = _filtered_lines(from_date, to_date, **scope)
    totals: Dict[str, Tuple[float, float]] = {}
    for line in lines:
        acct = accounts_db.get(line.account)
        if not acct or acct.type != acct_type:
            continue
        d, c = totals.get(line.account, (0.0, 0.0))
        totals[line.account] = (d + line.debit, c + line.credit)
    rows = []
    for code in sorted(totals):
        acct = accounts_db[code]
        d, c = totals[code]
        amount = d - c if acct.normal_side == "debit" else c - d
        rows.append({"code": code, "name": acct.name, "subtype": acct.subtype,
                     "amount": _round(amount), "debit": _round(d), "credit": _round(c)})
    return rows


def profit_and_loss(
    from_date: Any = None,
    to_date: Any = None,
    property_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    city_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Revenue − expenses for a period, optionally scoped to a property/scheme/city."""
    scope = {"property_id": property_id, "scheme_id": scheme_id, "city_id": city_id}
    income = _balance_by_type("income", from_date, to_date, **scope)
    expenses = _balance_by_type("expense", from_date, to_date, **scope)
    total_income = _round(sum(r["amount"] for r in income))
    total_expenses = _round(sum(r["amount"] for r in expenses))
    net = _round(total_income - total_expenses)
    return {
        "period": {"from": _iso(_as_date(from_date)), "to": _iso(_as_date(to_date)) or _iso(_today())},
        "income": income,
        "expenses": expenses,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_profit": net,
        "net_margin": _round(net / total_income, 4) if total_income else 0.0,
        "scope": {k: v for k, v in scope.items() if v},
    }


def balance_sheet(as_of: Any = None) -> Dict[str, Any]:
    """Assets, liabilities and equity at a point in time (includes retained P&L)."""
    as_of_date = _as_date(as_of) or _today()
    assets = []
    liabilities = []
    equity = []
    for acct in sorted(accounts_db.values(), key=lambda a: a.code):
        bal = account_balance(acct.code, as_of_date)["balance"]
        if not bal:
            continue
        row = {"code": acct.code, "name": acct.name, "subtype": acct.subtype, "amount": bal}
        if acct.type == "asset":
            row["amount"] = bal if acct.normal_side == "debit" else -bal
            assets.append(row)
        elif acct.type == "liability":
            row["amount"] = bal if acct.normal_side == "credit" else -bal
            liabilities.append(row)
        elif acct.type == "equity":
            row["amount"] = bal if acct.normal_side == "credit" else -bal
            equity.append(row)
    pl = profit_and_loss(to_date=as_of_date)
    equity.append({"code": "3900", "name": "Current Period Earnings", "subtype": "retained",
                   "amount": pl["net_profit"]})
    total_assets = _round(sum(r["amount"] for r in assets))
    total_liabilities = _round(sum(r["amount"] for r in liabilities))
    total_equity = _round(sum(r["amount"] for r in equity))
    return {
        "as_of": _iso(as_of_date),
        "assets": assets, "liabilities": liabilities, "equity": equity,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "total_liabilities_and_equity": _round(total_liabilities + total_equity),
        "balanced": abs(total_assets - (total_liabilities + total_equity)) < 0.01,
    }


def cash_flow_statement(from_date: Any = None, to_date: Any = None) -> Dict[str, Any]:
    """Simplified indirect cash-flow, classifying each cash movement by its counter-account."""
    start, end = _as_date(from_date), _as_date(to_date)
    buckets = {"operating": 0.0, "investing": 0.0, "financing": 0.0}
    detail: Dict[str, List[Dict[str, Any]]] = {k: [] for k in buckets}
    opening = 0.0
    for acct in accounts_db.values():
        if acct.is_bank or acct.is_cash:
            movement = _account_movement(acct.code, start - timedelta(days=1) if start else None) if start else (0, 0)
            opening += acct.opening_balance + (movement[0] - movement[1])

    for entry in journal_db:
        if entry.status != "posted":
            continue
        if start and entry.date < start:
            continue
        if end and entry.date > end:
            continue
        cash_lines = [l for l in entry.lines if accounts_db.get(l.account) and
                      (accounts_db[l.account].is_bank or accounts_db[l.account].is_cash)]
        if not cash_lines:
            continue
        other = [l for l in entry.lines if l not in cash_lines]
        net_cash = _round(sum(l.debit - l.credit for l in cash_lines))
        if not net_cash:
            continue
        kind = "operating"
        for line in other:
            acct = accounts_db.get(line.account)
            if not acct:
                continue
            if acct.subtype in ("ppe", "inventory", "prepaid"):
                kind = "investing"
                break
            if acct.type in ("equity",) or acct.subtype in ("loan",):
                kind = "financing"
                break
        buckets[kind] = _round(buckets[kind] + net_cash)
        detail[kind].append({
            "date": _iso(entry.date), "entry_no": entry.entry_no, "memo": entry.memo,
            "source": entry.source, "amount": net_cash,
        })
    closing = _round(opening + sum(buckets.values()))
    return {
        "period": {"from": _iso(start), "to": _iso(end) or _iso(_today())},
        "opening_cash": _round(opening),
        "operating": buckets["operating"],
        "investing": buckets["investing"],
        "financing": buckets["financing"],
        "net_change": _round(sum(buckets.values())),
        "closing_cash": closing,
        "detail": detail,
    }


def financial_ratios(as_of: Any = None) -> Dict[str, Any]:
    """Liquidity, leverage and profitability ratios from the statements."""
    bs = balance_sheet(as_of)
    pl = profit_and_loss(to_date=as_of)
    current_assets = _round(sum(r["amount"] for r in bs["assets"]
                               if r["subtype"] in ("cash", "bank", "receivable", "inventory", "prepaid")))
    current_liabilities = _round(sum(r["amount"] for r in bs["liabilities"]
                                     if r["subtype"] in ("payable", "accrued", "deposit", "tax")))
    total_debt = _round(sum(r["amount"] for r in bs["liabilities"] if r["subtype"] == "loan"))
    equity = bs["total_equity"]
    return {
        "as_of": bs["as_of"],
        "current_ratio": _round(current_assets / current_liabilities, 3) if current_liabilities else None,
        "quick_ratio": _round((current_assets - sum(r["amount"] for r in bs["assets"]
                                                   if r["subtype"] == "inventory")) / current_liabilities, 3)
        if current_liabilities else None,
        "debt_to_equity": _round(total_debt / equity, 3) if equity else None,
        "net_profit_margin": pl["net_margin"],
        "return_on_equity": _round(pl["net_profit"] / equity, 4) if equity else None,
        "return_on_assets": _round(pl["net_profit"] / bs["total_assets"], 4) if bs["total_assets"] else None,
        "working_capital": _round(current_assets - current_liabilities),
        "current_assets": current_assets,
        "current_liabilities": current_liabilities,
        "total_debt": total_debt,
    }


def accounting_dashboard(as_of: Any = None) -> Dict[str, Any]:
    """One-shot snapshot for a finance dashboard."""
    as_of_date = _as_of_date(as_of)
    bs = balance_sheet(as_of_date)
    pl = profit_and_loss(to_date=as_of_date)
    ar = receivable_total()
    ap = payable_total()
    cash = _round(sum(r["amount"] for r in bs["assets"] if r["subtype"] in ("cash", "bank")))
    overdue = [i for i in invoices_db if i.status not in ("paid", "void", "draft") and i.balance > 0
               and i.due_date and i.due_date < as_of_date]
    return {
        "as_of": _iso(as_of_date),
        "total_assets": bs["total_assets"],
        "total_liabilities": bs["total_liabilities"],
        "total_equity": bs["total_equity"],
        "cash_and_bank": cash,
        "accounts_receivable": ar,
        "accounts_payable": ap,
        "revenue": pl["total_income"],
        "expenses": pl["total_expenses"],
        "net_profit": pl["net_profit"],
        "overdue_invoices": len(overdue),
        "overdue_amount": _round(sum(i.balance for i in overdue)),
        "journal_entries": len([e for e in journal_db if e.status == "posted"]),
        "accounts": len(accounts_db),
        "ratios": financial_ratios(as_of_date),
    }


def _as_of_date(value: Any) -> date:
    return _as_date(value, _today())


# ============================================================
# BILLING: INVOICES, PAYMENTS, EXPENSES
# ============================================================


def _next_invoice_number(invoice_type: str) -> str:
    prefix = "INV" if invoice_type == "receivable" else "BILL"
    seq = len([i for i in invoices_db if i.invoice_type == invoice_type]) + 1
    return f"{prefix}-{date.today().year}-{seq:05d}"


def create_invoice(
    counterparty: str,
    lines: List[Dict[str, Any]],
    invoice_type: str = "receivable",
    issue_date: Any = None,
    due_date: Any = None,
    tax_rate: Optional[float] = None,
    property_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    city_id: Optional[str] = None,
    lease_id: Optional[str] = None,
    counterparty_id: Optional[str] = None,
    notes: Optional[str] = None,
    auto_post: bool = False,
) -> Dict[str, Any]:
    """Create an invoice. ``lines`` is ``[{description, quantity?, unit_price?, amount?, tax_rate?}]``."""
    if invoice_type not in INVOICE_TYPES:
        return {"error": f"invoice_type must be one of {INVOICE_TYPES}"}
    if not counterparty:
        return {"error": "counterparty is required"}
    if not lines:
        return {"error": "At least one invoice line is required"}
    parsed: List[InvoiceLine] = []
    subtotal = tax_total = 0.0
    rate = ACCOUNTING_CONFIG["default_sales_tax_rate"] if tax_rate is None else float(tax_rate)
    for raw in lines:
        qty = float(raw.get("quantity", 1.0) or 1.0)
        unit = float(raw.get("unit_price", 0.0) or 0.0)
        amount = float(raw.get("amount", qty * unit) or 0.0)
        line_tax_rate = float(raw.get("tax_rate", rate) or 0.0)
        parsed.append(InvoiceLine(description=str(raw.get("description", "Item")), quantity=qty,
                                  unit_price=_round(unit), amount=_round(amount), tax_rate=line_tax_rate))
        subtotal += amount
        tax_total += amount * line_tax_rate
    issued = _as_date(issue_date, _today())
    due = _as_date(due_date, issued + timedelta(days=30))
    subtotal = _round(subtotal)
    tax_total = _round(tax_total)
    total = _round(subtotal + tax_total)
    invoice = Invoice(
        number=_next_invoice_number(invoice_type), invoice_type=invoice_type, counterparty=counterparty,
        counterparty_id=counterparty_id, issue_date=issued, due_date=due, lines=parsed,
        subtotal=subtotal, tax_rate=rate, tax_amount=tax_total, total=total, balance=total,
        status="draft", property_id=property_id, scheme_id=scheme_id, city_id=city_id,
        lease_id=lease_id, notes=notes,
    )
    invoices_db.append(invoice)
    if auto_post:
        posted = post_invoice(invoice.id)
        if "error" in posted:
            return posted
    return _invoice_view(invoice)


def _invoice_view(invoice: Invoice) -> Dict[str, Any]:
    data = _m(invoice)
    today = _today()
    data["days_overdue"] = max(0, (today - invoice.due_date).days) if (
        invoice.due_date and invoice.balance > 0 and invoice.status not in ("paid", "void")) else 0
    data["is_overdue"] = bool(data["days_overdue"])
    return data


def get_invoice(invoice_id: str) -> Dict[str, Any]:
    inv = next((i for i in invoices_db if i.id == invoice_id or i.number == invoice_id), None)
    if not inv:
        return {"error": f"Invoice not found: {invoice_id}"}
    view = _invoice_view(inv)
    view["payments"] = [_m(p) for p in payments_db if p.invoice_id == inv.id]
    return view


def list_invoices(
    invoice_type: Optional[str] = None,
    status: Optional[str] = None,
    counterparty: Optional[str] = None,
    property_id: Optional[str] = None,
    overdue_only: bool = False,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    rows = list(invoices_db)
    if invoice_type:
        rows = [i for i in rows if i.invoice_type == invoice_type]
    if status:
        rows = [i for i in rows if i.status == status]
    if counterparty:
        needle = counterparty.lower()
        rows = [i for i in rows if needle in (i.counterparty or "").lower()]
    if property_id:
        rows = [i for i in rows if i.property_id == property_id]
    if overdue_only:
        today = _today()
        rows = [i for i in rows if i.balance > 0 and i.due_date and i.due_date < today
                and i.status not in ("paid", "void")]
    rows.sort(key=lambda i: i.issue_date, reverse=True)
    return [_invoice_view(i) for i in rows[:limit]]


def post_invoice(invoice_id: str) -> Dict[str, Any]:
    """Post an invoice to the ledger (AR/AP + income/expense + tax)."""
    inv = next((i for i in invoices_db if i.id == invoice_id or i.number == invoice_id), None)
    if not inv:
        return {"error": f"Invoice not found: {invoice_id}"}
    if inv.journal_entry_id:
        return {"error": "Invoice is already posted", "journal_entry_id": inv.journal_entry_id}
    scope = {"property_id": inv.property_id, "scheme_id": inv.scheme_id, "city_id": inv.city_id}
    if inv.invoice_type == "receivable":
        lines = [{"account": ACC_AR, "debit": inv.total, "description": inv.number, **scope},
                 {"account": ACC_RENT, "credit": inv.subtotal, "description": inv.number, **scope}]
        if inv.tax_amount:
            lines.append({"account": ACC_SALES_TAX, "credit": inv.tax_amount,
                          "description": f"{inv.number} tax", **scope})
    else:
        lines = [{"account": "5900", "debit": inv.subtotal, "description": inv.number, **scope},
                 {"account": ACC_PAYABLE, "credit": inv.total, "description": inv.number, **scope}]
        if inv.tax_amount:
            lines.append({"account": "1400", "debit": inv.tax_amount,
                          "description": f"{inv.number} input tax", **scope})
    entry = post_journal_entry(lines, date=inv.issue_date, memo=f"{inv.invoice_type} invoice {inv.number}",
                               reference=inv.number, source="invoice", source_id=inv.id)
    if "error" in entry:
        return entry
    inv.journal_entry_id = entry["id"]
    inv.status = "sent"
    inv.updated_at = datetime.now()
    return _invoice_view(inv)


def record_payment(
    amount: float,
    invoice_id: Optional[str] = None,
    direction: str = "in",
    method: str = "bank_transfer",
    account_code: str = ACC_BANK,
    date: Any = None,                          # noqa: A002
    counterparty: Optional[str] = None,
    reference: Optional[str] = None,
    notes: Optional[str] = None,
    auto_post: bool = True,
) -> Dict[str, Any]:
    """Record a receipt (``in``) or disbursement (``out``), allocating it to an invoice."""
    amount = _round(amount)
    if amount <= 0:
        return {"error": "Payment amount must be greater than zero"}
    if direction not in ("in", "out"):
        return {"error": "direction must be 'in' or 'out'"}
    if method not in PAYMENT_METHODS:
        return {"error": f"method must be one of {PAYMENT_METHODS}"}
    acct = accounts_db.get(account_code)
    if not acct or not (acct.is_bank or acct.is_cash):
        return {"error": f"{account_code} is not a cash/bank account"}

    inv = None
    if invoice_id:
        inv = next((i for i in invoices_db if i.id == invoice_id or i.number == invoice_id), None)
        if not inv:
            return {"error": f"Invoice not found: {invoice_id}"}
        if inv.status == "void":
            return {"error": "Cannot pay a void invoice"}
        if amount > inv.balance + 0.009:
            return {"error": "Payment exceeds the invoice balance",
                    "balance": inv.balance, "attempted": amount}
        direction = "in" if inv.invoice_type == "receivable" else "out"
        counterparty = counterparty or inv.counterparty

    paid_on = _as_date(date, _today())
    payment = Payment(date=paid_on, amount=amount, direction=direction, method=method,
                      account_code=account_code, invoice_id=inv.id if inv else None,
                      counterparty=counterparty, reference=reference, notes=notes)
    payments_db.append(payment)

    if auto_post:
        if direction == "in":
            lines = [{"account": account_code, "debit": amount, "description": f"Receipt {reference or ''}".strip()}]
            lines.append({"account": ACC_AR if inv else ACC_RENT, "credit": amount,
                          "description": counterparty or "Receipt"})
        else:
            lines = [{"account": ACC_PAYABLE if inv else "5900", "debit": amount,
                      "description": counterparty or "Payment"}]
            lines.append({"account": account_code, "credit": amount,
                          "description": f"Payment {reference or ''}".strip()})
        entry = post_journal_entry(lines, date=paid_on,
                                   memo=f"{'Receipt' if direction == 'in' else 'Payment'} — {counterparty or ''}".strip(),
                                   reference=reference, source="payment", source_id=payment.id)
        if "error" in entry:
            return entry
        payment.journal_entry_id = entry["id"]

    if inv:
        inv.amount_paid = _round(inv.amount_paid + amount)
        inv.balance = _round(inv.total - inv.amount_paid)
        inv.status = "paid" if inv.balance <= 0.009 else "part_paid"
        inv.updated_at = datetime.now()
    return {"payment": _m(payment), "invoice": _invoice_view(inv) if inv else None}


def create_expense(
    amount: float,
    account_code: str = "5900",
    category: str = "misc",
    date: Any = None,                          # noqa: A002
    vendor: Optional[str] = None,
    description: Optional[str] = None,
    tax_amount: float = 0.0,
    paid: bool = True,
    property_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    city_id: Optional[str] = None,
    payment_account: str = ACC_BANK,
) -> Dict[str, Any]:
    """Capture an expense; posts it straight to the ledger when ``paid``."""
    amount = _round(amount)
    if amount <= 0:
        return {"error": "Expense amount must be greater than zero"}
    acct = accounts_db.get(account_code)
    if not acct or acct.type != "expense":
        return {"error": f"{account_code} is not an expense account"}
    spent_on = _as_date(date, _today())
    expense = Expense(date=spent_on, category=category, account_code=account_code, vendor=vendor,
                      description=description, amount=amount, tax_amount=_round(tax_amount),
                      total=_round(amount + tax_amount), paid=paid,
                      property_id=property_id, scheme_id=scheme_id, city_id=city_id)
    expenses_db.append(expense)
    scope = {"property_id": property_id, "scheme_id": scheme_id, "city_id": city_id}
    credit_account = payment_account if paid else ACC_PAYABLE
    lines = [{"account": account_code, "debit": amount,
              "description": description or category, **scope}]
    if tax_amount:
        lines.append({"account": "1400", "debit": _round(tax_amount), "description": "Input tax", **scope})
    lines.append({"account": credit_account, "credit": expense.total, "description": vendor or category})
    entry = post_journal_entry(lines, date=spent_on, memo=f"Expense — {category}",
                               source="expense", source_id=expense.id)
    if "error" in entry:
        return entry
    expense.journal_entry_id = entry["id"]
    return _m(expense)


def receivable_total(overdue_only: bool = False) -> float:
    today = _today()
    rows = [i for i in invoices_db if i.invoice_type == "receivable" and i.balance > 0
            and i.status not in ("void", "draft")]
    if overdue_only:
        rows = [i for i in rows if i.due_date and i.due_date < today]
    return _round(sum(i.balance for i in rows))


def payable_total(overdue_only: bool = False) -> float:
    today = _today()
    rows = [i for i in invoices_db if i.invoice_type == "payable" and i.balance > 0
            and i.status not in ("void", "draft")]
    if overdue_only:
        rows = [i for i in rows if i.due_date and i.due_date < today]
    return _round(sum(i.balance for i in rows))


def invoice_aging(as_of: Any = None, invoice_type: Optional[str] = None) -> Dict[str, Any]:
    """Ageing buckets for open invoices (current, 1-30, 31-60, 61-90, 90+)."""
    as_of_date = _as_of_date(as_of)
    buckets = {"current": 0.0, "1-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    rows = []
    for inv in invoices_db:
        if inv.balance <= 0 or inv.status in ("void", "draft"):
            continue
        if invoice_type and inv.invoice_type != invoice_type:
            continue
        days = (as_of_date - inv.due_date).days if inv.due_date else 0
        key = "current" if days <= 0 else ("1-30" if days <= 30 else ("31-60" if days <= 60
                                      else ("61-90" if days <= 90 else "90+")))
        buckets[key] = _round(buckets[key] + inv.balance)
        rows.append({"number": inv.number, "counterparty": inv.counterparty, "type": inv.invoice_type,
                     "due_date": _iso(inv.due_date), "days_overdue": max(0, days),
                     "balance": inv.balance, "bucket": key})
    rows.sort(key=lambda r: r["days_overdue"], reverse=True)
    return {"as_of": _iso(as_of_date), "buckets": buckets, "total": _round(sum(buckets.values())),
            "invoices": rows}


# ============================================================
# LEASES + RENT ROLL
# ============================================================


def create_lease(
    tenant: str,
    rent_amount: float,
    property_id: Optional[str] = None,
    unit_label: Optional[str] = None,
    start_date: Any = None,
    end_date: Any = None,
    billing_cycle: str = "monthly",
    escalation_rate: Optional[float] = None,
    security_deposit: float = 0.0,
    tenant_id: Optional[str] = None,
    city_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    status: str = "active",
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    if not tenant:
        return {"error": "tenant is required"}
    if billing_cycle not in BILLING_CYCLES:
        return {"error": f"billing_cycle must be one of {list(BILLING_CYCLES)}"}
    if rent_amount <= 0:
        return {"error": "rent_amount must be greater than zero"}
    start = _as_date(start_date, _today())
    lease = Lease(
        tenant=tenant, tenant_id=tenant_id, property_id=property_id, unit_label=unit_label,
        start_date=start, end_date=_as_date(end_date, start + timedelta(days=365)),
        rent_amount=_round(rent_amount), billing_cycle=billing_cycle,
        escalation_rate=escalation_rate if escalation_rate is not None
        else ACCOUNTING_CONFIG["default_rent_escalation"],
        security_deposit=_round(security_deposit), status=status,
        city_id=city_id, scheme_id=scheme_id, notes=notes,
    )
    leases_db.append(lease)
    return _m(lease)


def list_leases(status: Optional[str] = None, property_id: Optional[str] = None,
                scheme_id: Optional[str] = None, city_id: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = list(leases_db)
    if status:
        rows = [l for l in rows if l.status == status]
    if property_id:
        rows = [l for l in rows if l.property_id == property_id]
    if scheme_id:
        rows = [l for l in rows if l.scheme_id == scheme_id]
    if city_id:
        rows = [l for l in rows if l.city_id == city_id]
    rows.sort(key=lambda l: l.rent_amount, reverse=True)
    return [_lease_view(l) for l in rows]


def _lease_view(lease: Lease) -> Dict[str, Any]:
    data = _m(lease)
    per_month = {"monthly": 1, "quarterly": 3, "semi_annual": 6, "annual": 12}[lease.billing_cycle]
    data["monthly_rent"] = _round(lease.rent_amount / per_month)
    data["annual_rent"] = _round(lease.rent_amount / per_month * 12)
    return data


def rent_roll(as_of: Any = None) -> Dict[str, Any]:
    """Active leases with contracted monthly/annual rent and deposits held."""
    as_of_date = _as_of_date(as_of)
    active = [l for l in leases_db if l.status == "active" and l.start_date <= as_of_date
              and (l.end_date is None or l.end_date >= as_of_date)]
    rows = [_lease_view(l) for l in active]
    monthly = _round(sum(r["monthly_rent"] for r in rows))
    return {
        "as_of": _iso(as_of_date),
        "leases": len(rows),
        "monthly_rent": monthly,
        "annual_rent": _round(monthly * 12),
        "security_deposits": _round(sum(l.security_deposit for l in active)),
        "by_cycle": {c: len([l for l in active if l.billing_cycle == c]) for c in BILLING_CYCLES},
        "tenants": rows,
    }


def generate_rent_invoices(period_month: Optional[int] = None, year: Optional[int] = None,
                           as_of: Any = None, auto_post: bool = True) -> Dict[str, Any]:
    """Raise this month's rent invoices for every due lease (idempotent per month)."""
    as_of_date = _as_of_date(as_of)
    month = period_month or as_of_date.month
    yr = year or as_of_date.year
    cycle_months = {"monthly": 1, "quarterly": 3, "semi_annual": 6, "annual": 12}
    created, skipped = [], []
    for lease in leases_db:
        if lease.status != "active":
            continue
        step = cycle_months[lease.billing_cycle]
        months_since = (yr - lease.start_date.year) * 12 + (month - lease.start_date.month)
        if months_since < 0 or months_since % step != 0:
            skipped.append({"lease_id": lease.id, "reason": "not in this billing cycle"})
            continue
        period_key = f"{lease.id}:{yr}-{month:02d}"
        if any(i.notes and period_key in i.notes for i in invoices_db):
            skipped.append({"lease_id": lease.id, "reason": "already invoiced"})
            continue
        years_elapsed = months_since // 12
        rent = _round(lease.rent_amount * (1 + lease.escalation_rate) ** years_elapsed)
        inv = create_invoice(
            counterparty=lease.tenant, counterparty_id=lease.tenant_id,
            invoice_type="receivable",
            lines=[{"description": f"Rent {yr}-{month:02d} — {lease.unit_label or lease.property_id or 'unit'}",
                    "quantity": 1, "unit_price": rent, "tax_rate": 0.0}],
            issue_date=date(yr, month, 1),
            due_date=date(yr, month, 10),
            tax_rate=0.0, property_id=lease.property_id, scheme_id=lease.scheme_id,
            city_id=lease.city_id, lease_id=lease.id,
            notes=f"{period_key} rent run", auto_post=auto_post,
        )
        if "error" in inv:
            return inv
        created.append({"invoice": inv["number"], "tenant": lease.tenant, "amount": rent})
    return {"period": f"{yr}-{month:02d}", "created": created, "skipped": skipped,
            "count": len(created), "total": _round(sum(c["amount"] for c in created))}


# ============================================================
# BUDGETS
# ============================================================


def create_budget(name: str, lines: Dict[str, float], fiscal_year: str = "",
                  scope: str = "portfolio", scope_id: Optional[str] = None,
                  notes: Optional[str] = None) -> Dict[str, Any]:
    if not name:
        return {"error": "Budget name is required"}
    unknown = [c for c in lines if c not in accounts_db]
    if unknown:
        return {"error": f"Unknown accounts in budget: {unknown}"}
    budget = Budget(name=name, fiscal_year=fiscal_year or str(_today().year), scope=scope,
                    scope_id=scope_id, lines={k: _round(v) for k, v in lines.items()}, notes=notes)
    budgets_db.append(budget)
    return _m(budget)


def list_budgets() -> List[Dict[str, Any]]:
    return [_m(b) for b in budgets_db]


def budget_variance(budget_id: str) -> Dict[str, Any]:
    budget = next((b for b in budgets_db if b.id == budget_id or b.name == budget_id), None)
    if not budget:
        return {"error": f"Budget not found: {budget_id}"}
    scope = {"city_id": budget.scope_id} if budget.scope == "city" else (
        {"scheme_id": budget.scope_id} if budget.scope == "scheme" else (
            {"property_id": budget.scope_id} if budget.scope == "property" else {}))
    rows, total_budget, total_actual = [], 0.0, 0.0
    for code, budgeted in sorted(budget.lines.items()):
        actual = _round(sum(r["amount"] for r in _balance_by_type(accounts_db[code].type, **scope)
                            if r["code"] == code))
        variance = _round(budgeted - actual)
        rows.append({"code": code, "name": accounts_db[code].name, "budget": _round(budgeted),
                     "actual": actual, "variance": variance,
                     "variance_pct": _round(variance / budgeted, 4) if budgeted else None,
                     "favorable": variance > 0 if accounts_db[code].type == "expense" else variance < 0})
        total_budget += budgeted
        total_actual += actual
    return {"budget": budget.name, "fiscal_year": budget.fiscal_year, "scope": budget.scope,
            "rows": rows, "total_budget": _round(total_budget), "total_actual": _round(total_actual),
            "total_variance": _round(total_budget - total_actual)}


# ============================================================
# INVESTMENT MATHS  (ROI / IRR / NPV / mortgage / cap rate)
# ============================================================


def npv(rate: float, cashflows: List[float]) -> float:
    """Net present value of a period-0-first cash-flow series."""
    return _round(sum(cf / ((1 + rate) ** i) for i, cf in enumerate(cashflows)))


def irr(cashflows: List[float], guess: float = 0.1) -> Optional[float]:
    """Internal rate of return via bisection. Returns ``None`` when there is no sign change."""
    if len(cashflows) < 2:
        return None
    low, high = -0.9999, 10.0
    f_low, f_high = npv(low, cashflows), npv(high, cashflows)
    if f_low * f_high > 0:
        return None
    for _ in range(300):
        mid = (low + high) / 2
        f_mid = npv(mid, cashflows)
        if abs(f_mid) < 1e-7:
            return _round(mid, 6)
        if f_low * f_mid < 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
    return _round((low + high) / 2, 6)


def payback_period(cashflows: List[float], discount_rate: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Payback period in periods, interpolated. ``discount_rate`` gives the discounted variant."""
    flows = cashflows
    if discount_rate:
        flows = [cf / ((1 + discount_rate) ** i) for i, cf in enumerate(cashflows)]
    cumulative = 0.0
    for i, cf in enumerate(flows):
        previous = cumulative
        cumulative += cf
        if cumulative >= 0 and previous < 0:
            fraction = (-previous / cf) if cf else 0.0
            return {"periods": _round(i - 1 + fraction, 2), "partial_period": _round(fraction, 3)}
    return None


def investment_metrics(cashflows: List[float], discount_rate: Optional[float] = None) -> Dict[str, Any]:
    """NPV, IRR, payback, profitability index, equity multiple and ROI for a cash-flow series.

    ``cashflows[0]`` is normally the (negative) initial investment; the final value
    should include any terminal/exit proceeds.
    """
    rate = ACCOUNTING_CONFIG["default_discount_rate"] if discount_rate is None else float(discount_rate)
    flows = [float(c or 0.0) for c in cashflows]
    invested = _round(sum(-cf for cf in flows if cf < 0))
    returned = _round(sum(cf for cf in flows if cf > 0))
    net = _round(returned - invested)
    periods = max(1, len(flows) - 1)
    simple_roi = _round(net / invested, 4) if invested else None
    annualised = _round((1 + simple_roi) ** (1 / periods) - 1, 4) if (invested and simple_roi is not None
                                                                      and simple_roi > -1) else None
    pv_inflows = _round(sum(cf / ((1 + rate) ** i) for i, cf in enumerate(flows) if i > 0 and cf > 0))
    pv_outflows = _round(sum(-cf / ((1 + rate) ** i) for i, cf in enumerate(flows) if cf < 0))
    return {
        "cashflows": [_round(c) for c in flows],
        "periods": periods,
        "discount_rate": rate,
        "invested": invested,
        "returned": returned,
        "net_profit": net,
        "simple_roi": simple_roi,
        "annualised_roi": annualised,
        "equity_multiple": _round(returned / invested, 3) if invested else None,
        "npv": npv(rate, flows),
        "irr": irr(flows),
        "payback": payback_period(flows),
        "discounted_payback": payback_period(flows, rate),
        "profitability_index": _round(pv_inflows / pv_outflows, 3) if pv_outflows else None,
    }


def cap_rate(noi: float, value: float) -> Dict[str, Any]:
    """Capitalisation rate and its inverse (value multiple)."""
    if value <= 0:
        return {"error": "value must be greater than zero"}
    rate = noi / value
    return {"noi": _round(noi), "value": _round(value), "cap_rate": _round(rate, 4),
            "value_multiple": _round(1 / rate, 2) if rate else None}


def cash_on_cash(annual_cash_flow: float, cash_invested: float) -> Dict[str, Any]:
    if cash_invested <= 0:
        return {"error": "cash_invested must be greater than zero"}
    return {"annual_cash_flow": _round(annual_cash_flow), "cash_invested": _round(cash_invested),
            "cash_on_cash": _round(annual_cash_flow / cash_invested, 4)}


def mortgage_schedule(
    principal: float,
    annual_rate: Optional[float] = None,
    years: Optional[int] = None,
    payments_per_year: int = 12,
    max_rows: int = 480,
) -> Dict[str, Any]:
    """Amortising mortgage: payment, total interest and the period-by-period schedule."""
    principal = _round(principal)
    if principal <= 0:
        return {"error": "principal must be greater than zero"}
    rate = ACCOUNTING_CONFIG["default_mortgage_rate"] if annual_rate is None else float(annual_rate)
    term = int(years or ACCOUNTING_CONFIG["default_mortgage_years"])
    n = max(1, term * payments_per_year)
    periodic = rate / payments_per_year
    if periodic:
        payment = principal * periodic / (1 - (1 + periodic) ** -n)
    else:
        payment = principal / n
    balance = principal
    schedule, total_interest = [], 0.0
    for period in range(1, n + 1):
        interest = balance * periodic
        principal_part = payment - interest
        balance = max(0.0, balance - principal_part)
        total_interest += interest
        if period <= max_rows:
            schedule.append({"period": period, "payment": _round(payment), "interest": _round(interest),
                             "principal": _round(principal_part), "balance": _round(balance)})
    return {
        "principal": principal, "annual_rate": rate, "years": term,
        "payments_per_year": payments_per_year, "periods": n,
        "payment": _round(payment), "total_paid": _round(payment * n),
        "total_interest": _round(total_interest),
        "interest_share": _round(total_interest / (payment * n), 4) if payment else None,
        "schedule": schedule,
        "schedule_truncated": n > max_rows,
    }


def roi_analysis(
    initial_investment: float,
    annual_cash_flow: float = 0.0,
    hold_years: Optional[int] = None,
    terminal_value: float = 0.0,
    discount_rate: Optional[float] = None,
    annual_growth: float = 0.0,
    annual_cost_inflation: float = 0.0,
    loan_amount: float = 0.0,
    loan_rate: Optional[float] = None,
    loan_years: Optional[int] = None,
    scenarios: bool = True,
) -> Dict[str, Any]:
    """ROI for a property/development investment, with optional leverage.

    Produces pessimistic / base / optimistic scenarios that scale the cash flow by
    ±15 % and the terminal value by ±10 %.
    """
    hold = int(hold_years or ACCOUNTING_CONFIG["default_hold_years"])
    initial_investment = _round(initial_investment)
    if initial_investment <= 0:
        return {"error": "initial_investment must be greater than zero"}
    equity = _round(initial_investment - loan_amount)

    def net_flow(flow: float, terminal: float) -> List[float]:
        flows = [-equity]
        rent = flow
        for _ in range(hold):
            flows.append(_round(rent))
            rent = rent * (1 + annual_growth) - (rent * annual_cost_inflation)
        flows[-1] = _round(flows[-1] + terminal)
        return flows

    debt_service = 0.0
    if loan_amount:
        mortgage = mortgage_schedule(loan_amount, loan_rate, loan_years)
        if "error" in mortgage:
            return mortgage
        debt_service = _round(mortgage["payment"] * 12)
        annual_cash_flow = annual_cash_flow - debt_service

    base = net_flow(annual_cash_flow, terminal_value)
    result: Dict[str, Any] = {
        "initial_investment": initial_investment,
        "loan_amount": _round(loan_amount),
        "equity_invested": equity,
        "annual_debt_service": debt_service,
        "hold_years": hold,
        "terminal_value": _round(terminal_value),
        "base": investment_metrics(base, discount_rate),
        "cap_rate": cap_rate(annual_cash_flow, initial_investment) if initial_investment else None,
        "cash_on_cash": cash_on_cash(annual_cash_flow, equity) if equity else None,
    }
    if scenarios:
        variants = {
            "pessimistic": (annual_cash_flow * 0.85, terminal_value * 0.90),
            "base": (annual_cash_flow, terminal_value),
            "optimistic": (annual_cash_flow * 1.15, terminal_value * 1.10),
        }
        result["scenarios"] = {
            name: {
                "annual_cash_flow": _round(flow),
                "terminal_value": _round(terminal),
                **investment_metrics(net_flow(flow, terminal), discount_rate),
            }
            for name, (flow, terminal) in variants.items()
        }
    return result


def property_roi(
    purchase_price: float,
    annual_rent: float = 0.0,
    annual_expenses: float = 0.0,
    hold_years: Optional[int] = None,
    appreciation_rate: float = 0.075,
    discount_rate: Optional[float] = None,
    down_payment_share: float = 1.0,
    loan_rate: Optional[float] = None,
    loan_years: Optional[int] = None,
    selling_cost_rate: float = 0.02,
) -> Dict[str, Any]:
    """Convenience ROI for a single property: rental yield, appreciation, leverage."""
    purchase_price = _round(purchase_price)
    if purchase_price <= 0:
        return {"error": "purchase_price must be greater than zero"}
    hold = int(hold_years or ACCOUNTING_CONFIG["default_hold_years"])
    noi = _round(annual_rent - annual_expenses)
    loan_amount = _round(purchase_price * (1 - down_payment_share))
    terminal = _round(purchase_price * ((1 + appreciation_rate) ** hold) * (1 - selling_cost_rate))
    result = roi_analysis(
        initial_investment=purchase_price, annual_cash_flow=noi, hold_years=hold,
        terminal_value=terminal, discount_rate=discount_rate,
        loan_amount=loan_amount, loan_rate=loan_rate, loan_years=loan_years,
    )
    if "error" in result:
        return result
    result.update({
        "purchase_price": purchase_price,
        "gross_rental_yield": _round(annual_rent / purchase_price, 4),
        "net_rental_yield": _round(noi / purchase_price, 4),
        "net_operating_income": noi,
        "appreciation_rate": appreciation_rate,
        "projected_sale_price": terminal,
    })
    return result


# ============================================================
# INFO
# ============================================================


def accounting_info() -> Dict[str, Any]:
    return {
        "config": ACCOUNTING_CONFIG,
        "account_types": ACCOUNT_TYPES,
        "account_subtypes": ACCOUNT_SUBTYPES,
        "invoice_types": INVOICE_TYPES,
        "invoice_statuses": INVOICE_STATUSES,
        "payment_methods": PAYMENT_METHODS,
        "billing_cycles": list(BILLING_CYCLES),
        "lease_statuses": LEASE_STATUSES,
        "counts": {
            "accounts": len(accounts_db),
            "journal_entries": len(journal_db),
            "invoices": len(invoices_db),
            "payments": len(payments_db),
            "expenses": len(expenses_db),
            "leases": len(leases_db),
            "budgets": len(budgets_db),
        },
    }


__all__ = [
    "ACCOUNTING_CONFIG", "ACCOUNT_TYPES", "ACCOUNT_SUBTYPES", "INVOICE_TYPES", "INVOICE_STATUSES",
    "PAYMENT_METHODS", "BILLING_CYCLES", "LEASE_STATUSES", "CHART_OF_ACCOUNTS",
    "Account", "JournalLine", "JournalEntry", "InvoiceLine", "Invoice", "Payment", "Expense",
    "Lease", "Budget",
    "accounts_db", "journal_db", "invoices_db", "payments_db", "expenses_db", "leases_db", "budgets_db",
    "reset", "seed_chart_of_accounts", "create_account", "update_account", "get_account",
    "list_accounts", "account_balance", "account_with_balance",
    "post_journal_entry", "get_journal_entry", "list_journal_entries", "void_journal_entry",
    "trial_balance", "general_ledger", "profit_and_loss", "balance_sheet", "cash_flow_statement",
    "financial_ratios", "accounting_dashboard",
    "create_invoice", "get_invoice", "list_invoices", "post_invoice", "record_payment",
    "create_expense", "receivable_total", "payable_total", "invoice_aging",
    "create_lease", "list_leases", "rent_roll", "generate_rent_invoices",
    "create_budget", "list_budgets", "budget_variance",
    "npv", "irr", "payback_period", "investment_metrics", "cap_rate", "cash_on_cash",
    "mortgage_schedule", "roi_analysis", "property_roi", "accounting_info",
]
