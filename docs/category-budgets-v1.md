# Supabase category budgets

Status: activated and verified in production on October 31, 2026 after explicit
deployment authorization. See [the production record](category-budgets-production-20261031.md).

`public.autonomy_budget_categories` is the current policy table for autonomous
work. Both numeric limits are seeded to **-1**, meaning unlimited, in all four
categories:

| Category | Scope |
| --- | --- |
| `research_assessment` | One assessment, including planning, experiment building and execution |
| `platform_manual` | One owner-requested platform improvement |
| `platform_maintenance` | One automatic general-maintenance task |
| `platform_repair` | One assessment-blocker repair task |

`max_spend_cents` limits conservative commitments in integer cents, not measured
charges. `max_model_calls` limits model-call admissions, including failed and
uncertain attempts. Zero is a real zero limit. NULL, missing categories and values
below -1 are invalid and never mean unlimited. Existing usage remains counted;
raising a limit does not refund or reset it. These limits are per work item, not a
daily organization budget or a cap on the complete AWS bill.

An assessment's call counter includes the original controller/native admission
counter across its claims. The builder's first native request uses the containing
controller admission; later native requests use additional admissions. Platform
calls use the original `platform_runs` ledger. Duplicate responses do not acquire
a new allowance. General maintenance retains its rolling daily admission cadence;
assessment blocker repairs continue to bypass it.

## Editing policy

Use the JumpServe project, `regphejnlvfpyokpniny`. A Supabase database administrator
can edit the table directly. Existing enrolled Google platform owners can update
only `max_spend_cents`, `max_model_calls` and `change_reason` through the checked
RLS policy. Viewers can read; other Google accounts and anonymous users cannot.
Workers have SELECT access and cannot increase their own budgets. Category
identities cannot be renamed or deleted.

For future policy edits, this administrative operation sets every category to
unlimited. The deployed migration initialized all eight limits to these values:

```sql
update public.autonomy_budget_categories
set max_spend_cents = -1,
    max_model_calls = -1,
    change_reason = 'Operator authorized unlimited budgets for every category';
```

Every insert/update increments a server-owned revision and appends the previous
and current values, actual actor and time to `autonomy_budget_history`. The
history is private and immutable. Private Platform Updates events record policy
changes; the dashboard displays all four current categories. New owner tasks
inherit their category instead of accepting a separate per-task budget override.
The old input remains accepted for older clients but cannot override table policy.

Admissions read current policy inside the original serialized transactions and
retain a shared row lock until admission commits. Active assessment and platform
budget projections synchronize during worker RPCs. Historical completed,
cancelled and expired work retains its recorded limits. For API compatibility,
legacy assessment `max_spend_cents` still uses explicit NULL for unlimited;
configuration in this policy table uses -1. New API responses carry versioned
category authority so prospective zero limits and a cap below already retained
usage do not make historical usage disappear. Older response contracts retain
their existing validation rules.

Only safe budget-stopped work resumes automatically after a policy increase.
Current cancellation, deadlines, leases, scientific criteria, frozen experiment
resource limits, pricing/usage reconciliation and uncertain-call fences still
apply. Unknown calls and unresolved external operations must reconcile under
their original identities. Cost estimates, byte/context limits, concurrency,
per-command timeouts and qualification trial sizes are separate from the category
budgets. An unlimited category never supplies a missing external prerequisite or
turns an inconclusive finding into a successful assessment.

## Qualified activation order

This change spans all three repositories and includes a platform worker update;
it cannot use a general infrastructure-only automatic release.

1. After explicit deployment authorization, publish exact reviewed source and
   pass protected checks. Release the compatible frontend first: it supports both
   existing records and versioned category metadata.
2. Coordinate a safe platform worker boundary and retain its original checkpoint
   and every in-flight action identity. Stage the compatible worker bundle and
   retain the prior pause/release settings. Stop the old platform service only at
   a confirmed safe boundary; do not interrupt or replace uncertain calls.
3. Apply only `database/202610310003_category_budgets.sql`, after migrations
   `202610310001_unlimited_assessment_defaults.sql` and
   `202610310002_assessment_blocker_repairs.sql`, to the verified JumpServe project.
   The migration initializes every category to -1 for both limits. Preserve the
   paused/release controls; do not rerun initial bootstrap or reenroll operators.
   Coordinate compatibility: the old Python controller treats -1 as a finite
   negative number and must not resume production coding after this migration.
   The updated controller understands -1; the database remains authoritative.
4. Qualify the staged compatible bundle on the existing AWS host with the
   unchanged pinned tool image. Keep the old service stopped and enable only the
   designated qualification admission while the fixture runs. The cloud software
   trial still admits at most six calls independently of unlimited production
   budgets. Its narrow task selector cannot consume another queued repair.
   Preserve host fencing and research priority; do not reuse an old whole-bundle
   qualification for changed worker bytes. Install/verify the qualified bundle
   and restore the prior admission setting. A failed qualification retains its
   original evidence and prior pause state rather than restarting old coding
   against the new -1 policy.
5. Qualify/publish the research controller code under its dedicated runtime
   procedure, including the new `budget_policy.py` file. Bind the runtime manifest
   to the exact released source; do not alter frozen experiment executors or
   scientific prompt criteria. Enable `RESEARCH_CATEGORY_BUDGETS_ENABLED=true` on
   the API and assessment worker only with the compatible controller. The CDK
   changes include this flag and a truthful description; they need a dedicated
   reviewed configuration/code release, not the older code-only default adapter.
   The source-qualified `bin/category-budgets-runtime-release.py` provides fixed
   `prepare`, `deploy` and `verify` actions for this release. Its renderer starts
   from the actual deployed template and retains all experiment code, versions,
   roles, parameters, outputs and other settings. The general release guard and
   historical defaults profile are unchanged.
6. Verify actual installed function sources, RLS/ACLs, all eight -1 limit values,
   refreshed worker leases, retained counters/deadlines and current dashboard
   responses. Record source revisions and production receipts in private Platform
   Updates. A successful merge is not an activation or a completed repair.

The existing refreshable AWS roles and Google owner identities are preserved. No
new human login is needed for ongoing budget reads or future table edits. The
connected Supabase tool's project must be checked before use; a connection to a
different project is not an acceptable transport.

## Local verification

`python3 -B test/check_category_budgets_database.py` runs the prior optional and
unlimited assessment funding regressions, then the actual new migration, RLS,
audit, live policy changes, fenced platform and assessment admissions, automatic
budget resumption, immutable request replay and unknown-call preservation. The
existing fixed loopback PostgreSQL transport is retained. Authentication and
Storage in this test are synthetic; no provider or production calls are made.

Backend policy/controller tests cover unlimited, zero, finite and malformed
limits, current defaults and versioned authority. The frontend checks include
legacy compatibility, category metadata and unlimited formatting. Browser
fixtures use the real component and built CSS on desktop/mobile in both themes,
with synthetic authentication/API/Realtime boundaries. Qualification's six-call
guard is tested independently of production budgets. The separate production record reports actual cloud qualification and activation;
these local tests alone do not establish either.
