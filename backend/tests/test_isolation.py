"""Proof that tenant isolation is enforced by Postgres, not by app code.

Nothing here filters by org. Every query is a plain `.all()` or a raw
`SELECT *`, so the only thing that can keep ORG-B rows away from ORG-A is the
RLS policy. Switch it off (`make rls-off`) and these tests fail; switch it
back on (`make rls-on`) and they pass.
"""
import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import DatabaseError, connection, transaction
from django.http import HttpResponse
from django.test import Client, RequestFactory

from recon.models import Location, ReasonCode, ReconException
from tenancy.middleware import TenantMiddleware
from tenancy.rls import TENANT_TABLES

from .helpers import org_context, set_org

pytestmark = pytest.mark.django_db


# --- fixtures ----------------------------------------------------------------

@pytest.fixture
def two_orgs():
    """One location and one exception per org, written the way ingest writes:
    one org at a time, with that org set, so WITH CHECK accepts them."""
    for org, loc, rec in [("ORG-A", "LOC-TA1", "REC-TA1"), ("ORG-B", "LOC-TB1", "REC-TB1")]:
        with org_context(org):
            location = Location.objects.create(location_id=loc, org_id=org, location_name=loc)
            ReconException.objects.create(
                org_id=org,
                record_id=rec,
                location=location,
                reason_code=ReasonCode.AMOUNT_MISMATCH,
            )


@pytest.fixture
def alice():
    return get_user_model().objects.create_user("t_alice", password="pw", org_id="ORG-A")


@pytest.fixture
def bob():
    return get_user_model().objects.create_user("t_bob", password="pw", org_id="ORG-B")


def through_middleware(user, query, request=None):
    """Run `query()` as if it were a view, behind the real TenantMiddleware."""
    request = request or RequestFactory().get("/probe")
    request.user = user
    captured = {}

    def view(req):
        captured["result"] = query()
        return HttpResponse()

    TenantMiddleware(view)(request)
    # In production the org vanishes when the middleware's transaction ends.
    # Here that "transaction" is a savepoint inside the test's transaction, so
    # SET LOCAL would survive it; clear it so later assertions start unset.
    set_org("")
    return captured["result"]


def orm_orgs():
    return sorted({e.org_id for e in ReconException.objects.all()})


def raw_orgs():
    with connection.cursor() as c:
        c.execute("SELECT * FROM exceptions")
        cols = [col.name for col in c.description]
        return sorted({dict(zip(cols, row))["org_id"] for row in c.fetchall()})


def raw_record_ids():
    with connection.cursor() as c:
        c.execute("SELECT record_id FROM exceptions")
        return {r[0] for r in c.fetchall()}


# --- the database is set up so RLS can't be skipped --------------------------

def test_tests_run_as_unprivileged_app_role():
    with connection.cursor() as c:
        c.execute(
            "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        assert c.fetchone() == ("dealeros_app", False, False)


@pytest.mark.parametrize("table", TENANT_TABLES)
def test_rls_enabled_and_forced(table):
    with connection.cursor() as c:
        c.execute(
            """
            SELECT c.relrowsecurity, c.relforcerowsecurity,
                   (SELECT count(*) FROM pg_policy p
                    WHERE p.polrelid = c.oid AND p.polname = 'org_isolation')
            FROM pg_class c WHERE c.relname = %s
            """,
            [table],
        )
        assert c.fetchone() == (True, True, 1)


# --- reads -------------------------------------------------------------------

def test_org_a_sees_only_org_a_via_orm_and_raw_sql(two_orgs, alice):
    assert through_middleware(alice, orm_orgs) == ["ORG-A"]
    assert through_middleware(alice, raw_orgs) == ["ORG-A"]
    assert "REC-TB1" not in through_middleware(alice, raw_record_ids)


def test_org_b_sees_only_org_b(two_orgs, bob):
    assert through_middleware(bob, orm_orgs) == ["ORG-B"]
    assert "REC-TA1" not in through_middleware(bob, raw_record_ids)


def test_locations_are_isolated_too(two_orgs, alice):
    loc_ids = through_middleware(alice, lambda: set(Location.objects.values_list("location_id", flat=True)))
    assert "LOC-TA1" in loc_ids
    assert "LOC-TB1" not in loc_ids


def test_no_org_set_returns_zero_rows(two_orgs):
    # Straight query, no middleware, no org: fail closed.
    assert ReconException.objects.count() == 0
    assert Location.objects.count() == 0
    assert raw_record_ids() == set()


def test_anonymous_request_gets_no_org(two_orgs):
    assert through_middleware(AnonymousUser(), lambda: ReconException.objects.count()) == 0


def test_client_supplied_org_is_ignored(two_orgs, alice):
    # Org smuggled in the body, the query string and a header: none of it counts.
    request = RequestFactory().post(
        "/probe?org_id=ORG-B",
        data=json.dumps({"org_id": "ORG-B"}),
        content_type="application/json",
        HTTP_X_ORG_ID="ORG-B",
    )
    assert through_middleware(alice, orm_orgs, request=request) == ["ORG-A"]


def test_login_body_org_is_ignored(alice):
    # End to end over HTTP: the org in /api/me comes from the user row.
    client = Client(enforce_csrf_checks=True)
    client.get("/api/me")  # sets the csrftoken cookie
    resp = client.post(
        "/api/login",
        data={"username": "t_alice", "password": "pw", "org_id": "ORG-B"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert resp.status_code == 200
    assert client.get("/api/me").json() == {"username": "t_alice", "org_id": "ORG-A"}


# --- writes ------------------------------------------------------------------

def test_cannot_write_a_row_for_another_org(two_orgs):
    with org_context("ORG-A"):
        location = Location.objects.get(location_id="LOC-TA1")
        with pytest.raises(DatabaseError, match="row-level security"):
            with transaction.atomic():  # savepoint, so the test can carry on
                ReconException.objects.create(
                    org_id="ORG-B",
                    record_id="REC-TX",
                    location=location,
                    reason_code=ReasonCode.AMOUNT_MISMATCH,
                )


def test_cannot_move_own_row_into_another_org(two_orgs):
    with org_context("ORG-A"):
        with pytest.raises(DatabaseError, match="row-level security"):
            with transaction.atomic():
                ReconException.objects.filter(record_id="REC-TA1").update(org_id="ORG-B")


def test_cannot_update_or_delete_another_orgs_rows(two_orgs):
    with org_context("ORG-A"):
        # ORG-B's rows are invisible, so these match nothing.
        assert ReconException.objects.filter(record_id="REC-TB1").update(a_amount=1) == 0
        assert ReconException.objects.filter(record_id="REC-TB1").delete()[0] == 0
    with org_context("ORG-B"):
        assert ReconException.objects.get(record_id="REC-TB1").a_amount is None
