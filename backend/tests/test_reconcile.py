"""The reconciliation oracle (CLAUDE.md §4), checked against the real CSVs.

Exactly these 11 exceptions, nothing more, and the five non-errors absent.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from recon.models import ReasonCode as R
from recon.models import ReconException
from recon.reconcile import EntryB, LocationRow, RecordA, reconcile, reconcile_dir
from recon.store import replace_all

from .helpers import through_middleware

DATA = Path(__file__).resolve().parents[2] / "data"

D = Decimal
# record, org, location, reason, A amount, B amount, B entry ids
ORACLE = [
    ("REC-1015", "ORG-A", "LOC-103", R.MISSING_IN_SYSTEM_B, D("41095.33"), None, ()),
    ("REC-1027", "ORG-A", "LOC-102", R.TAX_NOT_RECORDED, D("79259.03"), D("61921.12"), ("ENT/2026/4027",)),
    ("REC-1042", "ORG-A", "LOC-101", R.DUPLICATE_ENTRY, D("112837.06"), D("225674.12"), ("ENT/2026/4042", "ENT/2026/4902")),
    ("REC-1064", "ORG-A", "LOC-101", R.AMOUNT_MISMATCH, D("183244.16"), D("125400.00"), ("ENT/2026/4064",)),
    ("REC-1077", "ORG-A", "LOC-102", R.LOCATION_MISMATCH, D("83361.40"), D("83361.40"), ("ENT/2026/4077",)),
    ("REC-1088", "ORG-A", "LOC-103", R.TAX_NOT_RECORDED, D("138948.30"), D("108553.36"), ("ENT/2026/4088",)),
    ("REC-1999", "ORG-A", "LOC-102", R.MISSING_IN_SYSTEM_A, None, D("41250.00"), ("ENT/2026/4901",)),
    ("REC-1003", "ORG-B", "LOC-202", R.TAX_NOT_RECORDED, D("121388.01"), D("94834.38"), ("ENT/2026/4003",)),
    ("REC-1019", "ORG-B", "LOC-202", R.VOIDED_BUT_RECORDED, D("57092.35"), D("57092.35"), ("ENT/2026/4019",)),
    ("REC-1050", "ORG-B", "LOC-202", R.AMOUNT_BLANK, D("160405.85"), None, ("ENT/2026/4050",)),
    ("REC-1061", "ORG-B", "LOC-202", R.MISSING_IN_SYSTEM_B, D("87615.49"), None, ()),
]

NON_ERRORS = {
    "REC-1055": "split payment: parts sum to A's total",
    "REC-1034": "dirty ref rec1034",
    "REC-1070": "dirty ref ' REC - 1070 '",
    "REC-1112": "dirty ref 1112",
    "REC-1009": "B booked 2 days after A: within tolerance",
}


@pytest.fixture(scope="module")
def findings():
    return reconcile_dir(DATA)[1]


# --- the oracle ------------------------------------------------------------------

def test_exactly_the_oracle_and_nothing_else(findings):
    assert sorted((f.record_id, f.reason_code) for f in findings) == sorted((o[0], o[3]) for o in ORACLE)


@pytest.mark.parametrize("record, org, loc, reason, a, b, entries", ORACLE, ids=[o[0] for o in ORACLE])
def test_oracle_row(findings, record, org, loc, reason, a, b, entries):
    [f] = [f for f in findings if f.record_id == record]
    assert (f.org_id, f.location_id, f.reason_code) == (org, loc, reason)
    assert (f.a_amount, f.b_amount) == (a, b)
    assert f.b_entry_ids == entries


@pytest.mark.parametrize("record", NON_ERRORS, ids=list(NON_ERRORS))
def test_non_error_absent(findings, record):
    assert record not in {f.record_id for f in findings}, NON_ERRORS[record]


def test_counts_per_org(findings):
    assert sum(f.org_id == "ORG-A" for f in findings) == 7
    assert sum(f.org_id == "ORG-B" for f in findings) == 4


def test_rec_1077_cross_tenant_trap(findings):
    # A says LOC-102 (ORG-A), B booked it at LOC-201 (ORG-B). It belongs to
    # ORG-A, shown at ORG-A's own location. B's branch is kept for audit only.
    [f] = [f for f in findings if f.record_id == "REC-1077"]
    assert (f.org_id, f.location_id, f.b_location_id) == ("ORG-A", "LOC-102", "LOC-201")


def test_blank_actor_id_not_reported(findings):
    # REC-1050 has a blank actor_id in A; only B's blank amount is reported.
    assert [f.reason_code for f in findings if f.record_id == "REC-1050"] == [R.AMOUNT_BLANK]


# --- rules on small synthetic cases -----------------------------------------------

LOCS = {
    "L1": LocationRow("L1", "O1", "One"),
    "L2": LocationRow("L2", "O1", "Two"),
}
DAY = date(2026, 4, 1)


def a_rec(state="CONFIRMED", base="100.00", total="128.00", loc="L1"):
    return RecordA("REC-1", loc, DAY, D(base), D(total), state)


def b_ent(n, value="128.00", loc="L1", label="Entry for CAT-01", on=DAY):
    return EntryB(f"E{n}", "REC-1", loc, on, None if value is None else D(value), label)


def codes(records, entries):
    return [f.reason_code for f in reconcile(LOCS, records, entries)]


def test_clean_match_is_not_an_exception():
    assert codes([a_rec()], [b_ent(1)]) == []


def test_voided_with_no_accounts_entry_is_correct():
    assert codes([a_rec(state="VOIDED")], []) == []


def test_voided_reported_alone_even_if_amount_and_branch_differ():
    assert codes([a_rec(state="VOIDED")], [b_ent(1, value="1.00", loc="L2")]) == [R.VOIDED_BUT_RECORDED]


def test_zero_tax_record_matching_base_is_fine():
    # base == total (no adjustment): one entry equal to base is a full match,
    # not TAX_NOT_RECORDED.
    assert codes([a_rec(base="100.00", total="100.00")], [b_ent(1, value="100.00")]) == []


def test_split_labelled_parts_with_equal_values_are_not_duplicates():
    parts = [b_ent(1, "64.00", label="Entry part 1 of 2"), b_ent(2, "64.00", label="Entry part 2 of 2")]
    assert codes([a_rec()], parts) == []


def test_identical_unlabelled_entries_are_duplicates():
    assert codes([a_rec()], [b_ent(1), b_ent(2)]) == [R.DUPLICATE_ENTRY]


def test_same_value_on_different_days_is_not_a_duplicate():
    pair = [b_ent(1, "64.00"), b_ent(2, "64.00", on=date(2026, 4, 2))]
    assert codes([a_rec()], pair) == []


@pytest.mark.parametrize("days", [-5, 2, 3, 30])
def test_booking_date_lag_is_never_an_exception(days):
    # Dates aren't compared (DECISIONS.md): only ref, amount and branch matter.
    late = b_ent(1, on=date.fromordinal(DAY.toordinal() + days))
    assert codes([a_rec()], [late]) == []


def test_one_paisa_off_is_a_mismatch():
    assert codes([a_rec()], [b_ent(1, value="127.99")]) == [R.AMOUNT_MISMATCH]


def test_amount_and_branch_problems_are_both_reported():
    assert sorted(codes([a_rec()], [b_ent(1, value=None, loc="L2")])) == sorted(
        [R.AMOUNT_BLANK, R.LOCATION_MISMATCH]
    )


def test_unknown_location_fails_loudly():
    with pytest.raises(ValueError):
        codes([a_rec(loc="NOPE")], [])


# --- stored, then read back per org through RLS -------------------------------------

@pytest.mark.django_db
def test_stored_exceptions_are_scoped_per_org():
    # Same write path as `make ingest`, inside this test's rolled-back transaction.
    replace_all(*reconcile_dir(DATA))
    User = get_user_model()
    alice = User.objects.create_user("t_alice", password="pw", org_id="ORG-A")
    bob = User.objects.create_user("t_bob", password="pw", org_id="ORG-B")

    def rows():
        return list(ReconException.objects.values_list("record_id", "location_id", "org_id"))

    a_rows, b_rows = through_middleware(alice, rows), through_middleware(bob, rows)
    assert len(a_rows) == 7 and {r[2] for r in a_rows} == {"ORG-A"}
    assert len(b_rows) == 4 and {r[2] for r in b_rows} == {"ORG-B"}
    # ORG-A never gets an ORG-B branch as its location, not even for REC-1077.
    assert not {r[1] for r in a_rows} & {"LOC-201", "LOC-202"}
