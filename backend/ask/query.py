"""Run a validated intent and build the answer from a template.

Every number in an answer is computed here, by the database and Python, and
every number comes with the record IDs it was computed from. Nothing from the
model's output is copied into the answer text: only validated enum values,
which are mapped to our own labels.

The query is RLS-scoped like everything else: no org filter here.
"""
from collections import defaultdict
from decimal import Decimal

from recon.models import ReasonCode, ReconException

from .serializers import NO_GAP_REASONS


def format_inr(amount: Decimal) -> str:
    """Decimal('259509.40') -> '₹2,59,509.40' (Indian grouping)."""
    sign = "-" if amount < 0 else ""
    int_part, frac = f"{abs(amount):.2f}".split(".")
    if len(int_part) > 3:
        head, tail = int_part[:-3], int_part[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        int_part = ",".join(groups + [tail])
    return f"{sign}₹{int_part}.{frac}"


def _unique(ids):
    """Record IDs in order, without repeats (a record can have two exceptions)."""
    return list(dict.fromkeys(ids))


def _gap(e) -> Decimal:
    """Size of one exception's disagreement: |A - accounts|. No accounts entry
    at all (MISSING_IN_SYSTEM_B) means accounts holds nothing, i.e. zero."""
    return abs(e.a_amount - (e.b_amount if e.b_amount is not None else Decimal("0")))


def _scope_phrase(intent, location_names) -> str:
    """'' or e.g. ' (Accounts recorded the pre-tax amount only) at Location 103'."""
    parts = []
    if intent["reason_codes"]:
        parts.append(" (" + " or ".join(ReasonCode(c).label for c in intent["reason_codes"]) + ")")
    if intent["location_ids"]:
        parts.append(" at " + " or ".join(location_names[l] for l in intent["location_ids"]))
    if intent.get("date_from") and intent.get("date_to"):
        parts.append(f" dated {intent['date_from']} to {intent['date_to']}")
    elif intent.get("date_from"):
        parts.append(f" dated on or after {intent['date_from']}")
    elif intent.get("date_to"):
        parts.append(f" dated on or before {intent['date_to']}")
    return "".join(parts)


def _noun(n: int) -> str:
    return "exception" if n == 1 else "exceptions"


def run(intent: dict, locations: list[dict]) -> dict:
    location_names = {l["location_id"]: l["location_name"] for l in locations}

    qs = ReconException.objects.order_by("record_id", "reason_code")
    if intent["reason_codes"]:
        qs = qs.filter(reason_code__in=intent["reason_codes"])
    if intent["location_ids"]:
        qs = qs.filter(location_id__in=intent["location_ids"])
    if intent.get("date_from"):
        qs = qs.filter(record_date__gte=intent["date_from"])
    if intent.get("date_to"):
        qs = qs.filter(record_date__lte=intent["date_to"])
    rows = list(qs)

    scope = _scope_phrase(intent, location_names)
    metric, group_by = intent["metric"], intent["group_by"]

    excluded = []
    if metric == "sum_gap":
        # Leave out rows where a gap isn't meaningful, and say which ones.
        excluded = [r for r in rows if r.reason_code in NO_GAP_REASONS]
        rows = [r for r in rows if r.reason_code not in NO_GAP_REASONS]

    def summarise(subset):
        """(value, value_text, evidence) for one group of rows."""
        evidence = _unique(r.record_id for r in subset)
        if metric == "sum_gap":
            total = sum((_gap(r) for r in subset), Decimal("0.00"))
            return str(total), format_inr(total), evidence
        return len(subset), str(len(subset)), evidence

    if group_by == "none":
        value, text, evidence = summarise(rows)
        if metric == "sum_gap":
            answer = f"Total difference {text} across {len(rows)} {_noun(len(rows))}{scope}"
        else:
            answer = f"{text} {_noun(len(rows))}{scope}"
        if metric == "list" and evidence:
            answer += ": " + ", ".join(evidence)
        result = {"value": value, "evidence": evidence}
    else:
        buckets = defaultdict(list)
        for r in rows:
            buckets[r.reason_code if group_by == "reason_code" else r.location_id].append(r)

        def label(key):
            return ReasonCode(key).label if group_by == "reason_code" else location_names.get(key, key)

        groups = []
        for key in sorted(buckets):
            value, text, evidence = summarise(buckets[key])
            groups.append({"key": key, "label": label(key), "value": value, "text": text, "evidence": evidence})

        heading = "Total difference" if metric == "sum_gap" else "Exceptions"
        by = "reason" if group_by == "reason_code" else "location"
        if groups:
            body = "; ".join(f"{g['label']}: {g['text']} ({', '.join(g['evidence'])})" for g in groups)
            answer = f"{heading}{scope} by {by}: {body}"
        else:
            answer = f"0 exceptions{scope}"
        result = {
            "value": {g["key"]: g["value"] for g in groups},
            "evidence": _unique(r.record_id for r in rows),
            "groups": [{k: g[k] for k in ("key", "label", "value", "evidence")} for g in groups],
        }

    if excluded:
        names = ", ".join(_unique(r.record_id for r in excluded))
        answer += f". Not included (no meaningful difference to measure): {names}"
        result["excluded"] = _unique(r.record_id for r in excluded)

    return {"answered": True, "answer": answer, **result}
