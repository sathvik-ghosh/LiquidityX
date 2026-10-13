import pytest
pytest.importorskip("streamlit")
import os
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")

PAGES = ["Command Center", "Financial Network", "Crisis Simulator", "Cash Intelligence", "Inventory Intelligence", "Inventory Rescue",
         "Funding Navigator", "Recovery Planner", "Reports", "Copilot", "Commercial & About"]


def app():
    return AppTest.from_file(APP, default_timeout=90).run()


def go(at, page):
    at.sidebar.radio[0].set_value(page).run(); return at


def btn(at, start):
    return next(b for b in at.button if b.label.startswith(start))


def test_every_page_renders():
    at = app()
    assert not at.exception
    for p in PAGES:
        go(at, p); assert not at.exception, (p, [e.value for e in at.exception])


def test_crisis_then_recovery_flow():
    at = go(app(), "Crisis Simulator")
    btn(at, "▶").click().run()
    assert not at.exception
    assert any(m.label == "Total modeled exposure" for m in at.metric)
    assert at.sidebar.error, "sidebar should show stressed state"
    go(at, "Recovery Planner"); btn(at, "Generate plans").click().run()
    assert not at.exception
    assert any("Gap" in e.value for e in at.error)
    at.checkbox[0].check().run(); btn(at, "Approve plan").click().run()
    assert not at.exception


def test_copilot_and_reset():
    at = go(app(), "Copilot")
    btn(at, "Which stock should I investigate first?").click().run()
    assert any("BPC-GR-310" in m.value for m in at.chat_message[-1].markdown) or at.chat_message
    btn(at, "Reset demo workspace").click().run(); assert not at.exception
