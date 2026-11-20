# Decisions

Each entry: **decision**, the rejected alternative, and the one-line reason.
Entries are added as the build steps land.

## Tenant isolation

- **Postgres RLS** over a Django manager filter: a manager can be bypassed (raw SQL, `_base_manager`, a forgotten `.filter`), a policy can't.
- **Non-owner app role (`dealeros_app`) + `FORCE ROW LEVEL SECURITY`** over connecting as the table owner: owners and superusers skip RLS silently, so a passing test would prove nothing.
- **Ingest runs as `dealeros_owner` but writes one org at a time under `SET LOCAL app.current_org`** over giving the owner `BYPASSRLS`: FORCE RLS stays meaningful for every role, and the policy's `WITH CHECK` verifies that each row ingest writes lands in the org it claims. The brief described ingest as "bypassing RLS on purpose"; this was changed deliberately (step 2).
- **Policy compares against `NULLIF(current_setting('app.current_org', true), '')`** over the bare `current_setting(...)`: after a `SET LOCAL` ends, Postgres leaves the setting as `''` rather than NULL on that connection. Both fail closed today (no org is `''`), but NULLIF makes "unset means no rows" explicit instead of incidental.
- **Composite FK `exceptions(location_id, org_id) → locations(location_id, org_id)`** over relying on ingest code alone: an exception physically cannot point at another org's location, even if reconciliation code has a bug. FK checks bypass RLS by design, so the constraint works across the policy.

## Data model

- **Raw System A / B rows are not stored**, only `locations` and `exceptions`, over loading both CSVs into tenant tables: the feature only needs the exceptions, and every extra tenant table is another place a policy could be missing. Trade-off: no per-record drill-down (already on the not-built list).
- **Model named `ReconException`, table `exceptions`** over a model called `Exception`: shadowing Python's built-in `Exception` inside `models.py` would break any `except Exception` in that module.
