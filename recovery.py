"""Recovery planner. Builds candidate actions, enumerates combinations, ranks three plans.

Honesty rules enforced here:
* Only actions that land on/before the deadline (first projected breach) count toward the gap.
* Payment extensions are RELIEF, never "cash received".
* Sale/rescue/financing amounts are expected (probability-weighted), never confirmed cash.
* Each action is used once (no double counting); financing is sized only for the residual.
* If the gap is not covered by the deadline the plan is flagged NOT SOLVED.
"""
from datetime import timedelta
from itertools import combinations

from dataclasses import replace
from .cashflow import simulate, shortfall_profile
from .funding import size_for_net, DEFAULTS
from . import inventory as inv

P_COLLECT, P_EXTENSION, P_SALE, P_FINANCE = .60, .50, .70, .60
EXT_DAYS = 15


def _act(id, name, kind, day, cash, relief, cost, risk, approval, detail):
    return dict(id=id, name=name, kind=kind, day=day, expected_cash=int(cash), expected_relief=int(relief),
                cost=int(cost), risk=risk, requires_approval=approval, detail=detail)


def candidate_actions(state, conn, as_of, cid, deadline, crit_by_pair):
    acts = []
    # a) accelerate overdue receivables (only if currently expected AFTER the deadline)
    for i in state.invoices:
        if i["payee"] == cid and i["due"] < 0 and i["pay_day"] > deadline:
            payer = state.companies[i["payer"]]["name"]
            acts.append(_act(f"collect-{i['id']}", f"Chase overdue invoice from {payer}", "collect", 3,
                             i["amount"] * P_COLLECT, 0, i["amount"] * .01, .10, False,
                             f"Overdue; currently expected on day {i['pay_day']}. {int(P_COLLECT*100)}% "
                             f"chance of collection by day 3 (assumption), 1% concession cost."))
    # b) sell surplus inventory, c) rescue blocked stock
    batches = inv.load_batches(conn, as_of, cid)
    sells, rescues = [], []
    for b in batches:
        r = inv.recommendation(b)
        if r["action"] == "sell" and r["days"] <= deadline and r["cash_low"] > 0:
            sells.append(_act(f"sell-{b['id']}", f"Sell surplus {b['sku']} ({r['sellable_qty']} units)", "sell",
                              r["days"], r["cash_low"] * P_SALE, 0, 0, .30 if b["critical"] else .05, False,
                              r["reason"] + " Conservative (low) price case; buyer unconfirmed."))
        if b["status"] == "held":
            ro = inv.rescue_options(b)
            best = ro.get("best")
            if best and best["net"] > 0 and best["days"] <= deadline:
                rescues.append(_act(f"rescue-{b['id']}", f"{best['name']}: {b['sku']}", "rescue", best["days"],
                                    best["net"], 0, 0, .15, True,
                                    f"Net after costs, success prob {int(best['prob']*100)}% already included. "
                                    f"Approvals: {', '.join(best['approvals'])}."))
    sells.sort(key=lambda a: -a["expected_cash"]); rescues.sort(key=lambda a: -a["expected_cash"])
    acts += sells[:3] + rescues[:4]
    # d) payment extensions on supplier invoices due by the deadline (relief, not cash)
    ext = []
    for i in state.invoices:
        if i["payer"] == cid and i["pay_day"] <= deadline:
            crit, alt = crit_by_pair.get((i["payer"], i["payee"]), (3, 0))
            p = P_EXTENSION * (0.6 if crit >= 4 and not alt else 1)
            payee = state.companies[i["payee"]]["name"]
            ext.append(_act(f"extend-{i['id']}", f"Ask {payee} for {EXT_DAYS}-day extension", "extension", 1,
                            0, i["amount"] * p, 0, min(.6, crit / 8), False,
                            f"Relief only (not cash received). Criticality {crit}/5"
                            f"{'' if alt else ', no alternative supplier'}; success {int(p*100)}%."))
    ext.sort(key=lambda a: -a["expected_relief"])
    return acts + ext[:3]


def plan_for(state, conn, as_of, cid, shocks=(), expenses=(), funding=None, horizon=90):
    funding = funding or DEFAULTS
    res = simulate(state, horizon, shocks, expenses)
    gap, first, _ = shortfall_profile(state, res, cid)
    name = state.companies[cid]["name"]
    out = dict(company=name, company_id=cid, gap=gap, deadline_day=first, plans={}, notes=[])
    if gap == 0:
        out["notes"].append("No projected cash gap in this scenario; no recovery plan required.")
        return out
    deadline = first
    out["deadline_date"] = (as_of + timedelta(days=deadline)).isoformat()
    crit = {(r["payer_id"], r["payee_id"]): (r["criticality"], r["alternative_available"])
            for r in conn.execute("SELECT * FROM relationships")}
    acts = candidate_actions(state, conn, as_of, cid, deadline, crit)
    ids = {a["id"] for a in acts}
    out["later"] = sorted([a for a in candidate_actions(state, conn, as_of, cid, horizon, crit)
                           if a["id"] not in ids and a["day"] > deadline and a["expected_cash"] > 0],
                          key=lambda a: a["day"])[:6]
    if deadline < 1:
        out["notes"].append("Gap is immediate (day 0): few actions can land in time.")
    cands = []
    for k in range(len(acts) + 1):
        for sub in combinations(acts, k):
            cash = sum(a["expected_cash"] for a in sub)
            relief = sum(a["expected_relief"] for a in sub)
            residual = max(0, gap - cash - relief)
            base = dict(actions=list(sub), cash=cash, relief=relief,
                        cost=sum(a["cost"] for a in sub), risk=sum(a["risk"] for a in sub),
                        day=max((a["day"] for a in sub), default=0), financing=None, residual=residual)
            if residual == 0:
                cands.append(base)
                continue
            cands.append(base)                       # partial plan (kept for the not-solved fallback)
            for fname, a in funding.items():
                if a["days_to_funds"] <= deadline:
                    f = size_for_net(fname, a, residual / P_FINANCE)
                    c = dict(base); c["financing"] = f; c["residual"] = 0
                    c["cost"] += f["total_cost"]; c["day"] = max(c["day"], f["days_to_funds"])
                    c["risk"] += .2
                    cands.append(c)
    feasible = [c for c in cands if c["residual"] == 0]

    def verify(c):
        """Re-simulate with the plan applied: repayments/deferrals may create a LATER shortfall."""
        if "post" not in c:
            tx = plan_txns(dict(actions=c["actions"], financing=c["financing"]), cid)
            st2 = replace(state, txns=state.txns + tx)
            pk, fb, _ = shortfall_profile(st2, simulate(st2, horizon, shocks, expenses), cid)
            c["post"] = (pk, fb)
        return c["post"]
    # verify the cheapest and fastest candidates only (keeps planning fast)
    pool = {id(c): c for c in sorted(feasible, key=lambda c: (c["cost"], c["day"]))[:60]}
    pool.update({id(c): c for c in sorted(feasible, key=lambda c: (c["day"], c["cost"]))[:40]})
    for c in pool.values():
        verify(c)
    verified = list(pool.values())
    sustainable = [c for c in verified if c["post"][0] <= gap]      # no worse than doing nothing
    if sustainable:
        feasible = sustainable
    elif verified:
        best_post = min(c["post"][0] for c in verified)
        feasible = [c for c in verified if c["post"][0] == best_post]
        out["notes"].append("Every plan leaves a later shortfall (repayments/deferrals fall before delayed cash returns).")
    if not feasible:
        best = max(cands, key=lambda c: (c["cash"] + c["relief"], -c["cost"]))
        out["plans"]["best_effort"] = _finish("Best effort (gap NOT solved)", best, gap, deadline, as_of,
                                              "No combination covers the gap by the deadline.")
        out["notes"].append("The cash gap cannot be covered by the deadline with the available actions.")
        return out
    n = lambda c: len(c["actions"]) + (1 if c["financing"] else 0)
    lo = min(feasible, key=lambda c: (c["cost"], c["day"], n(c)))
    fast = min(feasible, key=lambda c: (c["day"], c["cost"], n(c)))
    mx = lambda key: max(max(c[key] for c in feasible), 1)
    mc, md, mr = mx("cost"), mx("day"), mx("risk")
    bal = min(feasible, key=lambda c: (c["cost"] / mc + c["day"] / md + c["risk"] / mr + c["post"][0] / max(gap, 1), n(c)))
    out["plans"]["lowest_cost"] = _finish("Lowest-cost feasible", lo, gap, deadline, as_of,
                                          "Smallest total cost among plans that cover the gap by the deadline.")
    out["plans"]["fastest"] = _finish("Fastest feasible", fast, gap, deadline, as_of,
                                      "Earliest last action among plans that cover the gap.")
    out["plans"]["balanced"] = _finish("Balanced", bal, gap, deadline, as_of,
                                       "Best equal-weight trade-off of cost, time, operational risk and the shortfall left after repayments.")
    return out


def _finish(label, c, gap, deadline, as_of, why):
    acts = []
    for a in c["actions"]:
        a = dict(a)
        a["date"] = (as_of + timedelta(days=a["day"])).isoformat()
        a["status"] = "awaiting approval" if a["requires_approval"] else "can start now"
        acts.append(a)
    f = c["financing"]
    if f:
        f = dict(f)
        f["date"] = (as_of + timedelta(days=f["days_to_funds"])).isoformat()
    post = c.get("post", (None, None))
    return dict(label=label, why=why, post_peak=post[0], post_first=post[1], actions=acts, financing=f, gap=gap, deadline_day=deadline,
                expected_cash=c["cash"], expected_relief=c["relief"], cost=int(c["cost"]),
                risk=round(c["risk"], 2), last_day=c["day"], residual=c["residual"],
                solved=c["residual"] == 0)


def plan_txns(plan, cid):
    """Hypothetical cash events for a 'recovery case' simulation (expected values, unapproved)."""
    t = []
    for a in plan["actions"]:
        if a["expected_cash"]:
            t.append(dict(company=cid, day=a["day"], amount=a["expected_cash"]))
        if a["expected_relief"]:     # deferral: keep cash now, pay later
            t.append(dict(company=cid, day=a["day"], amount=a["expected_relief"]))
            t.append(dict(company=cid, day=a["day"] + EXT_DAYS, amount=-a["expected_relief"]))
    f = plan.get("financing")
    if f:
        t.append(dict(company=cid, day=f["days_to_funds"], amount=int(f["net_proceeds"] * P_FINANCE)))
        for d, x in f["schedule"]:
            t.append(dict(company=cid, day=d, amount=-int(x * P_FINANCE)))
    return t
