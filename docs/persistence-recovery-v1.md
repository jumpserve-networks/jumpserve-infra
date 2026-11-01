# Persistence load reduction and independent monitoring

On 2026-11-01, production Supabase database connections timed out from both
the Management API and the AWS worker. Project service health reported the
database, REST, auth and storage unhealthy. The dashboard showed Nano compute
depleting its disk I/O budget. After the owner's Medium upgrade, all service
checks recovered and fresh dispatches completed. This supports resource
pressure as the incident mechanism; the exact historical I/O balance was not
available during the outage.

## Polling changes

- An idle research worker backs off claims through 1, 2, 4, 8 and 10 seconds.
  A claimed job resets the delay; the other slot can fill on the next loop.
- Research heartbeats run immediately on startup and every ten seconds, within
  the existing 30-second database freshness window.
- Model status reads back off through 2, 4 and 5 seconds. Transient read failures
  use a separate 2–10-second backoff. Sleeps cannot extend the original turn's
  elapsed-time deadline. Admission and provider transport are never retried.
- Research loop failures back off to 30 seconds; failed retained-result recovery
  backs off from 30 seconds to five minutes on its separate executor. Captured
  completions, task locks, unknown outcomes and cleanup requirements stay intact.
- The platform worker still checks for tasks every 15 seconds. New assessment
  blockers still enter through the existing database triggers immediately.
  Optional maintenance and unchanged-evidence rechecks run once per minute.
  Persistence failures back off to two minutes.
- Migration `202611010005_dispatch_status_projection.sql` projects only the
  existing result fields before JSON conversion. It avoids deserializing the
  original request just to remove it. Every other operation delegates to the
  unchanged private implementation. Browser grants and scientific guards stay
  unchanged. Actual PostgreSQL regression compares every retained fixture's
  response and verifies original ledgers, deadlines, budgets and access rights.

These are operational delays, not new research budgets. Existing `-1` category
limits, aggregate funding authorization, original deadlines, cancellation and
uncertain-call fences are retained.

## Independent AWS monitor

`JumpServeObservabilityStack` is a separate stack in account `395567831870`,
region `us-east-1`. It does not modify either worker, supervisor authority or
existing application stacks. Its Lambda makes one bounded, fixed-project,
read-only PostgREST query per minute. It runs outside the worker host and does
not depend on Supabase for storing its own telemetry or incident records.

The role can read only the existing Supabase service-key secret, publish metrics
in `JumpServe/Persistence`, and write its own logs. The handler has no write
request path, inference, release or restart operation. It refuses redirects,
has a five-second HTTP timeout and a 4-KB response limit, and logs only fixed
status metadata. AWS credentials come from the Lambda role. No Management API
token or subscription grant is copied.

- `JumpServe-Supabase-Unavailable`: three failed or missing one-minute probes;
  creates a critical availability OpsItem in Systems Manager OpsCenter. Missing
  telemetry is breaching so a stopped schedule or failed monitor is visible.
- `JumpServe-Supabase-Slow`: latency above two seconds in three of five minutes;
  creates a performance OpsItem.
- `JumpServe-Persistence`: CloudWatch dashboard with alarms and probe metrics.

CloudWatch creates the required service-linked OpsCenter action role when the
alarms are provisioned. Verify that role and alarm action history at release.
The probe uses unreserved Lambda concurrency: the initial production deployment
showed that this account's entire concurrency quota is the minimum unreserved
pool (10), so even a reservation of one prevents function creation. The once-per-
minute schedule, 20-second timeout and disabled retries bound ordinary probe
activity. If account-wide throttling prevents telemetry, the missing-data alarm
still creates an AWS incident. Existing research concurrency is unchanged.
Incidents are retained in AWS; email/SMS subscriptions are not configured.
The monitor deliberately cannot restart the database or replay work.

This is an availability and latency monitor, not direct disk-burst-balance
telemetry. Use Supabase Observability for disk I/O balance, memory, swap and
cache hit rate. Review query-counter deltas over the same statistics reset
interval. Cumulative counters do not reconstruct the outage's historical load.

## Verification and release

Local checks:

```sh
# In jumpserve-back-end:
python3 -B -m unittest discover -s research_workflow/tests -v
python3 -B -m unittest discover -s platform_supervisor/tests -v
# In jumpserve-infra, with the existing isolated local PostgreSQL test server:
python3 -B test/check_persistence_polling_database.py
python3 -B -m unittest discover -s test -p persistence_monitor_test.py -v
npm test -- --runInBand
npm run build
npm run cdk:observability -- synth --no-lookups
```

Use the existing explicitly authorized runtime release process for the backend
and platform bundles, including exact source hashes, qualification, bounded
maintenance hold and safe drain. The production runtime manifest and existing
approval certificate must not be relabeled as qualifying these new bytes.
Apply the projection migration before activating the compatible runtime. Deploy
the separate observability stack through its `cdk:observability` entry point.
No frontend release is required.

After an explicitly requested release, verify the exact installed source hashes,
the fixed database projection and access rights, actual probe invocation,
published CloudWatch points, both alarm actions and dashboard. A missing or
failed probe must produce an AWS alarm/incident during a bounded monitor-only
qualification without disrupting production Supabase. Restore the original
monitor settings and verify fresh successful points afterward.

Observe fresh worker heartbeats, completed dispatches, query latency, connection
waits, memory/swap and disk I/O balance before increasing admitted work. Resume
only already authorized, unexpired work through existing controls. Do not reset
deadlines, grant a replacement identity to an unknown call, or describe a ready
worker as a completed assessment. In the initial Medium verification the workers
were already unpaused and resumed automatically; no forced wake or restart was
needed. Assessment `444d171c-2fac-4ba9-b33c-2b46304cb0ec` still had a separate
retained incomplete native stream; that task correctly stayed waiting.

Sources: [Supabase disk I/O guidance](https://supabase.com/kb/troubleshooting/exhaust-disk-io),
[compute limits](https://supabase.com/docs/guides/platform/compute-and-disk),
[CloudWatch OpsCenter actions](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter-create-OpsItems-from-CloudWatch-Alarms.html).
