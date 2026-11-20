"""Re-validate everything the model returns before it touches a query.

The tool schema tells the model what's allowed; this serializer enforces it.
The model's output is treated like any untrusted client input.
"""
from rest_framework import serializers

from recon.models import ReasonCode

from . import refusals
from .tools import GROUP_BYS, METRICS

# Exceptions where "A minus accounts" isn't a meaningful number:
#   MISSING_IN_SYSTEM_A  there is no A amount at all
#   AMOUNT_BLANK         the accounts amount is unknown, not zero
#   VOIDED_BUT_RECORDED  the sale was cancelled, so A's total isn't what
#                        accounts should hold
# sum_gap refuses them when asked for explicitly, and leaves them out (naming
# them in the answer) otherwise. See DECISIONS.md.
NO_GAP_REASONS = {
    ReasonCode.MISSING_IN_SYSTEM_A,
    ReasonCode.AMOUNT_BLANK,
    ReasonCode.VOIDED_BUT_RECORDED,
}


class QuestionSerializer(serializers.Serializer):
    """The request body: {question}. Anything else in the body is ignored;
    in particular the org always comes from the logged-in user."""

    question = serializers.CharField(max_length=500, trim_whitespace=True, allow_blank=False)


class IntentSerializer(serializers.Serializer):
    metric = serializers.ChoiceField(choices=METRICS)
    reason_codes = serializers.ListField(
        child=serializers.ChoiceField(choices=ReasonCode.values), required=False, default=list, max_length=8
    )
    # Choices are filled in per request from the user's own (RLS-scoped)
    # locations, so another org's location is rejected as unknown.
    location_ids = serializers.ListField(
        child=serializers.ChoiceField(choices=[]), required=False, default=list, max_length=20
    )
    date_from = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])
    date_to = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])
    group_by = serializers.ChoiceField(choices=GROUP_BYS, required=False, default="none")

    def __init__(self, *args, location_ids=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location_ids"].child.choices = list(location_ids)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError({"unknown_keys": ["input is not an object"]})
        # additionalProperties: false, enforced here. An invented key such as
        # `org_id` or `sql` means the model went off-script: refuse outright.
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({"unknown_keys": sorted(unknown)})
        return super().to_internal_value(data)

    def validate(self, attrs):
        date_from, date_to = attrs.get("date_from"), attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError({"date_range": "date_from is after date_to"})
        if attrs["metric"] == "sum_gap" and NO_GAP_REASONS & set(attrs["reason_codes"]):
            raise serializers.ValidationError({"sum_gap": "no gap can be computed for these reasons"})
        return attrs


def refusal_for(errors: dict) -> str:
    """Map serializer errors to one refusal code. First match wins."""
    if "unknown_keys" in errors:
        return refusals.OUT_OF_SCOPE
    if "reason_codes" in errors or "location_ids" in errors:
        return refusals.UNKNOWN_FILTER
    if "sum_gap" in errors:
        return refusals.DATA_NOT_AVAILABLE
    if {"date_from", "date_to", "date_range"} & set(errors):
        return refusals.AMBIGUOUS
    return refusals.OUT_OF_SCOPE  # bad metric / group_by: not something we can query
