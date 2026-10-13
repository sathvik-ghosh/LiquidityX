"""Main window: splash, sidebar, top bar, page router, copilot panel, onboarding."""
import os
import time
import tkinter as tk
from tkinter import ttk, messagebox

from . import kit
from .kit import BG, NAVY, PANEL, CYAN, MINT, AMBER, CORAL, TEXT, MUTED, GRID, animate, mix, toast
from .pages_a import CommandCenter, NetworkPage, CrisisPage, CashPage
from .pages_b import InventoryPage, RescuePage, FundingPage, RecoveryPage, ReportsPage, SettingsPage
from ..db import get_setting, set_setting
from .. import copilot

PAGES = [("Command Center", "◈", CommandCenter), ("Financial Network", "⬡", NetworkPage), ("Crisis Simulator", "⚡", CrisisPage),
         ("Cash Intelligence", "∿", CashPage), ("Inventory Intelligence", "▦", InventoryPage), ("Inventory Rescue", "✚", RescuePage),
         ("Funding Navigator", "₹", FundingPage), ("Recovery Planner", "⟳", RecoveryPage), ("Reports", "▤", ReportsPage), ("Settings", "⚙", SettingsPage)]


class Splash(tk.Canvas):
    def __init__(self, root, done):
        super().__init__(root, bg=BG, highlightthickness=0)
        self.place(x=0, y=0, relwidth=1, relheight=1); self.lift()
        self.done, self.finished = done, False
        for ev in ("<Button-1>", "<Escape>", "<space>", "<Return>"):
            root.bind(ev, self.skip, add="+")
        self.tok = animate(self, 2300, self.frame, done=self.finish, ease=lambda t: t)
        self.focus_set()

    def frame(self, t):
        self.delete("all")
        w, h = max(self.winfo_width(), 800), max(self.winfo_height(), 500)
        fade = 1 - max(0, (t - .88) / .12)
        word = "LIQUIDITYX"
        a = min(1, t / .3); sp = 26 - 16 * min(1, t / .45)
        total = (len(word) - 1) * (26 + sp) / 1.0
        x = w / 2 - total / 2
        for ch in word:
            self.create_text(x, h / 2 - 20, text=ch, fill=mix(BG, TEXT, a * fade), font=(kit.FONT[0], 34, "bold"))
            x += 26 + sp
        if t > .35:
            p = min(1, (t - .35) / .3)
            self.create_line(0, h / 2 + 22, w * p, h / 2 + 22, fill=mix(BG, CYAN, fade), width=2)
        if t > .55:
            a2 = min(1, (t - .55) / .25)
            self.create_text(w / 2, h / 2 + 52, text="See the crisis before it spreads.", fill=mix(BG, MUTED, a2 * fade), font=(kit.FONT[0], 13))
        self.create_text(w / 2, h - 24, text="Click or press any key to skip", fill=mix(BG, GRID, fade * .8), font=(kit.FONT[0], 8))

    def skip(self, e=None):
        if self.tok:
            self.tok["cancel"] = True
        self.finish()

    def finish(self):
        if self.finished:
            return
        self.finished = True
        for ev in ("<Button-1>", "<Escape>", "<space>", "<Return>"):
            self.winfo_toplevel().unbind(ev)
        self.destroy(); self.done()


class App(tk.Tk):
    def __init__(self, ws, intro=True, onboarding=True):
        super().__init__()
        self.ws = ws
        self.title("LIQUIDITYX — Financial Network Intelligence & Crisis Recovery")
        self.geometry("1440x880"); self.minsize(1100, 700)
        kit.init_theme(self)
        kit.set_reduced(get_setting(ws.conn, "reduced_motion", False))
        self.cid = ws.default_focus()
        self.pages, self.current, self.name = {}, None, None
        self.protocol("WM_DELETE_WINDOW", self.shutdown)
        self._layout()
        self.reload(show=False)
        self.goto("Command Center")
        self.copilot_open = False
        skip = get_setting(ws.conn, "skip_intro", False) or kit.REDUCED or not intro
        after = (lambda: self.after(50, self.onboard)) if onboarding else (lambda: None)
        if skip:
            after()
        else:
            self.update_idletasks(); Splash(self, after)

    # ---------------------------------------------------------------- layout
    def _layout(self):
        self.columnconfigure(1, weight=1); self.rowconfigure(0, weight=1)
        sb = tk.Frame(self, bg=NAVY, width=230); sb.grid(row=0, column=0, sticky="ns"); sb.grid_propagate(False)
        tk.Label(sb, text="LIQUIDITYX", bg=NAVY, fg=TEXT, font=(kit.FONT[0], 15, "bold")).pack(anchor="w", padx=18, pady=(18, 0))
        tk.Label(sb, text="OBSIDIAN TERMINAL", bg=NAVY, fg=CYAN, font=(kit.FONT[0], 7, "bold")).pack(anchor="w", padx=18, pady=(0, 14))
        self.nav = tk.Frame(sb, bg=NAVY); self.nav.pack(fill="x")
        self.ind = tk.Frame(self.nav, bg=CYAN, width=3, height=34); self.ind.place(x=0, y=0)
        self.btns = {}
        for i, (name, icon, _) in enumerate(PAGES):
            b = tk.Button(self.nav, text=f"  {icon}   {name}", anchor="w", bg=NAVY, fg=MUTED, activebackground=PANEL, activeforeground=TEXT, bd=0, relief="flat",
                          font=(kit.FONT[0], 10), padx=14, pady=7, command=lambda n=name: self.goto(n), cursor="hand2", highlightthickness=0)
            b.pack(fill="x", pady=1)
            b.bind("<Enter>", lambda e, b=b, n=name: b.config(bg=PANEL) if n != self.name else None)
            b.bind("<Leave>", lambda e, b=b, n=name: b.config(bg=NAVY) if n != self.name else None)
            self.btns[name] = b
        self.engine = tk.Label(sb, text="● Engine ready", bg=NAVY, fg=MINT, font=(kit.FONT[0], 8), anchor="w"); self.engine.pack(side="bottom", anchor="w", padx=18, pady=(0, 8))
        tk.Label(sb, text="◉ Demo User · local workspace", bg=NAVY, fg=MUTED, font=(kit.FONT[0], 8)).pack(side="bottom", anchor="w", padx=18)
        main = tk.Frame(self, bg=BG); main.grid(row=0, column=1, sticky="nsew"); main.columnconfigure(0, weight=1); main.rowconfigure(1, weight=1)
        tb = tk.Frame(main, bg=NAVY); tb.grid(row=0, column=0, sticky="ew")
        pad = dict(side="left", padx=(12, 0), pady=8)
        tk.Label(tb, text="Company", bg=NAVY, fg=MUTED, font=(kit.FONT[0], 8)).pack(**pad)
        self.co = ttk.Combobox(tb, state="readonly", width=26); self.co.pack(side="left", padx=(6, 0), pady=8); self.co.bind("<<ComboboxSelected>>", self._co)
        tk.Label(tb, text="Search", bg=NAVY, fg=MUTED, font=(kit.FONT[0], 8)).pack(**pad)
        self.search = ttk.Entry(tb, width=18); self.search.pack(side="left", padx=(6, 0), pady=8); self.search.bind("<Return>", self._search)
        tk.Label(tb, text="Scenario", bg=NAVY, fg=MUTED, font=(kit.FONT[0], 8)).pack(**pad)
        self.sc = ttk.Combobox(tb, state="readonly", width=22, values=["Baseline"]); self.sc.set("Baseline"); self.sc.pack(side="left", padx=(6, 0), pady=8)
        self.sc.bind("<<ComboboxSelected>>", self._scenario)
        self.status = tk.Label(tb, text="Baseline", bg=NAVY, fg=MINT, font=(kit.FONT[0], 9, "bold")); self.status.pack(side="left", padx=14)
        self.demo = tk.Label(tb, text="", bg=NAVY, fg=AMBER, font=(kit.FONT[0], 8, "bold")); self.demo.pack(side="left")
        ttk.Button(tb, text="Copilot", command=self.toggle_copilot).pack(side="right", padx=8)
        self.bell = ttk.Button(tb, text="🔔 0", command=self._notify); self.bell.pack(side="right")
        self.content = tk.Frame(main, bg=BG); self.content.grid(row=1, column=0, sticky="nsew")
        self.cop = tk.Frame(self, bg=PANEL, width=340, highlightbackground=GRID, highlightthickness=1)
        tk.Label(self.cop, text="LIQUIDITYX COPILOT", bg=PANEL, fg=CYAN, font=(kit.FONT[0], 9, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        tk.Label(self.cop, text="Rule-based; answers come from workspace data.", bg=PANEL, fg=MUTED, font=(kit.FONT[0], 8)).pack(anchor="w", padx=10)
        self.chat = tk.Text(self.cop, bg=BG, fg=TEXT, wrap="word", width=40, height=24, relief="flat", font=(kit.FONT[0], 9), padx=8, pady=6, state="disabled")
        self.chat.pack(fill="both", expand=True, padx=8, pady=6)
        self.chat.tag_configure("me", foreground=CYAN); self.chat.tag_configure("bot", foreground=TEXT)
        self.q = ttk.Entry(self.cop); self.q.pack(fill="x", padx=8); self.q.bind("<Return>", lambda e: self.ask())
        ttk.Button(self.cop, text="Ask", style="Accent.TButton", command=self.ask).pack(fill="x", padx=8, pady=4)
        for ex in copilot.EXAMPLES[:5]:
            b = tk.Button(self.cop, text=ex, bg=PANEL, fg=MUTED, bd=0, anchor="w", wraplength=300, justify="left", font=(kit.FONT[0], 8), cursor="hand2",
                          command=lambda ex=ex: (self.q.delete(0, "end"), self.q.insert(0, ex), self.ask()))
            b.pack(fill="x", padx=8)

    # ---------------------------------------------------------------- routing
    def goto(self, name, **kw):
        t0 = time.perf_counter()
        if name not in self.pages:
            cls = next(c for n, _, c in PAGES if n == name)
            self.pages[name] = cls(self.content, self)
        if self.current and self.current is not self.pages[name]:
            self.current.place_forget()
        page = self.pages[name]
        self.current, self.name = page, name
        page.place(x=0, y=0, relwidth=1, relheight=1)
        animate(self, kit.PAGE, lambda p: page.place_configure(x=int((1 - p) * 28)))
        for n, b in self.btns.items():
            b.config(fg=TEXT if n == name else MUTED, bg=PANEL if n == name else NAVY)
        self.update_idletasks()
        y = self.btns[name].winfo_y()
        y0 = self.ind.winfo_y()
        animate(self, kit.STANDARD, lambda p: self.ind.place_configure(y=int(y0 + (y - y0) * p) + 2, height=30))
        page.on_show()
        if "sel" in kw and name == "Financial Network":
            page.select(*kw["sel"])
        if "batch" in kw and name == "Inventory Rescue":
            page.select(kw["batch"])
        self.engine.config(text=f"● Engine ready · {int((time.perf_counter() - t0) * 1000)} ms", fg=MINT)

    def refresh_current(self):
        if self.current:
            self.current.refresh()

    # ---------------------------------------------------------------- state
    def company_name(self):
        r = self.ws.conn.execute("SELECT name FROM companies WHERE id=?", (self.cid,)).fetchone()
        return r["name"] if r else ""

    def reload(self, show=True):
        cos = self.ws.companies()
        self.cmap = {c["name"]: c["id"] for c in cos}
        self.co["values"] = list(self.cmap)
        if self.cid not in self.cmap.values():
            self.cid = self.ws.default_focus()
        self.co.set(self.company_name())
        self.demo.config(text="● SYNTHETIC DEMO" if self.ws.is_demo() else ("" if cos else "Empty workspace"))
        self.ws.clear_scenario(); self.scenario_changed(refresh=False)
        if show:
            self.refresh_current()

    def scenario_changed(self, refresh=True):
        names = ["Baseline"] + [s["name"] for s in self.ws.saved_scenarios()]
        self.sc["values"] = names
        r = self.ws.last_result
        if r:
            self.status.config(text=f"Stressed · {r['total_exposure'] / 1e7:.1f}L · {len(r['companies'])} hit", fg=CORAL)
        else:
            self.sc.set("Baseline"); self.status.config(text="Baseline", fg=MINT)
        n = len([q for q in self.ws.action_queue(self.cid) if q["sev"] == "critical"]) if self.cid else 0
        self.bell.config(text=f"🔔 {n}")
        if refresh:
            self.refresh_current()

    def _co(self, e=None):
        self.cid = self.cmap[self.co.get()]; self.scenario_changed()

    def _scenario(self, e=None):
        n = self.sc.get()
        if n == "Baseline":
            self.ws.clear_scenario()
        else:
            s = next(s for s in self.ws.saved_scenarios() if s["name"] == n)
            try:
                self.ws.run_crisis(s["params"])
            except Exception as ex:
                messagebox.showerror("Scenario", str(ex)); return
        self.scenario_changed()

    def _search(self, e=None):
        t = self.search.get().strip().lower()
        if not t:
            return
        for name, cid in self.cmap.items():
            if t in name.lower():
                self.cid = cid; self.co.set(name); self.scenario_changed(); self.goto("Financial Network")
                self.pages["Financial Network"].net.find(t); return
        for b in self.ws.batches():
            if t in b["sku"].lower():
                self.cid = b["company_id"]; self.co.set(self.company_name()); self.goto("Inventory Intelligence"); self.pages["Inventory Intelligence"].q.set(b["sku"]); return
        toast(self, "No match", "warning")

    def _notify(self):
        items = self.ws.action_queue(self.cid)
        m = tk.Menu(self, tearoff=0, bg=NAVY, fg=TEXT, activebackground=PANEL)
        if not items:
            m.add_command(label="No notifications", state="disabled")
        for it in items[:8]:
            m.add_command(label=f"[{it['sev'].upper()}] {it['title']}", command=lambda it=it: self.open_action(it))
        m.tk_popup(self.bell.winfo_rootx(), self.bell.winfo_rooty() + 30)

    def open_action(self, it):
        d = tk.Toplevel(self); d.title(it["title"]); d.configure(bg=PANEL); d.transient(self); d.geometry("460x220")
        d.update_idletasks(); d.geometry(f"+{self.winfo_rootx() + 400}+{self.winfo_rooty() + 220}")
        col = {"critical": CORAL, "warning": AMBER}.get(it["sev"], CYAN)
        tk.Label(d, text=it["sev"].upper(), bg=PANEL, fg=col, font=(kit.FONT[0], 8, "bold")).pack(anchor="w", padx=16, pady=(14, 0))
        tk.Label(d, text=it["title"], bg=PANEL, fg=TEXT, font=(kit.FONT[0], 13, "bold"), wraplength=420, justify="left").pack(anchor="w", padx=16)
        tk.Label(d, text=it["detail"], bg=PANEL, fg=MUTED, wraplength=420, justify="left").pack(anchor="w", padx=16, pady=8)
        def go():
            d.destroy(); self.goto(it["page"], **({"batch": it["ref"]} if it.get("ref") else {}))
        ttk.Button(d, text=f"Open {it['page']}", style="Accent.TButton", command=go).pack(side="left", padx=16, pady=10)
        ttk.Button(d, text="Close", command=d.destroy).pack(side="left")
        d.bind("<Escape>", lambda e: d.destroy()); d.focus_set()
        alpha = lambda p: d.attributes("-alpha", p) if d.winfo_exists() else None
        try:
            animate(d, kit.MODAL, alpha)
        except tk.TclError:
            pass

    # ---------------------------------------------------------------- copilot
    def toggle_copilot(self):
        self.copilot_open = not self.copilot_open
        if self.copilot_open:
            self.cop.grid(row=0, column=2, sticky="ns"); self.cop.grid_propagate(False)
            if not self.chat.get("1.0", "end").strip():
                self._say("Ask me about exposure, scenarios, stock or recovery plans.\n", "bot")
        else:
            self.cop.grid_forget()

    def _say(self, t, tag):
        self.chat.config(state="normal"); self.chat.insert("end", t + "\n", tag); self.chat.config(state="disabled"); self.chat.see("end")

    def ask(self):
        q = self.q.get().strip()
        if not q:
            return
        self.q.delete(0, "end"); self._say("You: " + q, "me")
        try:
            a = copilot.answer(self.ws, self.cid, q)
        except Exception as ex:
            a = f"I could not compute that ({ex}). Please rephrase."
        self._say(a + "\n", "bot")

    # ---------------------------------------------------------------- onboarding & shutdown
    def onboard(self):
        if self.ws.has_data() or get_setting(self.ws.conn, "onboarded", False):
            return
        d = tk.Toplevel(self); d.title("Welcome to LIQUIDITYX"); d.configure(bg=PANEL); d.transient(self); d.grab_set(); d.geometry("520x330")
        d.geometry(f"+{self.winfo_rootx() + 380}+{self.winfo_rooty() + 200}")
        tk.Label(d, text="Welcome to LIQUIDITYX", bg=PANEL, fg=TEXT, font=(kit.FONT[0], 15, "bold")).pack(anchor="w", padx=20, pady=(18, 2))
        tk.Label(d, text="Choose how to start. Demo data is synthetic and always labelled; your own data is kept separate.", bg=PANEL, fg=MUTED, wraplength=470, justify="left").pack(anchor="w", padx=20)
        def pick(kind):
            set_setting(self.ws.conn, "onboarded", True); d.destroy()
            if kind == "demo":
                self.ws.load_demo(); self.reload(); toast(self, "Synthetic demo network loaded", "success")
            elif kind == "sample":
                st = self.pages["Settings"] if "Settings" in self.pages else None
                self._import_samples()
            else:
                self.reload(); toast(self, "Empty workspace — import CSV data in Settings", "info")
        for t, k, sub in (("Explore the demo network", "demo", "14 synthetic companies with a ready-made crisis scenario"),
                          ("Import sample data", "sample", "3 small fictional companies from CSV templates (marked as user data)"),
                          ("Create a new business workspace", "new", "Start empty; import your own CSV files in Settings")):
            f = tk.Frame(d, bg=PANEL); f.pack(fill="x", padx=20, pady=6)
            ttk.Button(f, text=t, style="Accent.TButton" if k == "demo" else "TButton", command=lambda k=k: pick(k)).pack(fill="x")
            tk.Label(f, text=sub, bg=PANEL, fg=MUTED, font=(kit.FONT[0], 8)).pack(anchor="w")
        d.protocol("WM_DELETE_WINDOW", lambda: pick("new"))

    def _import_samples(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            c, i = os.path.join(tmp, "c.csv"), os.path.join(tmp, "i.csv")
            open(c, "w").write("name,type,opening_cash,min_cash\nAcme Works,manufacturer,2500000,800000\nBeta Steel,supplier,900000,300000\nGamma Retail,customer,8000000,1000000\n")
            open(i, "w").write("payer,payee,amount,due_date,expected_delay_days\nGamma Retail,Acme Works,3000000,2026-10-25,0\nAcme Works,Beta Steel,2200000,2026-10-22,0\n")
            n1, e1 = self.ws.import_csv("companies", c); n2, e2 = self.ws.import_csv("invoices", i)
        self.cid = self.ws.default_focus(); self.reload(); toast(self, f"Imported {n1} companies, {n2} invoices", "success")

    def shutdown(self):
        try:
            for a in self.tk.call("after", "info"):          # cancel pending animation frames
                self.after_cancel(a)
            self.ws.conn.commit(); self.ws.conn.close()
        finally:
            self.destroy()
