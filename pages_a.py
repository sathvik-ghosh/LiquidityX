"""Command Center, Financial Network, Crisis Simulator, Cash Intelligence."""
import math
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np

from . import kit
from .kit import (BG, PANEL, NAVY, CYAN, MINT, AMBER, CORAL, TEXT, MUTED, GRID, KpiCard, DataTable, Tooltip,
                  animate, card, label, heading, mpl, style_ax, toast, mix)
from .network_canvas import NetworkCanvas
from ..money import fmt_lakh, lakh, PAISE_PER_LAKH


class Page(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app, self.ws = app, app.ws
        self.build()

    def build(self): ...
    def refresh(self): ...
    def on_show(self): self.refresh()


def lk(v):
    return f"₹{v / PAISE_PER_LAKH:,.1f}L"


# ============================================================ COMMAND CENTER
class CommandCenter(Page):
    def build(self):
        heading(self, "Command Center", "Detect → Trace → Simulate → Recover → Protect → Learn. All figures are computed by the "
                "backend engines from workspace data.").pack(fill="x", padx=18, pady=(14, 6))
        row = tk.Frame(self, bg=BG); row.pack(fill="x", padx=18)
        specs = [("Companies monitored", "Number of companies in this workspace.", lambda v: f"{int(round(v))}", CYAN),
                 ("Projected liquidity gaps", "Companies whose modeled balance falls below minimum operating cash within 90 days "
                  "(active scenario if one is running, otherwise baseline).", lambda v: f"{int(round(v))}", CORAL),
                 ("Critical relationships", "Relationships with criticality ≥ 4 and no alternative available.", lambda v: f"{int(round(v))}", AMBER),
                 ("Blocked inventory", "Book value of held batches (quality, certification, damaged, expired, …).", fmt_lakh, AMBER),
                 ("Est. recoverable cash", "POTENTIAL recovery: probability-weighted rescue nets plus conservative surplus-sale proceeds. "
                  "Not confirmed cash.", fmt_lakh, MINT),
                 ("Open recovery plans", "Proposed plans awaiting approval.", lambda v: f"{int(round(v))}", CYAN)]
        self.k = {}
        for i, (t, tip, f, c) in enumerate(specs):
            w = KpiCard(row, t, tip, f, accent=c); w.grid(row=0, column=i, sticky="nsew", padx=4)
            row.columnconfigure(i, weight=1); self.k[t] = w
        body = tk.Frame(self, bg=BG); body.pack(fill="both", expand=True, padx=18, pady=8)
        body.columnconfigure(0, weight=3); body.columnconfigure(1, weight=2); body.rowconfigure(0, weight=1)
        left = card(body); left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        label(left, "LIVE FINANCIAL NETWORK", 8, MUTED, True).pack(anchor="w", padx=10, pady=(8, 0))
        self.net = NetworkCanvas(left, on_select=lambda k, o: self.app.goto("Financial Network", sel=(k, o)) if o else None, height=360)
        self.net.pack(fill="both", expand=True, padx=6, pady=6)
        right = tk.Frame(body, bg=BG); right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1); right.columnconfigure(0, weight=1)
        rc = card(right); rc.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        label(rc, "RISK RADAR  (0 = low, 1 = high; n/a = insufficient data)", 8, MUTED, True).pack(anchor="w", padx=10, pady=(8, 0))
        self.fig, self.ax, self.cv = mpl(rc, 4.2, 2.6, polar=True)
        self.cv.get_tk_widget().pack(fill="x", padx=6)
        self.formulas = tk.Label(rc, text="", bg=PANEL, fg=MUTED, font=(kit.FONT[0], 7), justify="left", wraplength=420)
        self.formulas.pack(anchor="w", padx=10, pady=(0, 6))
        qc = card(right); qc.grid(row=1, column=0, sticky="nsew")
        label(qc, "ACTION QUEUE  (select to open)", 8, MUTED, True).pack(anchor="w", padx=10, pady=(8, 2))
        self.q = DataTable(qc, [("sev", "Priority", 70), ("title", "Action", 300)], on_select=self._open, height=5)
        self.q.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        tc = card(self); tc.pack(fill="x", padx=18, pady=(0, 10))
        label(tc, "FINANCIAL STRESS TIMELINE — next 30 days (focus company)", 8, MUTED, True).pack(anchor="w", padx=10, pady=(8, 0))
        self.tl = tk.Canvas(tc, bg=PANEL, height=170, highlightthickness=0); self.tl.pack(fill="x", padx=6, pady=4)
        self.items = []
        self.first = True

    def _open(self, iid):
        self.app.open_action(self.items[int(iid)])

    def refresh(self):
        ws = self.ws
        if not ws.has_data():
            self.net.set_data(dict(nodes=[], edges=[])); return
        kp = ws.kpis()
        for key, val in zip(self.k, [kp["companies"], kp["gaps"], kp["critical"], kp["blocked"], kp["recoverable"], kp["plans"]]):
            self.k[key].set(val, CORAL if key == "Projected liquidity gaps" and val else None)
        self.net.set_data(ws.graph_data(), ws.last_result, reveal=self.first)
        self.first = False
        self.items = ws.action_queue(self.app.cid)
        self.q.set_rows([(i, (it["sev"].upper(), it["title"]), {"critical": "critical", "warning": "warning"}.get(it["sev"]))
                         for i, it in enumerate(self.items)])
        self._radar()
        self._timeline()

    def _radar(self):
        r = self.ws.risk_radar(self.app.cid)
        vals = [0 if v is None else v for _, v, _ in r]
        names = [n + (" (n/a)" if v is None else "") for n, v, _ in r]
        ang = np.linspace(0, 2 * np.pi, len(r), endpoint=False)
        self.formulas.config(text="  ·  ".join(f"{n}: {f}" for n, _, f in r))

        def f(p):
            self.ax.clear(); style_ax(self.ax)
            a = np.concatenate([ang, ang[:1]]); v = np.array(vals + vals[:1]) * p
            self.ax.plot(a, v, color=CYAN, lw=2); self.ax.fill(a, v, color=CYAN, alpha=.25)
            self.ax.set_xticks(ang); self.ax.set_xticklabels(names, color=TEXT, fontsize=7)
            self.ax.set_ylim(0, 1); self.ax.set_yticks([.25, .5, .75]); self.ax.set_yticklabels([])
            self.fig.subplots_adjust(left=.1, right=.9, top=.88, bottom=.08)
            self.cv.draw_idle()
        animate(self, kit.CHART, f)

    def _timeline(self):
        c = self.tl
        self.update_idletasks()
        ev = self.ws.timeline(self.app.cid, 30)[:10]
        w = max(c.winfo_width(), 700)
        x0, x1, y = 40, w - 40, 84
        col = {"overdue": CORAL, "shortage": CORAL, "payment": AMBER, "receivable": MINT, "hold": AMBER, "recovery": MINT}
        icon = {"overdue": "▲", "shortage": "▲", "payment": "●", "receivable": "●", "hold": "!", "recovery": "✓"}
        levels = [-34, 30, -62, 58]          # label heights, cycled to avoid overlap

        def f(p):
            c.delete("all")
            c.create_line(x0, y, x1, y, fill=GRID, width=2)
            for d in (0, 7, 14, 21, 30):
                x = x0 + (x1 - x0) * d / 30
                c.create_line(x, y - 4, x, y + 4, fill=MUTED)
                c.create_text(x, y + 12, text=f"D+{d}", fill=MUTED, font=(kit.FONT[0], 7))
            if not ev:
                c.create_text(w / 2, 60, text="No upcoming events for this company in the next 30 days.", fill=MUTED)
            for i, (d, k, txt, amt) in enumerate(ev):
                vis = max(0, min(1, p * (len(ev) + 1) - i))
                if vis <= 0:
                    continue
                x = x0 + (x1 - x0) * d / 30
                yy = y + levels[i % 4] * vis
                anchor = "w" if x < w * .18 else ("e" if x > w * .82 else "center")
                c.create_line(x, y, x, yy, fill=mix(PANEL, col[k], .6))
                c.create_text(x, y, text=icon[k], fill=col[k], font=(kit.FONT[0], 11))
                s = (txt[:28] + ("…" if len(txt) > 28 else "")) + (f"  {lk(abs(amt))}" if amt else "")
                c.create_text(x, yy + (-8 if levels[i % 4] < 0 else 8), anchor=anchor, text=s, fill=mix(PANEL, TEXT, vis), font=(kit.FONT[0], 7))
        animate(c, kit.CHART, f)


# ============================================================ FINANCIAL NETWORK
class NetworkPage(Page):
    def build(self):
        heading(self, "Financial Network", "Edges follow the direction of money (payer → payee). Network importance, financial exposure "
                "and projected liquidity risk are shown separately.").pack(fill="x", padx=18, pady=(14, 6))
        bar = tk.Frame(self, bg=BG); bar.pack(fill="x", padx=18, pady=4)
        ttk.Label(bar, text="Filter type").pack(side="left")
        self.ftype = ttk.Combobox(bar, state="readonly", width=14, values=["all", "manufacturer", "supplier", "customer", "distributor", "service"])
        self.ftype.set("all"); self.ftype.pack(side="left", padx=6)
        self.ftype.bind("<<ComboboxSelected>>", lambda e: self.net.set_filter(None if self.ftype.get() == "all" else {self.ftype.get()}))
        ttk.Label(bar, text="Search").pack(side="left", padx=(12, 0))
        self.q = ttk.Entry(bar, width=18); self.q.pack(side="left", padx=6)
        self.q.bind("<Return>", lambda e: self.net.find(self.q.get()))
        ttk.Button(bar, text="Reset layout", command=lambda: (self.net.select(None), self.net.reset_view())).pack(side="left", padx=4)
        self.cmp = ttk.Button(bar, text="View: stressed", command=self._toggle); self.cmp.pack(side="left", padx=4)
        ttk.Button(bar, text="Replay shock wave", command=lambda: self.net.play_shock()).pack(side="left", padx=4)
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=18, pady=6)
        g = tk.Frame(nb, bg=BG); nb.add(g, text="  Graph  ")
        g.columnconfigure(0, weight=1); g.rowconfigure(0, weight=1)
        self.net = NetworkCanvas(g, on_select=self._sel); self.net.grid(row=0, column=0, sticky="nsew")
        side = card(g, width=300); side.grid(row=0, column=1, sticky="ns", padx=(6, 0)); side.grid_propagate(False)
        label(side, "EXPOSURE PANEL", 8, MUTED, True).pack(anchor="w", padx=10, pady=(10, 4))
        self.detail = tk.Label(side, text="Select a company or relationship.", bg=PANEL, fg=TEXT, justify="left", anchor="nw",
                               wraplength=270, font=(kit.FONT[0], 9)); self.detail.pack(fill="both", expand=True, padx=10, pady=4)
        t = tk.Frame(nb, bg=BG); nb.add(t, text="  Table view (accessible)  ")
        self.nt = DataTable(t, [("n", "Company", 190), ("t", "Type", 90), ("s", "Status", 80), ("r", "Receivables", 100, "e"), ("p", "Payables", 100, "e"),
                                ("ch", "Cust. HHI", 70, "e"), ("sh", "Supp. HHI", 70, "e"), ("d", "Downstream", 80, "e")], height=8)
        self.nt.pack(fill="x", pady=(6, 4))
        self.et = DataTable(t, [("a", "Payer", 190), ("b", "Payee", 190), ("m", "Amount", 90, "e"), ("d", "Due", 90), ("c", "Criticality", 70, "e"),
                                ("al", "Alternative", 80), ("h", "History", 260)], height=10)
        self.et.pack(fill="both", expand=True)
        self.first = True

    def _toggle(self):
        m = "baseline" if self.net.mode == "stressed" else "stressed"
        self.net.set_mode(m); self.cmp.config(text=f"View: {m}")

    def _sel(self, kind, obj):
        if not kind:
            self.detail.config(text="Select a company or relationship."); return
        N = {n["id"]: n for n in self.net.nodes.values()}
        if kind == "node":
            n = obj
            conc = lambda v: "n/a (no open amounts)" if v is None else f"{v:.2f}"
            txt = (f"{n['name']}\n{n['type']}\n\nFINANCIAL EXPOSURE\nReceivables {fmt_lakh(n['receivables'])}\nPayables {fmt_lakh(n['payables'])}\n"
                   f"\nNETWORK IMPORTANCE (separate from distress)\nBetweenness {n['importance']['betweenness']:.2f}\n"
                   f"Downstream reach {n['importance']['downstream_share']:.0%} of network\n\nCONCENTRATION (HHI)\nCustomers {conc(n['cust_hhi'])}\n"
                   f"Suppliers {conc(n['sup_hhi'])}\n\nPROJECTED LIQUIDITY\nStatus: {n['status']}\nCash vs minimum: {n['cash_ratio']:.1f}×")
            if n["affected"]:
                a = n["affected"]
                txt += f"\n\nIN SCENARIO ({a['role']}, wave {a['wave']})\nExtra shortfall {fmt_lakh(a['extra_shortfall'])}\nFirst breach {a['first_breach_date'] or '—'}"
        else:
            e = obj
            txt = (f"{N[e['payer']]['name']}\n→ {N[e['payee']]['name']}\n\nRelationship: {e['kind']}\nOutstanding {fmt_lakh(e['amount'])} ({e['n']} invoice(s))\n"
                   f"Next due {e['due']}\nCriticality {e['criticality']}/5\nAlternative available: {'yes' if e['alt'] else 'no'}\n\nPayment behaviour:\n{e['history']}")
        self.detail.config(text=txt)

    def refresh(self):
        if not self.ws.has_data():
            self.net.set_data(dict(nodes=[], edges=[])); return
        d = self.ws.graph_data()
        self.net.set_data(d, self.ws.last_result, reveal=self.first); self.first = False
        names = {n["id"]: n["name"] for n in d["nodes"]}
        self.nt.set_rows([(n["id"], (n["name"], n["type"], n["status"], fmt_lakh(n["receivables"]), fmt_lakh(n["payables"]),
                                     "n/a" if n["cust_hhi"] is None else f"{n['cust_hhi']:.2f}", "n/a" if n["sup_hhi"] is None else f"{n['sup_hhi']:.2f}",
                                     f"{n['importance']['downstream_share']:.0%}"), {"critical": "critical", "warning": "warning"}.get(n["status"])) for n in d["nodes"]])
        self.et.set_rows([(i, (names[e["payer"]], names[e["payee"]], fmt_lakh(e["amount"]), e["due"], e["criticality"], "yes" if e["alt"] else "no", e["history"]), None)
                          for i, e in enumerate(d["edges"])])

    def select(self, kind, obj):
        if kind == "node":
            self.net.select(("node", obj["id"]))
        elif kind == "edge":
            self.net.select(("edge", (obj["payer"], obj["payee"])))


# ============================================================ CRISIS SIMULATOR
class CrisisPage(Page):
    def build(self):
        heading(self, "Crisis Simulator", "Choose a payment, stress it, and watch the computed propagation. Only affected companies animate; "
                "unaffected ones stay unaffected. Same inputs always give the same result.").pack(fill="x", padx=18, pady=(14, 6))
        body = tk.Frame(self, bg=BG); body.pack(fill="both", expand=True, padx=18, pady=4)
        body.columnconfigure(1, weight=1); body.rowconfigure(0, weight=1)
        L = card(body, width=270); L.grid(row=0, column=0, sticky="ns", padx=(0, 6)); L.grid_propagate(False)
        pad = dict(anchor="w", padx=10, pady=(6, 0))
        label(L, "SCENARIO CONTROLS", 8, MUTED, True).pack(**pad)
        label(L, "Payment under stress (supplier disruption = a payment to that supplier)", 8, MUTED, wraplength=270, justify="left").pack(**pad)
        self.inv = ttk.Combobox(L, state="readonly", width=34); self.inv.pack(padx=10, pady=2)
        label(L, "Payment delay (days)", 9).pack(**pad)
        qb = tk.Frame(L, bg=PANEL); qb.pack(anchor="w", padx=10)
        self.delay = tk.StringVar(value="30")
        for d in (7, 15, 30, 60):
            ttk.Button(qb, text=f"{d}d", width=4, command=lambda d=d: self.delay.set(str(d))).pack(side="left", padx=2)
        ttk.Spinbox(qb, from_=0, to=365, width=5, textvariable=self.delay).pack(side="left", padx=6)
        label(L, "Paid on time (partial-payment %)", 9).pack(**pad)
        self.pct = tk.StringVar(value="0"); ttk.Spinbox(L, from_=0, to=100, width=6, textvariable=self.pct).pack(anchor="w", padx=10)
        self.default = tk.BooleanVar()
        ttk.Checkbutton(L, text="Default (late part never paid)", variable=self.default).pack(anchor="w", padx=10, pady=4)
        label(L, "Unexpected expense (₹ lakh, day) at:", 9).pack(**pad)
        self.exco = ttk.Combobox(L, state="readonly", width=30); self.exco.pack(padx=10, pady=2)
        ex = tk.Frame(L, bg=PANEL); ex.pack(anchor="w", padx=10)
        self.examt = tk.StringVar(value="0"); self.exday = tk.StringVar(value="5")
        ttk.Spinbox(ex, from_=0, to=1000, width=6, textvariable=self.examt).pack(side="left")
        label(ex, " day ", 9).pack(side="left"); ttk.Spinbox(ex, from_=0, to=365, width=5, textvariable=self.exday).pack(side="left")
        label(L, "Scenario duration (days)", 9).pack(**pad)
        self.hor = ttk.Combobox(L, state="readonly", width=8, values=["30", "60", "90", "180"]); self.hor.set("90"); self.hor.pack(anchor="w", padx=10)
        ttk.Button(L, text="▶  Run simulation", style="Accent.TButton", command=self.run).pack(fill="x", padx=10, pady=(12, 4))
        ttk.Button(L, text="Clear scenario", command=self.clear).pack(fill="x", padx=10)
        label(L, "Save as comparison case", 9).pack(**pad)
        self.sname = ttk.Entry(L); self.sname.insert(0, "Stress case"); self.sname.pack(fill="x", padx=10, pady=2)
        ttk.Button(L, text="Save scenario", command=self.save).pack(fill="x", padx=10, pady=(0, 10))
        mid = tk.Frame(body, bg=BG); mid.grid(row=0, column=1, sticky="nsew")
        mid.rowconfigure(1, weight=1); mid.columnconfigure(0, weight=1)
        self.counter = tk.Label(mid, text="Run a simulation to see the propagation.", bg=BG, fg=MUTED, font=(kit.MONO[0], 9), anchor="w", wraplength=520, justify="left")
        self.counter.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.net = NetworkCanvas(mid, on_select=self._pick); self.net.grid(row=1, column=0, sticky="nsew")
        R = card(body, width=350); R.grid(row=0, column=2, sticky="ns", padx=(6, 0)); R.grid_propagate(False)
        label(R, "RESULTS", 8, MUTED, True).pack(anchor="w", padx=10, pady=(10, 2))
        self.res = tk.Label(R, text="—", bg=PANEL, fg=TEXT, justify="left", anchor="nw", wraplength=325, font=(kit.FONT[0], 9)); self.res.pack(fill="x", padx=10)
        self.tab = DataTable(R, [("c", "Company", 120), ("r", "Role", 55), ("x", "Extra short", 65, "e"), ("b", "Breach", 80)], on_select=self._row, height=6)
        self.tab.pack(fill="x", padx=8, pady=6)
        self.note = tk.Label(R, text="", bg=PANEL, fg=MUTED, justify="left", anchor="nw", wraplength=325, font=(kit.FONT[0], 8)); self.note.pack(fill="x", padx=10)
        bot = card(self); bot.pack(fill="x", padx=18, pady=(6, 10))
        label(bot, "SCENARIO COMPARISON — Baseline · Stress · Recovery (focus-company recovery uses the Balanced plan; expected values, not confirmed cash)", 8, MUTED, True).pack(anchor="w", padx=10, pady=(6, 0))
        self.cmp = DataTable(bot, [("n", "Case", 260), ("c", "Companies below min cash", 150, "e"), ("t", "Total shortfall", 100, "e"), ("f", "Focus peak shortfall", 130, "e"), ("e", "Earliest breach", 100)], height=3)
        self.cmp.pack(fill="x", padx=6, pady=6)
        self.choices = []

    def refresh(self):
        if not self.ws.has_data():
            return
        self.choices = self.ws.invoice_choices()
        self.inv["values"] = [c["label"] for c in self.choices]
        if self.inv.current() < 0 and self.choices:
            big = next((i for i, c in enumerate(self.choices) if "Apex" in c["label"] and "Bharat" in c["label"]), 0)
            self.inv.current(big)
        cos = self.ws.companies()
        self.cn = {c["name"]: c["id"] for c in cos}
        self.exco["values"] = list(self.cn)
        if not self.exco.get():
            self.exco.set(next(c["name"] for c in cos if c["id"] == self.app.cid))
        self.net.set_data(self.ws.graph_data(), self.ws.last_result)
        self._show(self.ws.last_result)

    def _params(self):
        try:
            d, p, h = int(self.delay.get()), int(self.pct.get()), int(self.hor.get())
            amt, day = float(self.examt.get()), int(self.exday.get())
        except ValueError:
            raise ValueError("Delay, percentage, horizon, expense amount and day must be numbers.")
        if not 0 <= d <= 365: raise ValueError("Delay must be 0–365 days.")
        if not 0 <= p <= 100: raise ValueError("Partial payment must be 0–100 %.")
        if amt < 0 or not 0 <= day <= 365: raise ValueError("Expense must be ≥ 0 with day 0–365.")
        if self.inv.current() < 0: raise ValueError("Choose a payment to stress.")
        par = dict(invoice_id=self.choices[self.inv.current()]["id"], delay_days=d, paid_pct=p, default=self.default.get(), horizon=h)
        if amt > 0:
            par["expense"] = dict(company_id=self.cn[self.exco.get()], day=day, amount=lakh(amt))
        return par

    def run(self):
        try:
            par = self._params()
            res = self.ws.run_crisis(par)
        except ValueError as e:
            messagebox.showerror("Invalid scenario", str(e)); return
        self.net.set_data(self.ws.graph_data(), res)
        self.counter.config(text="Shock origin highlighted…", fg=AMBER)
        self.res.config(text="Replaying computed propagation…"); self.tab.set_rows([])

        def step(i, n, pair, expo, cnt):
            self.counter.config(text=f"Step {i}/{n}   affected companies {cnt}   modeled exposure {fmt_lakh(expo)}", fg=CORAL if expo else AMBER)

        def done():
            self.counter.config(text=f"Done · {len(res['direct']) + len(res['indirect'])} affected · exposure {fmt_lakh(res['total_exposure'])}", fg=CORAL)
            self._show(res); self.app.scenario_changed()
        self.net.play_shock(step, done)

    def _show(self, r):
        if not r:
            self.res.config(text="No scenario active (baseline)."); self.tab.set_rows([]); self.note.config(text="")
        else:
            self.res.config(text=(f"Initial shock: {fmt_lakh(r['initial_shock'])}\nDirect: {', '.join(r['direct']) or '—'}\n"
                                  f"Indirect: {', '.join(r['indirect']) or '—'}\nTotal modeled exposure: {fmt_lakh(r['total_exposure'])}\n"
                                  f"Earliest projected shortage: {r['earliest_shortage'] or 'none'}\nUnaffected: {len(r['unaffected'])} companies"))
            self.tab.set_rows([(c["company_id"], (c["name"], c["role"], fmt_lakh(c["extra_shortfall"]), c["first_breach_date"] or "—"),
                                "critical" if c["extra_shortfall"] else "warning") for c in r["companies"]])
            self.note.config(text="Assumptions: " + " ".join(r["assumptions"]) + "\nLimitations: simple trade-credit model; no new credit, no behavioural response; probabilities not modeled.")
        rows = self.ws.case_table(self.app.cid)
        self.cmp.set_rows([(i, (n, m["companies_short"], fmt_lakh(m["total_shortfall"]), fmt_lakh(m["focus_peak"]), m["earliest"] or "—"), None) for i, (n, m) in enumerate(rows)])

    def _pick(self, kind, obj):
        pass

    def _row(self, iid):
        self.net.select(("node", int(iid)))

    def clear(self):
        self.ws.clear_scenario(); self.net.set_data(self.ws.graph_data()); self.counter.config(text="Baseline restored.", fg=MUTED)
        self._show(None); self.app.scenario_changed()

    def save(self):
        try:
            self.ws.save_scenario(self.sname.get().strip() or "Scenario")
            toast(self.app, "Scenario saved", "success")
        except ValueError as e:
            messagebox.showinfo("Save scenario", str(e))


# ============================================================ CASH INTELLIGENCE
class CashPage(Page):
    def build(self):
        heading(self, "Cash Intelligence", "Daily projection from opening cash, invoice receipts/payments and scheduled transactions. "
                "Unapproved sales and loans are never counted as cash.").pack(fill="x", padx=18, pady=(14, 6))
        bar = tk.Frame(self, bg=BG); bar.pack(fill="x", padx=18)
        self.h = 30
        for d in (7, 30, 60, 90):
            ttk.Button(bar, text=f"{d} days", command=lambda d=d: self.set_h(d)).pack(side="left", padx=3)
        self.rec = tk.BooleanVar()
        ttk.Checkbutton(bar, text="Show recovery case (Balanced plan, expected values)", variable=self.rec, command=self.refresh).pack(side="left", padx=12)
        body = tk.Frame(self, bg=BG); body.pack(fill="both", expand=True, padx=18, pady=8)
        body.columnconfigure(0, weight=3); body.columnconfigure(1, weight=2); body.rowconfigure(0, weight=1)
        c = card(body); c.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.fig = mpl(c, 6, 4)[0]
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        self.fig.clear()
        gs = self.fig.add_gridspec(2, 1, height_ratios=[3, 1.4], hspace=.35)
        self.a1, self.a2 = self.fig.add_subplot(gs[0]), self.fig.add_subplot(gs[1])
        self.cv = FigureCanvasTkAgg(self.fig, master=c); self.cv.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=4)
        R = tk.Frame(body, bg=BG); R.grid(row=0, column=1, sticky="nsew")
        R.columnconfigure(0, weight=1); R.rowconfigure(1, weight=1); R.rowconfigure(3, weight=1)
        self.gap = tk.Label(R, text="", bg=PANEL, fg=TEXT, justify="left", anchor="w", wraplength=420, font=(kit.FONT[0], 9), padx=10, pady=8,
                            highlightbackground=GRID, highlightthickness=1); self.gap.grid(row=0, column=0, sticky="ew")
        self.sum = DataTable(R, [("i", "Cash item (confirmed / expected)", 250), ("a", "Amount", 100, "e")], height=8); self.sum.grid(row=1, column=0, sticky="nsew", pady=6)
        label(R, "MAJOR OBLIGATIONS", 8, MUTED, True, bg=BG).grid(row=2, column=0, sticky="w")
        self.ob = DataTable(R, [("d", "Date", 90), ("w", "Obligation", 220), ("a", "Amount", 90, "e")], height=6); self.ob.grid(row=3, column=0, sticky="nsew")
        self.view = None

    def set_h(self, d):
        self.h = d; self.refresh()

    def refresh(self):
        if not self.ws.has_data():
            return
        cid = self.app.cid
        v = self.ws.cash_view(cid, self.h); self.view = v
        L = PAISE_PER_LAKH
        base = np.array(v["base"]) / L
        stress = None if v["stress"] is None else np.array(v["stress"]) / L
        rec = None
        if self.rec.get() and stress is not None:
            cmpv = self.ws.compare_cases(cid)
            if "recovery" in cmpv:
                rec = np.array(cmpv["recovery"][:self.h + 1]) / L
        mn = v["min_cash"] / L
        x = np.arange(len(base))
        inflow, outflow = np.array(v["inflow"]) / L, np.array(v["outflow"]) / L
        w = 1 if self.h <= 30 else 7
        n = int(math.ceil(len(x) / w))
        binf = np.array([inflow[i * w:(i + 1) * w].sum() for i in range(n)]); bout = np.array([outflow[i * w:(i + 1) * w].sum() for i in range(n)])
        bx = np.array([i * w for i in range(n)])
        series = [("Baseline", base, CYAN, "-")]
        if stress is not None: series.append(("Stress", stress, CORAL, "--"))
        if rec is not None: series.append(("Recovery (expected)", rec, MINT, "-."))

        def f(p):
            k = max(2, int(len(x) * p))
            self.a1.clear(); style_ax(self.a1); self.a2.clear(); style_ax(self.a2)
            for nm, y, c, ls in series:
                self.a1.plot(x[:k], y[:k], color=c, ls=ls, lw=2, label=nm)
                self.a1.fill_between(x[:k], y[:k], mn, where=y[:k] < mn, color=CORAL, alpha=.3)
            self.a1.axhline(mn, color=AMBER, lw=1.2, ls=":", label=f"Minimum cash ({mn:.1f}L)")
            self.a1.set_xlim(0, len(x) - 1); allv = np.concatenate([s[1] for s in series] + [[mn]])
            self.a1.set_ylim(min(allv.min() * 1.1, -1), allv.max() * 1.1 + 1)
            self.a1.set_ylabel("Balance (₹ lakh)", fontsize=8); self.a1.set_title(self.app.company_name() + f" — {self.h}-day cash projection", fontsize=10)
            self.a1.legend(facecolor=NAVY, edgecolor=GRID, labelcolor=TEXT, fontsize=7, loc="upper right")
            kb = max(1, int(n * p))
            self.a2.bar(bx[:kb] + w * .1, binf[:kb] * 1, width=w * .4, color=MINT, label="Inflow")
            self.a2.bar(bx[:kb] + w * .5, -bout[:kb], width=w * .4, color=CORAL, label="Outflow")
            self.a2.set_xlim(0, len(x) - 1); self.a2.set_ylabel("Flows (L)", fontsize=8)
            self.a2.set_xlabel(f"Day (0 = {self.ws.as_of})", fontsize=8)
            self.a2.legend(facecolor=NAVY, edgecolor=GRID, labelcolor=TEXT, fontsize=7, loc="lower right")
            self.fig.subplots_adjust(left=.1, right=.97, top=.93, bottom=.12)
            self.cv.draw_idle()
        animate(self, kit.CHART, f)
        gb, gs = v["gap_base"], v["gap_stress"]
        txt = f"Baseline: {'no shortfall' if gb[0] == 0 else f'peak shortfall {fmt_lakh(gb[0])} from day {gb[1]} ({gb[2]} days below minimum)'}"
        if gs:
            txt += f"\nStress: {'no shortfall' if gs[0] == 0 else f'peak shortfall {fmt_lakh(gs[0])} from day {gs[1]} ({gs[2]} days below minimum)'}"
        self.gap.config(text="CASH GAP BREAKDOWN\n" + txt, fg=CORAL if (gs or gb)[0] else MINT)
        self.sum.set_rows([(i, (a, fmt_lakh(b)), None) for i, (a, b) in enumerate(v["summary"])])
        self.ob.set_rows([(i, (self.ws.date_of(d), w_, fmt_lakh(a)), "critical" if a < 0 else "good") for i, (d, w_, a) in enumerate(v["obligations"])])
