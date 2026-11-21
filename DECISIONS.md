# Decisions

Each entry: **decision**, the rejected alternative, and the one-line reason.
Where a decision departs from the brief (CLAUDE.md), the entry says so.

## Tenant isolation

- **Postgres RLS** over a Django manager filter: a manager can be bypassed (raw SQL, `_base_manager`, a forgotten `.filter`), a policy can't.
- **Non-owner app role (`dealeros_app`) + `FORCE ROW LEVEL SECURITY`** over connecting as the table owner: owners and superusers skip RLS silently, so a passing test would prove nothing.
- **Ingest runs as `dealeros_owner` but writes one org at a time under `SET LOCAL app.current_org`** over giving the owner `BYPASSRLS`: FORCE RLS stays meaningful for every role, and the policy's `WITH CHECK` verifies that each row ingest writes lands in the org it claims. The brief described ingest as "bypassing RLS on purpose"; this was changed deliberately (step 2).
- **Policy compares against `NULLIF(current_setting('app.current_org', true), '')`** over the bare `current_setting(...)`: after a `SET LOCAL` ends, Postgres leaves the setting as `''` rather than NULL on that connection. Both fail closed today (no org is `''`), but NULLIF makes "unset means no rows" explicit instead of incidental.
- **Composite FK `exceptions(location_id, org_id) → locations(location_id, org_id)`** over relying on ingest code alone: an exception physically cannot point at another org's location, even if reconciliation code has a bug. FK checks bypass RLS by design, so the constraint works across the policy.

## Request flow and auth

- **`SET LOCAL` (`set_config(..., true)`) inside a middleware-owned `transaction.atomic()`** over a session-level `SET`: a session setting survives on the connection, so a pooled or reused connection would carry one tenant's org into the next request. A local setting ends with the transaction. (Tested by hand: after a request, the same connection sees `''`, and the policy treats that as no org.)
- **The org comes only from `request.user.org_id`** over accepting it from the client: an `org_id` in the body, query string or a header is ignored (tested for each).
- **Django session auth (DRF `SessionAuthentication`)** over DRF token or JWT auth: those authenticate inside the DRF view, after middleware has run, so `TenantMiddleware` would see an anonymous user and set no org.
- **Login checks CSRF explicitly** over DRF's default: DRF only enforces CSRF for already-authenticated session users, so an anonymous login POST would skip it and allow login CSRF.
- **5xx responses roll the request's transaction back** over committing: Django turns a view exception into a 500 response before it reaches the middleware, so `atomic()` alone would commit half-done writes.

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

## API

- **Serializers are explicit allow-lists with no `org_id` or `b_location_id`** over `fields = "__all__"`: a new model field can never reach the API by accident, and REC-1077's ORG-B branch never reaches ORG-A.
- **An unknown `reason` or `location` filter returns 400** over silently returning an empty list: a typo looks different from "nothing matches". The location check is itself RLS-scoped and the message doesn't echo the value, so another org's location gets exactly the same answer as a made-up one, and its existence isn't confirmed.

## Grounded Q&A (`/api/ask`)

- **The LLM only parses the question into a tool call; Django validates it and computes every number** over text-to-SQL (a valid query can still be the wrong query, which is a confident lie with citations) and over putting rows in the prompt (the model would do the counting, and can miscount).
- **`IntentSerializer` re-validates every tool call** over trusting the API's schema enforcement: the schema guides the model, the serializer guarantees safety. Unknown keys (`org_id`, `sql`) → `OUT_OF_SCOPE`; unknown reason or another org's location → `UNKNOWN_FILTER`; bad or reversed dates → `AMBIGUOUS`; sum_gap on a code with no gap → `DATA_NOT_AVAILABLE`.
- **Refusal text is ours; the model's `explanation` is discarded** over displaying it: no number can originate from the model. Refusal messages contain no digits and never echo a filter value (tested).
- **Location enum built per request from the RLS-scoped `locations` table** over a static list: the model is never even offered another org's location IDs.
- **`sum_gap` = sum of |A − accounts| per exception, a missing accounts entry counting as 0** over a signed sum: a signed total lets an over-recording (the REC-1042 duplicate) cancel out an under-recording and report a misleadingly small gap. Rows where the difference isn't meaningful are left out and named in the answer: `MISSING_IN_SYSTEM_A` (no A amount), `AMOUNT_BLANK` (accounts amount unknown, not zero), `VOIDED_BUT_RECORDED` (the sale was cancelled, so A's total isn't what accounts should hold). Asking for sum_gap on those codes explicitly is refused.
- **Refusals return HTTP 200 with `answered: false`** over a 4xx: declining to answer is a valid outcome, not a client error, and the UI handles both shapes the same way.
- **Google Gemini (`google-genai`, default `gemini-3.1-flash-lite`) over the brief's Anthropic `claude-sonnet-5-5`**: a deliberate deviation from the brief's stack, because Gemini has a free API tier and this was built without a paid Anthropic key. The architecture doesn't depend on the provider: the model only returns a function call, and everything that makes Ask safe (the serializer, fixed refusals, RLS-scoped queries, template answers) is provider-independent and was written and tested before any model was plugged in. Switching back is a change to `ask/llm.py` alone. Rejected: shipping the Anthropic integration untested against a real model.
- **Function calling mode `ANY` restricted to the two function names, and `temperature: 0`**: exactly the brief's intent. Gemini accepts both (the Anthropic model named in the brief rejects forced tool use and sampling parameters with a 400, which is what we found before switching). A response with no function call (e.g. a safety block) is refused as `OUT_OF_SCOPE`, and model text is never used.
- **`gemini-3.1-flash-lite` as the default model (`ASK_MODEL` overrides it)** over larger flash models: with the free key, `gemini-2.5-flash` was closed to new users (404), and `gemini-3.8-flash` / `3.5-flash` often returned 503 "high demand". The lite model passed all live tests on repeated runs, in about 3 s per question, and parsing one question into a small JSON object doesn't need a bigger model.
- **`thinking_level: LOW` and a 45 s timeout**: the SDK sends the client timeout to Gemini as the server deadline, so the original 20 s plus default thinking produced 504s. Low thinking is plenty for this task.
- **Retry 429/503/504 up to 3 attempts (1 s → 8 s backoff), then `LLM_UNAVAILABLE`**: free-tier overload is usually seconds long. Any other failure (no key, bad key, quota, network) is `LLM_UNAVAILABLE` immediately: the table and filters don't depend on the LLM and keep working.
- **Live tests fail, not pass, when the model is unreachable**: `LLM_UNAVAILABLE` is itself a refusal, so without an explicit check the refusal tests passed against a 401 without ever reaching a model (this happened).
- **Counts are exceptions (rows); evidence is distinct record IDs** over counting records: matches the table the user sees.

## Frontend

- **Vite proxies `/api` with `changeOrigin: false`** over Vite's string shorthand (which sets `changeOrigin: true`) or adding `CSRF_TRUSTED_ORIGINS`: keeping the browser's `Host` (`localhost:5173`) makes Django's CSRF Origin check pass with no exception in Django's config. The shorthand rewrote `Host` to `:8000` and every login failed (found in the browser).
- **Rupee formatting works on the decimal string** over `Number(...)` + `Intl.NumberFormat`: a money value never passes through a float, even for display.
- **MUI (`@mui/material` + Emotion) for one component: a full-page `Backdrop` with a `CircularProgress` while Ask is waiting** over the brief's "no UI library". A deliberate deviation, made at the product owner's request: a free-tier LLM call can take tens of seconds, and a page-level loader makes that wait obvious and stops clicks on a table that's about to change. It's imported per component (`@mui/material/Backdrop`) and used nowhere else, so the rest of the UI stays plain HTML + CSS; it adds about 32 KB gzipped.
- **Missing amounts are labelled by meaning instead of a bare "—"** (a change from the brief's "—", at the product owner's request): "No entry" when accounts has no entry at all (REC-1061, `b_entry_ids` empty), "Amount blank" when an entry exists but its amount is empty (REC-1050), and "No sale record" on the System A side (REC-1999). The same "—" for REC-1050 and REC-1061 made two different problems look identical. The API already returned what's needed (`b_entry_ids`), so this is UI only.
- **Clicking an evidence chip clears the filters if they hide that row** over highlighting nothing: the user always gets to see the record an answer cites.

## Data model

- **Raw System A / B rows are not stored**, only `locations` and `exceptions`, over loading both CSVs into tenant tables: the feature only needs the exceptions, and every extra tenant table is another place a policy could be missing. Trade-off: no per-record drill-down (already on the not-built list).
- **Model named `ReconException`, table `exceptions`** over a model called `Exception`: shadowing Python's built-in `Exception` inside `models.py` would break any `except Exception` in that module.
