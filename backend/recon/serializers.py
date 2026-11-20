from rest_framework import serializers

from .models import Location, ReconException


class ExceptionSerializer(serializers.ModelSerializer):
    """The exception item shape from CLAUDE.md §7.

    Deliberately an allow-list: `org_id` and `b_location_id` are never
    included. For REC-1077, b_location_id is an ORG-B branch, and exposing it
    to ORG-A would be a cross-tenant leak.
    """

    # The join to locations is itself RLS-scoped; the composite FK guarantees
    # the location belongs to the same org, so it's always visible.
    location_name = serializers.CharField(source="location.location_name")
    reason_label = serializers.CharField(source="get_reason_code_display")
    # DRF renders Decimals as strings ("138948.30"), so no float ever appears.
    a_amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
    b_amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)

    class Meta:
        model = ReconException
        fields = [
            "record_id",
            "location_id",
            "location_name",
            "reason_code",
            "reason_label",
            "a_amount",
            "b_amount",
            "b_entry_ids",
        ]


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["location_id", "location_name"]  # no org_id
