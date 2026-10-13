"""Reports: CSV + printable HTML. Each states date, scope, assumptions, limitations, and actual/estimated/simulated."""
import csv
import html
import os
from datetime import datetime

from .money import fmt_lakh
from .engine import inventory as inv

KINDS = ["Network risk", "Crisis propagation", "Cash-flow forecast", "Inventory intelligence",
         "Inventory rescue", "Funding comparison", "Recovery plan", "Scenario comparison"]
L = fmt_lakh


def build(ws, kind, cid):
    st = ws.state()
    name = st.companies[cid]["name"] if cid in st.companies else "-"
    meta = dict(kind=kind, company=name, generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                as_of=str(ws.as_of), synthetic=ws.is_demo())
    tables, notes, assume = [], [], ["Deterministic model; payers pay only from cash on hand.",
                                     "Money in rupees (shown in lakh); amounts stored as integer paise."]
    limits = ["Modeled results are not predictions.", "Success probabilities and discounts are assumptions."]
    if kind == "Network risk":
        g = ws.graph_data()
        tables.append(("Companies [ACTUAL data, DERIVED metrics]",
                       ["Company", "Type", "Receivables", "Payables", "Customer HHI", "Supplier HHI", "Downstream share"],
                       [[n["name"], n["type"], L(n["receivables"]), L(n["payables"]),
                         "n/a" if n["cust_hhi"] is None else f"{n['cust_hhi']:.2f}",
                         "n/a" if n["sup_hhi"] is None else f"{n['sup_hhi']:.2f}",
                         f"{n['importance']['downstream_share']:.0%}"] for n in g["nodes"]]))
        nm = {n["id"]: n["name"] for n in g["nodes"]}
        tables.append(("Relationships", ["Payer", "Payee", "Amount", "Due", "Criticality", "Alternative"],
                       [[nm[e["payer"]], nm[e["payee"]], L(e["amount"]), e["due"], e["criticality"],
                         "yes" if e["alt"] else "no"] for e in g["edges"]]))
        assume.append("HHI = sum of squared counterparty shares. Connectivity != distress.")
    elif kind in ("Crisis propagation", "Scenario comparison"):
        res = ws.last_result
        if not res:
            notes.append("No scenario has been run. Run one in the Crisis Simulator first.")
        else:
            p = res["params"]
            tables.append(("Scenario summary [SIMULATED]", ["Item", "Value"],
                           [["Initial shock", L(res["initial_shock"])], ["Direct", ", ".join(res["direct"])],
                            ["Indirect", ", ".join(res["indirect"]) or "none"],
                            ["Total modeled exposure", L(res["total_exposure"])],
                            ["Earliest shortage", res["earliest_shortage"] or "none"],
                            ["Delay / paid % / default", f"{p.get('delay_days')}d / {p.get('paid_pct')}% / {p.get('default')}"]]))
            tables.append(("Affected companies [SIMULATED]", ["Company", "Role", "Wave", "Baseline shortfall", "Stressed shortfall", "First breach"],
                           [[c["name"], c["role"], c["wave"], L(c["baseline_peak_shortfall"]), L(c["stressed_peak_shortfall"]),
                             c["first_breach_date"] or "-"] for c in res["companies"]]))
            tables.append(("Propagation path [SIMULATED]", ["Wave", "Payer", "Payee", "Amount", "Delay (days)"],
                           [[e["wave"], st.companies[e["payer"]]["name"], st.companies[e["payee"]]["name"], L(e["amount"]), e["delay_days"]]
                            for e in res["propagation"]]))
        if kind == "Scenario comparison":
            sv = ws.saved_scenarios()
            tables.append(("Saved scenarios [SIMULATED]", ["Name", "Kind", "Shock", "Total exposure", "Affected"],
                           [[s["name"], s["params"].get("kind", "stress"), L(s["result"]["initial_shock"]),
                             L(s["result"]["total_exposure"]), len(s["result"]["companies"])] for s in sv]))
    elif kind == "Cash-flow forecast":
        v = ws.cash_view(cid, 30)
        tables.append((f"{name} cash summary, 30 days [ACTUAL opening / ESTIMATED flows]", ["Item", "Amount"],
                       [[a, L(b)] for a, b in v["summary"]]))
        rows = [[ws.date_of(d), L(v["base"][d]), "" if not v["stress"] else L(v["stress"][d])] for d in range(0, len(v["base"]), 3)]
        tables.append(("Projected balance every 3 days [ESTIMATED / SIMULATED]", ["Date", "Baseline", "Stress"], rows))
        assume.append("Unapproved inventory sales and loans are never counted as cash.")
    elif kind == "Inventory intelligence":
        bs = ws.batches(cid)
        tables.append(("Batches [ACTUAL qty/cost, ESTIMATED recovery]",
                       ["SKU", "Status", "Qty", "Book value", "Cover (d)", "Action", "Potential cash (low-high)", "Why"],
                       [[b["sku"], b["status"], b["qty"], L(b["book_value"]),
                         "n/a" if b["cover_days"] is None else f"{b['cover_days']:.0f}",
                         inv.recommendation(b)["action"],
                         f"{L(inv.recommendation(b)['cash_low'])} - {L(inv.recommendation(b)['cash_high'])}",
                         inv.recommendation(b)["reason"]] for b in bs]))
    elif kind == "Inventory rescue":
        rows = []
        for b in ws.batches(cid):
            if b["status"] == "held":
                r = inv.rescue_options(b)
                for o in r["options"]:
                    rows.append([b["sku"], b["hold_status"], o["name"], " > ".join(o["steps"]), L(o["gross"]), L(o["cost"]),
                                 L(o["net"]), o["days"], "; ".join(o["approvals"]), "; ".join(o["missing"]) or "-"])
        tables.append(("Rescue options [ESTIMATED]", ["SKU", "Hold", "Path", "Steps", "Gross", "Cost", "Expected net", "Days", "Approvals", "Missing info"], rows))
        notes.append("Write-off is an accounting adjustment, not cash. Restricted/expired stock is never offered for sale.")
    elif kind == "Funding comparison":
        gap = ws.recovery(cid)["gap"] or 10_000_000
        opts = ws.funding_compare(cid, gap)
        tables.append((f"Options for {L(gap)} [ILLUSTRATIVE - not offers]",
                       ["Option", "Net proceeds", "Fee", "Interest", "Total repayment", "Days to funds", "Collateral"],
                       [[o["name"], L(o["net_proceeds"]), L(o["fee"]), L(o["interest"]), L(o["total_repayment"]),
                         o["days_to_funds"], o["collateral"]] for o in opts]))
        limits.append("LiquidityX is not a lender or regulated financial adviser.")
    elif kind == "Recovery plan":
        r = ws.recovery(cid)
        if not r["plans"]:
            notes.append("No projected cash gap, so no recovery plan is required.")
        for k, p in r["plans"].items():
            rows = [[a["date"], a["name"], a["status"], L(a["expected_cash"]), L(a["expected_relief"]), L(a["cost"])] for a in p["actions"]]
            if p["financing"]:
                f = p["financing"]
                rows.append([f["date"], f"Financing: {f['name']} (ILLUSTRATIVE, unapproved)", "awaiting approval", L(f["net_proceeds"]), L(0), L(f["total_cost"])])
            tables.append((f"{p['label']} - {'SOLVED' if p['solved'] else 'NOT SOLVED'} [ESTIMATED]",
                           ["Date", "Action", "Status", "Expected cash", "Relief (not cash)", "Cost"], rows))
            notes.append(f"{p['label']}: {p['why']}")
    return dict(meta=meta, tables=tables, notes=notes, assumptions=assume, limitations=limits)


def to_csv(rep, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["LiquidityX report", rep["meta"]["kind"], rep["meta"]["company"], rep["meta"]["generated"]])
        for title, head, rows in rep["tables"]:
            w.writerow([]); w.writerow([title]); w.writerow(head)
            w.writerows(rows)


def to_html(rep, path):
    m = rep["meta"]
    e = html.escape
    parts = [f"<h1>LIQUIDITYX — {e(m['kind'])}</h1><p class=meta>Company/scope: {e(m['company'])} · Generated {m['generated']} · "
             f"Data as of {m['as_of']}{' · <b class=warn>SYNTHETIC DEMO DATA</b>' if m['synthetic'] else ''}</p>",
             "<p class=meta>Legend: ACTUAL = recorded data · ESTIMATED = model/assumption · SIMULATED = hypothetical scenario.</p>"]
    for title, head, rows in rep["tables"]:
        parts.append(f"<h2>{e(title)}</h2><table><tr>{''.join(f'<th>{e(str(h))}</th>' for h in head)}</tr>")
        parts += ["<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in r) + "</tr>" for r in rows]
        parts.append("</table>")
    for t, items in (("Notes & recommendations", rep["notes"]), ("Calculation assumptions", rep["assumptions"]),
                     ("Data limitations", rep["limitations"])):
        if items:
            parts.append(f"<h2>{t}</h2><ul>" + "".join(f"<li>{e(i)}</li>" for i in items) + "</ul>")
    css = ("body{font:14px Inter,Segoe UI,Arial;background:#fff;color:#101827;margin:32px}h1{color:#0b5c75}"
           "table{border-collapse:collapse;width:100%;margin:8px 0}td,th{border:1px solid #cdd5e0;padding:5px 8px;text-align:left}"
           "th{background:#eef3f9}.meta{color:#566}.warn{color:#b3261e}@media print{body{margin:10mm}}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"<!doctype html><meta charset=utf-8><title>{e(m['kind'])}</title><style>{css}</style>" + "".join(parts))
