from contextlib import contextmanager
from pathlib import Path

from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory

from tenancy.middleware import TenantMiddleware
from tenancy.rls import ORG_SETTING

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def set_org(org_id):
    with connection.cursor() as c:
        # true = local to the current transaction, exactly like the middleware.
        c.execute("SELECT set_config(%s, %s, true)", [ORG_SETTING, org_id])


@contextmanager
def org_context(org_id):
    """Act as `org_id` for the block, then clear the org again.

    Inside a test everything shares one outer transaction (it's rolled back at
    the end), so a SET LOCAL would otherwise last for the rest of the test.
    Clearing it to '' (which the policy treats as unset) stops one block's org
    from bleeding into the next assertion.
    """
    set_org(org_id)
    try:
        yield
    finally:
        set_org("")


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
