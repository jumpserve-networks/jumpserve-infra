# Local assessment architecture and hosted retirement

The owner selected this architecture on 2026-11-20 and authorized shutdown of
currently active work:

Claude/Codex + skill → local assessment and experiments → optional JumpServe
MCP sharing → public results.

The skill package is independently installable without a JumpServe checkout
or operator credentials. The Next.js `/mcp` route stages an assessment preview,
requires JumpServe account-owner approval in the browser, and submits the
approved bundle to Supabase. Original PDFs, raw logs, and model work belong to
the local workflow. Apply `202611210001_jumpserve_mcp_assessments.sql` before
enabling the route with `JUMPSERVE_MCP_ENABLED=true`. Publishing the skill and
enabling the live route are separate release steps.

## Retired services

- Dedicated paper-intake and OpenClaw/supervisor hosts, their instance profiles,
  dedicated security groups and automatic platform-release roles.
- The frontend paper continuation Lambda and minute schedule.
- Research autonomy, queue and networking-package workers, schedules, invocation
  permissions, PDF layer and package-only network.
- Legacy research POST routes and service-role execution grants for the eight
  Next.js hosted admission/control RPCs.

`cdk.json` selects `localAssessmentsOnly` and disables every hosted research
execution flag. The retired host/access entrypoints reject that mode. The
frontend credential role/secret are retained because existing assessment reads
still use their server-only Supabase connection. The Next.js MCP route can
also resolve its server-only Supabase credential through the retained secret.

## Retained services and evidence

Supabase tables, original private artifacts, RLS, authentication, assessment
identities, source hashes, scientific criteria, historical provider outcomes and
public assessment URLs remain intact. Recovery snapshots and historical AWS logs
remain private. Original stopped-host disks are retained during decommissioning;
they are not experiment results and must not become public skill assets.

The website and read API continue serving assessments and existing measurement
modules. Module chat, DNS and hosting serve independent product features and are retained.
The owner subsequently retired cloud benchmark execution, legacy AWS backups,
old deployment assets and custom monitoring; see `cloud-benchmark-retirement-v1.md`.
They are not required dependencies of the public assessment skill.

The named platform supervisor is paused, automatic releases disabled and unfinished
tasks receive cancellation requests. Original unknown actions remain unknown;
cancellation does not fabricate reconciliation or undo an existing merge.
Historical standing authorization records are preserved, not used to recreate
the retired service.

## Fixed retirement procedure

`bin/retire-hosted-assessments.py` is restricted to the existing AWS account and
named stacks. Inventory, templates, change plans, exact change-set identities and
execution receipts are saved privately under
`.test-artifacts/hosted-assessment-retirement-20261120`.

The procedure freezes admissions, stops the two hosts, snapshots their encrypted
disks, renders removals against the deployed templates and checks every actual
CloudFormation change before execution. Nonretired resources remain identical;
existing resolved SSM values become literal pins to prevent incidental upgrades.
Historical log groups require `DeletionPolicy: Retain`. The only direct retained
resource changes are the research API environment and removal of its worker
invocation policy. CloudFormation's derived permission/integration changes are
accepted only when their templates are identical and the API ARN cannot change.

Dedicated stacks are removed in dependency order: intake, platform access,
OpenClaw. Host removal requires stopped instances, retained original disks and
encrypted recovery snapshots. The procedure does not delete Supabase records or
claim a model review or an experiment finding.

Verify all enabled AWS regions for remaining experiment instances, removed worker
resources and schedules, completed stack operations, retained logs and the public
assessment pages. Record results in the private release receipts. A submitted
deletion or a passing unit test is not evidence of a completed production change.
