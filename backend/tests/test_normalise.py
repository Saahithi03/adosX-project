"""Unit tests for recon.normalise. Pure functions: no database needed."""
import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from recon.normalise import normalise_ref, parse_amount, parse_date, parse_part_label

DATA = Path(__file__).resolve().parents[2] / "data"


# --- refs ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("REC-1055", "REC-1055"),       # already clean
        ("rec1034", "REC-1034"),        # ENT/2026/4034: lower case, no dash
        (" REC - 1070 ", "REC-1070"),   # ENT/2026/4070: padded, spaced dash
        ("1112", "REC-1112"),           # ENT/2026/4112: digits only
        ("Rec-1001", "REC-1001"),
        ("REC--1001", "REC-1001"),
        ("\tREC 1001\n", "REC-1001"),
    ],
)
def test_normalise_ref(raw, expected):
    assert normalise_ref(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "REC", "REC-", "ABC-1001", "REC-10A1", "INV-1001", "1001REC"])
def test_normalise_ref_rejects_garbage(raw):
    with pytest.raises(ValueError):
        normalise_ref(raw)


def test_every_b_ref_in_the_data_normalises_to_rec_nnnn():
    with open(DATA / "system_b.csv", newline="") as f:
        for row in csv.DictReader(f):
            ref = normalise_ref(row["record_ref"])
            assert ref.startswith("REC-") and len(ref) == 8, row["entry_id"]


# --- amounts ------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("83361.40", Decimal("83361.40")),
        ("1,25,400.00", Decimal("125400.00")),  # ENT/2026/4064, Indian grouping
        ("125,400.00", Decimal("125400.00")),   # Western grouping
        (" 41250.00 ", Decimal("41250.00")),
        ("41250", Decimal("41250.00")),
        ("0.10", Decimal("0.10")),
        ("-12.50", Decimal("-12.50")),
    ],
)
def test_parse_amount(raw, expected):
    value = parse_amount(raw)
    assert value == expected
    assert isinstance(value, Decimal)
    assert value.as_tuple().exponent == -2  # always exactly two places


@pytest.mark.parametrize("raw", ["", "   "])
def test_blank_amount_is_none(raw):
    # ENT/2026/4050. None, not zero: blank must stay distinguishable (AMOUNT_BLANK).
    assert parse_amount(raw) is None


@pytest.mark.parametrize("raw", ["abc", "12.3.4", "NaN", "Infinity", "-inf", "₹100", "1.005"])
def test_parse_amount_rejects_garbage(raw):
    with pytest.raises(ValueError):
        parse_amount(raw)


def test_decimal_not_float():
    # 0.1 + 0.2 == 0.3 only holds with exact decimals.
    assert parse_amount("0.10") + parse_amount("0.20") == parse_amount("0.30")


def test_split_parts_sum_exactly():
    # REC-1055: the two B parts must equal A's total to the paisa.
    assert parse_amount("71950.93") + parse_amount("107926.39") == parse_amount("179877.32")


# --- dates and labels ----------------------------------------------------------

def test_parse_date():
    assert parse_date("2026-03-31") == date(2026, 3, 31)
    with pytest.raises(ValueError):
        parse_date("31/03/2026")


@pytest.mark.parametrize(
    "label, expected",
    [
        ("Entry part 1 of 2", (1, 2)),
        ("Entry part 2 of 2", (2, 2)),
        ("Entry for CAT-07", None),
        ("", None),
    ],
)
def test_parse_part_label(label, expected):
    assert parse_part_label(label) == expected
