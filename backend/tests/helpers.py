from contextlib import contextmanager

from django.db import connection

from tenancy.rls import ORG_SETTING


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
