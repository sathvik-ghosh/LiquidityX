"""Money is stored as integer paise (1 rupee = 100 paise) to avoid float error."""
from decimal import Decimal

PAISE_PER_LAKH = 10_000_000


def lakh(x) -> int:
    """Convert lakh rupees (e.g. 30 or '2.5') to integer paise."""
    return int((Decimal(str(x)) * PAISE_PER_LAKH).to_integral_value())


def fmt_lakh(paise: int) -> str:
    return f"₹{Decimal(paise) / PAISE_PER_LAKH:,.2f} L"
