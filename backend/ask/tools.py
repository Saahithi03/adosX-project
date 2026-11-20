"""Tool schemas offered to the model.

These guide the model; they don't make anything safe on their own. Whatever
comes back is re-validated by IntentSerializer, which is the real guarantee.

llm.py sends them with `strict: true`, so they stick to the JSON Schema subset
strict mode supports: enums, `format: date`, `additionalProperties: false`,
and no array or string length constraints.
"""
from recon.models import ReasonCode

from .refusals import MODEL_REASON_TYPES

METRICS = ["count", "list", "sum_gap"]
GROUP_BYS = ["none", "reason_code", "location"]


def build_tools(locations: list[dict]) -> list[dict]:
    """`locations`: this org's locations only, built per request."""
    location_ids = [loc["location_id"] for loc in locations]
    properties = {
        "metric": {
            "type": "string",
            "enum": METRICS,
            "description": "count = how many; list = which records; "
            "sum_gap = total size of the amount differences.",
        },
        "reason_codes": {
            "type": "array",
            "items": {"type": "string", "enum": list(ReasonCode.values)},
            "description": "; ".join(f"{c.value} = {c.label}" for c in ReasonCode),
        },
        "location_ids": {
            "type": "array",
            "items": {"type": "string", "enum": location_ids},
            "description": "Only these locations exist for this user: "
            + ", ".join(f"{loc['location_id']} = {loc['location_name']}" for loc in locations),
        },
        "date_from": {"type": "string", "format": "date", "description": "YYYY-MM-DD, inclusive"},
        "date_to": {"type": "string", "format": "date", "description": "YYYY-MM-DD, inclusive"},
        "group_by": {"type": "string", "enum": GROUP_BYS},
    }
    if not location_ids:
        # An empty enum is invalid JSON Schema: offer no location filter at all.
        del properties["location_ids"]

    return [
        {
            "name": "query_exceptions",
            "description": (
                "Query the user's reconciliation exceptions. Use for questions about how many "
                "exceptions there are, which records they are, or the total size of the amount "
                "differences, optionally filtered by reason, location or date."
            ),
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": ["metric"],
                "additionalProperties": False,
            },
        },
        {
            "name": "cannot_answer",
            "description": "Use when the question can't be answered by query_exceptions.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "reason_type": {"type": "string", "enum": MODEL_REASON_TYPES},
                    # Requested for debugging/logs only. Never shown to the user.
                    "explanation": {"type": "string"},
                },
                "required": ["reason_type"],
                "additionalProperties": False,
            },
        },
    ]
