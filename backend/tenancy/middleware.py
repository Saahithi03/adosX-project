"""Sets the tenant for each request, so Postgres RLS can filter by it.

Order matters: this must come after AuthenticationMiddleware, because the org
comes from request.user and nowhere else. Never from a header, query string or
request body.
"""
from django.db import connection, transaction

from .rls import ORG_SETTING


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user  # set by AuthenticationMiddleware (session auth)

        if not user.is_authenticated:
            # No org is set, so every RLS-protected query returns zero rows.
            # Login itself only touches users/sessions, which aren't tenant data.
            return self.get_response(request)

        # One transaction around the whole view, with the org set LOCAL to it.
        # When the transaction ends, Postgres drops the setting, so a pooled or
        # reused connection can't carry this org into the next request. A
        # session-level SET would survive and leak.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config(%s, %s, true)",  # true = is_local (SET LOCAL)
                    [ORG_SETTING, user.org_id],
                )
            response = self.get_response(request)

            # Django turns view exceptions into a 500 response before it gets
            # back here, so atomic() would see no exception and commit. Roll
            # back explicitly so a failed request never persists half its writes.
            if response.status_code >= 500:
                transaction.set_rollback(True)

        return response
