"""Row-level security SQL, in one place.

Used by the recon RLS migration and (step 4) by the rls-off / rls-on
walkthrough commands, so the policy text can't drift between them.
"""

# Every table that holds tenant data. Adding a tenant table means adding it here.
TENANT_TABLES = ("locations", "exceptions")

# The setting TenantMiddleware fills with SET LOCAL for each request.
ORG_SETTING = "app.current_org"

# current_setting(..., true) returns NULL if the setting was never set on this
# connection, and '' once a SET LOCAL from an earlier transaction has ended.
# NULLIF folds both to NULL, and `org_id = NULL` is never true: fail closed.
_CURRENT_ORG = f"NULLIF(current_setting('{ORG_SETTING}', true), '')"


def enable_rls_sql(table: str) -> str:
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        -- FORCE: the policy applies to the table owner too, not just dealeros_app.
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        -- Drop first so `rls on` can be re-run safely after `rls off`.
        DROP POLICY IF EXISTS org_isolation ON {table};
        CREATE POLICY org_isolation ON {table}
            USING (org_id = {_CURRENT_ORG})       -- which rows are visible
            WITH CHECK (org_id = {_CURRENT_ORG}); -- which rows may be written
    """


def disable_rls_sql(table: str) -> str:
    return f"""
        DROP POLICY IF EXISTS org_isolation ON {table};
        ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
    """
