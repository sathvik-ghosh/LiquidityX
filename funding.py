"""ILLUSTRATIVE funding options. Not offers, quotes or advice. All terms are editable."""
import math

DEFAULTS = {
 "Working-capital loan": dict(annual_rate=14.0, fee_pct=1.5, tenor_days=180, installments=6,
        days_to_funds=7, collateral="Hypothecation of stock/receivables", eligibility="2+ years of financials"),
 "Invoice financing": dict(annual_rate=16.0, fee_pct=1.0, tenor_days=45, installments=1,
        days_to_funds=3, collateral="Assignment of financed invoices", eligibility="Invoices from creditworthy buyers"),
 "Supplier credit": dict(annual_rate=0.0, fee_pct=2.0, tenor_days=30, installments=1,
        days_to_funds=1, collateral="None (relationship)", eligibility="Supplier agreement (fee = lost early-pay discount)"),
 "Customer advance": dict(annual_rate=0.0, fee_pct=1.5, tenor_days=30, installments=1,
        days_to_funds=4, collateral="Delivery obligation", eligibility="Customer agreement (fee = price concession)"),
 "Supply-chain finance": dict(annual_rate=9.0, fee_pct=0.5, tenor_days=60, installments=1,
        days_to_funds=5, collateral="Anchor-buyer approved invoices", eligibility="Anchor buyer programme"),
 "Purchase-order financing": dict(annual_rate=18.0, fee_pct=2.0, tenor_days=45, installments=1,
        days_to_funds=10, collateral="Confirmed purchase order", eligibility="Confirmed PO from reliable customer"),
}


def evaluate(name, a, amount):
    """amount = principal requested (paise). Interest: bullet = simple; installments = equal principal."""
    fee = int(amount * a["fee_pct"] / 100)
    n = max(1, int(a["installments"]))
    step = a["tenor_days"] / n
    sched, bal, interest = [], amount, 0
    for k in range(1, n + 1):
        princ = amount // n if k < n else bal
        intr = int(bal * a["annual_rate"] / 100 * step / 365)
        interest += intr
        sched.append((a["days_to_funds"] + int(round(step * k)), princ + intr))
        bal -= princ
    total = sum(x for _, x in sched) + fee      # fee paid upfront from proceeds, shown in total cost
    net = amount - fee
    return dict(name=name, requested=amount, fee=fee, interest=interest, net_proceeds=net,
                total_repayment=sum(x for _, x in sched), schedule=sched,
                days_to_funds=a["days_to_funds"], total_cost=fee + interest,
                effective_cost_pct=(fee + interest) / net * 100 if net > 0 else None,
                collateral=a["collateral"], eligibility=a["eligibility"],
                label="ILLUSTRATIVE - not an offer", approved=False)


def size_for_net(name, a, net_needed):
    amount = math.ceil(net_needed / (1 - a["fee_pct"] / 100))
    return evaluate(name, a, amount)


def apply_to_balances(balances, opt):
    """Return new daily balance list after funding inflow and repayments (hypothetical)."""
    out = list(balances)
    for d in range(len(out)):
        delta = opt["net_proceeds"] if d >= opt["days_to_funds"] else 0
        delta -= sum(x for day, x in opt["schedule"] if day <= d)
        out[d] += delta
    return out
