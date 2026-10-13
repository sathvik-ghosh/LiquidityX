"""Obsidian Terminal design system: colors, fonts, motion tokens, reusable widgets."""
import time
import tkinter as tk
from tkinter import ttk, font as tkfont

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

BG, NAVY, PANEL = "#080B12", "#101827", "#151F30"
CYAN, MINT, AMBER, CORAL = "#43D9FF", "#4DE2B1", "#FFBF69", "#FF657A"
TEXT, MUTED, GRID, GRAY = "#F3F6FC", "#98A6BC", "#1C2740", "#5D6B82"
EDGE = "#3A4A63"
STATUS_COLOR = {"ok": CYAN, "warning": AMBER, "critical": CORAL, "unknown": GRAY}
STATUS_ICON = {"ok": "", "warning": "!", "critical": "▲", "unknown": "?"}
FONT = ("DejaVu Sans", 10)
MONO = ("DejaVu Sans Mono", 10)

# ---- motion tokens (ms) ----
FAST, STANDARD, PAGE, MODAL, CHART, NETWORK, ALERT = 120, 260, 220, 200, 700, 900, 300
REDUCED = False


def set_reduced(v):
    global REDUCED
    REDUCED = bool(v)


def ease_out(t):
    return 1 - (1 - t) ** 3


def animate(w, ms, fn, done=None, ease=ease_out):
    """Run fn(progress 0..1) over ms. Instant when reduced motion is on. Never blocks input."""
    if REDUCED or ms <= 0:
        fn(1.0)
        if done:
            done()
        return None
    start = time.perf_counter()
    token = {"cancel": False}

    def tick():
        if token["cancel"] or not w.winfo_exists():
            return
        t = min(1.0, (time.perf_counter() - start) * 1000 / ms)
        fn(ease(t))
        if t < 1:
            w.after(16, tick)
        elif done:
            done()
    tick()
    return token


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def init_theme(root):
    global FONT, MONO
    fams = set(tkfont.families(root))
    pick = lambda opts, d: next((f for f in opts if f in fams), d)
    FONT = (pick(["Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue", "DejaVu Sans", "Arial"], "TkDefaultFont"), 10)
    MONO = (pick(["JetBrains Mono", "Consolas", "Menlo", "DejaVu Sans Mono", "Courier New"], "TkFixedFont"), 10)
    root.configure(bg=BG)
    root.option_add("*Font", FONT)
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL, bordercolor=GRID,
                lightcolor=GRID, darkcolor=GRID, troughcolor=NAVY, font=FONT)
    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=PANEL)
    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("Card.TLabel", background=PANEL, foreground=TEXT)
    s.configure("Muted.TLabel", background=BG, foreground=MUTED)
    s.configure("TButton", background=PANEL, foreground=TEXT, padding=(10, 5), borderwidth=1, focusthickness=1,
                focuscolor=CYAN)
    s.map("TButton", background=[("active", NAVY), ("pressed", GRID)], bordercolor=[("focus", CYAN)])
    s.configure("Accent.TButton", background=CYAN, foreground=BG, font=(FONT[0], 10, "bold"))
    s.map("Accent.TButton", background=[("active", mix(CYAN, "#ffffff", .25))])
    s.configure("Danger.TButton", background=CORAL, foreground=BG, font=(FONT[0], 10, "bold"))
    s.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT)
    s.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=TEXT, arrowcolor=CYAN)
    s.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", TEXT)])
    s.configure("TSpinbox", fieldbackground=PANEL, foreground=TEXT, arrowcolor=CYAN)
    s.configure("TCheckbutton", background=BG, foreground=TEXT)
    s.configure("TNotebook", background=BG, borderwidth=0)
    s.configure("TNotebook.Tab", background=NAVY, foreground=MUTED, padding=(14, 6))
    s.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", CYAN)])
    s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=26,
                borderwidth=0, font=FONT)
    s.configure("Treeview.Heading", background=NAVY, foreground=MUTED, font=(FONT[0], 9, "bold"), relief="flat")
    s.map("Treeview", background=[("selected", mix(PANEL, CYAN, .30))], foreground=[("selected", TEXT)])
    s.configure("Vertical.TScrollbar", background=NAVY, troughcolor=BG, arrowcolor=MUTED)
    s.configure("Horizontal.TScale", background=BG, troughcolor=NAVY)


class Tooltip:
    def __init__(self, w, text):
        self.w, self.text, self.tip = w, text, None
        w.bind("<Enter>", self.show, add="+")
        w.bind("<Leave>", self.hide, add="+")

    def show(self, e=None):
        if self.tip or not self.text:
            return
        self.tip = tk.Toplevel(self.w)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{self.w.winfo_rootx() + 12}+{self.w.winfo_rooty() + self.w.winfo_height() + 4}")
        tk.Label(self.tip, text=self.text, bg=NAVY, fg=TEXT, bd=1, relief="solid", justify="left",
                 wraplength=300, padx=8, pady=6, font=(FONT[0], 9)).pack()

    def hide(self, e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def card(parent, **kw):
    f = tk.Frame(parent, bg=PANEL, highlightbackground=GRID, highlightthickness=1, **kw)
    return f


def label(parent, text, size=10, color=TEXT, bold=False, bg=PANEL, mono=False, **kw):
    fam = MONO[0] if mono else FONT[0]
    return tk.Label(parent, text=text, bg=bg, fg=color, font=(fam, size, "bold" if bold else "normal"), **kw)


def heading(parent, text, sub=None, bg=BG):
    f = tk.Frame(parent, bg=bg)
    tk.Label(f, text=text, bg=bg, fg=TEXT, font=(FONT[0], 16, "bold")).pack(anchor="w")
    if sub:
        tk.Label(f, text=sub, bg=bg, fg=MUTED, font=(FONT[0], 9), wraplength=900, justify="left").pack(anchor="w")
    return f


class KpiCard(tk.Frame):
    def __init__(self, parent, title, tip, fmt=str, accent=CYAN):
        super().__init__(parent, bg=PANEL, highlightbackground=GRID, highlightthickness=1)
        self.fmt, self.prev, self.accent = fmt, None, accent
        tk.Label(self, text=title.upper(), bg=PANEL, fg=MUTED, font=(FONT[0], 8, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        self.val = tk.Label(self, text="–", bg=PANEL, fg=TEXT, font=(MONO[0], 18, "bold"))
        self.val.pack(anchor="w", padx=12)
        self.delta = tk.Label(self, text=" ", bg=PANEL, fg=MUTED, font=(FONT[0], 8))
        self.delta.pack(anchor="w", padx=12, pady=(0, 8))
        Tooltip(self, tip); Tooltip(self.val, tip)

    def set(self, v, color=None):
        if v == self.prev:
            return                                   # no re-animation when nothing changed
        old = self.prev if isinstance(self.prev, (int, float)) else 0
        if self.prev is not None:
            d = v - old
            self.delta.config(text=("▲ +" if d > 0 else "▼ ") + self.fmt(abs(d)) + " vs previous" if d else " ",
                              fg=CORAL if d > 0 and self.accent == CORAL else (MINT if d < 0 and self.accent == CORAL else MUTED))
        self.prev = v
        self.val.config(fg=color or TEXT)
        animate(self, 600, lambda t: self.val.config(text=self.fmt(old + (v - old) * t)))


class DataTable(tk.Frame):
    def __init__(self, parent, columns, on_select=None, height=8):
        super().__init__(parent, bg=PANEL)
        self.cols = [c[0] for c in columns]
        self.tree = ttk.Treeview(self, columns=self.cols, show="headings", height=height, selectmode="browse")
        for cid, text, w, *rest in columns:
            self.tree.heading(cid, text=text, command=lambda c=cid: self.sort(c))
            self.tree.column(cid, width=w, anchor=(rest[0] if rest else "w"), stretch=True)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.tree.tag_configure("hover", background=mix(PANEL, CYAN, .12))
        self.tree.tag_configure("critical", foreground=CORAL)
        self.tree.tag_configure("warning", foreground=AMBER)
        self.tree.tag_configure("good", foreground=MINT)
        self.tree.tag_configure("muted", foreground=MUTED)
        self.rev, self.hover, self.orig = {}, None, {}
        self.tree.bind("<Motion>", self._motion); self.tree.bind("<Leave>", lambda e: self._unhover())
        if on_select:
            self.tree.bind("<<TreeviewSelect>>", lambda e: (self.tree.selection() and on_select(self.tree.selection()[0])))

    def _unhover(self):
        if self.hover and self.tree.exists(self.hover):
            self.tree.item(self.hover, tags=self.orig.get(self.hover, ()))
        self.hover = None

    def _motion(self, e):
        r = self.tree.identify_row(e.y)
        if r == self.hover:
            return
        self._unhover()
        if r:
            self.orig[r] = self.tree.item(r, "tags")
            self.tree.item(r, tags=tuple(self.orig[r]) + ("hover",))
            self.hover = r

    def set_rows(self, rows):
        """rows: (iid, values, tag|None)"""
        self.hover = None
        self.tree.delete(*self.tree.get_children())
        for iid, vals, tag in rows:
            self.tree.insert("", "end", iid=str(iid), values=vals, tags=(tag,) if tag else ())

    def select(self, iid):
        if self.tree.exists(str(iid)):
            self.tree.selection_set(str(iid)); self.tree.see(str(iid))

    def sort(self, col):
        def key(v):
            s = str(v).replace("₹", "").replace(",", "").replace(" L", "").replace("%", "").strip()
            try:
                return (0, float(s))
            except ValueError:
                return (1, s.lower())
        self.rev[col] = not self.rev.get(col, True)
        items = [(key(self.tree.set(i, col)), i) for i in self.tree.get_children()]
        items.sort(reverse=self.rev[col])
        for n, (_, i) in enumerate(items):
            self.tree.move(i, "", n)


def toast(root, text, kind="info"):
    color = {"info": CYAN, "success": MINT, "warning": AMBER, "error": CORAL}[kind]
    t = tk.Label(root, text="  " + text + "  ", bg=NAVY, fg=color, font=(FONT[0], 10, "bold"),
                 highlightbackground=color, highlightthickness=1, pady=8)
    t.place(relx=1.0, rely=1.0, x=0, y=-24, anchor="se")
    animate(t, ALERT, lambda p: t.place_configure(x=-24 + (1 - p) * 60))
    root.after(2600, lambda: t.destroy() if t.winfo_exists() else None)


def mpl(parent, w=5, h=3, polar=False):
    fig = Figure(figsize=(w, h), dpi=100, facecolor=PANEL)
    ax = fig.add_subplot(111, polar=polar)
    style_ax(ax)
    canvas = FigureCanvasTkAgg(fig, master=parent)
    return fig, ax, canvas


def style_ax(ax):
    ax.set_facecolor(PANEL)
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(color=GRID, linewidth=.6)
    ax.xaxis.label.set_color(MUTED); ax.yaxis.label.set_color(MUTED)
    ax.title.set_color(TEXT)
