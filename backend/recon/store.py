"""Write reconciliation results to the tenant tables, one org at a time.

FORCE RLS applies to every role, the owner included, so there's no "write all
orgs at once". For each org we SET LOCAL app.current_org, then replace that
org's rows. The policy's WITH CHECK rejects any row whose org_id doesn't match
the org being written, so a bug that put an ORG-B row in the ORG-A batch would
fail the whole ingest instead of leaking.
"""
from django.db import connection, transaction

from tenancy.rls import ORG_SETTING

from .models import Location, ReconException
from .reconcile import Finding, LocationRow


def _set_org(org_id: str) -> None:
    with connection.cursor() as c:
        c.execute("SELECT set_config(%s, %s, true)", [ORG_SETTING, org_id])


@transaction.atomic  # all orgs or none: a failed ingest leaves the old data intact
def replace_all(locations: dict[str, LocationRow], findings: list[Finding]) -> dict[str, int]:
    orgs = sorted({loc.org_id for loc in locations.values()})
    written = {}

    for org in orgs:
        _set_org(org)  # later calls override earlier ones within this transaction

        # Exceptions first: they reference locations (on_delete=PROTECT).
        ReconException.objects.all().delete()  # RLS limits this to `org`

        org_locations = [loc for loc in locations.values() if loc.org_id == org]
        for loc in org_locations:
            Location.objects.update_or_create(
                location_id=loc.location_id,
                defaults={"org_id": org, "location_name": loc.location_name},
            )
        Location.objects.exclude(location_id__in=[l.location_id for l in org_locations]).delete()

        rows = [
            ReconException(
                org_id=f.org_id,
                record_id=f.record_id,
                location_id=f.location_id,
                reason_code=f.reason_code,
                a_amount=f.a_amount,
                b_amount=f.b_amount,
                b_entry_ids=list(f.b_entry_ids),
                b_location_id=f.b_location_id,
                record_date=f.record_date,
            )
            for f in findings
            if f.org_id == org
        ]
        ReconException.objects.bulk_create(rows)
        written[org] = len(rows)

    _set_org("")  # leave the transaction with no org set
    return written
