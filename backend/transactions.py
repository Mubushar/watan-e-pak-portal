"""Transaction & closing lifecycle (framework-free).

This is the module the roadmap calls the *moat*: it links the **transaction
lifecycle** directly to the **financial ledger**. It owns transactions, offers,
contract-term extraction, milestone/deadline tracking, e-signature verification,
commission computation and the revenue-share payout split.

The close step returns balanced journal lines (it does not post them itself) so the
server can hand them to ``accounting.post_journal_entry`` — one source of truth.
"""

import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


TRANSACTION_CONFIG: Dict[str, Any] = {
    "default_commission_rate": 0.02,
    "vat_rate": 0.17,
    "default_splits": {"platform_share": 0.20, "listing_agent_share": 0.40,
                       "selling_agent_share": 0.40},
    "fall_through_probability": 0.08,
    "reminder_lead_days": 3,
}

TRANSACTION_TYPES: Dict[str, str] = {
    "sale": "Sale (residential / commercial)",
    "purchase": "Purchase (buy side)",
    "rental": "Rental letting",
    "lease": "Commercial lease",
    "assignment": "File / allotment assignment",
}

TRANSACTION_STAGES: List[str] = [
    "draft", "listed", "offer", "negotiation", "under_contract", "due_diligence",
    "financing", "closing", "closed", "fallen_through",
]

STAGE_INDEX: Dict[str, int] = {s: i for i, s in enumerate(TRANSACTION_STAGES)}

# Milestone templates: (key, name, offset_days, owner, blocking)
CHECKLISTS: Dict[str, List[tuple]] = {
    "sale": [
        ("offer_accepted", "Offer accepted", 0, "broker", True),
        ("earnest_money", "Earnest money / token deposited", 3, "buyer", True),
        ("compliance_kyc", "KYC / AML & listing compliance cleared", 5, "compliance", True),
        ("title_search", "Title search & verification", 9, "legal", True),
        ("due_diligence", "Due diligence (structural, legal, dues)", 14, "valuer", True),
        ("financing_approval", "Buyer financing / mortgage approval", 21, "finance", True),
        ("contract_signing", "Sale agreement signed (e-sign)", 25, "both", True),
        ("noc_transfer", "NOC / transfer with authority", 30, "legal", True),
        ("closing_settlement", "Closing & settlement of funds", 35, "broker", True),
        ("ledger_posting", "Commission posted to the ledger", 36, "accounting", False),
        ("handover", "Possession / handover", 40, "broker", False),
    ],
    "purchase": [
        ("brief", "Buy brief confirmed", 0, "buyer", False),
        ("shortlist", "Shortlist & viewings", 7, "agent", True),
        ("offer", "Offer submitted", 14, "agent", True),
        ("contract_signing", "Agreement signed", 21, "both", True),
        ("closing_settlement", "Closing & settlement", 30, "broker", True),
        ("ledger_posting", "Commission posted to the ledger", 31, "accounting", False),
    ],
    "rental": [
        ("application", "Application & references", 0, "tenant", True),
        ("screening", "Screening decision", 3, "agent", True),
        ("deposit", "Security deposit received", 5, "tenant", True),
        ("lease_draft", "Tenancy agreement drafted", 6, "agent", False),
        ("lease_signing", "Tenancy agreement signed (e-sign)", 8, "both", True),
        ("first_rent", "First month's rent received", 10, "tenant", True),
        ("handover", "Keys / possession handover", 12, "agent", False),
    ],
    "lease": [
        ("heads_of_terms", "Heads of terms agreed", 0, "both", False),
        ("compliance_kyc", "KYC & compliance", 5, "compliance", True),
        ("draft_lease", "Lease drafted", 12, "legal", False),
        ("lease_signing", "Lease signed (e-sign)", 18, "both", True),
        ("deposit", "Security deposit received", 20, "tenant", True),
        ("handover", "Fit-out / handover", 30, "landlord", False),
    ],
    "assignment": [
        ("noc_check", "NOC / no-dues check with developer", 0, "legal", True),
        ("transfer_fee", "Transfer fee paid", 7, "buyer", True),
        ("compliance_kyc", "KYC & compliance", 8, "compliance", True),
        ("deed", "Assignment deed signed", 14, "both", True),
        ("society_record", "Society record updated", 21, "legal", False),
    ],
}

CONTRACT_TERM_PATTERNS: Dict[str, str] = {
    "price": r"(?:price|amount|consideration|sale price)\s*(?:of|:)?\s*(?:pkr|rs\.?)?\s*([\d,]+(?:\.\d+)?)",
    "deposit": r"(?:deposit|earnest|token)\s*(?:of|:)?\s*(?:pkr|rs\.?)?\s*([\d,]+(?:\.\d+)?)",
    "commission": r"commission\s*(?:of|:)?\s*(\d+(?:\.\d+)?)\s*%",
    "possession_date": r"(?:possession|handover)\s*(?:on|by|:)?\s*([0-9]{1,2}[\s\-/][A-Za-z0-9]{3,9}[\s\-/][0-9]{2,4}|\d{4}-\d{2}-\d{2})",
    "completion_date": r"(?:completion|closing)\s*(?:on|by|:)?\s*([0-9]{1,2}[\s\-/][A-Za-z0-9]{3,9}[\s\-/][0-9]{2,4}|\d{4}-\d{2}-\d{2})",
    "payment_terms": r"(?:payment terms?|instal+ments?)\s*(?:of|:)?\s*([^\n.;]{3,80})",
    "penalty": r"(?:penalty|late fee|default)\s*(?:of|:)?\s*([^\n.;]{3,60})",
    "tenure": r"(?:lease term|tenure|for)\s*(?:of|:)?\s*(\d+\s*(?:years?|months?))",
}
PARTY_PATTERN = r"\b(?:Mr|Mrs|Ms|M/s|Messrs)\.?\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})"
DATE_PATTERN = r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Z][a-z]+\s+\d{4})\b"


# ============================================================
# Models
# ============================================================


class ContractTerm(BaseModel):
    key: str
    label: str
    value: Any
    extracted_from: Optional[str] = None
    confidence: float = 0.8


class Milestone(BaseModel):
    key: str
    name: str
    offset_days: int = 0
    due_date: Optional[str] = None
    owner: str = "broker"
    status: str = "pending"  # pending | done | overdue | waived
    blocking: bool = False
    required: bool = True
    completed_at: Optional[str] = None


class Offer(BaseModel):
    id: str = Field(default_factory=lambda: "off_" + uuid.uuid4().hex[:8])
    transaction_id: str
    price: float
    buyer_name: Optional[str] = None
    terms: Optional[str] = None
    status: str = "submitted"  # draft | submitted | countered | accepted | rejected | withdrawn
    counter_price: Optional[float] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class Signature(BaseModel):
    id: str = Field(default_factory=lambda: "sig_" + uuid.uuid4().hex[:8])
    transaction_id: str
    signer: str
    role: str = "buyer"  # buyer | seller | witness | broker
    method: str = "esign"  # esign | wet
    signed: bool = False
    signed_at: Optional[str] = None
    reference: Optional[str] = None


class Transaction(BaseModel):
    id: str = Field(default_factory=lambda: "txn_" + uuid.uuid4().hex[:10])
    code: str = ""
    transaction_type: str = "sale"
    property_ref: Optional[str] = None
    property_title: Optional[str] = None
    buyer_name: Optional[str] = None
    seller_name: Optional[str] = None
    buyer_id: Optional[str] = None
    seller_id: Optional[str] = None
    listing_agent_id: Optional[str] = None
    selling_agent_id: Optional[str] = None
    price: float = 0.0
    currency: str = "PKR"
    commission_rate: Optional[float] = None
    stage: str = "draft"
    status: str = "open"  # open | closed | fallen_through
    source: str = "portal"
    milestones: List[Milestone] = Field(default_factory=list)
    terms: List[ContractTerm] = Field(default_factory=list)
    document_text: Optional[str] = None
    notes: Optional[str] = None
    risk_flags: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    closed_at: Optional[str] = None


transactions_db: List[Transaction] = []
offers_db: List[Offer] = []
signatures_db: List[Signature] = []


# ============================================================
# Helpers
# ============================================================


def _as_date(value: Any, default: Optional[date] = None) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value:
        for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return default or date.today()


def _iso(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def _num(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    return float(str(raw).replace(",", ""))


def transaction_stages() -> List[Dict[str, Any]]:
    return [{"stage": s, "index": i, "is_final": s in ("closed", "fallen_through")}
            for i, s in enumerate(TRANSACTION_STAGES)]


def build_milestones(transaction_type: str, start_date: Any = None) -> List[Milestone]:
    template = CHECKLISTS.get(transaction_type, CHECKLISTS["sale"])
    start = _as_date(start_date)
    out: List[Milestone] = []
    for key, name, offset, owner, blocking in template:
        due = start + timedelta(days=offset)
        out.append(Milestone(key=key, name=name, offset_days=offset, due_date=due.isoformat(),
                             owner=owner, blocking=blocking))
    return out


def _next_code() -> str:
    # max + 1, not count + 1: codes stay unique after a transaction is removed
    nums = [int(t.code[4:]) for t in transactions_db if (t.code or "").startswith("TXN-") and t.code[4:].isdigit()]
    return f"TXN-{max(nums, default=1000) + 1}"


# ============================================================
# CRUD
# ============================================================


def create_transaction(transaction_type: str = "sale", price: float = 0.0,
                       property_ref: Optional[str] = None, property_title: Optional[str] = None,
                       buyer_name: Optional[str] = None, seller_name: Optional[str] = None,
                       listing_agent_id: Optional[str] = None,
                       selling_agent_id: Optional[str] = None,
                       commission_rate: Optional[float] = None, start_date: Any = None,
                       source: str = "portal", notes: Optional[str] = None) -> Transaction:
    tx = Transaction(
        code=_next_code(), transaction_type=transaction_type, price=float(price or 0),
        property_ref=property_ref, property_title=property_title, buyer_name=buyer_name,
        seller_name=seller_name, listing_agent_id=listing_agent_id,
        selling_agent_id=selling_agent_id, commission_rate=commission_rate,
        source=source, notes=notes, stage="offer" if transaction_type != "purchase" else "draft",
    )
    tx.milestones = build_milestones(transaction_type, start_date)
    transactions_db.append(tx)
    return tx


def get_transaction(tx_id: str) -> Optional[Transaction]:
    return next((t for t in transactions_db if t.id == tx_id or t.code == tx_id), None)


def list_transactions(status: Optional[str] = None, stage: Optional[str] = None,
                      transaction_type: Optional[str] = None) -> List[Transaction]:
    rows = transactions_db
    if status:
        rows = [t for t in rows if t.status == status]
    if stage:
        rows = [t for t in rows if t.stage == stage]
    if transaction_type:
        rows = [t for t in rows if t.transaction_type == transaction_type]
    return rows


def update_transaction(tx_id: str, **fields: Any) -> Dict[str, Any]:
    tx = get_transaction(tx_id)
    if not tx:
        return {"error": f"Unknown transaction: {tx_id}"}
    for key in ("property_title", "buyer_name", "seller_name", "notes", "stage", "status",
                "commission_rate", "price", "listing_agent_id", "selling_agent_id", "source"):
        if fields.get(key) is not None:
            setattr(tx, key, fields[key])
    if tx.stage == "closed":
        tx.status = "closed"
        tx.closed_at = tx.closed_at or datetime.now().isoformat(timespec="seconds")
    if tx.stage == "fallen_through":
        tx.status = "fallen_through"
    tx.updated_at = datetime.now().isoformat(timespec="seconds")
    return {"transaction": txn_view(tx)}


def add_milestone(tx_id: str, key: str, name: str, due_date: Any = None, owner: str = "broker",
                  blocking: bool = False) -> Dict[str, Any]:
    tx = get_transaction(tx_id)
    if not tx:
        return {"error": f"Unknown transaction: {tx_id}"}
    tx.milestones.append(Milestone(key=key, name=name, due_date=_iso(_as_date(due_date)) if due_date else None,
                                   owner=owner, blocking=blocking))
    tx.updated_at = datetime.now().isoformat(timespec="seconds")
    return {"transaction": txn_view(tx)}


def complete_milestone(tx_id: str, key: str, as_of: Any = None) -> Dict[str, Any]:
    tx = get_transaction(tx_id)
    if not tx:
        return {"error": f"Unknown transaction: {tx_id}"}
    m = next((m for m in tx.milestones if m.key == key), None)
    if not m:
        return {"error": f"Unknown milestone '{key}'", "keys": [x.key for x in tx.milestones]}
    m.status = "done"
    m.completed_at = _iso(_as_date(as_of))
    tx.updated_at = datetime.now().isoformat(timespec="seconds")
    return {"transaction": txn_view(tx)}


# ============================================================
# Contract-term extraction
# ============================================================


def extract_terms(text: str) -> Dict[str, Any]:
    """Best-effort extraction of key terms, parties and dates from a contract text."""
    if not text:
        return {"error": "no document text supplied"}
    terms: List[ContractTerm] = []
    for key, pattern in CONTRACT_TERM_PATTERNS.items():
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        raw = m.group(1).strip()
        value: Any = raw
        if key in ("price", "deposit"):
            num = _num(raw)
            value = num if num is not None else raw
        elif key == "commission":
            value = float(raw) / 100.0
        elif key == "payment_terms":
            value = re.sub(r"\s+", " ", raw)[:80]
        terms.append(ContractTerm(key=key, label=key.replace("_", " ").title(), value=value,
                                  extracted_from=re.sub(r"\s+", " ", m.group(0))[:120]))
    parties = list(dict.fromkeys(re.findall(PARTY_PATTERN, text)))[:8]
    dates = list(dict.fromkeys(re.findall(DATE_PATTERN, text)))[:8]
    confidence = round(min(0.98, 0.4 + 0.06 * len(terms) + 0.02 * len(parties)), 2)
    return {"terms": [t.model_dump() for t in terms], "term_count": len(terms),
            "parties": parties, "dates": dates, "confidence": confidence}


# ============================================================
# Offers & signatures
# ============================================================


def add_offer(tx_id: str, price: float, buyer_name: Optional[str] = None,
              terms: Optional[str] = None) -> Dict[str, Any]:
    tx = get_transaction(tx_id)
    if not tx:
        return {"error": f"Unknown transaction: {tx_id}"}
    offer = Offer(transaction_id=tx.id, price=float(price), buyer_name=buyer_name or tx.buyer_name,
                  terms=terms)
    offers_db.append(offer)
    tx.stage = "negotiation" if any(o.status == "countered" for o in offers_db
                                    if o.transaction_id == tx.id) else "offer"
    tx.updated_at = datetime.now().isoformat(timespec="seconds")
    return {"offer": offer.model_dump(), "transaction": txn_view(tx)}


def respond_offer(offer_id: str, action: str, counter_price: Optional[float] = None) -> Dict[str, Any]:
    offer = next((o for o in offers_db if o.id == offer_id), None)
    if not offer:
        return {"error": f"Unknown offer: {offer_id}"}
    tx = get_transaction(offer.transaction_id)
    action = action.lower()
    if action == "counter":
        offer.status = "countered"
        offer.counter_price = counter_price
        if tx:
            tx.stage = "negotiation"
    elif action == "accept":
        offer.status = "accepted"
        if tx:
            tx.price = counter_price or offer.price
            tx.stage = "under_contract"
    elif action == "reject":
        offer.status = "rejected"
    elif action == "withdraw":
        offer.status = "withdrawn"
    else:
        return {"error": f"Unknown action: {action}",
                "allowed": ["counter", "accept", "reject", "withdraw"]}
    if tx:
        tx.updated_at = datetime.now().isoformat(timespec="seconds")
    return {"offer": offer.model_dump(), "transaction": txn_view(tx) if tx else None}


def add_signature(tx_id: str, signer: str, role: str = "buyer", method: str = "esign",
                  signed: bool = False, reference: Optional[str] = None) -> Dict[str, Any]:
    tx = get_transaction(tx_id)
    if not tx:
        return {"error": f"Unknown transaction: {tx_id}"}
    sig = Signature(transaction_id=tx.id, signer=signer, role=role, method=method,
                    signed=signed, reference=reference,
                    signed_at=datetime.now().isoformat(timespec="seconds") if signed else None)
    signatures_db.append(sig)
    return {"signature": sig.model_dump(), "verification": verify_signatures(tx.id)}


def verify_signatures(tx_id: str) -> Dict[str, Any]:
    tx = get_transaction(tx_id)
    if not tx:
        return {"error": f"Unknown transaction: {tx_id}"}
    sigs = [s for s in signatures_db if s.transaction_id == tx.id]
    expected = {"sale": ["buyer", "seller"], "purchase": ["buyer"],
                "rental": ["tenant"], "lease": ["tenant", "landlord"],
                "assignment": ["buyer", "seller"]}.get(tx.transaction_type, ["buyer", "seller"])
    present = {s.role for s in sigs if s.signed}
    missing = [r for r in expected if r not in present]
    return {"transaction_id": tx.id, "expected_roles": expected,
            "signed_roles": sorted(present), "missing": missing,
            "complete": not missing, "signature_count": len(sigs)}


# ============================================================
# Progress & deadlines
# ============================================================


def transaction_progress(tx_id: str, as_of: Any = None) -> Dict[str, Any]:
    tx = get_transaction(tx_id)
    if not tx:
        return {"error": f"Unknown transaction: {tx_id}"}
    today = _as_date(as_of)
    total = len(tx.milestones)
    done = sum(1 for m in tx.milestones if m.status == "done")
    overdue = []
    next_due = None
    for m in tx.milestones:
        if m.status == "done":
            continue
        due = _as_date(m.due_date) if m.due_date else None
        if due and due < today:
            m.status = "overdue"
            overdue.append({"key": m.key, "name": m.name, "due_date": m.due_date,
                            "days_late": (today - due).days, "blocking": m.blocking})
        elif due and (next_due is None or due < _as_date(next_due["due_date"])):
            next_due = {"key": m.key, "name": m.name, "due_date": m.due_date,
                        "days_left": (due - today).days}
    pct = round(100.0 * done / total, 1) if total else 0.0
    rag = "green"
    if overdue:
        rag = "red" if any(o["blocking"] for o in overdue) else "amber"
    elif next_due and next_due["days_left"] <= TRANSACTION_CONFIG["reminder_lead_days"]:
        rag = "amber"
    return {"transaction_id": tx.id, "code": tx.code, "stage": tx.stage,
            "progress_pct": pct, "milestones_total": total, "milestones_done": done,
            "overdue": overdue, "next_deadline": next_due, "rag": rag}


def upcoming_deadlines(horizon_days: int = 14, as_of: Any = None,
                       transactions: Optional[List[Transaction]] = None) -> Dict[str, Any]:
    today = _as_date(as_of)
    horizon = today + timedelta(days=horizon_days)
    rows: List[Dict[str, Any]] = []
    for tx in (transactions if transactions is not None else transactions_db):
        if tx.status != "open":
            continue
        for m in tx.milestones:
            if m.status in ("done", "waived") or not m.due_date:
                continue
            due = _as_date(m.due_date)
            if due <= horizon:
                rows.append({"transaction_id": tx.id, "code": tx.code, "milestone": m.key,
                             "name": m.name, "due_date": m.due_date,
                             "days_left": (due - today).days, "owner": m.owner,
                             "blocking": m.blocking,
                             "overdue": due < today})
    rows.sort(key=lambda r: r["due_date"])
    return {"horizon_days": horizon_days, "count": len(rows),
            "overdue": sum(1 for r in rows if r["overdue"]), "deadlines": rows}


# ============================================================
# Commission, revenue share & close
# ============================================================


def revenue_share(commission_gross: float, policy: Optional[Dict[str, float]] = None,
                  vat_rate: Optional[float] = None) -> Dict[str, Any]:
    splits = {**TRANSACTION_CONFIG["default_splits"], **(policy or {})}
    vat = float(vat_rate if vat_rate is not None else TRANSACTION_CONFIG["vat_rate"])
    total_share = sum(splits.values())
    if total_share > 1.0001:
        return {"error": "revenue shares exceed 100%", "splits": splits}
    commission_gross = float(commission_gross)
    vat_amount = round(commission_gross * vat, 2)
    allocation = {k: round(commission_gross * v, 2) for k, v in splits.items()}
    return {"commission_gross": round(commission_gross, 2), "vat_amount": vat_amount,
            "vat_rate": vat, "splits": {k: round(v, 4) for k, v in splits.items()},
            "allocation": allocation,
            "net_after_vat": round(commission_gross - vat_amount, 2)}


def close_transaction(tx_id: str, commission_rate: Optional[float] = None,
                       splits: Optional[Dict[str, float]] = None,
                       as_of: Any = None) -> Dict[str, Any]:
    """Close a transaction: compute commission, allocate revenue share and return
    balanced journal lines (to be posted by the accounting module)."""
    tx = get_transaction(tx_id)
    if not tx:
        return {"error": f"Unknown transaction: {tx_id}"}
    if tx.status == "closed":
        return {"error": "transaction already closed", "transaction": txn_view(tx)}
    rate = float(commission_rate if commission_rate is not None
                 else (tx.commission_rate or TRANSACTION_CONFIG["default_commission_rate"]))
    gross = round(tx.price * rate, 2)
    share = revenue_share(gross, splits)
    vat = share["vat_amount"]
    # +Commission receivable, -Commission income, -VAT payable
    ledger_lines = [
        {"account": "1100", "debit": round(gross + vat, 2), "credit": 0.0,
         "description": f"Commission receivable {tx.code}"},
        {"account": "4030", "debit": 0.0, "credit": gross,
         "description": f"Brokerage commission {tx.code}"},
        {"account": "2100", "debit": 0.0, "credit": vat,
         "description": f"Output VAT on commission {tx.code}"},
    ]
    tx.stage = "closed"
    tx.status = "closed"
    tx.closed_at = _iso(_as_date(as_of))
    tx.updated_at = datetime.now().isoformat(timespec="seconds")
    return {
        "transaction": txn_view(tx),
        "commission": {"rate": rate, "gross": gross, "vat": vat,
                       "commission_income": gross, "net_after_vat": share["net_after_vat"]},
        "revenue_share": share,
        "ledger_lines": ledger_lines,
        "balanced": round(sum(l["debit"] for l in ledger_lines), 2)
        == round(sum(l["credit"] for l in ledger_lines), 2),
    }


def txn_view(tx: Transaction) -> Dict[str, Any]:
    view = tx.model_dump()
    view["stage_index"] = STAGE_INDEX.get(tx.stage, 0)
    view["type_label"] = TRANSACTION_TYPES.get(tx.transaction_type, tx.transaction_type)
    view["milestone_progress"] = {
        "total": len(tx.milestones),
        "done": sum(1 for m in tx.milestones if m.status == "done"),
    }
    return view
