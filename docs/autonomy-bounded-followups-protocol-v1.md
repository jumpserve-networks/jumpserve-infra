# Bounded follow-up implementation and verification protocol v1

Frozen 2026-10-19 before the new verification campaign. This extends, and does
not replace, the earlier production protocols and their failed results.

## Questions and criteria

1. Can planning after the retained IPv6 single-figure check stay below the
   unchanged 96,000-byte application request ceiling, without deleting evidence?
2. Can complete matched-data calculations and claim coverage span more than
   1,000 records, preserving exact decimals, identifiers and missing states?
3. Can a registered networking experiment reserve its cost automatically and
   enforce its resource limits independently of an AI answer?

Development checks must cover all six retained IPv6 checks, follow-up after a
192-record check, at least 1,152 accumulated observations, earlier discrepancies,
invalid/missing observations, exact source/configuration matching, prompt
injection, unauthorized evidence IDs, pagination boundaries and oversized rows.
The decision rule stays the frozen matched-cell tolerance; no inferential
interval or causal/generalization conclusion is introduced. A claim's required
checks are inventoried before execution; partial checks can accumulate coverage
but cannot silently become a whole-claim conclusion.

The first bounded networking runner will make real TCP exchanges on loopback
with a controlled application delay. This is a host-local emulated experiment,
not Internet/CDN evidence or kernel netem. Its immutable implementation accepts
only numeric configuration, opens no remote destinations, creates no EC2
resources, and is isolated in a separate Lambda with a hard timeout, fixed
memory, bounded payload/count/output and no cloud API credentials granted to
the experiment role. All sockets close on success/failure; Lambda timeout is
the independent execution watchdog. Existing EC2/custom-package runners remain
ineligible for autonomous spending until their own enforceable policies exist.

## Sampling, resources and exclusions

Functional tests are deterministic development regressions, not independent
scientific replications. Local TCP timings are measured values with descriptive
summaries only; adjacent exchanges share one process and are not independent
replications. No confidence interval is justified by this check.

Run the existing backend tests, actual local Postgres control/security checks,
infrastructure synthesis/assertions and applicable frontend checks. Freeze any
live model cases before calling a provider; no more than 8 calls and $5 in
conservative model reservations in this campaign. Missing credentials are a
conditional verification gap, not a passing live evaluation. All tuned cases
remain development cases; primary Codex review is AI and not independent/human.

No production mutation, deployment, paper-limit reset or existing experiment
relaunch is part of this local implementation campaign. A cloud deployment and
authenticated production experiment require a subsequent release instruction.
Before any cloud/database mutation verify account 395567831870 and Supabase
regphejnlvfpyokpniny. Record known usage separately from estimates and missing
invoice charges. Failed/excluded checks remain in the validation report.

## Release blockers

- No silent prompt/data truncation, no unknown-cost admission or budget bypass.
- No conclusive label without the original frozen claim coverage and criterion.
- No repeated uncertain provider call or experiment launch.
- Atomic parallel reservations; a timeout/cancellation cannot create orphan
  billable experiment machines. New runner has zero such machines by design.
- Candidate prompt remains unpublished until its declared live answer and
  integration checks pass; local fixtures do not establish live model accuracy.
- Original artifacts, prompts and migration history remain immutable/private.

## Conditional release verification

Verify deployed Lambda configuration/code identity, a real cloud loopback run,
stored original/parsed hashes, authenticated queue rendering and cleanup after
deployment. Local socket and CDK tests cannot establish these cloud properties.
