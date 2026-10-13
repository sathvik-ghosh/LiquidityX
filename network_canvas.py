"""Interactive financial network drawn on a Tk Canvas. Stable layered layout (no continuous motion)."""
import math
import tkinter as tk
import networkx as nx

from . import kit
from .kit import (BG, PANEL, NAVY, CYAN, MINT, AMBER, CORAL, TEXT, MUTED, EDGE, GRID, STATUS_COLOR,
                  STATUS_ICON, mix, animate)

WW, WH = 1000, 560


class NetworkCanvas(tk.Canvas):
    def __init__(self, parent, on_select=None, **kw):
        super().__init__(parent, bg=BG, highlightthickness=1, highlightbackground=GRID, takefocus=1, **kw)
        self.on_select = on_select
        self.nodes, self.edges, self.result = {}, [], None
        self.pos, self.layer = {}, {}
        self.sc, self.ox, self.oy = 1.0, 0.0, 0.0
        self.fx = self.fy = 1.0
        self.sel = self.hov = None
        self.reveal, self.mixt, self.mode = 1.0, 1.0, "stressed"
        self.anim, self.pulses, self.filter = None, {}, None
        self.prop_pairs, self.shock_pair = set(), None
        self.user_moved, self._press, self._drag = False, None, False
        self.mouse = (0, 0)
        self._key = None
        self.bind("<Configure>", lambda e: (self.fit() if not self.user_moved else None, self.draw()))
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._set_hover(None))
        self.bind("<ButtonPress-1>", self._press_ev)
        self.bind("<B1-Motion>", self._drag_ev)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Double-Button-1>", lambda e: self.reset_view())
        self.bind("<MouseWheel>", lambda e: self._zoom(e.x, e.y, 1.1 if e.delta > 0 else 1 / 1.1))
        self.bind("<Button-4>", lambda e: self._zoom(e.x, e.y, 1.1))
        self.bind("<Button-5>", lambda e: self._zoom(e.x, e.y, 1 / 1.1))
        for k in ("<Right>", "<Down>"):
            self.bind(k, lambda e: self._cycle(1))
        for k in ("<Left>", "<Up>"):
            self.bind(k, lambda e: self._cycle(-1))
        self.bind("<Escape>", lambda e: self.select(None))
        self.bind("<plus>", lambda e: self._zoom(self.winfo_width() / 2, self.winfo_height() / 2, 1.15))
        self.bind("<minus>", lambda e: self._zoom(self.winfo_width() / 2, self.winfo_height() / 2, 1 / 1.15))

    # ------------------------------------------------------------ data
    def set_data(self, data, result=None, reveal=False):
        self.nodes = {n["id"]: n for n in data["nodes"]}
        self.edges = data["edges"]
        self.result = result
        self.prop_pairs = {(e["payer"], e["payee"]) for e in result["propagation"]} if result else set()
        self.shock_pair = tuple(result["shock_edge"]) if result else None
        key = (tuple(sorted(self.nodes)), tuple((e["payer"], e["payee"]) for e in self.edges))
        if key != self._key:
            self._key = key
            self._layout()
            self.user_moved = False
        self.fit()
        if reveal:
            self.play_reveal()
        else:
            self.draw()

    def _layout(self):
        g = nx.DiGraph()
        g.add_nodes_from(self.nodes)
        g.add_edges_from((e["payer"], e["payee"]) for e in self.edges)
        self.pos, self.layer = {}, {}
        if g and nx.is_directed_acyclic_graph(g):
            for n in nx.topological_sort(g):
                self.layer[n] = max((self.layer[p] + 1 for p in g.predecessors(n)), default=0)
            cols = {}
            for n, l in self.layer.items():
                cols.setdefault(l, []).append(n)
            order = {n: i for l in cols.values() for i, n in enumerate(sorted(l, key=lambda x: self.nodes[x]["name"]))}
            for _ in range(3):                         # barycenter sweeps for fewer crossings
                for l in sorted(cols):
                    cols[l].sort(key=lambda n: (sum(order[p] for p in g.predecessors(n)) / max(1, g.in_degree(n))
                                                if g.in_degree(n) else order[n], self.nodes[n]["name"]))
                    for i, n in enumerate(cols[l]):
                        order[n] = i
            top = max(self.layer.values(), default=0)
            for l, ns in cols.items():
                for i, n in enumerate(ns):
                    self.pos[n] = (60 + (WW - 120) * (l / max(top, 1)), 40 + (WH - 80) * ((i + .5) / len(ns)))
        elif g:
            p = nx.spring_layout(g, seed=7)
            for n, (x, y) in p.items():
                self.pos[n] = (60 + (x + 1) / 2 * (WW - 120), 40 + (y + 1) / 2 * (WH - 80))
            self.layer = {n: 0 for n in g}

    # ------------------------------------------------------------ view
    def fit(self):
        w, h = max(self.winfo_width(), 200), max(self.winfo_height(), 150)
        self.fx, self.fy = w * .9 / WW, (h - 70) * .9 / WH
        self.sc = 1.0
        self.ox, self.oy = w * .05, 30 + (h - 70) * .05

    def reset_view(self):
        self.user_moved = False
        self.fit(); self.draw()

    def _zoom(self, x, y, f):
        ns = max(.5, min(4.0, self.sc * f))
        f = ns / self.sc
        self.ox, self.oy, self.sc = x - (x - self.ox) * f, y - (y - self.oy) * f, ns
        self.user_moved = True
        self.draw()

    def P(self, n):
        x, y = self.pos[n]
        return x * self.fx * self.sc + self.ox, y * self.fy * self.sc + self.oy

    def R(self, n):
        mx = max((v["exposure"] for v in self.nodes.values()), default=1) or 1
        return (12 + 18 * math.sqrt(self.nodes[n]["exposure"] / mx)) * max(.75, min(1.5, (min(self.fx, self.fy) * self.sc) ** .35 * 1.3))

    # ------------------------------------------------------------ state helpers
    def _status(self, n):
        node = self.nodes[n]
        if self.anim is not None:
            return node["status"] if n in self.anim["reached"] else node["base_status"]
        return node["status"] if self.mode == "stressed" else node["base_status"]

    def _focus(self):
        if self.sel and self.sel[0] == "node":
            s = self.sel[1]
            return {s} | {e["payer"] for e in self.edges if e["payee"] == s} | {e["payee"] for e in self.edges if e["payer"] == s}
        if self.sel and self.sel[0] == "edge":
            return set(self.sel[1])
        return None

    # ------------------------------------------------------------ drawing
    def draw(self):
        self.delete("all")
        if not self.nodes:
            self.create_text(self.winfo_width() / 2, self.winfo_height() / 2, fill=MUTED, font=(kit.FONT[0], 12),
                             text="No companies yet.\nLoad the demo network or import CSV data in Settings.", justify="center")
            return
        self._grid()
        focus = self._focus()
        rv = self.reveal
        emph = set()
        if self.hov and self.hov[0] == "node":
            emph = {self.hov[1]}
        for e in self.edges:
            a, b = e["payer"], e["payee"]
            pair = (a, b)
            ep = max(0, min(1, (rv - .35) / .65))
            hot = (emph and (a in emph or b in emph)) or (self.hov == ("edge", pair)) or (self.sel == ("edge", pair))
            col = mix(EDGE, TEXT, .35) if e["criticality"] >= 4 else EDGE
            if self.anim is not None:
                p = self.anim["edge_p"].get(pair, 0)
                if p > 0:
                    ep, col = p, CORAL
                else:
                    ep = max(0, min(1, (rv - .35) / .65))
            elif self.mode == "stressed" and (pair in self.prop_pairs or pair == self.shock_pair):
                col = mix(EDGE, CORAL, self.mixt)
            if hot:
                col = CYAN if col != CORAL else col
            if self.sel and self.sel[0] == "node":
                dim_sel = not (a == self.sel[1] or b == self.sel[1])
            elif self.sel and self.sel[0] == "edge":
                dim_sel = pair != self.sel[1]
            else:
                dim_sel = False
            dim = dim_sel or bool(self.filter and not ({self.nodes[a]["type"], self.nodes[b]["type"]} & self.filter))
            if dim:
                col = mix(col, BG, .72)
            self._edge(a, b, e, col, ep, bool(hot))
        for n in self.nodes:
            self._node(n, focus, rv)
        for n, (t, color) in list(self.pulses.items()):
            x, y = self.P(n)
            r = self.R(n) + 6 + 26 * t
            self.create_oval(x - r, y - r, x + r, y + r, outline=mix(color, BG, min(1, t * 1.2)), width=2)
        self._legend()
        self._tooltip()

    def _grid(self):
        w, h = self.winfo_width(), self.winfo_height()
        for x in range(0, w, 48):
            self.create_line(x, 0, x, h, fill=mix(BG, GRID, .45))
        for y in range(0, h, 48):
            self.create_line(0, y, w, y, fill=mix(BG, GRID, .45))

    def _edge(self, a, b, e, col, prog, hot):
        if prog <= 0:
            return
        (x1, y1), (x2, y2) = self.P(a), self.P(b)
        d = math.hypot(x2 - x1, y2 - y1) or 1
        ux, uy = (x2 - x1) / d, (y2 - y1) / d
        sx, sy = x1 + ux * (self.R(a) + 3), y1 + uy * (self.R(a) + 3)
        ex, ey = x2 - ux * (self.R(b) + 5), y2 - uy * (self.R(b) + 5)
        tx, ty = sx + (ex - sx) * prog, sy + (ey - sy) * prog
        mx = max((v["amount"] for v in self.edges), default=1)
        w = 1 + 3 * math.sqrt(e["amount"] / mx) + (1 if hot else 0)
        self.create_line(sx, sy, tx, ty, fill=col, width=w, dash=(5, 3) if e["alt"] else (),
                         arrow=tk.LAST if prog >= .98 else None, arrowshape=(9, 11, 4))
        if hot or col == CORAL:
            from ..money import fmt_lakh
            self.create_text((sx + tx) / 2, (sy + ty) / 2 - 9, text=fmt_lakh(e["amount"]), fill=col if col != EDGE else MUTED,
                             font=(kit.MONO[0], 8))

    def _node(self, n, focus, rv):
        node = self.nodes[n]
        x, y = self.P(n)
        grow = max(0, min(1, (rv - self.layer.get(n, 0) * .07) / .4))
        if grow <= 0:
            return
        r = self.R(n) * grow
        st = self._status(n)
        col = STATUS_COLOR[st]
        if self.anim is None and self.mode == "stressed" and st != node["base_status"]:
            col = mix(STATUS_COLOR[node["base_status"]], col, self.mixt)
        dim = (focus is not None and n not in focus) or (self.filter and node["type"] not in self.filter)
        fill = mix(PANEL, col, .10)
        if dim:
            col, fill = mix(col, BG, .75), mix(fill, BG, .6)
        sel = self.sel == ("node", n)
        self.create_oval(x - r, y - r, x + r, y + r, fill=fill, outline=col, width=3 if sel or self.hov == ("node", n) else 2)
        ratio = node["cash_ratio"]
        ring = MINT if ratio >= 1.5 else (AMBER if ratio >= 1 else CORAL)
        self.create_arc(x - r - 5, y - r - 5, x + r + 5, y + r + 5, start=90, extent=-359.9 * min(1, ratio / 3),
                        style=tk.ARC, outline=mix(ring, BG, .7) if dim else ring, width=2)
        icon = STATUS_ICON[st]
        if icon:
            self.create_text(x, y, text=icon, fill=col, font=(kit.FONT[0], int(max(9, r * .7)), "bold"))
        if (node["cust_hhi"] or 0) > .6 or (node["sup_hhi"] or 0) > .6:
            self.create_text(x + r * .85, y - r * .85, text="◆", fill=mix(AMBER, BG, .7) if dim else AMBER, font=(kit.FONT[0], 9))
        name = " ".join(node["name"].split()[:2])
        self.create_text(x, y + r + 14, text=name, fill=mix(TEXT, BG, .65) if dim else TEXT, font=(kit.FONT[0], 8, "bold"))
        self.create_text(x, y + r + 26, text=node["type"], fill=mix(MUTED, BG, .5) if dim else MUTED, font=(kit.FONT[0], 7))

    def _legend(self):
        h = self.winfo_height()
        self.create_text(10, h - 46, anchor="w", fill=MUTED, font=(kit.FONT[0], 8),
                         text="Size = receivables + payables · Ring = cash ÷ min cash · ◆ concentration > 0.6")
        self.create_text(10, h - 32, anchor="w", fill=MUTED, font=(kit.FONT[0], 8),
                         text="Cyan ok · Amber ! warning · Coral ▲ shortfall · Dashed = alternative · Bright = critical")
        self.create_text(10, h - 18, anchor="w", fill=MUTED, font=(kit.FONT[0], 8),
                         text=f"View: {'stressed scenario' if self.mode == 'stressed' and self.result else 'baseline'} · wheel zoom · drag pan · double-click reset")

    def _tooltip(self):
        if not self.hov:
            return
        from ..money import fmt_lakh
        if self.hov[0] == "node":
            n = self.nodes[self.hov[1]]
            lines = [n["name"], f"{n['type']} · status: {self._status(n['id'])}", f"Receivables {fmt_lakh(n['receivables'])}",
                     f"Payables {fmt_lakh(n['payables'])}"]
        else:
            a, b = self.hov[1]
            e = next(x for x in self.edges if (x["payer"], x["payee"]) == (a, b))
            lines = [f"{self.nodes[a]['name']} → {self.nodes[b]['name']}", f"{e['kind']} · {fmt_lakh(e['amount'])} · due {e['due']}",
                     f"Criticality {e['criticality']}/5 · alternative: {'yes' if e['alt'] else 'no'}", e["history"]]
        x, y = self.mouse
        wd = max(len(s) for s in lines) * 6.6 + 16
        x = min(x + 14, self.winfo_width() - wd - 4)
        y = min(y + 14, self.winfo_height() - 70)
        self.create_rectangle(x, y, x + wd, y + 16 * len(lines) + 8, fill=NAVY, outline=CYAN)
        for i, s in enumerate(lines):
            self.create_text(x + 8, y + 12 + i * 16, anchor="w", text=s, fill=TEXT if i == 0 else MUTED,
                             font=(kit.FONT[0], 9, "bold" if i == 0 else "normal"))

    # ------------------------------------------------------------ interaction
    def _hit(self, x, y):
        for n in self.nodes:
            nx_, ny_ = self.P(n)
            if math.hypot(x - nx_, y - ny_) <= self.R(n) + 4:
                return ("node", n)
        best = None
        for e in self.edges:
            (x1, y1), (x2, y2) = self.P(e["payer"]), self.P(e["payee"])
            dx, dy = x2 - x1, y2 - y1
            t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy or 1)))
            d = math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))
            if d <= 6 and (best is None or d < best[0]):
                best = (d, ("edge", (e["payer"], e["payee"])))
        return best[1] if best else None

    def _set_hover(self, h):
        if h != self.hov:
            self.hov = h
            self.config(cursor="hand2" if h else "")
            self.draw()

    def _motion(self, e):
        self.mouse = (e.x, e.y)
        h = self._hit(e.x, e.y)
        if h != self.hov:
            self._set_hover(h)
        elif h:
            self.draw()

    def _press_ev(self, e):
        self.focus_set()
        self._press, self._drag = (e.x, e.y, self.ox, self.oy), False

    def _drag_ev(self, e):
        if not self._press:
            return
        dx, dy = e.x - self._press[0], e.y - self._press[1]
        if abs(dx) + abs(dy) > 4:
            self._drag = True
            self.ox, self.oy = self._press[2] + dx, self._press[3] + dy
            self.user_moved = True
            self.draw()

    def _release(self, e):
        if self._press and not self._drag:
            self.select(self._hit(e.x, e.y))
        self._press = None

    def select(self, target):
        self.sel = target
        self.draw()
        if self.on_select:
            if target is None:
                self.on_select(None, None)
            elif target[0] == "node":
                self.on_select("node", self.nodes[target[1]])
            else:
                self.on_select("edge", next(x for x in self.edges if (x["payer"], x["payee"]) == target[1]))

    def _cycle(self, d):
        ids = sorted(self.nodes, key=lambda n: (self.layer.get(n, 0), self.pos[n][1]))
        if not ids:
            return
        cur = ids.index(self.sel[1]) if self.sel and self.sel[0] == "node" else -1
        self.select(("node", ids[(cur + d) % len(ids)]))

    def set_filter(self, types):
        self.filter = set(types) if types else None
        self.draw()

    def find(self, text):
        t = text.strip().lower()
        if not t:
            return self.select(None)
        for n, v in self.nodes.items():
            if t in v["name"].lower():
                return self.select(("node", n))

    def set_mode(self, mode):
        """baseline <-> stressed comparison with a short colour blend."""
        self.mode = mode
        self.mixt = 0.0
        def f(p):
            self.mixt = p if mode == "stressed" else 1.0
            self.draw()
        animate(self, kit.STANDARD, f)

    # ------------------------------------------------------------ animations
    def play_reveal(self):
        def f(p):
            self.reveal = p
            self.draw()
        self.reveal = 0.0
        animate(self, kit.NETWORK, f, done=lambda: (setattr(self, "reveal", 1.0), self.draw()))

    def _pulse(self, n, color):
        def f(p):
            self.pulses[n] = (p, color)
            self.draw()
        animate(self, 650, f, done=lambda: (self.pulses.pop(n, None), self.draw()))

    def play_shock(self, on_step=None, on_done=None):
        """THE SHOCK WAVE: replays the computed propagation order only (no invented paths)."""
        res = self.result
        if not res:
            return
        steps, seen = [], set()
        pair0 = tuple(res["shock_edge"])
        steps.append(pair0); seen.add(pair0)
        for e in sorted(res["propagation"], key=lambda e: (e["wave"], e["stressed_day"] if e["stressed_day"] is not None else 999)):
            p = (e["payer"], e["payee"])
            if p not in seen:
                seen.add(p); steps.append(p)
        by_c = {c["company_id"]: c for c in res["companies"]}
        self.mode, self.mixt = "stressed", 1.0
        self.anim = dict(reached={pair0[0]}, edge_p={})
        self._pulse(pair0[0], AMBER)
        total = [0]

        def run(i):
            if i >= len(steps):
                self.anim = None
                self.draw()
                if on_done:
                    on_done()
                return
            pair = steps[i]

            def f(p):
                self.anim["edge_p"][pair] = max(p, .01)
                self.draw()

            def landed():
                self.anim["reached"].add(pair[1])
                c = by_c.get(pair[1])
                if c:
                    total[0] += c["extra_shortfall"] if pair[1] not in {x[1] for x in steps[:i]} else 0
                    if c["extra_shortfall"] > 0:
                        self._pulse(pair[1], CORAL)
                if on_step:
                    on_step(i + 1, len(steps), pair, sum(by_c[n]["extra_shortfall"] for n in self.anim["reached"] if n in by_c),
                            len([n for n in self.anim["reached"] if n in by_c]))
                self.after(0 if kit.REDUCED else 120, lambda: run(i + 1))
            animate(self, 520, f, done=landed)
        run(0)
