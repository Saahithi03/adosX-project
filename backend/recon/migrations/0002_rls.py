"""Turn on row-level security for every tenant table.

Runs as dealeros_owner (the table owner), the only role allowed to change it.
Reversing this migration is one way to switch RLS off for the isolation-test
walkthrough; the isolation test must then fail.
"""
from django.db import migrations

from tenancy.rls import TENANT_TABLES, disable_rls_sql, enable_rls_sql

# Defence in depth beside RLS: an exception may only point at a location of
# its own org. (location_id alone is already unique; the extra UNIQUE exists
# so the composite FK below has something to reference.) FK checks bypass
# RLS by design in Postgres, so this holds even though both tables are RLS'd.
SAME_ORG_FK = """
    ALTER TABLE locations
        ADD CONSTRAINT locations_id_org_uniq UNIQUE (location_id, org_id);
    ALTER TABLE exceptions
        ADD CONSTRAINT exceptions_location_same_org_fk
        FOREIGN KEY (location_id, org_id) REFERENCES locations (location_id, org_id);
"""

SAME_ORG_FK_REVERSE = """
    ALTER TABLE exceptions DROP CONSTRAINT exceptions_location_same_org_fk;
    ALTER TABLE locations DROP CONSTRAINT locations_id_org_uniq;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("recon", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(SAME_ORG_FK, reverse_sql=SAME_ORG_FK_REVERSE),
        *[
            migrations.RunSQL(enable_rls_sql(t), reverse_sql=disable_rls_sql(t))
            for t in TENANT_TABLES
        ],
    ]
