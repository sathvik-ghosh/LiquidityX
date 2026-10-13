import pytest
from liquidityx.db import connect
from liquidityx.seed import seed_demo, AS_OF
from liquidityx.money import lakh
from liquidityx.engine.cashflow import load_state, simulate, Shock, shortfall_profile
from liquidityx.engine.network import build_graph, customer_concentration, hhi, downstream
from liquidityx.engine.crisis import run_scenario


@pytest.fixture()
def env():
    conn = connect()
    ids = seed_demo(conn)
    st = load_state(conn, AS_OF)
    big = next(i for i in st.invoices
               if i["payer"] == ids["Apex Motors"] and i["payee"] == ids["Bharat Precision Components"])
    return conn, ids, st, big


def test_money_conservation_no_shock(env):
    _, _, st, _ = env
    r = simulate(st, 90)
    total0 = sum(c["opening_cash"] for c in st.companies.values())
    external = sum(t["amount"] for t in st.txns)
    assert sum(b[-1] for b in r.balances.values()) == total0 + external


def test_baseline_has_no_breach(env):
    _, ids, st, _ = env
    r = simulate(st, 90)
    assert shortfall_profile(st, r, ids["Bharat Precision Components"])[0] == 0


def test_graph_direction_and_exposure(env):
    _, ids, st, _ = env
    g = build_graph(st)
    assert g.has_edge(ids["Apex Motors"], ids["Bharat Precision Components"])
    assert not g.has_edge(ids["Bharat Precision Components"], ids["Apex Motors"])
    assert ids["Madras Alloy Works"] in downstream(g, ids["Apex Motors"])


def test_concentration():
    assert hhi([50, 50]) == pytest.approx(0.5)
    assert hhi([100]) == 1
    assert hhi([]) is None


def test_cascade_30_day_delay(env):
    _, ids, st, big = env
    res = run_scenario(st, [Shock(big["id"], delay_days=30, paid_pct=0)])
    assert res["initial_shock"] == lakh(30)
    assert res["direct"] == ["Bharat Precision Components"]
    assert "Sundaram Castings" in res["indirect"]
    assert res["total_exposure"] > 0
    waves = {c["name"]: c["wave"] for c in res["companies"]}
    assert waves["Sundaram Castings"] == 1
    assert "Apex Motors" in res["unaffected"]
    for e in res["propagation"]:            # animated edges only for affected firms
        assert e["wave"] is not None


def test_scenario_deterministic(env):
    _, _, st, big = env
    s = [Shock(big["id"], delay_days=15, paid_pct=50)]
    assert run_scenario(st, s) == run_scenario(st, s)


def test_longer_delay_not_better(env):
    _, _, st, big = env
    e = [run_scenario(st, [Shock(big["id"], delay_days=d)])["total_exposure"] for d in (7, 15, 30, 60)]
    assert e == sorted(e)


def test_validation(env):
    _, _, st, big = env
    with pytest.raises(ValueError):
        simulate(st, 30, [Shock(big["id"], delay_days=-1)])
    with pytest.raises(ValueError):
        simulate(st, 30, [Shock(big["id"], paid_pct=150)])


def test_default_never_counts_as_cash(env):
    _, ids, st, big = env
    b = ids["Bharat Precision Components"]
    base = simulate(st, 90)
    r = simulate(st, 90, [Shock(big["id"], default=True)])
    # the defaulted 30L never arrives as an inflow, and the invoice is never marked paid
    assert sum(r.inflow[b]) == sum(base.inflow[b]) - lakh(30) or sum(r.inflow[b]) < sum(base.inflow[b])
    assert sum(base.inflow[b]) - sum(r.inflow[b]) >= lakh(30)
    assert r.invoice_paid_day[big["id"]] is None
