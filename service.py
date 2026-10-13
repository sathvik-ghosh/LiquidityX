"""Service layer: the ONLY thing the UI talks to. All numbers come from the engines/DB."""
import csv
import json
import os
from datetime import date, datetime, timedelta, timezone
from dataclasses import replace

from .db import connect, audit, get_setting, set_setting
from .money import fmt_lakh, lakh
from .engine import cashflow as cf, network as nw, crisis, inventory as inv, funding as fd, recovery as rc
from .engine.cashflow import Shock, ExpenseShock
from .seed import seed_demo


class Workspace:
    def __init__(self, path=":memory:"):
        self.path = path
        self.conn = connect(path)
        self.last_result = None          # active stressed scenario (dict) or None
        self.last_params = None

    # ---------- basics ----------
    @property
    def as_of(self):
        v = get_setting(self.conn, "as_of")
        return date.fromisoformat(v) if v else date.today()

    def state(self, extra_txns=()):
        st = cf.load_state(self.conn, self.as_of)
        if extra_txns:
            st = replace(st, txns=st.txns + list(extra_txns))
        return st

    def companies(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM companies ORDER BY id")]

    def has_data(self):
        return self.conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] > 0

    def is_demo(self):
        r = self.conn.execute("SELECT COUNT(*) c FROM companies WHERE is_demo=1").fetchone()
        return r["c"] > 0

    def load_demo(self):
        if not self.has_data():
            seed_demo(self.conn)

    def date_of(self, day):
        return (self.as_of + timedelta(days=day)).isoformat()

    def funding_assumptions(self):
        return get_setting(self.conn, "funding", fd.DEFAULTS)

    def default_focus(self):
        r = self.conn.execute("SELECT id FROM companies WHERE name LIKE 'Bharat%'").fetchone()
        if r:
            return r["id"]
        r = self.conn.execute("SELECT id FROM companies ORDER BY id LIMIT 1").fetchone()
        return r["id"] if r else None

    # ---------- crisis ----------
    def invoice_choices(self):
        st = self.state()
        n = lambda c: st.companies[c]["name"]
        return [dict(id=i["id"], payer=i["payer"], payee=i["payee"], amount=i["amount"], due_day=i["due"],
                     label=f"{n(i['payer'])} → {n(i['payee'])}  {fmt_lakh(i['amount'])}  due {self.date_of(i['due'])}")
                for i in sorted(st.invoices, key=lambda x: -x["amount"])]

    def run_crisis(self, p):
        """p: invoice_id, delay_days, paid_pct, default, horizon, expense{company_id,day,amount}"""
        shocks = [Shock(int(p["invoice_id"]), int(p.get("delay_days", 0)), int(p.get("paid_pct", 0)),
                        bool(p.get("default", False)))]
        exps = []
        if p.get("expense") and p["expense"].get("amount", 0) > 0:
            e = p["expense"]
            exps = [ExpenseShock(int(e["company_id"]), int(e.get("day", 0)), int(e["amount"]))]
        horizon = int(p.get("horizon", 90))
        if horizon not in range(7, 366):
            raise ValueError("horizon must be 7..365 days")
        st = self.state()
        res = crisis.run_scenario(st, shocks, exps, horizon)
        res["params"] = dict(p)
        inv_ = next(i for i in st.invoices if i["id"] == shocks[0].invoice_id)
        res["shock_edge"] = (inv_["payer"], inv_["payee"])
        self.last_result, self.last_params = res, dict(p)
        audit(self.conn, "run_scenario", p)
        return res

    def clear_scenario(self):
        self.last_result = self.last_params = None

    def save_scenario(self, name, res=None, kind="stress"):
        res = res or self.last_result
        if not res:
            raise ValueError("Run a scenario first")
        crisis.save_scenario(self.conn, name, dict(res.get("params", {}), kind=kind), res)
        audit(self.conn, "save_scenario", {"name": name})

    def saved_scenarios(self):
        return [dict(id=r["id"], name=r["name"], created=r["created_at"],
                     params=json.loads(r["params_json"]), result=json.loads(r["result_json"]))
                for r in self.conn.execute("SELECT * FROM scenarios ORDER BY id")]

    def stress_args(self):
        """(shocks, expenses, horizon) of the active scenario."""
        p = self.last_params
        if not p:
            return (), (), 90
        shocks = (Shock(int(p["invoice_id"]), int(p.get("delay_days", 0)), int(p.get("paid_pct", 0)),
                        bool(p.get("default", False))),)
        e = p.get("expense")
        exps = (ExpenseShock(int(e["company_id"]), int(e.get("day", 0)), int(e["amount"])),) \
            if e and e.get("amount", 0) > 0 else ()
        return shocks, exps, int(p.get("horizon", 90))

    def compare_cases(self, cid):
        """Baseline vs stress vs recovery for one company (recovery uses the Balanced plan)."""
        st = self.state()
        shocks, exps, h = self.stress_args()
        base = cf.simulate(st, 90)
        out = dict(baseline=base.balances[cid], min_cash=st.companies[cid]["min_cash"])
        if shocks:
            s = cf.simulate(st, 90, shocks, exps)
            out["stress"] = s.balances[cid]
            plan = self.recovery(cid)["plans"]
            pl = plan.get("balanced") or plan.get("best_effort")
            if pl:
                st2 = self.state(rc.plan_txns(pl, cid))
                out["recovery"] = cf.simulate(st2, 90, shocks, exps).balances[cid]
                out["recovery_label"] = pl["label"]
        return out

    # ---------- cash ----------
    def cash_view(self, cid, horizon):
        st = self.state()
        shocks, exps, _ = self.stress_args()
        base = cf.simulate(st, max(horizon, 90))
        stress = cf.simulate(st, max(horizon, 90), shocks, exps) if shocks else None
        sl = slice(0, horizon + 1)
        mn = st.companies[cid]["min_cash"]
        cats = {}
        for t in self.conn.execute("SELECT * FROM cash_transactions WHERE company_id=?", (cid,)):
            d = (date.fromisoformat(t["txn_date"]) - self.as_of).days
            if 0 <= d <= horizon:
                k = ("Confirmed " if t["confirmed"] else "Expected ") + t["category"]
                cats[k] = cats.get(k, 0) + t["amount"]
        rec = sum(i["amount"] for i in st.invoices if i["payee"] == cid and 0 <= i["pay_day"] <= horizon and i["due"] >= 0)
        over = sum(i["amount"] for i in st.invoices if i["payee"] == cid and i["due"] < 0)
        pay = sum(i["amount"] for i in st.invoices if i["payer"] == cid and i["pay_day"] <= horizon)
        summary = [("Opening cash (confirmed)", st.companies[cid]["opening_cash"]),
                   ("Expected collections (invoices)", rec), ("Overdue receivables (expected)", over),
                   ("Supplier payments (scheduled)", -pay)] + sorted(cats.items()) + [
                   ("Minimum operating cash", mn)]
        obligations = sorted([(i["pay_day"], f"Pay {st.companies[i['payee']]['name']}", -i["amount"])
                              for i in st.invoices if i["payer"] == cid and i["pay_day"] <= horizon]
                             + [(t["day"], "Payroll/other", t["amount"]) for t in st.txns
                                if t["company"] == cid and 0 <= t["day"] <= horizon and t["amount"] < 0])
        return dict(base=base.balances[cid][sl], stress=None if not stress else stress.balances[cid][sl],
                    inflow=(stress or base).inflow[cid][sl], outflow=(stress or base).outflow[cid][sl],
                    min_cash=mn, summary=summary, obligations=obligations, horizon=horizon,
                    gap_base=cf.shortfall_profile(st, base, cid),
                    gap_stress=cf.shortfall_profile(st, stress, cid) if stress else None)

    # ---------- network ----------
    def graph_data(self):
        st = self.state()
        g = nw.build_graph(st)
        imp = nw.network_importance(g)
        rels = {(r["payer_id"], r["payee_id"]): dict(r) for r in self.conn.execute("SELECT * FROM relationships")}
        res = self.last_result
        affected = {c["company_id"]: c for c in res["companies"]} if res else {}
        nodes = []
        base = cf.simulate(st, 90)
        for cid, c in st.companies.items():
            e = nw.exposure(g, cid)
            bp, _, _ = cf.shortfall_profile(st, base, cid)
            a = affected.get(cid)
            status = "ok"
            base_status = "warning" if bp > 0 else "ok"
            if a:
                status = "critical" if a["extra_shortfall"] > 0 else "warning"
            elif bp > 0:
                status = "warning"
            buf = base.balances[cid][0] - c["min_cash"]
            nodes.append(dict(id=cid, name=c["name"], type=c["type"], status=status, base_status=base_status,
                              cash_ratio=(base.balances[cid][0] / c["min_cash"]) if c["min_cash"] else 3,
                              cash_buffer=buf, exposure=e["receivables"] + e["payables"],
                              receivables=e["receivables"], payables=e["payables"],
                              cust_hhi=nw.customer_concentration(g, cid), sup_hhi=nw.supplier_concentration(g, cid),
                              importance=imp[cid], affected=a))
        edges = []
        for a, b, d in g.edges(data=True):
            invs = [i for i in st.invoices if i["payer"] == a and i["payee"] == b]
            r = rels.get((a, b), {})
            delays = [i["pay_day"] - max(i["due"], 0) for i in invs]
            edges.append(dict(payer=a, payee=b, amount=d["amount"], due_day=min(i["due"] for i in invs),
                              due=self.date_of(min(i["due"] for i in invs)), n=len(invs),
                              criticality=r.get("criticality", 3), alt=bool(r.get("alternative_available")),
                              kind=r.get("kind", "trade_payment"),
                              history=(f"Invoices carry {max(delays)}d expected delay" if max(delays) > 0
                                       else "No delay recorded (history data limited)")))
        return dict(nodes=nodes, edges=edges)

    def risk_radar(self, cid):
        """Each score 0..1 (1 = riskier) or None when data is insufficient. Formulas shown to user."""
        st = self.state()
        g = nw.build_graph(st)
        shocks, exps, _ = self.stress_args()
        res = cf.simulate(st, 90, shocks, exps)
        mn = st.companies[cid]["min_cash"]
        peak, _, _ = cf.shortfall_profile(st, res, cid)
        liq = min(1, peak / mn) if mn else None
        batches = inv.load_batches(self.conn, self.as_of, cid)
        tot = sum(b["book_value"] for b in batches)
        obs = None if not tot else sum(b["book_value"] for b in batches
                                       if b["status"] in ("held", "slow", "dead")) / tot
        pays = [(i["payee"], i["amount"]) for i in st.invoices if i["payer"] == cid]
        rels = {(r["payer_id"], r["payee_id"]): r for r in self.conn.execute("SELECT * FROM relationships")}
        dep = None
        if pays:
            tp = sum(a for _, a in pays)
            dep = sum(a for p, a in pays if rels[(cid, p)]["criticality"] >= 4
                      and not rels[(cid, p)]["alternative_available"]) / tp
        return [
            ("Liquidity", liq, "min(1, peak projected shortfall ÷ minimum operating cash), 90-day sim"),
            ("Customer conc.", nw.customer_concentration(g, cid), "HHI of open receivables by customer"),
            ("Supplier conc.", nw.supplier_concentration(g, cid), "HHI of open payables by supplier"),
            ("Inventory obsolescence", obs, "book value of held/slow/dead stock ÷ total stock value"),
            ("Critical dependency", dep, "share of payables to suppliers with criticality ≥4 and no alternative"),
        ]

    # ---------- KPIs / queue / timeline ----------
    def kpis(self):
        st = self.state()
        shocks, exps, _ = self.stress_args()
        res = cf.simulate(st, 90, shocks, exps)
        gaps = sum(1 for c in st.companies if cf.shortfall_profile(st, res, c)[0] > 0)
        crit = self.conn.execute("SELECT COUNT(*) c FROM relationships WHERE criticality>=4 AND alternative_available=0").fetchone()["c"]
        batches = inv.load_batches(self.conn, self.as_of)
        blocked = sum(b["book_value"] for b in batches if b["status"] == "held")
        rec = 0
        for b in batches:
            if b["status"] == "held":
                best = inv.rescue_options(b).get("best")
                rec += best["net"] if best and best["net"] > 0 else 0
            else:
                rec += inv.recommendation(b)["cash_low"]
        plans = self.conn.execute("SELECT COUNT(*) c FROM recovery_plans WHERE status='proposed'").fetchone()["c"]
        return dict(companies=len(st.companies), gaps=gaps, critical=crit, blocked=blocked, recoverable=rec, plans=plans)

    def timeline(self, cid, horizon=30):
        st = self.state()
        shocks, exps, _ = self.stress_args()
        res = cf.simulate(st, 90, shocks, exps)
        n = lambda c: st.companies[c]["name"]
        ev = []
        for i in st.invoices:
            if i["payee"] == cid and i["due"] < 0:
                ev.append((0, "overdue", f"Overdue receivable from {n(i['payer'])}", i["amount"]))
            elif i["payee"] == cid and i["amount"] >= lakh(5):
                ev.append((i["pay_day"], "receivable", f"Large receivable from {n(i['payer'])}", i["amount"]))
            if i["payer"] == cid:
                ev.append((i["pay_day"], "payment", f"Supplier payment to {n(i['payee'])}", -i["amount"]))
        for t in st.txns:
            if t["company"] == cid and t["amount"] < 0:
                ev.append((t["day"], "payment", "Payroll / operating outflow", t["amount"]))
        peak, first, _ = cf.shortfall_profile(st, res, cid)
        if first is not None:
            ev.append((first, "shortage", "Forecast cash shortage begins", -peak))
        for b in inv.load_batches(self.conn, self.as_of, cid):
            if b["hold_deadline"]:
                ev.append(((date.fromisoformat(b["hold_deadline"]) - self.as_of).days, "hold",
                           f"Hold deadline: {b['sku']} ({b['hold_status']})", 0))
        for r in self.conn.execute("SELECT * FROM recovery_plans WHERE company_id=? AND status='approved'", (cid,)):
            for a in json.loads(r["plan_json"])["actions"]:
                ev.append((a["day"], "recovery", f"Recovery: {a['name']}", a["expected_cash"]))
        return sorted([e for e in ev if 0 <= e[0] <= horizon])

    def action_queue(self, cid):
        q = []
        st = self.state()
        for b in inv.load_batches(self.conn, self.as_of, cid):
            if b["hold_status"] == "quality":
                dl = (date.fromisoformat(b["hold_deadline"]) - self.as_of).days if b["hold_deadline"] else None
                q.append(dict(sev="critical", title=f"Investigate quality-held batch {b['sku']}",
                              detail=f"{fmt_lakh(b['book_value'])} blocked. {b['hold_reason']}. Deadline in {dl} days.",
                              page="Inventory Rescue", ref=b["id"]))
            if b["hold_status"] == "customer_order":
                q.append(dict(sev="warning", title=f"Confirm release date for {b['sku']}",
                              detail=f"{fmt_lakh(b['book_value'])} held for a customer order. {b['hold_reason']}.",
                              page="Inventory Rescue", ref=b["id"]))
        res = cf.simulate(st, 90, *self.stress_args()[:2])
        peak, first, _ = cf.shortfall_profile(st, res, cid)
        if peak:
            q.insert(0, dict(sev="critical", title="Review upcoming cash deficit",
                             detail=f"Projected shortfall {fmt_lakh(peak)} from {self.date_of(first)}.",
                             page="Cash Intelligence", ref=None))
            q.append(dict(sev="warning", title="Approve a proposed recovery plan",
                          detail="Generate and compare plans for the projected gap.", page="Recovery Planner", ref=None))
        for r in self.conn.execute("SELECT * FROM relationships WHERE payer_id=? AND criticality>=4 AND alternative_available=1", (cid,)):
            q.append(dict(sev="info", title=f"Evaluate alternative to {st.companies[r['payee_id']]['name']}",
                          detail="Critical supplier with an alternative available.", page="Financial Network", ref=None))
        return q

    # ---------- inventory ----------
    def batches(self, cid=None):
        return inv.load_batches(self.conn, self.as_of, cid)

    # ---------- funding / recovery ----------
    def funding_compare(self, cid, amount):
        a = self.funding_assumptions()
        return [fd.evaluate(n, v, amount) for n, v in a.items()]

    def recovery(self, cid):
        shocks, exps, h = self.stress_args()
        return rc.plan_for(self.state(), self.conn, self.as_of, cid, shocks, exps, self.funding_assumptions())

    def save_plan(self, cid, plan):
        with self.conn:
            cur = self.conn.execute("INSERT INTO recovery_plans(company_id,label,plan_json,created_at) VALUES(?,?,?,?)",
                                    (cid, plan["label"], json.dumps(plan), datetime.now(timezone.utc).isoformat()))
        audit(self.conn, "plan_proposed", {"plan": plan["label"], "company": cid})
        return cur.lastrowid

    def approve_plan(self, plan_id, user="demo.user"):
        with self.conn:
            self.conn.execute("UPDATE recovery_plans SET status='approved', approved_by=? WHERE id=?", (user, plan_id))
        audit(self.conn, "plan_approved", {"plan_id": plan_id, "by": user})

    # ---------- import ----------
    def import_csv(self, kind, path):
        """kinds: companies(name,type,opening_cash,min_cash) | invoices(payer,payee,amount,due_date[,expected_delay_days])
        amounts in rupees. Returns (imported, errors). All-or-nothing per file."""
        errors, rows = [], []
        with open(path, newline="", encoding="utf-8-sig") as f:
            for n, r in enumerate(csv.DictReader(f), start=2):
                rows.append((n, r))
        ids = {c["name"]: c["id"] for c in self.companies()}
        try:
            with self.conn:
                for n, r in rows:
                    try:
                        if kind == "companies":
                            self.conn.execute("INSERT INTO companies(name,type,opening_cash,min_cash,is_demo) VALUES(?,?,?,?,0)",
                                              (r["name"].strip(), r["type"].strip(), int(float(r["opening_cash"]) * 100),
                                               int(float(r["min_cash"]) * 100)))
                        elif kind == "invoices":
                            a, b = r["payer"].strip(), r["payee"].strip()
                            if a not in ids or b not in ids:
                                raise ValueError(f"unknown company {a if a not in ids else b}")
                            date.fromisoformat(r["due_date"].strip())
                            rid = self.conn.execute(
                                "INSERT INTO relationships(payer_id,payee_id,kind) VALUES(?,?,'trade_payment') "
                                "ON CONFLICT(payer_id,payee_id) DO UPDATE SET kind=kind RETURNING id",
                                (ids[a], ids[b])).fetchone()[0]
                            self.conn.execute("INSERT INTO invoices(relationship_id,amount,due_date,expected_delay_days) VALUES(?,?,?,?)",
                                              (rid, int(float(r["amount"]) * 100), r["due_date"].strip(),
                                               int(r.get("expected_delay_days") or 0)))
                        else:
                            raise ValueError("unknown import kind")
                    except Exception as e:      # collect, then roll back everything
                        errors.append(f"row {n}: {e}")
                if errors:
                    raise RuntimeError("rollback")
        except RuntimeError:
            return 0, errors
        audit(self.conn, "import_csv", {"kind": kind, "rows": len(rows)})
        return len(rows), []

    def case_table(self, cid):
        """Baseline / Stress / Recovery metrics for the scenario comparison (focus company + network)."""
        st = self.state()
        shocks, exps, h = self.stress_args()
        def metrics(state, sh, ex):
            r = cf.simulate(state, 90, sh, ex)
            prof = {c: cf.shortfall_profile(state, r, c) for c in state.companies}
            firsts = [p[1] for p in prof.values() if p[1] is not None]
            return dict(companies_short=sum(1 for p in prof.values() if p[0] > 0),
                        total_shortfall=sum(p[0] for p in prof.values()), focus_peak=prof[cid][0],
                        earliest=None if not firsts else self.date_of(min(firsts)))
        rows = [("Baseline", metrics(st, (), ()))]
        if shocks:
            rows.append(("Stress case", metrics(st, shocks, exps)))
            plans = self.recovery(cid)["plans"]
            pl = plans.get("balanced") or plans.get("best_effort")
            if pl:
                rows.append((f"Recovery case ({pl['label']})", metrics(self.state(rc.plan_txns(pl, cid)), shocks, exps)))
        return rows
