# Dependency-aware claim evaluation: implementation protocol v1

Frozen before implementation on 2026-10-07. This is a software development
protocol, not a prospective scientific registration. Reviewer: primary Codex AI,
implementer, not independent. Cases below are development regressions; no held-out
or human review is asserted. Earlier workflow protocols/results remain preserved.

Claims are tracking units; campaigns are execution units. One job can serve several
claims through applicable claim checks. Execution completion never changes claim
labels. Source review, theory, standards and unavailable empirical dependencies
remain explicit manual tasks; only the registered numerical adapter runs here.

## Questions and acceptance criteria

- Can durable jobs execute concurrently without duplicate claims, exceeding global
  four/study two slots or overlapping declared exclusive resources?
- Can prerequisites require either a complete recorded run or reviewed evidence,
  without confusing numerical discrepancy with software failure?
- Are originals hash-verified, protocols immutable, owners isolated, attempts and
  cancellation/failure/expired leases preserved, with browser writes denied?
- Can owners see every claim's work and its separate scientific assessment, queue
  dependencies, blocked reasons, limits and immutable event history?

Release-blocking: backend regressions including actual worker overlap; isolated
Postgres multi-client concurrency, authorization, RLS, immutable job definitions
and events, missing prerequisites, review gate, cancellation and expired lease
fencing; frontend tests/lint/build, desktop/mobile queue states and navigation;
CDK bounded worker resources, schedule and IAM; exact runtime byte manifest.
Conditional: real Google-owner queue request, remote Supabase Storage round trip,
deployed scheduled workers and end-to-end production checks. No deployment is
authorized on this editing turn. No generic AI evaluator is enabled.

## Fixed configuration and limits

Postgres 17 local isolated test databases; Python stdlib adapters; existing Next.js
16.1.6/React 19.2.3 and pinned Playwright 1.62.1. Worker poll every minute, two
threads per invocation, two reserved Lambda invocations, global maximum four jobs,
study maximum two, 180-second hosting deadline, 600-second lease. At most two jobs
claimed per poll; no experiment retry on failure or expired lease. Follow-ups use
new job IDs with previous-job rationale. Queue maximum 1,000 jobs per study,
256 KB original inputs, 1,000 observations, 10-second numerical algorithm limit.
Job definitions/dependencies cannot be rewritten. Existing-job-only dependencies
make cycles impossible; successors wait for explicitly selected completion criteria.
All recorded dependency observations may share evidence; parallelism does not
establish statistical or reviewer independence. Protocols retain sampling units,
multiple-testing decisions, prior exposure and stopping rules.

## Validation and reporting

Synthetic fixtures include exact agreement, scientific discrepancy, missing/invalid
observations, execution failure, manual tasks, shared resources, dependencies,
review acceptance, cancellation and lease expiry. One successful case per distinct
invariant, with repeated clients for concurrency races; these counts establish
software behavior only, not statistical power or empirical replication. Test
failures remain recorded; fixes amend implementation without rewriting this file.
Report actual checks and timings when available, costs/peak memory as missing when
unavailable. Retain earlier reports. Stop verification after blockers pass unless
new failures or implementation changes justify further checks.
