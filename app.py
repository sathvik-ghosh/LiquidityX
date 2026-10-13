"""LIQUIDITYX web app (Streamlit).  Run locally:  streamlit run app.py
Each visitor gets a private in-memory workspace loaded with SYNTHETIC demo data (nothing is shared or stored)."""
import json
import os
import tempfile

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from liquidityx import copilot, reports, webviz as wv, commercial
from liquidityx.db import get_setting, set_setting
from liquidityx.engine import funding as fd, inventory as inv
from liquidityx.money import fmt_lakh as L, lakh, PAISE_PER_LAKH
from liquidityx.service import Workspace

st.set_page_config(page_title="LIQUIDITYX", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
.block-container{padding-top:1.4rem} h1,h2,h3{letter-spacing:.2px}
.chip{display:inline-block;padding:3px 10px;margin:2px;border:1px solid #43D9FF;border-radius:6px;color:#43D9FF;font-size:.8rem;font-weight:700}
.chip.g{border-color:#4DE2B1;color:#4DE2B1}.chip.a{border-color:#FFBF69;color:#FFBF69}
.note{color:#98A6BC;font-size:.85rem}
</style>""", unsafe_allow_html=True)

PAGES = ["Command Center", "Financial Network", "Crisis Simulator", "Cash Intelligence", "Inventory Intelligence", "Inventory Rescue",
         "Funding Navigator", "Recovery Planner", "Reports", "Copilot", "Commercial & About"]


def show(fig):
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:
        st.plotly_chart(fig, use_container_width=True)


def table(df):
    try:
        st.dataframe(df, hide_index=True, width="stretch")
    except TypeError:
        st.dataframe(df, hide_index=True, use_container_width=True)


def get_ws():
    if "ws" not in st.session_state:
        w = Workspace(); w.load_demo()
        st.session_state.ws = w
    return st.session_state.ws


ws = get_ws()
companies = ws.companies()
names = {c["id"]: c["name"] for c in companies}

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("## ◈ LIQUIDITYX")
    st.caption("OBSIDIAN TERMINAL · See the crisis before it spreads.")
    page = st.radio("Navigate", PAGES, label_visibility="collapsed")
    st.divider()
    default = ws.default_focus()
    cid = st.selectbox("Focus company", list(names), format_func=names.get, index=list(names).index(default))
    saved = ws.saved_scenarios()
    opts = ["Baseline"] + [s["name"] for s in saved]
    cur = "Baseline" if not ws.last_result else st.session_state.get("scn_name", "Baseline")
    pick = st.selectbox("Scenario", opts, index=opts.index(cur) if cur in opts else 0)
    if pick != cur:
        if pick == "Baseline":
            ws.clear_scenario()
        else:
            ws.run_crisis(next(s for s in saved if s["name"] == pick)["params"])
        st.session_state["scn_name"] = pick; st.rerun()
    r = ws.last_result
    if r:
        st.error(f"Stressed · exposure {L(r['total_exposure'])} · {len(r['companies'])} affected")
    else:
        st.success("Baseline (no scenario)")
    st.warning("SYNTHETIC DEMO DATA. Modeled results, not predictions. Not a lender or financial adviser.")
    if st.button("Reset demo workspace"):
        del st.session_state["ws"]
        for k in ("rec", "chat", "scn_name"):
            st.session_state.pop(k, None)
        st.rerun()

st.title(page)
res = ws.last_result

# ================================================================ COMMAND CENTER
if page == "Command Center":
    st.caption("Detect → Trace → Simulate → Recover → Protect → Learn. Every figure is computed by the Python engines from workspace data.")
    k = ws.kpis()
    c = st.columns(6)
    c[0].metric("Companies monitored", k["companies"], help="Companies in this workspace.")
    c[1].metric("Projected liquidity gaps", k["gaps"], help="Companies falling below minimum operating cash within 90 days (active scenario, else baseline).")
    c[2].metric("Critical relationships", k["critical"], help="Criticality ≥ 4 with no alternative available.")
    c[3].metric("Blocked inventory", L(k["blocked"]), help="Book value of held batches.")
    c[4].metric("Est. recoverable cash", L(k["recoverable"]), help="POTENTIAL recovery (probability-weighted rescue + conservative surplus sales). Not confirmed cash.")
    c[5].metric("Open recovery plans", k["plans"])
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Live financial network")
        show(wv.network_fig(ws.graph_data(), res, height=470))
        st.caption("Size = receivables + payables · shape also encodes status (○ ok, ◇ warning, ▲ shortfall) · dashed edge = alternative available · bright edge = criticality ≥ 4.")
    with right:
        st.subheader("Risk radar")
        sc = ws.risk_radar(cid)
        show(wv.radar_fig(sc))
        with st.expander("Formulas (n/a = insufficient data)"):
            for n, v, f in sc:
                st.write(f"**{n}**: {'n/a' if v is None else f'{v:.2f}'} — {f}")
    st.subheader("Action queue")
    q = ws.action_queue(cid)
    if not q:
        st.info("No actions require attention for this company.")
    for it in q:
        icon = {"critical": "🔴", "warning": "🟠"}.get(it["sev"], "🔵")
        with st.expander(f"{icon} {it['title']}"):
            st.write(it["detail"]); st.caption(f"Go to: **{it['page']}** (sidebar)")
    st.subheader("Financial stress timeline — next 30 days")
    ev = ws.timeline(cid, 30)
    if ev:
        lane = {"overdue": 4, "shortage": 5, "payment": 3, "receivable": 2, "hold": 1, "recovery": 0}
        col = {"overdue": wv.CORAL, "shortage": wv.CORAL, "payment": wv.AMBER, "receivable": wv.MINT, "hold": wv.AMBER, "recovery": wv.MINT}
        f = go.Figure(go.Scatter(x=[e[0] for e in ev], y=[lane[e[1]] for e in ev], mode="markers", marker=dict(size=14, color=[col[e[1]] for e in ev]),
                                 hovertext=[f"D+{e[0]} · {e[2]}" + (f" · {L(abs(e[3]))}" if e[3] else "") for e in ev], hoverinfo="text"))
        f.update_layout(paper_bgcolor=wv.BG, plot_bgcolor=wv.PANEL, height=240, margin=dict(l=10, r=10, t=10, b=30), font=dict(color=wv.TEXT),
                        xaxis=dict(title="Days from today", gridcolor=wv.GRID, range=[-1, 31]),
                        yaxis=dict(tickvals=list(lane.values()), ticktext=list(lane), gridcolor=wv.GRID))
        show(f)
    else:
        st.info("No upcoming events in the next 30 days.")

# ================================================================ NETWORK
elif page == "Financial Network":
    st.caption("Edges follow the direction of money (payer → payee). Network importance, financial exposure and projected liquidity risk are shown separately.")
    a, b, c3 = st.columns(3)
    types = a.multiselect("Filter by type", ["manufacturer", "supplier", "customer", "distributor", "service"])
    sel = b.selectbox("Select company (dims unrelated)", [None] + list(names), format_func=lambda i: "—" if i is None else names[i])
    mode = c3.radio("View", ["stressed", "baseline"], horizontal=True) if res else "baseline"
    data = ws.graph_data()
    t1, t2 = st.tabs(["Graph", "Table view (accessible)"])
    with t1:
        show(wv.network_fig(data, res, mode, sel, types, height=600))
    with t2:
        nm = {n["id"]: n["name"] for n in data["nodes"]}
        table(pd.DataFrame([{"Company": n["name"], "Type": n["type"], "Status": n["status"], "Receivables": L(n["receivables"]), "Payables": L(n["payables"]),
                             "Customer HHI": "n/a" if n["cust_hhi"] is None else f"{n['cust_hhi']:.2f}", "Supplier HHI": "n/a" if n["sup_hhi"] is None else f"{n['sup_hhi']:.2f}",
                             "Betweenness": round(n["importance"]["betweenness"], 2), "Downstream reach": f"{n['importance']['downstream_share']:.0%}"} for n in data["nodes"]]))
        table(pd.DataFrame([{"Payer": nm[e["payer"]], "Payee": nm[e["payee"]], "Amount": L(e["amount"]), "Due": e["due"], "Criticality": e["criticality"],
                             "Alternative": "yes" if e["alt"] else "no", "History": e["history"]} for e in data["edges"]]))
    if sel:
        n = next(x for x in data["nodes"] if x["id"] == sel)
        st.markdown(f"**{n['name']}** — importance (betweenness {n['importance']['betweenness']:.2f}, reaches {n['importance']['downstream_share']:.0%} of network) "
                    f"is separate from exposure ({L(n['receivables'])} receivable / {L(n['payables'])} payable) and projected status (**{n['status']}**).")

# ================================================================ CRISIS
elif page == "Crisis Simulator":
    st.caption("Stress one payment and replay the computed propagation. Only affected companies change; unaffected stay unaffected. Same inputs → same result.")
    ch = ws.invoice_choices()
    big = next((i for i, c in enumerate(ch) if "Apex Motors → Bharat" in c["label"]), 0)
    L1, R1 = st.columns([1, 2.4])
    with L1:
        i = st.selectbox("Payment under stress (supplier disruption = payment to that supplier)", range(len(ch)), index=big, format_func=lambda x: ch[x]["label"])
        preset = st.radio("Delay preset (days)", [7, 15, 30, 60, "custom"], index=2, horizontal=True)
        delay = st.number_input("Delay (days)", 0, 365, 30) if preset == "custom" else preset
        pct = st.slider("Paid on time (partial-payment %)", 0, 100, 0)
        dflt = st.checkbox("Default (late part never paid)")
        with st.expander("Unexpected expense"):
            ex_co = st.selectbox("At company", list(names), format_func=names.get, index=list(names).index(cid))
            ex_amt = st.number_input("Amount (₹ lakh)", 0.0, 1000.0, 0.0, 0.5)
            ex_day = st.number_input("On day", 0, 365, 5)
        hor = st.selectbox("Scenario duration (days)", [30, 60, 90, 180], index=2)
        if st.button("▶ Run simulation", type="primary"):
            par = dict(invoice_id=ch[i]["id"], delay_days=int(delay), paid_pct=int(pct), default=dflt, horizon=hor)
            if ex_amt > 0:
                par["expense"] = dict(company_id=ex_co, day=int(ex_day), amount=lakh(ex_amt))
            try:
                ws.run_crisis(par); st.session_state["scn_name"] = "Baseline"; st.rerun()
            except ValueError as e:
                st.error(str(e))
        if res and st.button("Clear scenario"):
            ws.clear_scenario(); st.rerun()
    with R1:
        res = ws.last_result
        if res:
            show(wv.network_fig(ws.graph_data(), res, "stressed", animate=True, height=520))
            st.caption("Press ▶ Play shock wave (or drag the Step slider). The animation replays exactly the payments the engine computed as delayed.")
        else:
            show(wv.network_fig(ws.graph_data(), None, "baseline", height=520)); st.info("Choose a payment and press Run simulation.")
    if res:
        m = st.columns(4)
        m[0].metric("Initial shock", L(res["initial_shock"])); m[1].metric("Total modeled exposure", L(res["total_exposure"]))
        m[2].metric("Earliest shortage", res["earliest_shortage"] or "none"); m[3].metric("Unaffected companies", len(res["unaffected"]))
        st.write(f"**Direct:** {', '.join(res['direct']) or '—'}  \n**Indirect:** {', '.join(res['indirect']) or '—'}")
        table(pd.DataFrame([{"Company": c["name"], "Role": c["role"], "Wave": str(c["wave"]), "Baseline shortfall": L(c["baseline_peak_shortfall"]),
                             "Stressed shortfall": L(c["stressed_peak_shortfall"]), "Extra shortfall": L(c["extra_shortfall"]), "First breach": c["first_breach_date"] or "—"} for c in res["companies"]]))
        st.caption("Assumptions: " + " ".join(res["assumptions"]) + " Limitations: simple trade-credit model; no new credit, no behavioural response.")
        n1, n2 = st.columns([3, 1])
        nm_ = n1.text_input("Save scenario as", "Stress case")
        if n2.button("Save scenario"):
            ws.save_scenario(nm_.strip() or "Scenario"); st.success("Saved"); st.rerun()
    st.subheader("Scenario comparison: baseline · stress · recovery")
    st.caption("Recovery case applies the Balanced plan's expected values (not confirmed cash) for the focus company.")
    rows = ws.case_table(cid)
    table(pd.DataFrame([{"Case": n, "Companies below min cash": m["companies_short"], "Total shortfall": L(m["total_shortfall"]),
                         "Focus peak shortfall": L(m["focus_peak"]), "Earliest breach": m["earliest"] or "—"} for n, m in rows]))
    if saved:
        st.write("Saved scenarios: " + ", ".join(f"**{s['name']}** ({L(s['result']['total_exposure'])})" for s in saved))

# ================================================================ CASH
elif page == "Cash Intelligence":
    st.caption("Daily projection from opening cash, invoice receipts/payments and scheduled transactions. Unapproved sales and loans are never counted as cash.")
    h = st.radio("Horizon (days)", [7, 30, 60, 90], index=1, horizontal=True)
    show_rec = st.checkbox("Show recovery case (Balanced plan, expected values)", disabled=res is None)
    v = ws.cash_view(cid, h)
    series = [("Baseline", v["base"], wv.CYAN, "solid")]
    if v["stress"] is not None:
        series.append(("Stress", v["stress"], wv.CORAL, "dash"))
    if show_rec and res:
        cmp_ = ws.compare_cases(cid)
        if "recovery" in cmp_:
            series.append(("Recovery (expected)", cmp_["recovery"][:h + 1], wv.MINT, "dashdot"))
    show(wv.cash_fig(v, series, h, ws.as_of)); show(wv.flows_fig(v, h))
    gb, gs = v["gap_base"], v["gap_stress"]
    st.write(f"**Baseline:** {'no shortfall' if gb[0] == 0 else f'peak shortfall {L(gb[0])} from day {gb[1]} ({gb[2]} days below minimum)'}")
    if gs:
        st.write(f"**Stress:** {'no shortfall' if gs[0] == 0 else f'peak shortfall {L(gs[0])} from day {gs[1]} ({gs[2]} days below minimum)'}")
    a, b = st.columns(2)
    with a:
        st.subheader("Cash items"); table(pd.DataFrame([{"Item": i, "Amount": L(x)} for i, x in v["summary"]]))
    with b:
        st.subheader("Major obligations"); table(pd.DataFrame([{"Date": ws.date_of(d), "Obligation": w, "Amount": L(x)} for d, w, x in v["obligations"]]))

# ================================================================ INVENTORY
elif page == "Inventory Intelligence":
    st.caption("Cash figures are POTENTIAL recovery with stated assumptions — never confirmed cash. Production reserve is protected before anything is called surplus.")
    bs = ws.batches(cid)
    if not bs:
        st.info("No inventory for this company.")
        st.stop()
    s = inv.summary(bs)
    m = st.columns(4)
    m[0].metric("Total stock", L(s["total_value"])); m[1].metric("Held", L(s["held_value"])); m[2].metric("Slow / dead", L(s["slow_value"])); m[3].metric("Surplus-sale cash (high case)", L(s["sellable_cash_high"]))
    a, b = st.columns(2)
    status = a.selectbox("Status", ["all", "normal", "surplus", "slow", "dead", "held"]); q = b.text_input("Search SKU / description / location")
    rows = [x for x in bs if (status == "all" or x["status"] == status) and q.lower() in (x["sku"] + x["description"] + x["location"]).lower()]
    table(pd.DataFrame([{"SKU": x["sku"], "Description": x["description"], "Location": x["location"], "Qty": x["qty"], "Book value": L(x["book_value"]),
                         "Cover (d)": "n/a" if x["cover_days"] is None else str(round(x["cover_days"])), "Idle (d)": x["idle_days"], "Status": x["status"],
                         "Action": inv.recommendation(x)["action"]} for x in rows]))
    cats = {}
    for x in bs:
        c = cats.setdefault(x["category"], [0, 0]); c[0] += x["book_value"]; c[1] += x["book_value"] if x["status"] == "held" else 0
    f = go.Figure([go.Bar(x=list(cats), y=[v[0] / 1e7 for v in cats.values()], name="Total book value", marker_color=wv.CYAN),
                   go.Bar(x=list(cats), y=[v[1] / 1e7 for v in cats.values()], name="of which held", marker_color=wv.CORAL)])
    f.update_layout(barmode="overlay", paper_bgcolor=wv.BG, plot_bgcolor=wv.PANEL, height=260, margin=dict(l=40, r=10, t=30, b=40), font=dict(color=wv.TEXT),
                    title="Stock distribution by category (₹ lakh)", yaxis=dict(gridcolor=wv.GRID), legend=dict(orientation="h", y=1.2))
    show(f)
    st.subheader("Batch detail")
    pick = st.selectbox("Batch", [x["id"] for x in rows] or [None], format_func=lambda i: next((f"{x['sku']} · {x['location']} · {x['description']}" for x in bs if x["id"] == i), "—"))
    if pick:
        x = next(y for y in bs if y["id"] == pick); r = inv.recommendation(x); sc_, warn = inv.scenarios(x, bs)
        st.markdown(f"**{x['sku']} — {x['description']}**  ·  {x['qty']} units · book {L(x['book_value'])} · margin {x['margin_pct']:.0f}% · age {x['age_days']}d · idle {x['idle_days']}d · "
                    f"cover {'n/a' if x['cover_days'] is None else str(round(x['cover_days'])) + 'd'} · lead time {x['lead_time_days']}d{' · CRITICAL' if x['critical'] else ''}")
        st.write("**Why:** " + r["reason"] + (f" Estimated time to cash: {r['days']} days (assumption)." if r["days"] else ""))
        sell = r["sellable_qty"] if x["status"] != "held" else 0
        parts = [("Held", x["qty"], wv.CORAL)] if x["status"] == "held" else [("Reserve", x["qty"] - sell, wv.CYAN), ("Sellable surplus", sell, wv.MINT)]
        fl = go.Figure([go.Bar(y=["Stock"], x=[p[1]], name=p[0], orientation="h", marker_color=p[2]) for p in parts])
        fl.update_layout(barmode="stack", height=110, paper_bgcolor=wv.BG, plot_bgcolor=wv.PANEL, margin=dict(l=10, r=10, t=10, b=10), font=dict(color=wv.TEXT), showlegend=True, legend=dict(orientation="h"))
        show(fl)
        if warn:
            st.warning(f"{warn}: selling beyond the surplus would break lead-time cover.")
        table(pd.DataFrame([{"Option": o["option"], "Cash (low–high)": f"{L(o['cash_low'])} – {L(o['cash_high'])}" if o["cash_high"] else "—", "Relief (not cash)": L(o["relief"]) if o["relief"] else "—",
                             "Cost": L(o["cost"]) if o["cost"] else "—", "Days": "—" if o["days"] is None else str(o["days"]), "Note": o["note"]} for o in sc_]))

# ================================================================ RESCUE
elif page == "Inventory Rescue":
    st.caption("Only applicable pathways are shown. Restricted or expired stock is never offered for sale. A write-off is an accounting adjustment, not cash.")
    held = [x for x in ws.batches(cid) if x["status"] == "held"]
    if not held:
        st.info("No held stock for this company."); st.stop()
    held.sort(key=lambda x: -x["book_value"])
    pick = st.selectbox("Held batch", [x["id"] for x in held], format_func=lambda i: next(f"{x['sku']} · {x['hold_status'] if not x['expired'] else 'expired'} · {L(x['book_value'])}" for x in held if x["id"] == i))
    x = next(y for y in held if y["id"] == pick); ro = inv.rescue_options(x)
    restricted = x["restricted"] or x["expired"]
    (st.error if restricted else st.info)(("RESTRICTED STOCK — sale and shipment are blocked. " if restricted else "") + f"{x['sku']} ({x['hold_status']}): {x['hold_reason']}  \n**→ {ro['recommendation']}**")
    f = go.Figure(go.Bar(y=[o["name"] for o in ro["options"]][::-1], x=[o["net"] / 1e7 for o in ro["options"]][::-1], orientation="h",
                         marker_color=[wv.MINT if o["net"] > 0 else wv.MUTED for o in ro["options"]][::-1]))
    f.update_layout(title="Expected net recovery by pathway (₹ lakh; write-off = no cash)", paper_bgcolor=wv.BG, plot_bgcolor=wv.PANEL, height=60 + 55 * len(ro["options"]),
                    margin=dict(l=10, r=10, t=40, b=30), font=dict(color=wv.TEXT), xaxis=dict(gridcolor=wv.GRID))
    show(f)
    for o in ro["options"]:
        with st.expander(f"{o['name']} — " + ("accounting loss " + L(x["book_value"]) + " (no cash)" if o["name"] == "Write-off" else f"net {L(o['net'])} · ~{o['days']} days"), expanded=o is ro["options"][0]):
            chips = " → ".join(f"<span class='chip {'g' if (i == len(o['steps']) - 1 and o['net'] > 0) else ('a' if o['name'] == 'Write-off' else '')}'>{s}</span>" for i, s in enumerate(o["steps"]))
            st.markdown(chips, unsafe_allow_html=True)
            c = st.columns(4); c[0].metric("Gross", L(o["gross"])); c[1].metric("Cost", L(o["cost"])); c[2].metric("Expected net", L(o["net"])); c[3].metric("Time", f"{o['days']} d")
            st.write(f"**Operational impact:** {o['impact']}  \n**Compliance:** {o['compliance']}  \n**Required human approvals:** {', '.join(o['approvals'])}  \n"
                     f"**Confidence:** {o['confidence']}  \n**Missing information:** {'; '.join(o['missing']) or 'none identified'}")

# ================================================================ FUNDING
elif page == "Funding Navigator":
    st.error("ILLUSTRATIVE TERMS ONLY — not offers, quotes or approvals. LiquidityX is not a lender or regulated financial adviser. Edit assumptions to match real quotes.")
    gap = ws.recovery(cid)["gap"]
    amt = st.number_input("Amount needed (₹ lakh)", 0.1, 10000.0, round(gap / PAISE_PER_LAKH, 2) if gap else 10.0, 1.0, help="Defaults to the projected gap when a scenario is active.")
    ass = ws.funding_assumptions()
    df = pd.DataFrame([{"Option": n, **{k: a[k] for k in ("annual_rate", "fee_pct", "tenor_days", "installments", "days_to_funds")}} for n, a in ass.items()]).set_index("Option")
    st.subheader("Editable assumptions")
    ed = st.data_editor(df, key="fund_ed")
    if st.button("Save assumptions"):
        try:
            new = {n: {**ass[n], **{k: (float(r[k]) if k in ("annual_rate", "fee_pct") else int(r[k])) for k in df.columns}} for n, r in ed.iterrows()}
            if any(a["installments"] < 1 or a["tenor_days"] < 1 or min(a["annual_rate"], a["fee_pct"], a["days_to_funds"]) < 0 for a in new.values()):
                raise ValueError
            set_setting(ws.conn, "funding", new); st.success("Saved"); st.rerun()
        except (ValueError, TypeError):
            st.error("Check values: rates ≥ 0, tenor and installments ≥ 1.")
    opts = ws.funding_compare(cid, lakh(amt))
    table(pd.DataFrame([{"Option": o["name"], "Net proceeds": L(o["net_proceeds"]), "Fee": L(o["fee"]), "Interest": L(o["interest"]), "Total repayment": L(o["total_repayment"]),
                         "Effective cost": f"{o['effective_cost_pct']:.1f}%", "Days to funds": o["days_to_funds"], "Collateral": o["collateral"], "Eligibility assumption": o["eligibility"]} for o in opts]))
    v = ws.cash_view(cid, 90); base = v["stress"] if v["stress"] is not None else v["base"]
    f = go.Figure(); f.add_trace(go.Scatter(y=[b / 1e7 for b in base], name="Without funding", line=dict(color=wv.CORAL if v["stress"] is not None else wv.MUTED, width=3)))
    for o in opts:
        f.add_trace(go.Scatter(y=[b / 1e7 for b in fd.apply_to_balances(base, o)], name=o["name"], line=dict(width=1.5)))
    f.add_hline(y=v["min_cash"] / 1e7, line_dash="dot", line_color=wv.AMBER, annotation_text="minimum cash")
    f.update_layout(title="Balance with each ILLUSTRATIVE option (repayments included)", paper_bgcolor=wv.BG, plot_bgcolor=wv.PANEL, height=420, font=dict(color=wv.TEXT),
                    xaxis=dict(title="Day", gridcolor=wv.GRID), yaxis=dict(title="₹ lakh", gridcolor=wv.GRID), margin=dict(t=50))
    show(f)

# ================================================================ RECOVERY
elif page == "Recovery Planner":
    st.caption("Expected values are not confirmed cash · extensions are relief, not receipts · a gap is 'solved' only if actions cover it by the deadline · every plan is re-simulated.")
    sig = (cid, json.dumps(ws.last_params, sort_keys=True, default=str))
    if st.button("Generate plans", type="primary") or (st.session_state.get("rec", {}).get("sig") == sig):
        if st.session_state.get("rec", {}).get("sig") != sig:
            st.session_state["rec"] = dict(sig=sig, out=ws.recovery(cid))
        out = st.session_state["rec"]["out"]
        if not out["plans"]:
            st.success("No projected cash gap in the current scenario — no recovery plan required. Run a crisis scenario first.")
        else:
            st.error(f"Gap {L(out['gap'])} · deadline {out['deadline_date']} (day {out['deadline_day']})")
            for n in out["notes"]:
                st.warning(n)
            pl = out["plans"]
            table(pd.DataFrame([{"Plan": p["label"], "Gap covered by deadline?": "YES" if p["solved"] else "NO — NOT SOLVED", "Expected cash": L(p["expected_cash"]), "Relief (not cash)": L(p["expected_relief"]),
                                 "Cost": L(p["cost"]), "Last action day": p["last_day"], "Op. risk": p["risk"], "Residual": L(p["residual"]),
                                 "Peak shortfall after plan": "n/a" if p["post_peak"] is None else L(p["post_peak"])} for p in pl.values()]))
            key = st.selectbox("Selected plan", list(pl), format_func=lambda k: pl[k]["label"]); p = pl[key]
            evs = [(a["day"], a["name"], a["status"], a["expected_cash"] or a["expected_relief"], "relief" if a["expected_relief"] else "cash") for a in p["actions"]]
            if p["financing"]:
                evs.append((p["financing"]["days_to_funds"], f"Financing: {p['financing']['name']} (ILLUSTRATIVE)", "awaiting approval", p["financing"]["net_proceeds"], "financing"))
            evs.sort()
            f = go.Figure(go.Scatter(x=[e[0] for e in evs], y=list(range(len(evs)))[::-1], mode="markers+text", textposition="middle right",
                                     text=[f"{e[1][:44]} · {e[2]} · {L(e[3])}" for e in evs], marker=dict(size=14, color=[wv.CYAN if e[4] == "financing" else (wv.MINT if e[2] == "can start now" else wv.AMBER) for e in evs])))
            f.add_vline(x=out["deadline_day"], line_dash="dash", line_color=wv.CORAL, annotation_text=f"DEADLINE D+{out['deadline_day']}")
            f.update_layout(title="Recovery timeline (green = can start now · amber = awaiting approval · cyan = illustrative financing)", paper_bgcolor=wv.BG, plot_bgcolor=wv.PANEL,
                            height=120 + 60 * len(evs), font=dict(color=wv.TEXT), xaxis=dict(title="Day", gridcolor=wv.GRID, range=[-1, max(out["deadline_day"] + 14, 20)]), yaxis=dict(visible=False), margin=dict(t=50))
            show(f)
            st.write(f"**Why this plan:** {p['why']}")
            if p["post_peak"]:
                st.warning(f"After-plan check (re-simulated): a shortfall of {L(p['post_peak'])} remains later because repayments/deferrals fall due before delayed customer cash returns. The deadline gap is covered, but this is NOT a full fix.")
            st.write(f"**Residual risk:** " + ("gap covered on expected values; outcomes remain uncertain." if p["solved"] else f"NOT SOLVED — {L(p['residual'])} uncovered by the deadline."))
            other = st.selectbox("Compare with", [k for k in pl if k != key] or [None], format_func=lambda k: "—" if k is None else pl[k]["label"])
            if other:
                o = pl[other]; better = [t for t, c in (("cheaper", p["cost"] < o["cost"]), ("faster", p["last_day"] < o["last_day"]), ("lower risk", p["risk"] < o["risk"])) if c]
                st.write(f"vs **{o['label']}**: cost {L(p['cost'])} vs {L(o['cost'])} · last day {p['last_day']} vs {o['last_day']} · risk {p['risk']} vs {o['risk']} → this plan is {', '.join(better) or 'not better on cost, speed or risk'}.")
            if out["later"]:
                st.caption("Later recovery NOT counted toward the deadline: " + "; ".join(f"D+{a['day']} {a['name']} ({L(a['expected_cash'])})" for a in out["later"]))
            st.subheader("Human approval")
            ok = st.checkbox(f"I approve '{p['label']}'. This records the decision in the audit log; it does not move any money.")
            if st.button("Approve plan", disabled=not ok):
                pid = ws.save_plan(cid, p); ws.approve_plan(pid, "web.user"); st.success("Plan approved and logged."); st.rerun()
    appr = ws.conn.execute("SELECT label, approved_by, created_at FROM recovery_plans WHERE status='approved' AND company_id=?", (cid,)).fetchall()
    if appr:
        st.subheader("Approved plans (this session)"); table(pd.DataFrame([dict(r) for r in appr]))

# ================================================================ REPORTS
elif page == "Reports":
    st.caption("Every report states date, scope, assumptions, limitations and which figures are actual, estimated or simulated. Download the HTML and print/save as PDF from your browser.")
    kind = st.selectbox("Report", reports.KINDS)
    rep = reports.build(ws, kind, cid)
    for title, head, rows in rep["tables"]:
        st.markdown(f"**{title}**"); table(pd.DataFrame(rows, columns=head))
    for n in rep["notes"]:
        st.info(n)
    with tempfile.TemporaryDirectory() as tmp:
        reports.to_html(rep, os.path.join(tmp, "r.html")); reports.to_csv(rep, os.path.join(tmp, "r.csv"))
        html_b, csv_b = open(os.path.join(tmp, "r.html"), "rb").read(), open(os.path.join(tmp, "r.csv"), "rb").read()
    base = kind.lower().replace(" ", "_")
    a, b = st.columns(2)
    a.download_button("⬇ Download HTML report", html_b, f"{base}.html", "text/html"); b.download_button("⬇ Download CSV", csv_b, f"{base}.csv", "text/csv")

# ================================================================ COPILOT
elif page == "Copilot":
    st.caption("Rule-based assistant. Answers come only from the workspace data and the engines; if data is missing it says so.")
    hist = st.session_state.setdefault("chat", [])
    cols = st.columns(2)
    for i, ex in enumerate(copilot.EXAMPLES):
        if cols[i % 2].button(ex, key=f"ex{i}"):
            hist += [("user", ex), ("assistant", copilot.answer(ws, cid, ex))]
    for role, text in hist:
        with st.chat_message(role):
            st.write(text)
    if q := st.chat_input("Ask about exposure, scenarios, stock or recovery plans"):
        hist += [("user", q), ("assistant", copilot.answer(ws, cid, q))]; st.rerun()

# ================================================================ COMMERCIAL
else:
    st.warning("Prototype: each visitor gets a private in-memory demo workspace. Not production-ready enterprise software.")
    st.markdown(commercial.TEXT)
    st.subheader("Subscription tiers — ILLUSTRATIVE, editable, not market-validated")
    t = st.session_state.setdefault("tiers", pd.DataFrame(commercial.TIERS).T.rename_axis("tier").reset_index())
    st.session_state["tiers"] = st.data_editor(t, hide_index=True, key="tier_ed")
