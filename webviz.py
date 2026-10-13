"""Plotly figure builders for the web app (no Streamlit import, so they are testable)."""
import math
import networkx as nx
import numpy as np
import plotly.graph_objects as go

BG, PANEL, GRID = "#080B12", "#151F30", "#1C2740"
CYAN, MINT, AMBER, CORAL, TEXT, MUTED, EDGE = "#43D9FF", "#4DE2B1", "#FFBF69", "#FF657A", "#F3F6FC", "#98A6BC", "#3A4A63"
SC = {"ok": CYAN, "warning": AMBER, "critical": CORAL}
SYM = {"ok": "circle", "warning": "diamond", "critical": "triangle-up"}   # not colour alone


def mix(a, b, t):
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]; pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(pa, pb))


def layout(nodes, edges):
    g = nx.DiGraph(); g.add_nodes_from(n["id"] for n in nodes); g.add_edges_from((e["payer"], e["payee"]) for e in edges)
    names = {n["id"]: n["name"] for n in nodes}
    if not g:
        return {}
    if not nx.is_directed_acyclic_graph(g):
        p = nx.spring_layout(g, seed=7)
        return {n: ((x + 1) / 2, (y + 1) / 2) for n, (x, y) in p.items()}
    layer = {}
    for n in nx.topological_sort(g):
        layer[n] = max((layer[q] + 1 for q in g.predecessors(n)), default=0)
    cols = {}
    for n, l in layer.items():
        cols.setdefault(l, []).append(n)
    order = {}
    for l in cols.values():
        for i, n in enumerate(sorted(l, key=names.get)):
            order[n] = i
    for _ in range(3):
        for l in sorted(cols):
            cols[l].sort(key=lambda n: (sum(order[q] for q in g.predecessors(n)) / max(1, g.in_degree(n)) if g.in_degree(n) else order[n], names[n]))
            for i, n in enumerate(cols[l]):
                order[n] = i
    top = max(layer.values())
    return {n: (l / max(top, 1), (i + .5) / len(ns)) for l, ns in cols.items() for i, n in enumerate(ns)}


def steps_from_result(res):
    """Replay order = computed propagation only (origin edge, then delayed payments by wave/day)."""
    first = tuple(res["shock_edge"]); steps, seen = [first], {first}
    for e in sorted(res["propagation"], key=lambda e: (e["wave"], e["stressed_day"] if e["stressed_day"] is not None else 999)):
        p = (e["payer"], e["payee"])
        if p not in seen:
            seen.add(p); steps.append(p)
    return steps


def _lk(v):
    return f"₹{v / 1e7:,.2f} L"


def network_fig(data, result=None, mode="stressed", selected=None, types=None, animate=False, height=540):
    nodes = {n["id"]: n for n in data["nodes"]}; edges = data["edges"]
    pos = layout(data["nodes"], edges)
    fig = go.Figure()
    if not nodes:
        fig.add_annotation(text="No companies in this workspace", showarrow=False, font=dict(color=MUTED))
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG, height=300, xaxis_visible=False, yaxis_visible=False)
        return fig
    stressed = bool(result) and mode == "stressed"
    prop = {(e["payer"], e["payee"]) for e in result["propagation"]} if result else set()
    shock = tuple(result["shock_edge"]) if result else None
    steps = steps_from_result(result) if (animate and result) else []
    mx_e = max(e["amount"] for e in edges) if edges else 1
    mx_x = max(n["exposure"] for n in nodes.values()) or 1
    focus = None
    if selected in nodes:
        focus = {selected} | {e["payer"] for e in edges if e["payee"] == selected} | {e["payee"] for e in edges if e["payer"] == selected}

    def state(k):
        """k = number of animation steps shown (None = final static state)."""
        if k is None:
            reached = None; hot = (prop | {shock}) if stressed else set()
        else:
            hot = set(steps[:k]); reached = {steps[0][0]} | {p[1] for p in steps[:k]}
        return reached, hot

    def node_cols(reached):
        out = []
        for n, v in nodes.items():
            st = (v["status"] if n in reached else v["base_status"]) if reached is not None else (v["status"] if stressed else v["base_status"])
            dim = (focus is not None and n not in focus) or (types and v["type"] not in types)
            out.append((st, SC[st], dim))
        return out

    def edge_col(e, hot):
        pair = (e["payer"], e["payee"])
        c = CORAL if pair in hot else (mix(EDGE, TEXT, .35) if e["criticality"] >= 4 else EDGE)
        dim = (focus is not None and not (e["payer"] in focus and e["payee"] in focus and selected in pair)) or \
              (types and not ({nodes[e["payer"]]["type"], nodes[e["payee"]]["type"]} & set(types)))
        return mix(c, BG, .72) if dim else c

    k0 = 0 if steps else None
    reached, hot = state(k0)
    for e in edges:
        (x1, y1), (x2, y2) = pos[e["payer"]], pos[e["payee"]]
        d = math.hypot(x2 - x1, y2 - y1) or 1; ux, uy = (x2 - x1) / d, (y2 - y1) / d
        sx, sy, ex, ey = x1 + ux * .03, y1 + uy * .03, x2 - ux * .035, y2 - uy * .035
        col = edge_col(e, hot)
        fig.add_trace(go.Scatter(x=[sx, (sx + ex) / 2, ex], y=[sy, (sy + ey) / 2, ey], mode="lines+markers", hoverinfo="skip",
                                 line=dict(color=col, width=1 + 3 * math.sqrt(e["amount"] / mx_e), dash="dash" if e["alt"] else "solid"),
                                 marker=dict(size=[0, 0, 11], symbol="arrow", angleref="previous", color=col)))
    nE = len(edges)
    fig.add_trace(go.Scatter(x=[(pos[e["payer"]][0] + pos[e["payee"]][0]) / 2 for e in edges], y=[(pos[e["payer"]][1] + pos[e["payee"]][1]) / 2 for e in edges],
                             mode="markers", marker=dict(size=16, opacity=0), showlegend=False,
                             hovertext=[f"<b>{nodes[e['payer']]['name']} → {nodes[e['payee']]['name']}</b><br>{e['kind']} · {_lk(e['amount'])} · due {e['due']}"
                                        f"<br>Criticality {e['criticality']}/5 · alternative: {'yes' if e['alt'] else 'no'}<br>{e['history']}" for e in edges], hoverinfo="text"))
    nc = node_cols(reached)
    ids = list(nodes)
    fig.add_trace(go.Scatter(
        x=[pos[n][0] for n in ids], y=[pos[n][1] for n in ids], mode="markers+text", textposition="bottom center", cliponaxis=False,
        text=[" ".join(nodes[n]["name"].split()[:2]) for n in ids], textfont=dict(color=TEXT, size=11),
        marker=dict(size=[24 + 26 * math.sqrt(nodes[n]["exposure"] / mx_x) for n in ids], symbol=[SYM[c[0]] for c in nc],
                    color=[mix(PANEL, c[1], .15) if not c[2] else mix(PANEL, BG, .5) for c in nc],
                    line=dict(width=3, color=[c[1] if not c[2] else mix(c[1], BG, .75) for c in nc])),
        hovertext=[f"<b>{nodes[n]['name']}</b> ({nodes[n]['type']})<br>Status: {nc[i][0]}<br>Receivables {_lk(nodes[n]['receivables'])}<br>Payables {_lk(nodes[n]['payables'])}"
                   f"<br>Cash ÷ min cash: {nodes[n]['cash_ratio']:.1f}×" for i, n in enumerate(ids)], hoverinfo="text"))
    nidx = nE + 1
    if steps:
        frames = []
        for k in range(len(steps) + 1):
            r, h = state(k)
            ncs = node_cols(r)
            fd = [go.Scatter(line=dict(color=edge_col(e, h)), marker=dict(color=edge_col(e, h))) for e in edges]
            fd.append(go.Scatter(marker=dict(symbol=[SYM[c[0]] for c in ncs], color=[mix(PANEL, c[1], .15) for c in ncs], line=dict(width=3, color=[c[1] for c in ncs]))))
            frames.append(go.Frame(data=fd, traces=list(range(nE)) + [nidx], name=str(k)))
        fig.frames = frames
        fig.update_layout(
            updatemenus=[dict(type="buttons", showactive=False, x=0.0, y=1.12, xanchor="left", bgcolor=PANEL, font=dict(color=CYAN),
                              buttons=[dict(label="▶ Play shock wave", method="animate",
                                            args=[None, dict(frame=dict(duration=900, redraw=True), fromcurrent=False, transition=dict(duration=0))])])],
            sliders=[dict(active=0, x=0.25, len=0.7, y=1.1, currentvalue=dict(prefix="Step ", font=dict(color=TEXT)), font=dict(color=MUTED),
                          steps=[dict(method="animate", label=str(k), args=[[str(k)], dict(mode="immediate", frame=dict(duration=0, redraw=True), transition=dict(duration=0))])
                                 for k in range(len(steps) + 1)])])
    fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG, height=height, showlegend=False, margin=dict(l=10, r=10, t=70 if steps else 10, b=10),
                      xaxis=dict(visible=False, range=[-.08, 1.08]), yaxis=dict(visible=False, range=[-.08, 1.08]), hovermode="closest",
                      hoverlabel=dict(bgcolor=PANEL, font_color=TEXT))
    return fig


def radar_fig(scores):
    names = [n + (" (n/a)" if v is None else "") for n, v, _ in scores]
    vals = [0 if v is None else v for _, v, _ in scores]
    fig = go.Figure(go.Scatterpolar(r=vals + vals[:1], theta=names + names[:1], fill="toself", line=dict(color=CYAN, width=2), fillcolor="rgba(67,217,255,.25)",
                                    hovertext=[f"{n}: {f}" for n, _, f in scores] + [""], hoverinfo="text"))
    fig.update_layout(polar=dict(bgcolor=PANEL, radialaxis=dict(range=[0, 1], tickvals=[.25, .5, .75], gridcolor=GRID, tickfont=dict(color=MUTED, size=9)),
                                 angularaxis=dict(gridcolor=GRID, tickfont=dict(color=TEXT, size=10))),
                      paper_bgcolor=BG, height=330, margin=dict(l=60, r=60, t=20, b=20), showlegend=False)
    return fig


def cash_fig(view, series, horizon, as_of):
    L = 1e7
    x = list(range(len(view["base"])))
    mn = view["min_cash"] / L
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=[mn] * len(x), mode="lines", line=dict(color=AMBER, dash="dot", width=1.3), name=f"Minimum cash ({mn:.1f} L)"))
    for name, y, col, dash in series:
        y = np.array(y) / L
        fig.add_trace(go.Scatter(x=x, y=[mn] * len(x), mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x, y=np.minimum(y, mn), mode="lines", line=dict(width=0), fill="tonexty", fillcolor="rgba(255,101,122,.28)", showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=name, line=dict(color=col, width=2.5, dash=dash), hovertemplate="Day %{x}: ₹%{y:.2f} L<extra>" + name + "</extra>"))
    fig.update_layout(paper_bgcolor=BG, plot_bgcolor=PANEL, height=380, margin=dict(l=40, r=10, t=30, b=40), font=dict(color=TEXT),
                      xaxis=dict(title=f"Day (0 = {as_of})", gridcolor=GRID), yaxis=dict(title="Balance (₹ lakh)", gridcolor=GRID), legend=dict(orientation="h", y=1.1))
    return fig


def flows_fig(view, horizon):
    L, w = 1e7, (1 if horizon <= 30 else 7)
    inf, out = np.array(view["inflow"]) / L, np.array(view["outflow"]) / L
    xs = list(range(0, len(inf), w))
    fig = go.Figure([go.Bar(x=xs, y=[inf[i:i + w].sum() for i in xs], name="Inflow", marker_color=MINT),
                     go.Bar(x=xs, y=[-out[i:i + w].sum() for i in xs], name="Outflow", marker_color=CORAL)])
    fig.update_layout(barmode="relative", paper_bgcolor=BG, plot_bgcolor=PANEL, height=240, margin=dict(l=40, r=10, t=20, b=40), font=dict(color=TEXT),
                      xaxis=dict(title="Day" + (" (weekly buckets)" if w > 1 else ""), gridcolor=GRID), yaxis=dict(title="₹ lakh", gridcolor=GRID), legend=dict(orientation="h", y=1.15))
    return fig
