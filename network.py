"""Network analysis. Edge direction = direction of money (payer -> payee).

Three separate, documented measures (a well-connected firm is NOT 'distressed'):
* network importance : betweenness centrality + share of downstream firms reachable.
* financial exposure : open receivables + open payables (paise).
* liquidity risk     : from the baseline simulation (see cashflow.shortfall_profile).
Concentration (HHI) = sum(share_i^2) over counterparties, 0..1; None if no open amounts.
"""
import networkx as nx


def build_graph(state) -> nx.DiGraph:
    g = nx.DiGraph()
    for cid, c in state.companies.items():
        g.add_node(cid, name=c["name"], type=c["type"])
    for inv in state.invoices:
        a, b = inv["payer"], inv["payee"]
        if g.has_edge(a, b):
            g[a][b]["amount"] += inv["amount"]
        else:
            g.add_edge(a, b, amount=inv["amount"])
    return g


def hhi(amounts):
    tot = sum(amounts)
    if tot <= 0:
        return None
    return sum((a / tot) ** 2 for a in amounts)


def customer_concentration(g, cid):
    """HHI of open receivables by paying customer."""
    return hhi([d["amount"] for _, _, d in g.in_edges(cid, data=True)])


def supplier_concentration(g, cid):
    """HHI of open payables by supplier."""
    return hhi([d["amount"] for _, _, d in g.out_edges(cid, data=True)])


def exposure(g, cid):
    rec = sum(d["amount"] for _, _, d in g.in_edges(cid, data=True))
    pay = sum(d["amount"] for _, _, d in g.out_edges(cid, data=True))
    return {"receivables": rec, "payables": pay}


def downstream(g, cid):
    """Companies whose payments could be hit if `cid` pays late (money-flow successors)."""
    return sorted(nx.descendants(g, cid))


def network_importance(g):
    n = max(len(g) - 1, 1)
    bc = nx.betweenness_centrality(g)
    return {c: {"betweenness": bc[c], "downstream_share": len(nx.descendants(g, c)) / n}
            for c in g}
