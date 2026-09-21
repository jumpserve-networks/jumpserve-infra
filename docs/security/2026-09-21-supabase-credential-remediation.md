# Supabase credential exposure remediation

Vishal Misra reported a public service-role JWT in two emulated benchmark
runners on 18 September 2026. Remediation was performed on 21 September 2026.
No credential values are recorded here.

## Containment and credential revocation

- Paused new emulated launches while changing credentials. No emulated runner
  instances were active in the launch region when containment began.
- Created dedicated modern publishable and secret keys. Updated Secrets Manager,
  all JumpServe Lambda credential consumers, local frontend configuration, CDK
  public configuration, and the Amplify app and branch environments. Amplify
  build 87 succeeded with the replacement public key.
- Disabled legacy API keys. Verification found that the old service-role JWT
  still worked as a bearer token with a modern publishable API key.
- Migrated authentication signing to ES256 and revoked the legacy JWT signing
  key. Subsequent read-only probes returned HTTP 401 for both the legacy API
  key and the legacy bearer token. Replacement-key probes returned HTTP 200.
- Existing user access tokens signed by the revoked key must refresh; some
  users may need to sign in again. The exposed credential remains in Git
  history but is invalid; repository history was not rewritten.

## Runner and ingestion changes

Removed hardcoded service-role defaults and secret command-line arguments.
Trusted local runners read their credential only from the environment and fail
before test setup if persistence is unconfigured. EC2 instead uses a random,
expiring capability scoped to one job. Its hash is private to the backend.

The ingestion RPC validates the job and configuration, rejects foreign run IDs,
inserts the report atomically, and links the actual parent run. Exact retries
return the committed IDs; changed retries and terminal-job updates fail. Tokens
cannot read tables, mutate other jobs, or invoke arbitrary database operations.
The EC2 role explicitly denies Secrets Manager reads; user data has no database
credential. Incompatible prebuilt images fail the ingestion-client check.

The first live verification used a fresh base-image t3.medium instance. Job
`e1447aea-d0f7-4828-9efb-a729f76e893f` saved parent run **2353**, two client rows,
and measurement samples. The verification data is tagged `verification` and
should be excluded from research cohorts. Fresh user data was inspected without
printing its capability and contained no Supabase credential.

## Database and activity review

RLS was already enabled on all 21 public and 8 storage tables. The new private
ingestion-token table also has RLS enabled. Unnecessary TRUNCATE, REFERENCES,
and TRIGGER privileges were removed from browser roles on sessions,
configurations and jobs; RLS does not restrict TRUNCATE.

Anonymous REST checks across all 22 public tables confirmed the intended split:
public measurements/status history can be read, while private application data
and ingestion capabilities cannot. The safe public benchmark-job column
projection also remains readable.

Seven daily windows of aggregate API activity were reviewed. Observed writes
used test, reporting, authentication and prompt-management paths. There were no
relational-table DELETE requests. One Storage DELETE request appeared for the
real-world-results bucket. Aggregate logs do not establish its actor or payload.
This review cannot rule out unauthorized reads, writes using a shared credential,
direct database activity, or activity outside the available review window.

## Verification

- Backend persistence/metrics suite: 12 tests, one existing Linux-only skip on macOS.
- Infrastructure Jest suite: 74 passed, including real runner CLI contracts.
- Existing Python analysis/AMI suite: 51 passed.
- Dedicated PostgreSQL ingestion, public/private access, and prompt tests passed.
- Production migration verifies RLS and RPC/table grants before committing.
- Production probes confirmed legacy credential rejection and modern-key access.

Operational scripts in `scripts/` have fixed JumpServe scope and avoid printing
credentials. Private temporary AWS parameter files are removed after use. Tests
use an isolated PostgreSQL database and roll back their fixtures.
