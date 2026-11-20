"""`manage.py rls off|on`: the isolation-test walkthrough switch.

    make rls-off && make test   -> isolation tests FAIL (ORG-B rows leak)
    make rls-on  && make test   -> isolation tests pass

Only the table owner may change RLS, so this must run as dealeros_owner
(the Makefile targets set DEALEROS_DB_ROLE=owner). It uses the same SQL as the
RLS migration, so "on" restores exactly what the migration created. For demos
only: never leave a real deployment with RLS off.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from tenancy.rls import TENANT_TABLES, disable_rls_sql, enable_rls_sql


class Command(BaseCommand):
    help = "Switch row-level security off or on for every tenant table (demo only)."

    def add_arguments(self, parser):
        parser.add_argument("state", choices=["off", "on"])

    def handle(self, *args, state, **options):
        if settings.DB_ROLE != "owner":
            raise CommandError("Run as the table owner: DEALEROS_DB_ROLE=owner (make rls-off / rls-on).")

        sql = disable_rls_sql if state == "off" else enable_rls_sql
        with transaction.atomic(), connection.cursor() as c:
            for table in TENANT_TABLES:
                c.execute(sql(table))
        self.stdout.write(f"RLS {state.upper()} for: {', '.join(TENANT_TABLES)}")
