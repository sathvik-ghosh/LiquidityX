"""LIQUIDITYX COPILOT - deterministic, rule-based. Every answer is computed from workspace data."""
import re
from .money import fmt_lakh
from .engine import inventory as inv, cashflow as cf
from .engine.cashflow import Shock

EXAMPLES = [
    "Which company is most exposed to late payments?",
    "What happens if Apex Motors pays 30 days late?",
    "Which stock should I investigate first?",
    "Why is BPC-GR-310 blocked?",
    "What can we do with BPC-RB-070?",
    "How much cash is required by the end of next week?",
    "Which recovery plan has the lowest estimated cost?",
    "Which suppliers could be affected by Apex Motors?",
]


def _find_company(ws, q):
    for c in sorted(ws.companies(), key=lambda c: -len(c["name"])):
        if c["name"].lower() in q.lower() or c["name"].split()[0].lower() in q.lower().split():
            return c
    return None


def _find_batch(ws, q):
    for b in ws.batches():
        if b["sku"].lower() in q.lower():
            return b
    return None


def _delay(q, default=30):
    m = re.search(r"(\d+)\s*(?:days?|d)\b", q)
    return int(m.group(1)) if m else default


def _cascade_for_customer(ws, comp, days):
    st = ws.state()
    shocks = [Shock(i["id"], days, 0) for i in st.invoices if i["payer"] == comp["id"]]
    if not shocks:
        return None
    from .engine.crisis import run_scenario
    return run_scenario(st, shocks, (), 90)


def answer(ws, cid, q):
    ql = q.lower().strip()
    if not ws.has_data():
        return "The workspace is empty. Import data or load the demo network first."
    if "most exposed" in ql or "late payment" in ql and "which" in ql:
        st = ws.state()
        base = cf.simulate(st, 90)
        rows = []
        for c, info in st.companies.items():
            rec = sum(i["amount"] for i in st.invoices if i["payee"] == c)
            buf = max(base.balances[c][0] - info["min_cash"], 0)
            if rec:
                rows.append((rec / max(buf, 1), info["name"], rec, buf))
        rows.sort(reverse=True)
        top = rows[:3]
        return "Most exposed = open receivables relative to cash above the minimum buffer:\n" + "\n".join(
            f"• {n}: receivables {fmt_lakh(r)} vs buffer {fmt_lakh(b)}" for _, n, r, b in top)
    if ("what happens" in ql or "pays" in ql and "late" in ql) and _find_company(ws, q):
        comp = _find_company(ws, q)
        res = _cascade_for_customer(ws, comp, _delay(q))
        if res is None:
            return f"{comp['name']} has no open payables in the data, so a late payment cannot be modeled."
        names = ", ".join(res["indirect"]) or "none"
        return (f"If {comp['name']} pays {_delay(q)} days late (all open invoices, modeled): "
                f"initial shock {fmt_lakh(res['initial_shock'])}; direct: {', '.join(res['direct']) or 'none'}; "
                f"indirect: {names}; total modeled exposure {fmt_lakh(res['total_exposure'])}; earliest shortage "
                f"{res['earliest_shortage'] or 'none'}. Modeled, not a prediction.")
    if "suppliers" in ql and "affected" in ql:
        comp = _find_company(ws, q)
        if comp:
            res = _cascade_for_customer(ws, comp, _delay(q))
            if res:
                return "Companies hit downstream (30-day delay): " + (", ".join(res["direct"] + res["indirect"]) or "none")
        return "Name the customer or disruption source, e.g. 'Which suppliers could be affected by Apex Motors?'"
    if "investigate first" in ql or "which stock" in ql:
        held = sorted([b for b in ws.batches(cid) if b["status"] == "held"], key=lambda b: -b["book_value"])
        if not held:
            return "No held stock for this company."
        b = held[0]
        return (f"Start with {b['sku']} ({b['description']}): {fmt_lakh(b['book_value'])} blocked. "
                f"Reason: {b['hold_reason'] or b['hold_status']}. It is the largest blocked batch.")
    if "why" in ql and "block" in ql:
        b = _find_batch(ws, q)
        if not b:
            return "Tell me the SKU, e.g. 'Why is BPC-GR-310 blocked?'"
        if b["status"] != "held":
            return f"{b['sku']} is not blocked (status: {b['status']})."
        return f"{b['sku']} is on {b['hold_status']} hold: {b['hold_reason']}" + (
            f" Deadline {b['hold_deadline']}." if b["hold_deadline"] else "")
    if "unsellable" in ql or "what can we do" in ql or "rescue" in ql:
        b = _find_batch(ws, q)
        if not b:
            return "Tell me the SKU of the held batch, e.g. 'What can we do with BPC-RB-070?'"
        r = inv.rescue_options(b)
        if not r["options"]:
            return f"{b['sku']} is not held; use sell/retain analysis instead."
        lines = [f"• {o['name']}: net {fmt_lakh(o['net'])}, ~{o['days']}d" for o in r["options"]]
        return r["recommendation"] + "\n" + "\n".join(lines)
    if "required" in ql or "next week" in ql:
        st = ws.state()
        res = cf.simulate(st, 90, *ws.stress_args()[:2])
        out = sum(res.outflow[cid][:8])
        low = min(res.balances[cid][:8])
        need = max(0, st.companies[cid]["min_cash"] - low)
        return (f"{st.companies[cid]['name']}: scheduled outflows over 7 days {fmt_lakh(out)}; lowest projected "
                f"balance {fmt_lakh(low)} vs minimum {fmt_lakh(st.companies[cid]['min_cash'])}. "
                f"Extra cash needed to stay at minimum: {fmt_lakh(need)}.")
    if "lowest" in ql and ("cost" in ql or "plan" in ql):
        r = ws.recovery(cid)
        if not r["plans"]:
            return "No cash gap in the current scenario, so no recovery plan is needed. Run a crisis scenario first."
        p = r["plans"].get("lowest_cost") or r["plans"]["best_effort"]
        return (f"{p['label']}: cost {fmt_lakh(p['cost'])}, finishes by day {p['last_day']}, "
                f"{'covers' if p['solved'] else 'does NOT cover'} the {fmt_lakh(p['gap'])} gap. "
                f"Actions: {', '.join(a['name'] for a in p['actions']) or 'none'}"
                f"{' + ' + p['financing']['name'] if p['financing'] else ''}.")
    return "I can answer questions like:\n" + "\n".join("• " + e for e in EXAMPLES)
