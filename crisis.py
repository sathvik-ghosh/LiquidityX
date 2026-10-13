"""Crisis cascade: run baseline and stressed sims with the SAME engine and diff them.

Propagation edge = an invoice that was NOT shocked but is paid later (or left unpaid)
in the stressed run versus baseline. Only these edges are reported/animated.
"""
import json
from datetime import datetime, timezone, timedelta

from .cashflow import simulate, shortfall_profile, Shock, ExpenseShock


def run_scenario(state, shocks, expenses=(), horizon=90):
    base = simulate(state, horizon)
    stress = simulate(state, horizon, shocks, expenses)
    shocked_ids = {s.invoice_id for s in shocks}
    inv = {i["id"]: i for i in state.invoices}
    name = lambda c: state.companies[c]["name"]

    edges = []
    for i, v in inv.items():
        if i in shocked_ids:
            continue
        b, s = base.invoice_paid_day[i], stress.invoice_paid_day[i]
        late = (s is None and b is not None) or (s is not None and b is not None and s > b)
        if late:
            delay = (horizon + 1 - b) if s is None else s - b
            edges.append(dict(invoice_id=i, payer=v["payer"], payee=v["payee"], amount=v["amount"],
                              baseline_day=b, stressed_day=s, delay_days=delay))
    edges.sort(key=lambda e: (e["stressed_day"] if e["stressed_day"] is not None else horizon + 1,
                              e["invoice_id"]))

    # propagation order: BFS depth from the initial payee(s)
    depth = {inv[s]["payee"]: 0 for s in shocked_ids}
    changed = True
    while changed:
        changed = False
        for e in edges:
            if e["payer"] in depth and e["payee"] not in depth:
                depth[e["payee"]] = depth[e["payer"]] + 1
                changed = True
    for e in edges:
        e["wave"] = depth.get(e["payee"])
    edges = [e for e in edges if e["wave"] is not None]  # drop edges not linked to the shock
    for e in edges:
        depth.setdefault(e["payee"], e["wave"])

    companies = []
    for cid in state.companies:
        bp, bf, _ = shortfall_profile(state, base, cid)
        sp, sf, _ = shortfall_profile(state, stress, cid)
        extra = max(0, sp - bp)
        affected = cid in depth or extra > 0
        if affected:
            companies.append(dict(
                company_id=cid, name=name(cid),
                role="direct" if depth.get(cid) == 0 else "indirect",
                wave=depth.get(cid), baseline_peak_shortfall=bp, stressed_peak_shortfall=sp,
                extra_shortfall=extra, first_breach_date=(
                    None if sf is None else (state.as_of + timedelta(days=sf)).isoformat())))
    companies.sort(key=lambda c: (c["wave"] is None, c["wave"] or 0, c["company_id"]))
    shock_amount = sum(inv[s.invoice_id]["amount"] * (100 - s.paid_pct) // 100 for s in shocks)
    breaches = [c["first_breach_date"] for c in companies if c["first_breach_date"]]
    return dict(
        horizon=horizon, initial_shock=shock_amount,
        direct=[c["name"] for c in companies if c["role"] == "direct"],
        indirect=[c["name"] for c in companies if c["role"] == "indirect"],
        companies=companies, propagation=edges,
        total_exposure=sum(c["extra_shortfall"] for c in companies),
        earliest_shortage=min(breaches) if breaches else None,
        unaffected=[name(c) for c in state.companies if c not in {x["company_id"] for x in companies}],
        assumptions=["Deterministic; payers pay only from cash on hand.",
                     "Shortfall = max(0, min_cash - balance).",
                     "Demo data is synthetic; results are modeled, not predictions."],
    )


def save_scenario(conn, name, params: dict, result: dict):
    with conn:
        conn.execute("INSERT INTO scenarios(name,params_json,result_json,created_at) VALUES(?,?,?,?)",
                     (name, json.dumps(params, sort_keys=True), json.dumps(result, sort_keys=True),
                      datetime.now(timezone.utc).isoformat()))
