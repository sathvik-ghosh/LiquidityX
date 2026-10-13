"""Inventory intelligence + rescue. All cash figures are POTENTIAL RECOVERY (unconfirmed).

Assumptions (editable constants, documented in reports):
 reserve_days = lead_time + (30 if critical else 14)  -> stock kept for production
 sellable_qty = max(0, qty - ceil(daily_demand * reserve_days))
 discount by class: normal 3%, surplus 10%, slow 15%, dead 35%; low case = a further 10 pts off.
"""
import math
from datetime import date

DISCOUNT = {"normal": .03, "surplus": .10, "slow": .15, "dead": .35}
DAYS_TO_CASH = {"normal": 10, "surplus": 14, "slow": 21, "dead": 30}
TRANSFER_COST_PCT = .02
TRANSFER_DAYS = 7


def _d(s, as_of):
    return None if not s else (as_of - date.fromisoformat(s)).days


def load_batches(conn, as_of, company_id=None):
    q = "SELECT b.*, c.name AS company FROM inventory_batches b JOIN companies c ON c.id=b.company_id"
    args = ()
    if company_id:
        q += " WHERE company_id=?"
        args = (company_id,)
    out = []
    for r in conn.execute(q + " ORDER BY b.id", args):
        b = dict(r)
        b["book_value"] = b["qty"] * b["unit_cost"]
        b["margin_pct"] = (0 if not b["selling_price"] else
                           (b["selling_price"] - b["unit_cost"]) / b["selling_price"] * 100)
        b["age_days"] = _d(b["purchase_date"], as_of)
        b["idle_days"] = _d(b["last_move_date"], as_of)
        b["daily_demand"] = b["monthly_demand"] / 30
        b["cover_days"] = None if b["daily_demand"] == 0 else b["qty"] / b["daily_demand"]
        exp = None if not b["expiry_date"] else (date.fromisoformat(b["expiry_date"]) - as_of).days
        b["expired"] = exp is not None and exp < 0
        b["status"] = classify(b)
        out.append(b)
    return out


def classify(b):
    if b["hold_status"] != "none":
        return "held"
    if b["expired"] or b["restricted"]:
        return "held"
    if b["daily_demand"] == 0 and b["idle_days"] > 180:
        return "dead"
    if (b["cover_days"] or 0) > 180 or b["idle_days"] > 120:
        return "slow"
    if b["cover_days"] is not None and b["cover_days"] > b["lead_time_days"] + 60:
        return "surplus"
    return "normal"


def recommendation(b):
    """Sell-first recommendation with reasoning. Never recommends selling held/restricted stock."""
    if b["status"] == "held":
        return dict(action="investigate", sellable_qty=0, cash_low=0, cash_high=0, days=None,
                    reason=f"Held ({b['hold_status']}): cannot be sold normally. See Inventory Rescue.")
    reserve_days = b["lead_time_days"] + (30 if b["critical"] else 14)
    reserve = math.ceil(b["daily_demand"] * reserve_days)
    sellable = max(0, b["qty"] - reserve)
    if b["status"] == "dead":
        sellable = b["qty"]
    disc = DISCOUNT[b["status"]]
    high = int(sellable * b["selling_price"] * (1 - disc))
    low = int(sellable * b["selling_price"] * (1 - disc - .10))
    if sellable == 0:
        return dict(action="retain", sellable_qty=0, cash_low=0, cash_high=0, days=None,
                    reason=f"Keep: {b['qty']} units ≈ reserve of {reserve} units "
                           f"({reserve_days} days = lead time {b['lead_time_days']} + safety).")
    why = (f"{b['status'].capitalize()} stock; keep {reserve} units for {reserve_days} days of demand "
           f"(lead time {b['lead_time_days']}d{', critical item' if b['critical'] else ''}); "
           f"{sellable} units are surplus. Assumed {disc*100:.0f}% discount; low case 10 pts deeper.")
    return dict(action="sell", sellable_qty=sellable, cash_low=low, cash_high=high,
                days=DAYS_TO_CASH[b["status"]], reason=why)


def scenarios(b, all_batches):
    """Compare hold / sell / transfer / retain for one batch."""
    rec = recommendation(b)
    rows = []
    rows.append(dict(option="Hold", cash_low=0, cash_high=0, relief=0, cost=0, days=None,
                     note="No cash; carrying cost continues."))
    if rec["action"] == "sell":
        rows.append(dict(option="Sell surplus", cash_low=rec["cash_low"], cash_high=rec["cash_high"],
                         relief=0, cost=0, days=rec["days"], note=f"{rec['sellable_qty']} units, unconfirmed buyers"))
    elif b["status"] != "held":
        rows.append(dict(option="Sell surplus", cash_low=0, cash_high=0, relief=0, cost=0, days=None,
                         note="Nothing surplus after production reserve."))
    twin = [o for o in all_batches if o["sku"] == b["sku"] and o["location"] != b["location"]
            and o["cover_days"] is not None and o["cover_days"] < 60 and o["company_id"] == b["company_id"]]
    if twin and rec["action"] == "sell" and b["status"] != "held":
        t = twin[0]
        need = max(0, math.ceil(t["daily_demand"] * 60) - t["qty"])
        mv = min(rec["sellable_qty"], need)
        rows.append(dict(option=f"Transfer to {t['location']}", cash_low=0, cash_high=0,
                         relief=mv * b["unit_cost"], cost=int(mv * b["unit_cost"] * TRANSFER_COST_PCT),
                         days=TRANSFER_DAYS,
                         note=f"{mv} units avoid new purchases (relief, not cash received)"))
    rows.append(dict(option="Retain", cash_low=0, cash_high=0, relief=0, cost=0, days=None,
                     note="Protects production; no cash."))
    warn = None
    if b["critical"] and b["status"] != "held":
        keep = b["qty"] - rec["sellable_qty"]
        cover = keep / b["daily_demand"] if b["daily_demand"] else None
        if cover is not None and cover < b["lead_time_days"]:
            warn = "Stockout risk"
        # selling everything would break lead-time cover:
        all_cover = 0
        rows.append(dict(option="Sell ALL (not advised)", cash_low=0, cash_high=int(b["qty"] * b["selling_price"] * .9),
                         relief=0, cost=0, days=DAYS_TO_CASH["normal"],
                         note=f"STOCKOUT: 0 days of cover vs {b['lead_time_days']}d replenishment lead time"))
    return rows, warn


def summary(batches):
    held = sum(b["book_value"] for b in batches if b["status"] == "held")
    return dict(total_value=sum(b["book_value"] for b in batches), held_value=held,
                slow_value=sum(b["book_value"] for b in batches if b["status"] in ("slow", "dead")),
                sellable_cash_high=sum(recommendation(b)["cash_high"] for b in batches))


# ----------------------------- RESCUE ---------------------------------
# key: (steps, prob, gross_pct, gross_basis, cost_pct_book, days, sells, impact, compliance, approvals, missing)
P = lambda steps, prob, g, basis, cost, days, sells, impact, comp, appr, miss: dict(
    steps=steps, prob=prob, gross_pct=g, basis=basis, cost_pct=cost, days=days, sells=sells,
    impact=impact, compliance=comp, approvals=appr, missing=miss)

PATHWAYS = {
 "quality": {
   "Inspect & release": P(["INSPECT", "RELEASE", "RESELL"], .75, .97, "price", .015, 10, True,
        "Production line may be delayed during inspection", "QA release record before any sale",
        ["QA manager sign-off"], ["Historical inspection pass rate (75% assumed)"]),
   "Supplier return": P(["RETURN", "NEGOTIATE", "RECOVER"], .5, .90, "book", .02, 30, False,
        "None on production", "Return authorisation / credit note", ["Procurement head"],
        ["Supplier warranty terms"])},
 "certification": {
   "Re-certify & resell": P(["ASSESS", "RECERTIFY", "RESELL"], .70, .95, "price", .04, 25, True,
        "Delay to dispatch until certificate renewed", "Valid certificate required before shipment",
        ["Compliance officer"], ["Certification body fee quote", "Retest outcome"])},
 "customer_order": {
   "Confirm release with customer": P(["CONFIRM", "NEGOTIATE", "RELEASE"], .80, 1.0, "price", 0.0, 12, True,
        "None; stock already allocated", "Customer PO terms", ["Sales head"], ["Confirmed release date"]),
   "Find alternative buyer": P(["FIND BUYER", "DISCOUNT", "SELL"], .50, .80, "price", .01, 21, True,
        "May breach customer commitment", "Check customer contract/IP", ["Sales head"], ["Contract clause review"])},
 "cancelled_order": {
   "Collect cancellation fee": P(["NEGOTIATE", "INVOICE FEE", "COLLECT"], .40, .25, "book", 0.0, 20, False,
        "Customer relationship strain", "Contract cancellation terms", ["Sales head"], ["Cancellation clause"]),
   "Alternative buyer": P(["FIND BUYER", "DISCOUNT", "SELL"], .60, .75, "price", .01, 25, True,
        "None", "None", ["Sales head"], ["Buyer pipeline"])},
 "damaged": {
   "Repair & resell": P(["INSPECT", "REPAIR", "RESELL"], .70, .85, "price", .15, 21, True,
        "Uses workshop capacity", "Re-inspection before sale", ["QA manager"], ["Repair quote", "Success rate"]),
   "Salvage": P(["ASSESS", "SALVAGE", "DOCUMENT LOSS"], .90, .12, "book", .02, 14, False,
        "None", "Scrap documentation", ["Finance controller"], [])},
 "obsolete": {
   "Discount sale": P(["LIST", "DISCOUNT", "SELL"], .60, .40, "price", .01, 45, True,
        "Frees warehouse space", "None", ["Sales head"], ["Buyer demand at discount"]),
   "Bundle with active SKUs": P(["BUNDLE", "OFFER", "SELL"], .40, .55, "price", .02, 60, True,
        "Complicates order picking", "None", ["Sales head"], ["Compatible active SKUs"]),
   "Salvage / recycle": P(["ASSESS", "RECYCLE", "DOCUMENT LOSS"], .90, .08, "book", .01, 14, False,
        "None", "Disposal records", ["Finance controller"], [])},
 "expired": {
   "Salvage / recycle": P(["ASSESS", "SALVAGE", "DOCUMENT LOSS"], .90, .03, "book", .03, 14, False,
        "None", "Safe disposal of expired material", ["Finance controller"], ["Disposal vendor quote"])},
 "supplier_dispute": {
   "Return & recover": P(["RETURN", "NEGOTIATE", "RECOVER"], .60, .85, "book", .03, 30, False,
        "None", "Dispute documentation", ["Procurement head"], ["Delivery receipts"]),
   "Discounted sale": P(["LIST", "DISCOUNT", "SELL"], .50, .70, "price", .01, 30, True,
        "May weaken dispute position", "Legal check on disputed goods", ["Procurement head", "Legal"],
        ["Dispute status"])},
 "missing_docs": {
   "Regularise documents & resell": P(["DOCUMENT", "VERIFY", "RESELL"], .70, .95, "price", .02, 15, True,
        "Delay until paperwork cleared", "Customs / import documents must be complete",
        ["Compliance officer"], ["Bill of entry copy"])},
 "customer_specific": {
   "Customer buy-back": P(["NEGOTIATE", "AGREE PRICE", "RECOVER"], .50, .50, "book", 0.0, 30, False,
        "Relationship dependent", "Contract terms", ["Sales head"], ["Customer's future demand"]),
   "Rework for other buyer": P(["REWORK", "FIND BUYER", "SELL"], .35, .60, "price", .12, 40, True,
        "Uses workshop capacity", "Check customer IP on drawings", ["QA manager", "Sales head"],
        ["Rework feasibility"]),
   "Salvage": P(["ASSESS", "SALVAGE", "DOCUMENT LOSS"], .90, .10, "book", .02, 14, False,
        "None", "Scrap documentation", ["Finance controller"], [])},
}
WRITE_OFF = dict(steps=["ASSESS", "WRITE OFF", "DOCUMENT LOSS"], prob=1.0, gross_pct=0, basis="book",
                 cost_pct=0, days=7, sells=False, impact="None",
                 compliance="Accounting adjustment; not a cash inflow", approvals=["Finance controller"],
                 missing=[])


def rescue_options(b):
    """Return applicable pathways with economics. Restricted/expired stock never gets a sale path."""
    if b["status"] != "held":
        return dict(options=[], recommendation="Not a held batch.", loss=0)
    table = dict(PATHWAYS.get(b["hold_status"], {}))
    if b["expired"] and not table:
        table = dict(PATHWAYS["expired"])
    out = []
    for name, p in table.items():
        if p["sells"] and (b["restricted"] or b["expired"]):
            continue                       # safety rule: never sell restricted/expired stock
        base = b["qty"] * (b["selling_price"] if p["basis"] == "price" else b["unit_cost"])
        gross = int(base * p["gross_pct"])
        cost = int(b["book_value"] * p["cost_pct"])
        out.append(dict(name=name, steps=p["steps"], gross=gross, cost=cost, prob=p["prob"],
                        net=int(gross * p["prob"]) - cost, days=p["days"], impact=p["impact"],
                        compliance=p["compliance"], approvals=p["approvals"], missing=p["missing"],
                        confidence=f"{int(p['prob']*100)}% success is an ASSUMPTION"))
    out.append(dict(name="Write-off", steps=WRITE_OFF["steps"], gross=0, cost=0, prob=1.0, net=0,
                    days=7, impact="None", compliance=WRITE_OFF["compliance"],
                    approvals=WRITE_OFF["approvals"], missing=[],
                    confidence="Accounting adjustment, NOT cash"))
    best = max((o for o in out if o["name"] != "Write-off"), key=lambda o: o["net"], default=None)
    if best is None or best["net"] <= 0:
        rec = "No feasible cash recovery: minimise loss (write-off / salvage documentation)."
        best = None
    else:
        rec = f"Best expected net recovery: {best['name']}."
    return dict(options=out, recommendation=rec, best=best, loss=b["book_value"])
