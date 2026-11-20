"""Turn raw CSV strings into clean values before reconciliation.

These are formatting fixes only. Anything a function here accepts is NOT an
exception: `rec1034` and `REC-1034` are the same record, and `1,25,400.00` is
just 125400.00 written the Indian way. Anything it can't make sense of raises
ValueError, so ingest stops loudly instead of guessing.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

_REF_BODY = re.compile(r"REC(\d+)")
_PART_LABEL = re.compile(r"Entry part (\d+) of (\d+)")
_PAISA = Decimal("0.01")


def normalise_ref(raw: str) -> str:
    """Clean a System B `record_ref` into A's `REC-NNNN` form.

    trim -> upper-case -> drop spaces and dashes -> add REC if digits only
    -> reformat as REC-<digits>.

        "rec1034"       -> "REC-1034"
        " REC - 1070 "  -> "REC-1070"
        "1112"          -> "REC-1112"
    """
    s = raw.strip().upper().replace(" ", "").replace("-", "")
    if s.isdigit():
        s = "REC" + s
    m = _REF_BODY.fullmatch(s)
    if not m:
        raise ValueError(f"Unrecognised record reference: {raw!r}")
    return f"REC-{m.group(1)}"


def parse_amount(raw: str) -> Decimal | None:
    """Parse a money string into an exact Decimal, or None if blank.

    Commas are dropped wherever they are, which handles both Indian
    (1,25,400.00) and Western (125,400.00) grouping. Never goes through float.
    """
    s = raw.strip()
    if s == "":
        return None  # a blank amount is data (AMOUNT_BLANK), not a parse error
    try:
        value = Decimal(s.replace(",", ""))
    except InvalidOperation:
        raise ValueError(f"Not an amount: {raw!r}") from None
    # Decimal happily parses "NaN" and "Infinity"; money can't be either.
    if not value.is_finite():
        raise ValueError(f"Not an amount: {raw!r}")
    # Amounts are compared exact to the paisa. Refuse anything finer rather
    # than rounding it silently.
    if value != value.quantize(_PAISA):
        raise ValueError(f"More precise than a paisa: {raw!r}")
    return value.quantize(_PAISA)


def parse_date(raw: str) -> date:
    """Parse YYYY-MM-DD into a plain (timezone-naive) date."""
    return date.fromisoformat(raw.strip())


def parse_part_label(label: str) -> tuple[int, int] | None:
    """`"Entry part 1 of 2"` -> (1, 2). Any other label -> None.

    Split-payment parts are legitimate separate entries, so they must not be
    mistaken for duplicates.
    """
    m = _PART_LABEL.fullmatch(label.strip())
    return (int(m.group(1)), int(m.group(2))) if m else None
