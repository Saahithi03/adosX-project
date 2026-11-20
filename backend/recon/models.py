"""Tenant tables. Every one has an `org_id` column that RLS filters on.

The raw System A / System B rows are not stored: ingest reads the CSVs,
reconciles in memory, and writes only locations and exceptions. Fewer tenant
tables means fewer places for a policy to be missing (see DECISIONS.md).
"""
from django.db import models


class ReasonCode(models.TextChoices):
    # value = code stored in the DB; label = plain English for the UI.
    MISSING_IN_SYSTEM_B = "MISSING_IN_SYSTEM_B", "Sale recorded, but no matching entry in accounts"
    MISSING_IN_SYSTEM_A = "MISSING_IN_SYSTEM_A", "Accounts entry points to a sale that doesn't exist"
    TAX_NOT_RECORDED = "TAX_NOT_RECORDED", "Accounts recorded the pre-tax amount only"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH", "Amounts differ between the two systems"
    DUPLICATE_ENTRY = "DUPLICATE_ENTRY", "Recorded twice in accounts"
    AMOUNT_BLANK = "AMOUNT_BLANK", "Accounts entry has no amount"
    VOIDED_BUT_RECORDED = "VOIDED_BUT_RECORDED", "Sale was cancelled, but the accounts entry still exists"
    LOCATION_MISMATCH = "LOCATION_MISMATCH", "Branch differs between the two systems"


class Location(models.Model):
    location_id = models.CharField(max_length=16, primary_key=True)
    org_id = models.CharField(max_length=16, db_index=True)
    location_name = models.CharField(max_length=100)

    class Meta:
        db_table = "locations"

    def __str__(self):
        return self.location_id


class ReconException(models.Model):
    """One disagreement between System A and System B.

    Named ReconException, not Exception, so it never shadows Python's built-in
    inside this module. The table is still called `exceptions`.
    """

    org_id = models.CharField(max_length=16, db_index=True)
    record_id = models.CharField(max_length=16)  # normalised, e.g. REC-1088
    # The location shown to this org: A's location, or B's when A is missing.
    # A composite FK (location_id, org_id) added in the RLS migration
    # guarantees it belongs to the same org as the exception.
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, db_column="location_id", related_name="+"
    )
    reason_code = models.CharField(max_length=32, choices=ReasonCode.choices)
    a_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    b_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    b_entry_ids = models.JSONField(default=list)  # e.g. ["ENT/2026/4088"]
    # B's location when it differs from A's (REC-1077). Kept for audit, but it
    # may belong to another org, so it is never serialised to the API.
    b_location_id = models.CharField(max_length=16, null=True)
    # A's event_date, or B's recorded_on when there is no A record.
    # Used for date filters in /api/ask.
    record_date = models.DateField(null=True)

    class Meta:
        db_table = "exceptions"
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "record_id", "reason_code"],
                name="exceptions_one_per_reason",
            ),
        ]
