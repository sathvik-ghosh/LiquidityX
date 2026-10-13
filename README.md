# LIQUIDITYX — Financial Network Intelligence & Crisis Recovery (Obsidian Terminal)

*See the crisis before it spreads. Turn trapped capital into intelligent action.*

A pure **Python / Tkinter** desktop application. No Node, no web server, no paid APIs.
Detect → Trace → Simulate → Recover → Protect → Learn.

> **Synthetic demo data.** The 14 companies are fictional. All results are *modeled*, not predictions.
> LiquidityX is not a lender or regulated financial adviser; funding terms are illustrative.

## Web version (hostable) — see DEPLOY.md
```bash
pip install -r requirements.txt
streamlit run app.py                # http://localhost:8501
```
Deploy free on Streamlit Community Cloud, Render, Hugging Face Spaces or Docker (`DEPLOY.md`).

## Desktop version (optional, Tkinter)

```bash
pip install -r requirements-desktop.txt     # Linux also: sudo apt install python3-tk
python main.py --demo               # first run: loads the synthetic demo network
python main.py --no-intro           # skip the intro   |  --reduced-motion  disables animations
python main.py --db my_workspace.db # use a different workspace file
pytest -q                           # run the automated tests
```
Default workspace: `~/.liquidityx/workspace.db` (SQLite). Reports go to a `reports/` folder beside it.
Nothing listens on a network port, so there is nothing to expose or shut down; closing the window commits and closes the database.

## Architecture
`Tkinter UI  →  service.Workspace  →  engines (pure Python)  →  SQLite`

| Module | Purpose |
|---|---|
| `liquidityx/engine/cashflow.py` | Day-by-day joint cash simulation of the whole network (payers pay only from cash on hand) |
| `liquidityx/engine/crisis.py` | Baseline vs stressed run; propagation edges = payments actually delayed by the shock |
| `liquidityx/engine/network.py` | NetworkX graph (payer→payee), HHI concentration, exposure, importance |
| `liquidityx/engine/inventory.py` | Batch intelligence, production-reserve protection, rescue pathways (restricted stock never sold) |
| `liquidityx/engine/funding.py` | Illustrative financing maths (editable assumptions) |
| `liquidityx/engine/recovery.py` | Candidate actions → combinations → Lowest-cost / Fastest / Balanced, re-simulated after the plan |
| `liquidityx/copilot.py` | Rule-based assistant; answers only from workspace data |
| `liquidityx/reports.py` | HTML (print/save as PDF) + CSV with assumptions and limitations |
| `liquidityx/ui/` | Design system, animated network canvas, 10 pages, copilot panel |

Money is stored as integer paise. Same inputs always give the same result.

## Formulas (also shown in-app)
* **Shortfall** = max(0, minimum cash − balance). **HHI** = Σ(counterparty share²), shown as *n/a* when there are no open amounts.
* **Risk radar** (0–1): Liquidity = min(1, peak shortfall ÷ min cash); Customer/Supplier concentration = HHI; Inventory obsolescence = value of held/slow/dead stock ÷ total; Critical dependency = share of payables to criticality ≥4 suppliers with no alternative.
* **Sellable surplus** = qty − ceil(daily demand × (lead time + 30 days if critical else 14)).
* **Rescue net** = success probability × gross − cost. A write-off is an accounting loss, never cash.
* **Recovery gap** = peak shortfall; **deadline** = first breach day. Only actions landing by the deadline count; extensions are *relief*, not cash; financing is sized only for the residual.

## Demo walk-through
1. **Crisis Simulator** → *Run simulation* (Apex pays Bharat's ₹30 L late by 30 days): shock wave → Bharat, Sundaram, Kaveri, Chola, Madras; 9 firms unaffected.
2. **Cash Intelligence** → stress vs baseline, threshold breach shaded.
3. **Inventory Intelligence / Rescue** → ₹89.8 L blocked stock, pathways, approvals, restricted-stock rules.
4. **Funding Navigator** → compare illustrative options against the stressed cash curve.
5. **Recovery Planner** → *Generate plans*, compare, approve (audit-logged; moves no money).
6. **Reports** → HTML / CSV. **Copilot** (top bar) answers the example questions.

## Tests
`pytest -q` → 22 tests: cash conservation, graph direction, cascade, determinism, monotonic delay, validation,
inventory valuation, restricted-stock rules, funding maths, recovery honesty (no double counting, relief ≠ cash),
persistence, atomic CSV import, empty database, copilot grounding, all reports.

## Known limitations
* Simple trade-credit model: no new credit, no behavioural response, no probabilistic defaults.
* Success probabilities, discounts, time-to-cash and funding terms are **assumptions**, not data.
* History of customer payment behaviour is limited to the expected-delay field on invoices.
* Not implemented: PDF engine (print HTML to PDF), inventory CSV import, multi-user access, authentication,
  ERP integration, demand forecasting beyond the supplied monthly-demand field, reduce-purchases action.
* UI verified under a virtual display (Xvfb) with scripted interaction and screenshots; not tested on Windows/macOS.
* Local single-workspace prototype — **not production-ready enterprise software.**

## Commercial roadmap (hypotheses, not validated)
Targets: SME manufacturers, distributors, supply-chain-finance and procurement teams, risk analysts.
Revenue ideas: SaaS tiers (prices in Settings are illustrative/editable), premium analytics, enterprise licences,
integration services, permitted financing-partner referrals. Roadmap: workspaces, role-based permissions,
multi-company separation, alert thresholds, ERP/accounting connectors, PostgreSQL deployment with authentication.
