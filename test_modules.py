import csv
import pytest
from liquidityx.db import connect
from liquidityx.seed import seed_demo, AS_OF
from liquidityx.money import lakh
from liquidityx.service import Workspace
from liquidityx.engine import inventory as inv, funding as fd
from liquidityx import copilot, reports


@pytest.fixture()
def ws():
    w = Workspace(); w.load_demo(); return w


def stressed(w):
    big = next(c for c in w.invoice_choices() if "Apex Motors → Bharat" in c["label"])
    w.run_crisis(dict(invoice_id=big["id"], delay_days=30, paid_pct=0, horizon=90)); return w


def test_inventory_valuation(ws):
    b = ws.batches()[0]
    assert b["book_value"] == b["qty"] * b["unit_cost"]
    assert sum(x["book_value"] for x in ws.batches()) == inv.summary(ws.batches())["total_value"]


def test_restricted_and_expired_never_sold(ws):
    seen = 0
    for b in ws.batches():
        if b["status"] == "held" and (b["restricted"] or b["expired"]):
            seen += 1
            for o in inv.rescue_options(b)["options"]:
                assert not {"RESELL", "SELL", "RELEASE"} & set(o["steps"])
    assert seen >= 2


def test_writeoff_is_not_cash_and_loss_minimisation(ws):
    b = next(x for x in ws.batches() if x["sku"] == "BPC-RB-070")
    r = inv.rescue_options(b)
    wo = next(o for o in r["options"] if o["name"] == "Write-off")
    assert wo["gross"] == 0 and wo["net"] == 0
    assert r.get("best") is None and "minimise loss" in r["recommendation"]


def test_production_reserve_protected(ws):
    b = next(x for x in ws.batches() if x["sku"] == "BPC-ST-100")
    r = inv.recommendation(b)
    assert b["qty"] - r["sellable_qty"] >= b["daily_demand"] * (b["lead_time_days"] + 30) - 1
    rows, warn = inv.scenarios(b, ws.batches())
    assert any("Sell ALL" in x["option"] and "STOCKOUT" in x["note"] for x in rows)


def test_funding_math():
    a = dict(annual_rate=12.0, fee_pct=2.0, tenor_days=60, installments=1, days_to_funds=3, collateral="", eligibility="")
    o = fd.evaluate("x", a, lakh(10))
    assert o["fee"] == lakh(10) * 2 // 100 and o["net_proceeds"] == lakh(10) - o["fee"]
    assert o["interest"] == int(lakh(10) * .12 * 60 / 365)
    assert o["total_repayment"] == lakh(10) + o["interest"]
    bal = fd.apply_to_balances([0] * 100, o)
    assert bal[0] == 0 and bal[3] == o["net_proceeds"] and bal[-1] == o["net_proceeds"] - o["total_repayment"]


def test_recovery_honesty(ws):
    stressed(ws); cid = ws.default_focus()
    out = ws.recovery(cid)
    assert out["gap"] > 0 and out["plans"]
    for p in out["plans"].values():
        ids = [a["id"] for a in p["actions"]]
        assert len(ids) == len(set(ids))                      # no double counting
        for a in p["actions"]:
            if a["kind"] == "extension":
                assert a["expected_cash"] == 0 and a["expected_relief"] > 0   # relief is not cash
            assert a["day"] <= out["deadline_day"]
        fin = p["financing"]["net_proceeds"] * .6 if p["financing"] else 0
        if p["solved"]:
            assert p["expected_cash"] + p["expected_relief"] + fin >= p["gap"] - 1
            assert p["residual"] == 0
        else:
            assert p["residual"] > 0


def test_no_gap_no_plan(ws):
    assert ws.recovery(ws.default_focus())["plans"] == {}


def test_persistence(tmp_path):
    f = str(tmp_path / "w.db")
    w = Workspace(f); w.load_demo(); stressed(w); w.save_scenario("S1"); w.conn.close()
    w2 = Workspace(f)
    assert len(w2.companies()) == 14 and w2.saved_scenarios()[0]["name"] == "S1"
    assert w2.conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] >= 2


def test_import_ok_and_atomic_rollback(tmp_path):
    w = Workspace()
    p = tmp_path / "c.csv"; p.write_text("name,type,opening_cash,min_cash\nA,manufacturer,1000,100\nB,supplier,500,50\n")
    assert w.import_csv("companies", str(p)) == (2, [])
    bad = tmp_path / "i.csv"; bad.write_text("payer,payee,amount,due_date\nA,B,100,2026-11-01\nA,ZZZ,100,2026-11-01\nA,B,10,not-a-date\n")
    n, errs = w.import_csv("invoices", str(bad))
    assert n == 0 and len(errs) == 2
    assert w.conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 0       # nothing imported


def test_service_validation(ws):
    inv_id = ws.invoice_choices()[0]["id"]
    for bad in (dict(delay_days=-1), dict(paid_pct=150), dict(horizon=3)):
        with pytest.raises(ValueError):
            ws.run_crisis(dict(invoice_id=inv_id, **bad))


def test_empty_database_and_copilot():
    w = Workspace()
    assert not w.has_data() and w.default_focus() is None
    assert "empty" in copilot.answer(w, None, "anything").lower()


def test_copilot_grounded(ws):
    cid = ws.default_focus()
    assert "BPC-GR-310" in copilot.answer(ws, cid, "Which stock should I investigate first?")
    assert "Sundaram" in copilot.answer(ws, cid, "What happens if Apex Motors pays 30 days late?")
    assert "I can answer" in copilot.answer(ws, cid, "tell me a joke")


def test_all_reports(ws, tmp_path):
    stressed(ws); cid = ws.default_focus()
    for k in reports.KINDS:
        r = reports.build(ws, k, cid)
        assert r["meta"]["generated"] and r["limitations"] and r["assumptions"]
        reports.to_html(r, str(tmp_path / "r.html")); reports.to_csv(r, str(tmp_path / "r.csv"))
    assert "SYNTHETIC DEMO DATA" in (tmp_path / "r.html").read_text()
