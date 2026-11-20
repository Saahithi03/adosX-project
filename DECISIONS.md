# Decisions

Each entry: **decision**, the rejected alternative, and the one-line reason.
Entries are added as the build steps land.

## Tenant isolation

- **Postgres RLS** over a Django manager filter: a manager can be bypassed (raw SQL, `_base_manager`, a forgotten `.filter`), a policy can't.
- **Non-owner app role (`dealeros_app`) + `FORCE ROW LEVEL SECURITY`** over connecting as the table owner: owners and superusers skip RLS silently, so a passing test would prove nothing.
- **Ingest runs as `dealeros_owner` but writes one org at a time under `SET LOCAL app.current_org`** over giving the owner `BYPASSRLS`: FORCE RLS stays meaningful for every role, and the policy's `WITH CHECK` verifies that each row ingest writes lands in the org it claims. The brief described ingest as "bypassing RLS on purpose"; this was changed deliberately (step 2).
- **Policy compares against `NULLIF(current_setting('app.current_org', true), '')`** over the bare `current_setting(...)`: after a `SET LOCAL` ends, Postgres leaves the setting as `''` rather than NULL on that connection. Both fail closed today (no org is `''`), but NULLIF makes "unset means no rows" explicit instead of incidental.
- **Composite FK `exceptions(location_id, org_id) → locations(location_id, org_id)`** over relying on ingest code alone: an exception physically cannot point at another org's location, even if reconciliation code has a bug. FK checks bypass RLS by design, so the constraint works across the policy.

## Testing isolation

- **Tests run against the existing, migrated `dealeros` database as `dealeros_app`, each test rolled back** over letting pytest-django create a `test_dealeros` database: creating databases would need `CREATEDB` (more privilege), and the tests must connect as the app role anyway. A session guard aborts the run if the connection is a superuser, has `BYPASSRLS`, or owns a tenant table. Test rows use `LOC-T*` / `REC-T*` / `t_*` IDs so they never collide with ingested data.
- **`manage.py rls off|on` (as owner) for the walkthrough** over rolling back the RLS migration: the rollback would also drop the same-org composite FK, and would leave migration history out of step. The command reuses the exact SQL from `tenancy/rls.py`, so "on" restores precisely what the migration created.

## Parsing (`recon/normalise.py`)

- **Unparseable refs and amounts raise `ValueError` and stop ingest** over skipping the row or guessing: a silently dropped row could hide a real disagreement. Today's data has none (every B ref normalises, every non-blank amount parses), and a test checks that across the whole of `system_b.csv`.
- **Amounts finer than a paisa are rejected, not rounded** over quantizing them: comparison is exact to 0.01, so rounding could turn a real mismatch into a match.
- **Blank amount parses to `None`, never `0`**: a blank must stay distinguishable so it can be reported as `AMOUNT_BLANK`.

## Reconciliation (`recon/reconcile.py`)

- **Compare A's total with the sum of all matching B entries** over one-to-one matching: split payments (REC-1055) are legitimate. Note REC-1055's first part is labelled "Entry for CAT-08", not "part 1 of 2", so the split is recognised by the sum, never by the labels.
- **Org and location come from A (the master record); REC-1077 goes to ORG-A only, shown at LOC-102, with B's LOC-201 stored in `b_location_id` but never serialised** over showing the record to both orgs: that would leak one tenant's branch details to the other.
- **`MISSING_IN_SYSTEM_A` takes the org of B's location** (REC-1999 → LOC-102 → ORG-A): there is no A row to take it from.
- **Codes per record: `VOIDED_BUT_RECORDED` alone; otherwise at most one amount code (blank → duplicate → tax → mismatch) plus `LOCATION_MISMATCH` if the branch differs** over always reporting a single code: amount and branch are independent facts, so hiding one behind the other would under-report. In today's data no record has both.
- **A VOIDED record with no B entry is not an exception** over flagging it: a cancelled sale with nothing in accounts is the correct state.
- **`TAX_NOT_RECORDED` is only checked after the sum fails to match** over checking it first: a record with zero adjustment has base == total, and a correct single entry would otherwise be mislabelled.
- **Dates are not compared at all** over adding a ninth code (e.g. `DATE_MISMATCH`) for B entries booked outside the 3-day window: matching is by record ref, not date, and the brief defines no reason code for a date gap, so the window has nothing to enforce. The only gap in today's data is REC-1009 (B 2 days after A), which is within it either way. `event_date` (`recorded_on` for `MISSING_IN_SYSTEM_A`) is still stored as `record_date` for Ask's date filters. If a date rule is wanted later, it would be an independent check alongside `LOCATION_MISMATCH` in `reconcile()`, with its own code and label.
- **Blank `actor_id` (REC-1050) not reported** over flagging it: it is an A-internal data gap, not a disagreement between the systems.

## Data model

- **Raw System A / B rows are not stored**, only `locations` and `exceptions`, over loading both CSVs into tenant tables: the feature only needs the exceptions, and every extra tenant table is another place a policy could be missing. Trade-off: no per-record drill-down (already on the not-built list).
- **Model named `ReconException`, table `exceptions`** over a model called `Exception`: shadowing Python's built-in `Exception` inside `models.py` would break any `except Exception` in that module.
