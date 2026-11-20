"""Compare System A (deal records) with System B (accounts entries).

Pure Python, no database: CSV paths in, a list of Findings out. The ingest
command stores them; tests check them against the oracle in CLAUDE.md §4.

Matching: every A record is matched to ALL B entries whose normalised
record_ref equals its record_id, and A's total is compared with the SUM of
those entries. One-to-one matching would wrongly flag split payments (REC-1055).

Which codes a record can get:
- VOIDED_BUT_RECORDED stands alone: once the sale is cancelled, comparing
  amounts or branches is meaningless.
- Otherwise at most ONE amount code (the most specific that applies, in the
  order of `_amount_code`), plus LOCATION_MISMATCH if the branch differs.
  Amount and branch are independent facts, so both are reported if both
  are wrong.
"""
import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from .models import ReasonCode
from .normalise import normalise_ref, parse_amount, parse_date, parse_part_label


@dataclass(frozen=True)
class LocationRow:
    location_id: str
    org_id: str
    location_name: str


@dataclass(frozen=True)
class RecordA:
    record_id: str
    location_id: str
    event_date: date
    base_value: Decimal
    total_value: Decimal
    state: str  # CONFIRMED | VOIDED


@dataclass(frozen=True)
class EntryB:
    entry_id: str
    record_id: str  # normalised record_ref
    location_id: str
    recorded_on: date
    value: Decimal | None  # None = blank in the CSV
    label: str


@dataclass(frozen=True)
class Finding:
    org_id: str
    record_id: str
    location_id: str  # the location shown to org_id (always one of its own)
    reason_code: str
    a_amount: Decimal | None
    b_amount: Decimal | None
    b_entry_ids: tuple[str, ...]
    b_location_id: str | None
    record_date: date


# --- loading ------------------------------------------------------------------

def _rows(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def load_locations(path: Path) -> dict[str, LocationRow]:
    return {
        r["location_id"]: LocationRow(r["location_id"], r["org_id"], r["location_name"])
        for r in _rows(path)
    }


def load_system_a(path: Path) -> list[RecordA]:
    # actor_id and category_code aren't needed: a blank actor_id (REC-1050) is
    # an A-internal data gap, not a disagreement between systems. Not reported.
    return [
        RecordA(
            record_id=r["record_id"].strip(),
            location_id=r["location_id"].strip(),
            event_date=parse_date(r["event_date"]),
            base_value=_required_amount(r["base_value"], r["record_id"]),
            total_value=_required_amount(r["total_value"], r["record_id"]),
            state=r["state"].strip().upper(),
        )
        for r in _rows(path)
    ]


def load_system_b(path: Path) -> list[EntryB]:
    return [
        EntryB(
            entry_id=r["entry_id"].strip(),
            record_id=normalise_ref(r["record_ref"]),
            location_id=r["location_id"].strip(),
            recorded_on=parse_date(r["recorded_on"]),
            value=parse_amount(r["value"]),
            label=r["label"].strip(),
        )
        for r in _rows(path)
    ]


def _required_amount(raw: str, record_id: str) -> Decimal:
    value = parse_amount(raw)
    if value is None:
        raise ValueError(f"{record_id}: System A amount is blank")
    return value


# --- rules --------------------------------------------------------------------

def _is_duplicate(entries: list[EntryB]) -> bool:
    """>= 2 entries with identical value, date and location, not labelled as
    split parts. Parts are legitimate separate entries, never duplicates."""
    seen = set()
    for e in entries:
        if parse_part_label(e.label):
            continue
        key = (e.value, e.recorded_on, e.location_id)
        if key in seen:
            return True
        seen.add(key)
    return False


def _amount_code(a: RecordA, entries: list[EntryB]) -> str | None:
    """The single most specific amount problem, or None if amounts agree."""
    values = [e.value for e in entries]
    if any(v is None for v in values):
        return ReasonCode.AMOUNT_BLANK  # can't sum what isn't there
    if _is_duplicate(entries):
        return ReasonCode.DUPLICATE_ENTRY
    if sum(values) == a.total_value:  # Decimals at 2 dp: exact to the paisa
        return None
    if len(entries) == 1 and values[0] == a.base_value:
        return ReasonCode.TAX_NOT_RECORDED
    return ReasonCode.AMOUNT_MISMATCH


def _b_total(entries: list[EntryB]) -> Decimal | None:
    values = [e.value for e in entries]
    if not values or any(v is None for v in values):
        return None  # shown as "—"
    return sum(values)


def reconcile(
    locations: dict[str, LocationRow],
    records: list[RecordA],
    entries: list[EntryB],
) -> list[Finding]:
    def org_of(location_id: str) -> str:
        if location_id not in locations:
            raise ValueError(f"Unknown location {location_id!r}")
        return locations[location_id].org_id

    by_record: dict[str, list[EntryB]] = defaultdict(list)
    for e in entries:
        org_of(e.location_id)  # fail loudly on an unknown location
        by_record[e.record_id].append(e)

    findings: list[Finding] = []
    a_ids = set()

    for a in records:
        a_ids.add(a.record_id)
        matched = sorted(by_record.get(a.record_id, []), key=lambda e: e.entry_id)

        # A is the master record: the exception belongs to A's org and is
        # shown at A's location, even when B booked it elsewhere (REC-1077).
        def finding(code, b_location_id=None):
            return Finding(
                org_id=org_of(a.location_id),
                record_id=a.record_id,
                location_id=a.location_id,
                reason_code=code,
                a_amount=a.total_value,
                b_amount=_b_total(matched),
                b_entry_ids=tuple(e.entry_id for e in matched),
                b_location_id=b_location_id,
                record_date=a.event_date,
            )

        if not matched:
            # A cancelled sale with nothing in accounts is the correct state.
            if a.state != "VOIDED":
                findings.append(finding(ReasonCode.MISSING_IN_SYSTEM_B))
            continue

        if a.state == "VOIDED":
            findings.append(finding(ReasonCode.VOIDED_BUT_RECORDED))
            continue

        code = _amount_code(a, matched)
        if code:
            findings.append(finding(code))

        elsewhere = [e.location_id for e in matched if e.location_id != a.location_id]
        if elsewhere:
            # b_location_id may be another org's branch. It is stored for
            # audit but never serialised to the API.
            findings.append(finding(ReasonCode.LOCATION_MISMATCH, b_location_id=elsewhere[0]))

    # B entries pointing at a record A doesn't have. No A row, so the org
    # comes from B's own location (REC-1999 -> LOC-102 -> ORG-A).
    for record_id, orphans in sorted(by_record.items()):
        if record_id in a_ids:
            continue
        orphans.sort(key=lambda e: e.entry_id)
        location_id = orphans[0].location_id
        findings.append(
            Finding(
                org_id=org_of(location_id),
                record_id=record_id,
                location_id=location_id,
                reason_code=ReasonCode.MISSING_IN_SYSTEM_A,
                a_amount=None,
                b_amount=_b_total(orphans),
                b_entry_ids=tuple(e.entry_id for e in orphans),
                b_location_id=None,
                record_date=min(e.recorded_on for e in orphans),
            )
        )

    return sorted(findings, key=lambda f: (f.org_id, f.record_id, f.reason_code))


def reconcile_dir(data_dir: Path) -> tuple[dict[str, LocationRow], list[Finding]]:
    """Load the three CSVs from `data_dir` and reconcile them."""
    locations = load_locations(data_dir / "locations.csv")
    findings = reconcile(
        locations,
        load_system_a(data_dir / "system_a.csv"),
        load_system_b(data_dir / "system_b.csv"),
    )
    return locations, findings
