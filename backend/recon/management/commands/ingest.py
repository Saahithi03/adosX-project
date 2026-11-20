"""`manage.py ingest`: read data/*.csv, reconcile, store the exceptions.

Run as dealeros_owner (`make ingest`). It does NOT bypass RLS: it writes one
org at a time under SET LOCAL, so the policy checks every row (recon/store.py).
Safe to re-run: each org's rows are replaced in a single transaction.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from recon.reconcile import reconcile_dir
from recon.store import replace_all


class Command(BaseCommand):
    help = "Reconcile System A against System B and store the exceptions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            type=Path,
            default=settings.REPO_ROOT / "data",
            help="Folder holding locations.csv, system_a.csv, system_b.csv",
        )

    def handle(self, *args, data_dir, **options):
        locations, findings = reconcile_dir(data_dir)
        written = replace_all(locations, findings)
        for org, n in written.items():
            self.stdout.write(f"{org}: {n} exceptions")
