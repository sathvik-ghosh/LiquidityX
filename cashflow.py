"""Deterministic joint cash simulation of the whole network.

Rules (documented assumptions):
* Each open invoice is paid by the payer on max(due_date, as_of) + expected_delay_days.
* A payer pays only from cash it actually holds (never below zero for supplier
  payments); unpaid amounts stay pending and are retried every day.
* Payroll/other cash transactions are applied on their date and may push cash
  negative; that is reported as a shortfall, not hidden.
* Shortfall at a date = max(0, min_cash - balance).
* Hypothetical shocks never count as received cash.
"""
from dataclasses import dataclass, field
from datetime import date

from ..money import PAISE_PER_LAKH


@dataclass(frozen=True)
class Shock:
    invoice_id: int
    delay_days: int = 0       # delay applied to the late part
    paid_pct: int = 0         # % paid on the normal date (0..100)
    default: bool = False     # late part never paid within the horizon


@dataclass(frozen=True)
class ExpenseShock:
    company_id: int
    day: int
    amount: int               # paise, positive = extra outflow


def validate_shocks(shocks, expenses=()):
    for s in shocks:
        if not 0 <= s.delay_days <= 365:
            raise ValueError("delay_days must be between 0 and 365")
        if not 0 <= s.paid_pct <= 100:
            raise ValueError("paid_pct must be between 0 and 100")
    for e in expenses:
        if e.amount <= 0 or e.day < 0:
            raise ValueError("expense amount must be positive and day >= 0")


@dataclass
class State:
    as_of: date
    companies: dict          # id -> dict(name,type,opening_cash,min_cash)
    invoices: list           # dict(id,payer,payee,amount,pay_day)
    txns: list               # dict(company,day,amount)


def load_state(conn, as_of: date) -> State:
    cos = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM companies")}
    invs = []
    for r in conn.execute("""SELECT i.*, r.payer_id, r.payee_id FROM invoices i
                             JOIN relationships r ON r.id=i.relationship_id
                             WHERE i.status='open' ORDER BY i.id"""):
        due = (date.fromisoformat(r["due_date"]) - as_of).days
        invs.append(dict(id=r["id"], payer=r["payer_id"], payee=r["payee_id"],
                         amount=r["amount"], due=due,
                         pay_day=max(due, 0) + r["expected_delay_days"]))
    txns = [dict(company=r["company_id"], day=(date.fromisoformat(r["txn_date"]) - as_of).days,
                 amount=r["amount"])
            for r in conn.execute("SELECT * FROM cash_transactions ORDER BY id")]
    return State(as_of, cos, invs, txns)


@dataclass
class SimResult:
    horizon: int
    balances: dict                      # company -> [balance per day 0..horizon]
    invoice_paid_day: dict              # invoice id -> day fully paid (None = not within horizon)
    invoice_unpaid: dict                # invoice id -> paise unpaid at horizon end
    invoice_scheduled: dict             # invoice id -> scheduled day of final tranche (None=default)
    inflow: dict = field(default_factory=dict)    # company -> [paise per day]
    outflow: dict = field(default_factory=dict)


def simulate(state: State, horizon=90, shocks=(), expenses=()) -> SimResult:
    validate_shocks(shocks, expenses)
    shock_by_inv = {s.invoice_id: s for s in shocks}
    cash = {cid: c["opening_cash"] for cid, c in state.companies.items()}
    tranches = []   # dict(inv, payer, payee, due_day, remaining)
    sched = {}
    for inv in state.invoices:
        s = shock_by_inv.get(inv["id"])
        if s is None:
            parts = [(inv["pay_day"], inv["amount"])]
        else:
            now = inv["amount"] * s.paid_pct // 100
            parts = [(inv["pay_day"], now)] if now else []
            rest = inv["amount"] - now
            if rest and not s.default:
                parts.append((inv["pay_day"] + s.delay_days, rest))
        sched[inv["id"]] = max((d for d, _ in parts), default=None) \
            if not (s and s.default) else None
        for d, amt in parts:
            tranches.append(dict(inv=inv["id"], payer=inv["payer"], payee=inv["payee"],
                                 due=d, remaining=amt))
    tranches.sort(key=lambda t: (t["due"], t["inv"]))
    txn_by_day, exp_by_day = {}, {}
    for t in state.txns:
        txn_by_day.setdefault(t["day"], []).append(t)
    for e in expenses:
        exp_by_day.setdefault(e.day, []).append(e)
    paid_day = {i["id"]: None for i in state.invoices}
    balances = {cid: [] for cid in cash}
    inflow = {cid: [0] * (horizon + 1) for cid in cash}
    outflow = {cid: [0] * (horizon + 1) for cid in cash}
    for day in range(horizon + 1):
        for t in txn_by_day.get(day, []):
            cash[t["company"]] += t["amount"]
            (inflow if t["amount"] > 0 else outflow)[t["company"]][day] += abs(t["amount"])
        for e in exp_by_day.get(day, []):
            cash[e.company_id] -= e.amount
            outflow[e.company_id][day] += e.amount
        progress = True
        while progress:
            progress = False
            for t in tranches:
                if t["remaining"] <= 0 or t["due"] > day:
                    continue
                pay = min(t["remaining"], max(0, cash[t["payer"]]))
                if pay > 0:
                    cash[t["payer"]] -= pay
                    cash[t["payee"]] += pay
                    outflow[t["payer"]][day] += pay
                    inflow[t["payee"]][day] += pay
                    t["remaining"] -= pay
                    if t["remaining"] == 0:
                        t["done"] = day
                    progress = True
        for cid in cash:
            balances[cid].append(cash[cid])
    unpaid = {i["id"]: 0 for i in state.invoices}
    for t in tranches:
        unpaid[t["inv"]] += t["remaining"]
    for inv in state.invoices:
        i = inv["id"]
        mine = [t for t in tranches if t["inv"] == i]
        if i not in {x.invoice_id for x in shocks if x.default} and \
                all(t["remaining"] == 0 for t in mine):
            paid_day[i] = max((t.get("done", 0) for t in mine), default=0)
    return SimResult(horizon, balances, paid_day, unpaid, sched, inflow, outflow)


def shortfall_profile(state: State, res: SimResult, cid: int):
    """Return (peak_shortfall, first_breach_day or None, breach_days)."""
    mn = state.companies[cid]["min_cash"]
    peak, first, n = 0, None, 0
    for d, b in enumerate(res.balances[cid]):
        gap = mn - b
        if gap > 0:
            n += 1
            first = d if first is None else first
            peak = max(peak, gap)
    return peak, first, n
