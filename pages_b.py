"""Inventory, Rescue, Funding, Recovery, Reports, Settings."""
import os
import json
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox, filedialog

import numpy as np

from . import kit
from .kit import (BG, PANEL, NAVY, CYAN, MINT, AMBER, CORAL, TEXT, MUTED, GRID, DataTable, animate, card, label, heading,
                  mpl, style_ax, toast, mix)
from .pages_a import Page, lk
from ..money import fmt_lakh, lakh, PAISE_PER_LAKH
from ..engine import inventory as inv, funding as fd
from .. import reports


# ============================================================ INVENTORY INTELLIGENCE
class InventoryPage(Page):
    def build(self):
        heading(self, "Inventory Intelligence", "Cash figures here are POTENTIAL recovery with stated assumptions — never confirmed cash. "
                "Production reserve is protected before anything is called surplus.").pack(fill="x", padx=18, pady=(14, 6))
        self.sumv = tk.Label(self, text="", bg=BG, fg=MUTED, anchor="w", font=(kit.MONO[0], 9)); self.sumv.pack(fill="x", padx=18)
        bar = tk.Frame(self, bg=BG); bar.pack(fill="x", padx=18, pady=4)
        ttk.Label(bar, text="Status").pack(side="left")
        self.fs = ttk.Combobox(bar, state="readonly", width=10, values=["all", "normal", "surplus", "slow", "dead", "held"]); self.fs.set("all"); self.fs.pack(side="left", padx=6)
        self.fs.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Label(bar, text="Search").pack(side="left", padx=(10, 0))
        self.q = tk.StringVar(); ttk.Entry(bar, textvariable=self.q, width=20).pack(side="left", padx=6)
        self.q.trace_add("write", lambda *a: self.refresh())
        body = tk.Frame(self, bg=BG); body.pack(fill="both", expand=True, padx=18, pady=4)
        body.columnconfigure(0, weight=3); body.columnconfigure(1, weight=2); body.rowconfigure(0, weight=1)
        L = tk.Frame(body, bg=BG); L.grid(row=0, column=0, sticky="nsew", padx=(0, 6)); L.rowconfigure(0, weight=1); L.columnconfigure(0, weight=1)
        self.tab = DataTable(L, [("sku", "SKU", 90), ("d", "Description", 170), ("loc", "Location", 70), ("q", "Qty", 55, "e"), ("v", "Book value", 80, "e"),
                                 ("cov", "Cover (d)", 65, "e"), ("idle", "Idle (d)", 60, "e"), ("st", "Status", 70), ("a", "Action", 80)], on_select=self._sel, height=9)
        self.tab.grid(row=0, column=0, sticky="nsew")
        cc = card(L); cc.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.fig, self.ax, self.cv = mpl(cc, 5, 2.0); self.cv.get_tk_widget().pack(fill="x")
        R = card(body); R.grid(row=0, column=1, sticky="nsew")
        label(R, "BATCH DETAIL", 8, MUTED, True).pack(anchor="w", padx=10, pady=(8, 0))
        self.title = tk.Label(R, text="Select a batch", bg=PANEL, fg=TEXT, font=(kit.FONT[0], 12, "bold"), anchor="w", wraplength=380, justify="left"); self.title.pack(fill="x", padx=10)
        self.info = tk.Label(R, text="", bg=PANEL, fg=MUTED, justify="left", anchor="nw", wraplength=380, font=(kit.FONT[0], 9)); self.info.pack(fill="x", padx=10)
        self.flow = tk.Canvas(R, bg=PANEL, height=44, highlightthickness=0); self.flow.pack(fill="x", padx=10, pady=4)
        self.warn = tk.Label(R, text="", bg=PANEL, fg=AMBER, font=(kit.FONT[0], 9, "bold"), wraplength=380, justify="left", anchor="w"); self.warn.pack(fill="x", padx=10)
        self.sc = DataTable(R, [("o", "Option", 130), ("c", "Cash (low–high)", 110, "e"), ("r", "Relief", 70, "e"), ("d", "Days", 40, "e"), ("n", "Note", 200)], height=5)
        self.sc.pack(fill="both", expand=True, padx=8, pady=6)
        self.batches = {}
        self.first = True

    def refresh(self):
        if not self.ws.has_data():
            return
        allb = self.ws.batches(self.app.cid)
        self.batches = {b["id"]: b for b in allb}
        s = inv.summary(allb)
        self.sumv.config(text=f"Total stock {fmt_lakh(s['total_value'])}   ·   Held {fmt_lakh(s['held_value'])}   ·   Slow/dead {fmt_lakh(s['slow_value'])}   ·   "
                              f"Potential surplus-sale cash (high case) {fmt_lakh(s['sellable_cash_high'])}")
        fl, q = self.fs.get(), self.q.get().lower()
        rows = []
        for b in allb:
            if fl != "all" and b["status"] != fl or q and q not in (b["sku"] + b["description"] + b["location"]).lower():
                continue
            r = inv.recommendation(b)
            rows.append((b["id"], (b["sku"], b["description"], b["location"], b["qty"], fmt_lakh(b["book_value"]),
                                   "n/a" if b["cover_days"] is None else f"{b['cover_days']:.0f}", b["idle_days"], b["status"], r["action"]),
                         {"held": "critical", "dead": "critical", "slow": "warning", "surplus": "warning"}.get(b["status"])))
        self.tab.set_rows(rows)
        cats = {}
        for b in allb:
            c = cats.setdefault(b["category"], [0, 0]); c[0] += b["book_value"]; c[1] += b["book_value"] if b["status"] == "held" else 0
        names = list(cats); tot = np.array([cats[n][0] for n in names]) / PAISE_PER_LAKH; held = np.array([cats[n][1] for n in names]) / PAISE_PER_LAKH

        def f(p):
            self.ax.clear(); style_ax(self.ax)
            self.ax.bar(names, tot * p, color=CYAN, label="Total book value"); self.ax.bar(names, held * p, color=CORAL, label="of which held")
            self.ax.set_ylabel("₹ lakh", fontsize=8); self.ax.set_title("Stock distribution by category", fontsize=9)
            self.ax.tick_params(axis="x", labelrotation=30, labelsize=7); self.ax.legend(facecolor=NAVY, edgecolor=GRID, labelcolor=TEXT, fontsize=7)
            self.fig.subplots_adjust(left=.09, right=.98, top=.88, bottom=.32); self.cv.draw_idle()
        animate(self, kit.CHART, f)

    def _sel(self, iid):
        b = self.batches[int(iid)]
        r = inv.recommendation(b)
        rows, warn = inv.scenarios(b, list(self.batches.values()))
        self.title.config(text=f"{b['sku']} — {b['description']}")
        cover = "n/a (no demand data)" if b["cover_days"] is None else f"{b['cover_days']:.0f} days"
        self.info.config(text=(f"{b['qty']} units @ {fmt_lakh(b['unit_cost'])[:-2]} · book {fmt_lakh(b['book_value'])} · margin {b['margin_pct']:.0f}%\n"
                               f"Location {b['location']} · age {b['age_days']}d · idle {b['idle_days']}d · cover {cover} · lead time {b['lead_time_days']}d"
                               f"{' · CRITICAL item' if b['critical'] else ''}\nStatus: {b['status']}"
                               f"{' (' + b['hold_status'] + ')' if b['hold_status'] != 'none' else ''}\n\nWHY: {r['reason']}"
                               f"{chr(10) + 'Estimated time to cash: ' + str(r['days']) + ' days (assumption).' if r['days'] else ''}"))
        self.warn.config(text=("⚠ " + warn + ": selling beyond surplus would break lead-time cover.") if warn else "")
        self.sc.set_rows([(i, (o["option"], f"{lk(o['cash_low'])}–{lk(o['cash_high'])}" if o["cash_high"] else "—",
                               lk(o["relief"]) if o["relief"] else "—", o["days"] or "—", o["note"]), "critical" if "ALL" in o["option"] else None)
                          for i, o in enumerate(rows)])
        # INVENTORY FLOW: stock splits into reserve / surplus / held
        c = self.flow; w = max(c.winfo_width(), 300) - 4
        qty = max(b["qty"], 1)
        if b["status"] == "held":
            segs = [("Held", qty, CORAL)]
        else:
            sell = r["sellable_qty"]; segs = [("Reserve", qty - sell, CYAN), ("Sellable surplus", sell, MINT)]

        def f(p):
            c.delete("all"); x = 2
            for nm, q, col in segs:
                ww = w * q / qty * p
                if ww > 1:
                    c.create_rectangle(x, 6, x + ww, 28, fill=col, outline=""); c.create_text(x + 4, 17, anchor="w", text=f"{nm} {q}" if ww > 90 else "", fill=BG, font=(kit.FONT[0], 8, "bold")); x += ww
            c.create_text(2, 38, anchor="w", text="Stock split: reserve for production · surplus · held", fill=MUTED, font=(kit.FONT[0], 7))
        animate(self, kit.STANDARD, f)


# ============================================================ INVENTORY RESCUE
class RescuePage(Page):
    def build(self):
        heading(self, "Inventory Rescue Center", "Only pathways that apply to the selected batch are shown. Restricted or expired stock is never offered for sale; "
                "a write-off is an accounting adjustment, not cash.").pack(fill="x", padx=18, pady=(14, 6))
        body = tk.Frame(self, bg=BG); body.pack(fill="both", expand=True, padx=18, pady=4)
        body.columnconfigure(1, weight=1); body.rowconfigure(0, weight=1)
        self.tab = DataTable(body, [("sku", "SKU", 90), ("h", "Hold", 110), ("v", "Book value", 80, "e"), ("b", "Best path (net)", 170)], on_select=self._sel, height=14)
        self.tab.grid(row=0, column=0, sticky="ns", padx=(0, 6))
        R = tk.Frame(body, bg=BG); R.grid(row=0, column=1, sticky="nsew"); R.rowconfigure(1, weight=1); R.columnconfigure(0, weight=1)
        self.banner = tk.Label(R, text="Select a held batch.", bg=PANEL, fg=TEXT, anchor="w", justify="left", wraplength=800, padx=10, pady=8,
                               highlightbackground=GRID, highlightthickness=1, font=(kit.FONT[0], 10, "bold")); self.banner.grid(row=0, column=0, sticky="ew")
        self.cv = tk.Canvas(R, bg=PANEL, highlightthickness=1, highlightbackground=GRID); self.cv.grid(row=1, column=0, sticky="nsew", pady=6)
        self.cv.bind("<Button-1>", self._click)
        self.det = tk.Label(R, text="", bg=PANEL, fg=TEXT, anchor="nw", justify="left", wraplength=800, padx=10, pady=8,
                            highlightbackground=GRID, highlightthickness=1, font=(kit.FONT[0], 9)); self.det.grid(row=2, column=0, sticky="ew")
        self.opts, self.batch, self.chosen = [], None, 0

    def refresh(self):
        if not self.ws.has_data():
            return
        held = [b for b in self.ws.batches(self.app.cid) if b["status"] == "held"]
        self.map = {b["id"]: b for b in held}
        rows = []
        for b in sorted(held, key=lambda b: -b["book_value"]):
            r = inv.rescue_options(b); best = r.get("best")
            rows.append((b["id"], (b["sku"], b["hold_status"] if not b["expired"] else "expired", fmt_lakh(b["book_value"]),
                                   f"{best['name']} ({lk(best['net'])})" if best else "Loss minimisation"), "critical" if b["restricted"] or b["expired"] else None))
        self.tab.set_rows(rows)
        if held and not self.batch:
            self.tab.select(max(held, key=lambda b: b["book_value"])["id"])

    def select(self, bid):
        self.tab.select(bid)

    def _sel(self, iid):
        b = self.map[int(iid)]; self.batch = b
        r = inv.rescue_options(b); self.opts = r["options"]; self.chosen = 0
        restricted = b["restricted"] or b["expired"]
        self.banner.config(text=("RESTRICTED STOCK — sale and shipment are blocked. " if restricted else "") + f"{b['sku']} ({b['hold_status']}): {b['hold_reason']}\n→ {r['recommendation']}",
                           fg=CORAL if restricted else TEXT)
        self._detail()
        animate(self, 1100, self._draw)

    def _draw(self, p=1.0):
        c = self.cv; c.delete("all"); n = len(self.opts)
        W = max(c.winfo_width(), 700)
        total = sum(len(o["steps"]) for o in self.opts) or 1
        seen = 0
        for i, o in enumerate(self.opts):
            y = 36 + i * 74
            sel = i == self.chosen
            c.create_rectangle(8, y - 30, W - 8, y + 34, outline=CYAN if sel else GRID, fill=mix(PANEL, CYAN, .06) if sel else PANEL)
            c.create_text(18, y - 20, anchor="w", text=o["name"], fill=TEXT, font=(kit.FONT[0], 10, "bold"))
            x = 20
            for j, s in enumerate(o["steps"]):
                vis = max(0, min(1, p * total - seen)); seen += 1
                if vis <= 0:
                    continue
                last = j == len(o["steps"]) - 1
                col = MINT if (last and o["net"] > 0 and o["name"] != "Write-off") else (AMBER if o["name"] == "Write-off" or last else CYAN)
                c.create_rectangle(x, y - 4, x + 110 * vis, y + 22, outline=col, fill=mix(PANEL, col, .12))
                if vis > .6:
                    c.create_text(x + 55, y + 9, text=s, fill=col, font=(kit.FONT[0], 8, "bold"))
                if j < len(o["steps"]) - 1 and vis > .9:
                    c.create_text(x + 122, y + 9, text="→", fill=MUTED, font=(kit.FONT[0], 12))
                x += 140
            netc = MINT if o["net"] > 0 else (MUTED if o["name"] == "Write-off" else CORAL)
            c.create_text(W - 20, y - 18, anchor="e", fill=netc, font=(kit.MONO[0], 10, "bold"),
                          text=("accounting loss " + lk(self.batch["book_value"]) + " (no cash)") if o["name"] == "Write-off" else f"net {lk(o['net'])}")
            if o["name"] != "Write-off":
                c.create_text(20, y + 28, anchor="w", fill=MUTED, font=(kit.FONT[0], 8), text=f"gross {lk(o['gross'])} · cost {lk(o['cost'])} · ~{o['days']}d · {int(o['prob'] * 100)}% success (assumed)")
            if o["missing"]:
                c.create_text(W - 20, y + 28, anchor="e", fill=AMBER, font=(kit.FONT[0], 8), text="missing: " + "; ".join(o["missing"])[:60])

    def _click(self, e):
        i = int((e.y - 6) // 74)
        if 0 <= i < len(self.opts):
            self.chosen = i; self._draw(); self._detail()

    def _detail(self):
        if not self.opts:
            return
        o = self.opts[self.chosen]
        self.det.config(text=f"{o['name'].upper()}  ·  {' → '.join(o['steps'])}\nOperational impact: {o['impact']}\nCompliance: {o['compliance']}\n"
                             f"Required human approvals: {', '.join(o['approvals'])}\nConfidence: {o['confidence']}\nMissing information: {'; '.join(o['missing']) or 'none identified'}")


# ============================================================ FUNDING
class FundingPage(Page):
    def build(self):
        heading(self, "Funding Navigator", "ILLUSTRATIVE TERMS ONLY — not offers, quotes or approvals. LiquidityX is not a lender or a regulated financial adviser. "
                "Edit the assumptions to match real quotes.").pack(fill="x", padx=18, pady=(14, 6))
        bar = tk.Frame(self, bg=BG); bar.pack(fill="x", padx=18)
        ttk.Label(bar, text="Amount needed (₹ lakh)").pack(side="left")
        self.amt = tk.StringVar(value="10"); ttk.Spinbox(bar, from_=0.1, to=10000, increment=1, width=8, textvariable=self.amt).pack(side="left", padx=6)
        ttk.Button(bar, text="Use projected gap", command=self.use_gap).pack(side="left", padx=4)
        ttk.Button(bar, text="Compare", style="Accent.TButton", command=self.refresh).pack(side="left", padx=4)
        body = tk.Frame(self, bg=BG); body.pack(fill="both", expand=True, padx=18, pady=6)
        body.columnconfigure(0, weight=3); body.columnconfigure(1, weight=2); body.rowconfigure(0, weight=1)
        L = tk.Frame(body, bg=BG); L.grid(row=0, column=0, sticky="nsew", padx=(0, 6)); L.columnconfigure(0, weight=1); L.rowconfigure(1, weight=1)
        self.tab = DataTable(L, [("n", "Option", 150), ("np", "Net proceeds", 85, "e"), ("f", "Fee", 60, "e"), ("i", "Interest", 65, "e"), ("t", "Total repay", 85, "e"),
                                 ("e", "Cost %", 55, "e"), ("d", "Days", 40, "e"), ("c", "Collateral", 190)], on_select=self._sel, height=6)
        self.tab.grid(row=0, column=0, sticky="ew")
        cc = card(L); cc.grid(row=1, column=0, sticky="nsew", pady=6)
        self.fig, self.ax, self.cv = mpl(cc, 6, 3.2); self.cv.get_tk_widget().pack(fill="both", expand=True)
        R = card(body); R.grid(row=0, column=1, sticky="nsew")
        label(R, "EDIT ASSUMPTIONS (selected option)", 8, MUTED, True).pack(anchor="w", padx=10, pady=(8, 4))
        self.vars = {}
        for k, t in (("annual_rate", "Annual interest rate %"), ("fee_pct", "Upfront fee %"), ("tenor_days", "Tenor (days)"), ("installments", "Installments"), ("days_to_funds", "Days to funds")):
            r = tk.Frame(R, bg=PANEL); r.pack(fill="x", padx=10, pady=2); label(r, t, 9).pack(side="left")
            v = tk.StringVar(); ttk.Entry(r, textvariable=v, width=8).pack(side="right"); self.vars[k] = v
        ttk.Button(R, text="Save assumptions", command=self.save).pack(fill="x", padx=10, pady=(8, 2))
        ttk.Button(R, text="Reset to defaults", command=self.reset).pack(fill="x", padx=10)
        self.elig = tk.Label(R, text="", bg=PANEL, fg=MUTED, wraplength=340, justify="left", anchor="nw", font=(kit.FONT[0], 9)); self.elig.pack(fill="x", padx=10, pady=8)
        self.opts, self.cur = [], None

    def use_gap(self):
        g = self.ws.recovery(self.app.cid)["gap"]
        if not g:
            toast(self.app, "No projected gap in the current scenario", "info"); return
        self.amt.set(f"{g / PAISE_PER_LAKH:.2f}"); self.refresh()

    def refresh(self):
        if not self.ws.has_data():
            return
        try:
            a = float(self.amt.get()); assert a > 0
        except Exception:
            messagebox.showerror("Funding", "Enter a positive amount in lakh."); return
        self.opts = self.ws.funding_compare(self.app.cid, lakh(a))
        self.tab.set_rows([(o["name"], (o["name"], fmt_lakh(o["net_proceeds"]), fmt_lakh(o["fee"]), fmt_lakh(o["interest"]), fmt_lakh(o["total_repayment"]),
                                         f"{o['effective_cost_pct']:.1f}%", o["days_to_funds"], o["collateral"]), None) for o in self.opts])
        self._chart()

    def _chart(self):
        cid = self.app.cid
        v = self.ws.cash_view(cid, 90)
        base = v["stress"] if v["stress"] is not None else v["base"]
        L = PAISE_PER_LAKH
        pal = [CYAN, MINT, AMBER, "#B79CFF", "#FF9E7A", "#7AE0FF"]
        x = np.arange(len(base)); mn = v["min_cash"] / L
        curves = [(o["name"], np.array(fd.apply_to_balances(base, o)) / L) for o in self.opts]
        b0 = np.array(base) / L

        def f(p):
            k = max(2, int(len(x) * p))
            self.ax.clear(); style_ax(self.ax)
            self.ax.plot(x[:k], b0[:k], color=CORAL if v["stress"] is not None else MUTED, lw=2.2, label="Without funding")
            for i, (n, y) in enumerate(curves):
                self.ax.plot(x[:k], y[:k], color=pal[i % 6], lw=1.3, label=n)
            self.ax.axhline(mn, color=AMBER, ls=":", lw=1.2)
            self.ax.set_title(f"{self.app.company_name()}: balance with each ILLUSTRATIVE option (repayments included)", fontsize=9)
            self.ax.set_ylabel("₹ lakh", fontsize=8); self.ax.set_xlabel("Day", fontsize=8)
            self.ax.legend(facecolor=NAVY, edgecolor=GRID, labelcolor=TEXT, fontsize=6, ncol=2, loc="lower right")
            self.fig.subplots_adjust(left=.09, right=.98, top=.9, bottom=.14); self.cv.draw_idle()
        animate(self, kit.CHART, f)

    def _sel(self, name):
        self.cur = name
        a = self.ws.funding_assumptions()[name]
        for k, v in self.vars.items():
            v.set(str(a[k]))
        self.elig.config(text=f"Eligibility assumption: {a['eligibility']}\nCollateral: {a['collateral']}")

    def save(self):
        if not self.cur:
            return
        try:
            a = dict(self.ws.funding_assumptions()); cur = dict(a[self.cur])
            for k, v in self.vars.items():
                cur[k] = float(v.get()) if k in ("annual_rate", "fee_pct") else int(float(v.get()))
            if cur["installments"] < 1 or cur["tenor_days"] < 1 or min(cur["annual_rate"], cur["fee_pct"], cur["days_to_funds"]) < 0:
                raise ValueError
        except (ValueError, KeyError):
            messagebox.showerror("Funding", "Check the values: rates ≥ 0, tenor and installments ≥ 1."); return
        a[self.cur] = cur
        from ..db import set_setting
        set_setting(self.ws.conn, "funding", a); toast(self.app, "Assumptions saved", "success"); self.refresh()

    def reset(self):
        from ..db import set_setting
        set_setting(self.ws.conn, "funding", fd.DEFAULTS); self.refresh(); toast(self.app, "Defaults restored", "info")


# ============================================================ RECOVERY PLANNER
class RecoveryPage(Page):
    def build(self):
        heading(self, "Recovery Planner", "Combines collections, inventory, rescue, extensions and financing. Expected values are not confirmed cash; extensions are relief, "
                "not receipts; a gap is only 'solved' if actions cover it by the deadline.").pack(fill="x", padx=18, pady=(14, 6))
        top = tk.Frame(self, bg=BG); top.pack(fill="x", padx=18)
        ttk.Button(top, text="Generate plans", style="Accent.TButton", command=self.generate).pack(side="left")
        self.status = tk.Label(top, text="", bg=BG, fg=MUTED, font=(kit.FONT[0], 10, "bold")); self.status.pack(side="left", padx=12)
        self.tab = DataTable(self, [("l", "Plan", 170), ("s", "Gap covered by deadline?", 150), ("c", "Exp. cash", 80, "e"), ("r", "Relief (not cash)", 100, "e"), ("co", "Cost", 70, "e"),
                                    ("d", "Last day", 55, "e"), ("k", "Op. risk", 55, "e"), ("re", "Residual", 65, "e"), ("pp", "Peak shortfall after plan", 150, "e")], on_select=self._sel, height=4)
        self.tab.pack(fill="x", padx=18, pady=6)
        mid = tk.Frame(self, bg=BG); mid.pack(fill="both", expand=True, padx=18)
        mid.columnconfigure(0, weight=3); mid.columnconfigure(1, weight=2); mid.rowconfigure(0, weight=1)
        self.cv = tk.Canvas(mid, bg=PANEL, highlightthickness=1, highlightbackground=GRID, height=260); self.cv.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        R = card(mid); R.grid(row=0, column=1, sticky="nsew")
        row = tk.Frame(R, bg=PANEL); row.pack(fill="x", padx=8, pady=(8, 2)); label(row, "Compare with:", 9).pack(side="left")
        self.cmp = ttk.Combobox(row, state="readonly", width=24); self.cmp.pack(side="left", padx=6); self.cmp.bind("<<ComboboxSelected>>", lambda e: self._explain())
        self.why = tk.Label(R, text="", bg=PANEL, fg=TEXT, justify="left", anchor="nw", wraplength=380, font=(kit.FONT[0], 9)); self.why.pack(fill="both", expand=True, padx=10, pady=4)
        self.appr = ttk.Button(R, text="Approve selected plan…", style="Accent.TButton", command=self.approve); self.appr.pack(fill="x", padx=10, pady=8)
        self.later = tk.Label(self, text="", bg=BG, fg=MUTED, justify="left", anchor="w", wraplength=1100, font=(kit.FONT[0], 8)); self.later.pack(fill="x", padx=18, pady=(2, 8))
        self.out, self.sel = None, None

    def refresh(self):
        if self.out is None and self.ws.has_data():
            self.status.config(text="Press Generate plans to analyse the focus company in the current scenario.", fg=MUTED)

    def generate(self):
        if not self.ws.has_data():
            return
        out = self.ws.recovery(self.app.cid); self.out = out
        if not out["plans"]:
            self.tab.set_rows([]); self.cv.delete("all"); self.why.config(text="\n".join(out["notes"]))
            self.status.config(text="No projected cash gap — no recovery plan required.", fg=MINT); return
        some = next(iter(out["plans"].values()))
        self.status.config(text=f"Gap {fmt_lakh(out['gap'])} · deadline {out['deadline_date']} (day {out['deadline_day']})", fg=CORAL)
        self.tab.set_rows([(k, (p["label"], "YES" if p["solved"] else "NO — NOT SOLVED", fmt_lakh(p["expected_cash"]), fmt_lakh(p["expected_relief"]),
                                fmt_lakh(p["cost"]), p["last_day"], p["risk"], fmt_lakh(p["residual"]), "n/a" if p["post_peak"] is None else fmt_lakh(p["post_peak"])), "good" if p["solved"] else "critical") for k, p in out["plans"].items()])
        self.cmp["values"] = list(out["plans"])
        self.later.config(text=("Additional later recovery NOT counted toward the deadline: " + "; ".join(f"D+{a['day']} {a['name']} ({lk(a['expected_cash'])})" for a in out["later"])) if out["later"] else "")
        first = next(iter(out["plans"])); self.tab.select(first)

    def _sel(self, key):
        self.sel = key; p = self.out["plans"][key]
        self.cmp.set(next((k for k in self.out["plans"] if k != key), ""))
        animate(self, 1300, lambda t: self._draw(p, t)); self._explain()

    def _draw(self, p, t):
        c = self.cv; c.delete("all"); W = max(c.winfo_width(), 600)
        evs = [(a["day"], a["name"], a["status"], a["expected_cash"] or a["expected_relief"], "relief" if a["expected_relief"] else "cash") for a in p["actions"]]
        if p["financing"]:
            f = p["financing"]; evs.append((f["days_to_funds"], f"Financing: {f['name']} (ILLUSTRATIVE)", "awaiting approval", f["net_proceeds"], "fin"))
        evs.sort(); dl = p["deadline_day"]; span = max(dl + 3, max([e[0] for e in evs] + [1]) + 2)
        x0, x1, y = 40, W - 40, 40
        X = lambda d: x0 + (x1 - x0) * d / span
        c.create_line(x0, y, x1, y, fill=GRID, width=2)
        c.create_line(X(dl), y - 14, X(dl), 250, fill=CORAL, dash=(4, 3)); c.create_text(X(dl), y - 22, text=f"DEADLINE D+{dl}", fill=CORAL, font=(kit.FONT[0], 8, "bold"))
        cum = 0; yy = 70
        for d in range(0, span + 1, max(1, span // 8)):
            c.create_text(X(d), y + 12, text=f"D+{d}", fill=MUTED, font=(kit.FONT[0], 7))
        for i, (d, name, st, amt, kind) in enumerate(evs):
            vis = max(0, min(1, t * (len(evs) + 1) * (1 if span else 1) - i)) if True else 1
            if X(d) > x0 + (x1 - x0) * t * 1.05 and not kit.REDUCED:
                continue
            col = CYAN if kind == "fin" else (MINT if st == "can start now" else AMBER)
            c.create_oval(X(d) - 6, y - 6, X(d) + 6, y + 6, fill=col, outline="")
            c.create_line(X(d), y + 6, X(d), yy + 8, fill=mix(PANEL, col, .5))
            c.create_text(min(X(d) + 8, W - 250), yy + 8, anchor="w", fill=TEXT, font=(kit.FONT[0], 8, "bold"), text=f"D+{d}  {name[:48]}")
            c.create_text(min(X(d) + 8, W - 250), yy + 22, anchor="w", fill=col, font=(kit.FONT[0], 8),
                          text=f"{st} · {'relief' if kind == 'relief' else 'expected cash'} {lk(amt)}")
            yy += 36
        c.create_text(12, 248, anchor="w", fill=MINT if p["solved"] else CORAL, font=(kit.FONT[0], 9, "bold"),
                      text=("Residual risk: " + ("gap covered by deadline on expected values; outcomes remain uncertain." if p["solved"] else f"NOT SOLVED — {lk(p['residual'])} uncovered by deadline.")))

    def _explain(self):
        if not self.sel:
            return
        a = self.out["plans"][self.sel]; b = self.out["plans"].get(self.cmp.get())
        txt = f"WHY THIS PLAN\n{a['why']}\n"
        if a.get("post_peak"):
            txt += (f"\nAFTER-PLAN CHECK (re-simulated): a shortfall of {fmt_lakh(a['post_peak'])} remains later, because repayments/deferrals fall due before the delayed customer cash returns. "
                    "The deadline gap is covered, but this is NOT a full fix.\n")
        elif a.get("post_peak") == 0:
            txt += "\nAFTER-PLAN CHECK (re-simulated): no shortfall remains.\n"
        if b and b is not a:
            d = lambda k, f=lambda v: v: f"{f(a[k])} vs {f(b[k])}"
            txt += (f"\nVS {b['label'].upper()}\nCost: {d('cost', fmt_lakh)}\nLast action day: {d('last_day')}\nOperational risk: {d('risk')}\n")
            better = []
            if a["cost"] < b["cost"]: better.append("cheaper")
            if a["last_day"] < b["last_day"]: better.append("faster")
            if a["risk"] < b["risk"]: better.append("lower risk")
            txt += "This plan is " + (", ".join(better) if better else "not better on cost, speed or risk") + "."
        self.why.config(text=txt)

    def approve(self):
        if not self.sel:
            return
        p = self.out["plans"][self.sel]
        if not p["solved"]:
            if not messagebox.askyesno("Approve unsolved plan?", "This plan does NOT cover the gap by the deadline. Record it anyway?"):
                return
        if not messagebox.askyesno("Human approval", f"Approve '{p['label']}'?\nExpected cash {fmt_lakh(p['expected_cash'])}, cost {fmt_lakh(p['cost'])}.\n"
                                   "This records the decision in the audit log; it does not move any money."):
            return
        pid = self.ws.save_plan(self.app.cid, p); self.ws.approve_plan(pid)
        toast(self.app, "Plan approved and logged", "success"); self.app.scenario_changed()


# ============================================================ REPORTS
class ReportsPage(Page):
    def build(self):
        heading(self, "Reports", "HTML reports can be printed or saved as PDF from your browser. Every report states its date, scope, assumptions, limitations and "
                "which figures are actual, estimated or simulated.").pack(fill="x", padx=18, pady=(14, 6))
        self.tab = DataTable(self, [("k", "Report", 300)], height=9); self.tab.pack(fill="x", padx=18, pady=6)
        self.tab.set_rows([(k, (k,), None) for k in reports.KINDS])
        bar = tk.Frame(self, bg=BG); bar.pack(fill="x", padx=18)
        ttk.Button(bar, text="Generate HTML report", style="Accent.TButton", command=lambda: self.make("html")).pack(side="left")
        ttk.Button(bar, text="Export CSV", command=lambda: self.make("csv")).pack(side="left", padx=6)
        self.msg = tk.Label(self, text="", bg=BG, fg=MUTED, anchor="w", justify="left"); self.msg.pack(fill="x", padx=18, pady=8)

    def make(self, fmt):
        sel = self.tab.tree.selection()
        if not sel:
            messagebox.showinfo("Reports", "Select a report first."); return
        kind = sel[0]
        folder = os.path.join(os.path.dirname(os.path.abspath(self.ws.path)) if self.ws.path != ":memory:" else os.path.expanduser("~/.liquidityx"), "reports")
        os.makedirs(folder, exist_ok=True)
        self.msg.config(text="Generating…", fg=AMBER); self.update_idletasks()
        rep = reports.build(self.ws, kind, self.app.cid)
        fn = os.path.join(folder, f"{kind.lower().replace(' ', '_')}_{rep['meta']['generated'][:10]}.{fmt}")
        (reports.to_html if fmt == "html" else reports.to_csv)(rep, fn)
        self.ws.conn.execute("INSERT INTO audit_log(ts,action,detail) VALUES(datetime('now'),'report',?)", (fn,)); self.ws.conn.commit()
        self.msg.config(text=f"Saved: {fn}", fg=MINT); toast(self.app, "Report generated", "success")
        if fmt == "html":
            webbrowser.open("file://" + fn)


# ============================================================ SETTINGS / COMMERCIAL
TIERS = {"Starter": dict(price=4999, companies=15, users=2, note="Local workspace, CSV import/export, core engines"),
         "Growth": dict(price=19999, companies=75, users=10, note="+ premium analytics, scheduled reports, alert thresholds"),
         "Enterprise": dict(price=0, companies=1000, users=100, note="+ SSO, audit exports, ERP integrations, SLA (custom quote)")}


class SettingsPage(Page):
    def build(self):
        heading(self, "Settings & Commercial Product", "Prototype status: single-user local application — NOT production-ready enterprise software.").pack(fill="x", padx=18, pady=(14, 6))
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=18, pady=6)
        g = tk.Frame(nb, bg=BG); nb.add(g, text="  General  ")
        self.rm = tk.BooleanVar(value=kit.REDUCED); self.si = tk.BooleanVar()
        ttk.Checkbutton(g, text="Reduced motion (disables animations)", variable=self.rm, command=self._rm).pack(anchor="w", padx=14, pady=(14, 4))
        ttk.Checkbutton(g, text="Skip the intro on launch", variable=self.si, command=self._si).pack(anchor="w", padx=14, pady=4)
        d = tk.Frame(nb, bg=BG); nb.add(d, text="  Data  ")
        self.dinfo = tk.Label(d, text="", bg=BG, fg=MUTED, justify="left", anchor="w", wraplength=900); self.dinfo.pack(fill="x", padx=14, pady=10)
        for t, cmd in (("Load synthetic demo network", self.load_demo), ("Write sample CSV templates", self.write_samples),
                       ("Import companies.csv…", lambda: self.imp("companies")), ("Import invoices.csv…", lambda: self.imp("invoices")),
                       ("Erase workspace (start empty)…", self.erase)):
            ttk.Button(d, text=t, command=cmd).pack(anchor="w", padx=14, pady=3)
        label(d, "CSV columns — companies: name,type,opening_cash,min_cash (rupees).  invoices: payer,payee,amount,due_date(YYYY-MM-DD)[,expected_delay_days].",
              8, MUTED, bg=BG, wraplength=900, justify="left").pack(anchor="w", padx=14, pady=8)
        c = tk.Frame(nb, bg=BG); nb.add(c, text="  Commercial product  ")
        self.tiers = DataTable(c, [("t", "Tier (ILLUSTRATIVE — editable, not market-validated)", 330), ("p", "Price ₹/month", 110, "e"), ("c", "Companies", 80, "e"), ("u", "Users", 60, "e"), ("n", "Includes", 380)], on_select=self._tsel, height=3)
        self.tiers.pack(fill="x", pady=(10, 4))
        er = tk.Frame(c, bg=BG); er.pack(anchor="w", pady=2); label(er, "Edit price of selected tier (₹/month):", 9, bg=BG).pack(side="left")
        self.price = tk.StringVar(); ttk.Entry(er, textvariable=self.price, width=10).pack(side="left", padx=6); ttk.Button(er, text="Save", command=self._tsave).pack(side="left")
        txt = tk.Text(c, bg=PANEL, fg=TEXT, wrap="word", height=16, relief="flat", font=(kit.FONT[0], 9), padx=10, pady=8)
        txt.pack(fill="both", expand=True, pady=6)
        txt.insert("1.0", COMMERCIAL); txt.config(state="disabled")
        self.cur_tier = None

    def _rm(self):
        kit.set_reduced(self.rm.get()); from ..db import set_setting; set_setting(self.ws.conn, "reduced_motion", self.rm.get())

    def _si(self):
        from ..db import set_setting; set_setting(self.ws.conn, "skip_intro", self.si.get())

    def refresh(self):
        from ..db import get_setting
        self.si.set(bool(get_setting(self.ws.conn, "skip_intro", False))); self.rm.set(kit.REDUCED)
        n = self.ws.conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        self.dinfo.config(text=f"Workspace file: {self.ws.path}\nCompanies: {n} · Data type: {'SYNTHETIC DEMO' if self.ws.is_demo() else ('USER-PROVIDED' if n else 'empty')}")
        t = get_setting(self.ws.conn, "tiers", TIERS)
        self.tiers.set_rows([(k, (k, f"{v['price']:,}" if v["price"] else "custom", v["companies"], v["users"], v["note"]), None) for k, v in t.items()])

    def _tsel(self, k):
        self.cur_tier = k; from ..db import get_setting
        self.price.set(str(get_setting(self.ws.conn, "tiers", TIERS)[k]["price"]))

    def _tsave(self):
        from ..db import get_setting, set_setting
        try:
            p = int(self.price.get()); assert p >= 0
        except Exception:
            messagebox.showerror("Tier", "Enter a non-negative whole number."); return
        t = get_setting(self.ws.conn, "tiers", TIERS); t[self.cur_tier]["price"] = p; set_setting(self.ws.conn, "tiers", t); self.refresh()

    def load_demo(self):
        if self.ws.has_data() and not messagebox.askyesno("Demo", "The workspace already contains data. Load demo only works on an empty workspace.\nErase first?"):
            return
        if self.ws.has_data():
            self.erase(confirm=False)
        self.ws.load_demo(); self.app.reload(); toast(self.app, "Synthetic demo loaded", "success")

    def erase(self, confirm=True):
        if confirm and not messagebox.askyesno("Erase workspace", "Delete ALL companies, invoices, inventory, scenarios and plans?"):
            return
        with self.ws.conn:
            for t in ("recovery_plans", "scenarios", "inventory_batches", "cash_transactions", "invoices", "relationships", "companies"):
                self.ws.conn.execute(f"DELETE FROM {t}")
        self.ws.clear_scenario(); self.app.reload()

    def write_samples(self):
        folder = os.path.join(os.path.dirname(os.path.abspath(self.ws.path)) if self.ws.path != ":memory:" else os.path.expanduser("~/.liquidityx"), "samples")
        os.makedirs(folder, exist_ok=True)
        open(os.path.join(folder, "companies.csv"), "w").write("name,type,opening_cash,min_cash\nAcme Works,manufacturer,2500000,800000\nBeta Steel,supplier,900000,300000\nGamma Retail,customer,8000000,1000000\n")
        open(os.path.join(folder, "invoices.csv"), "w").write("payer,payee,amount,due_date,expected_delay_days\nGamma Retail,Acme Works,3000000,2026-10-25,0\nAcme Works,Beta Steel,2200000,2026-10-22,0\n")
        messagebox.showinfo("Samples", f"Sample CSV files written to:\n{folder}")

    def imp(self, kind):
        p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if not p:
            return
        try:
            n, errs = self.ws.import_csv(kind, p)
        except Exception as e:
            messagebox.showerror("Import failed", str(e)); return
        if errs:
            messagebox.showerror("Import rejected — nothing was imported", "\n".join(errs[:12])); return
        self.app.reload(); toast(self.app, f"Imported {n} rows", "success")


COMMERCIAL = """TARGET CUSTOMERS
• Small and medium manufacturers · distributors and wholesalers · supply-chain finance teams · procurement teams · financial risk analysts · larger enterprises with multi-company supplier networks.

REVENUE STREAMS (hypotheses — not market-validated)
• SaaS subscriptions · premium analytics · enterprise licensing · integration/implementation services · financing-partner referrals where legally permitted.
• Tier prices above are ILLUSTRATIVE placeholders and are editable. No evidence yet that customers will pay them.

IMPLEMENTED IN THIS PROTOTYPE
✓ Single local workspace (SQLite) · synthetic demo data · CSV import (companies, invoices) · CSV and HTML report export · audit log for scenarios, approvals and reports
✓ Deterministic cash, network-cascade, inventory, rescue, funding and recovery engines with automated tests

ROADMAP (NOT implemented)
○ Company workspaces and secure multi-company data separation · role-based permissions · SSO
○ Configurable alert thresholds and scheduled alerts · PDF report generation
○ ERP / accounting integrations (Tally, SAP, Zoho, etc.) · inventory CSV import
○ Authorised financing-partner integrations (LiquidityX is not a lender or regulated adviser)
○ PostgreSQL multi-user deployment, authentication and hardening before any networked use
"""
