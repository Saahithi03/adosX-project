"""Test setup: run against the real, migrated `dealeros` database as dealeros_app.

pytest-django normally creates a fresh `test_dealeros` database. The app role
is (deliberately) not allowed to create databases, and tests must never run as
the owner, because owners skip RLS unless forced and that would make the
isolation tests prove nothing. So instead:

- `django_db_setup` is overridden to do nothing: use the existing database.
- Each `@pytest.mark.django_db` test runs inside a transaction that is rolled
  back afterwards, so tests never leave rows behind.
- Test data uses IDs (LOC-T*, REC-T*, t_* users) that can't collide with
  ingested data.
"""
import pytest
from django.db import connection

from tenancy.rls import TENANT_TABLES

from .helpers import DATA_DIR


@pytest.fixture(scope="session")
def django_db_setup():
    """Use the database from settings as-is; don't create a test database."""


@pytest.fixture(scope="session", autouse=True)
def _refuse_privileged_role(django_db_blocker):
    """Abort the whole run if we're connected as a role that can skip RLS."""
    with django_db_blocker.unblock():
        with connection.cursor() as c:
            c.execute(
                """
                SELECT current_user, r.rolsuper, r.rolbypassrls,
                       EXISTS (SELECT 1 FROM pg_tables
                               WHERE schemaname = 'public'
                                 AND tablename = ANY(%s)
                                 AND tableowner = current_user)
                FROM pg_roles r WHERE r.rolname = current_user
                """,
                [list(TENANT_TABLES)],
            )
            user, is_super, bypass, owns = c.fetchone()
    if is_super or bypass or owns:
        pytest.exit(
            f"Tests are connected as {user!r} (superuser={is_super}, "
            f"bypassrls={bypass}, owns tenant tables={owns}). That role can skip "
            "or switch off RLS, so isolation tests would prove nothing. "
            "Use DATABASE_URL_APP.",
            returncode=1,
        )


# --- shared fixtures -----------------------------------------------------------

@pytest.fixture
def alice(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user("t_alice", password="pw", org_id="ORG-A")


@pytest.fixture
def bob(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user("t_bob", password="pw", org_id="ORG-B")


@pytest.fixture
def ingested(db):
    """The real CSVs reconciled and stored, exactly as `make ingest` does,
    inside this test's rolled-back transaction."""
    from recon.reconcile import reconcile_dir
    from recon.store import replace_all

    replace_all(*reconcile_dir(DATA_DIR))
