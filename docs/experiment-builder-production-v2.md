# Builder v2 production release — 2026-10-27/28 UTC

The general OpenClaw experiment builder is enabled at
https://jumpserve.quaint-lab.org. Assessment admission and both polling rules are
enabled. The existing worker `i-087f1493809643115` and its native ChatGPT grant were
preserved; actual subscription refresh and the model catalog passed. No API-key
or Bedrock fallback was added.

The backend was fast-forwarded and pushed to main at
`f5453c866bfd74e770398fd6adfebae3265b01c6`. The infrastructure qualification and
explicit activation context were merged and pushed. Deployable CDK inputs were
committed before deployment; verification-only helpers were corrected during the
release and committed afterward. There was no frontend source change or Amplify
build in this release.

## What was deployed and checked

* Runtime manifest 53: all 49 original file hashes match the deployed API, queue
  worker, autonomous controller and existing inference host. The API/controller
  are enabled for OpenClaw and the builder. The queue receives the immutable
  execution target and exact reviewed cost-policy hash. Arbitrary submitted
  custom packages remain disabled.
* Prompt `research-experiment-builder-v2` was published through the guarded RPC
  after migration `202610270007`. Its exact qualified report is
  `54be72374de3326592a63dbd9e008064710d6e4e9f7cf3d6143c37dcd067dd37`.
  The existing autonomy v10 prompt is unchanged. Original failed evaluations and
  publication history are preserved.
* The exact qualified x86 Docker image and a permanent separate, hash-bound vendor
  correction are installed. The upstream package and credentials were retained.
  Native write/edit/exec/sudo/read/resume checks passed under matching production
  systemd restrictions, with **eight synthetic transport calls and zero actual
  provider calls**. This checks real tools and Docker, not production SQL admission
  or a Google-authenticated request.
* Forty-two research relations retain the declared RLS/read classifications;
  27 are private. Browser writes are denied, eight service-only RPCs are denied
  to browser roles, and the original-artifact bucket remains private.
* The new executor Lambda version is `5`. Its full ZIP changed because the shared
  runtime bundle changed. Independently retrieved before/after ZIPs show unchanged
  `network_package.py`, `store.py`, `workflow.py`, `network_spec.py`,
  `package_runtime.py`, `generated_package.py` and `netem_iperf.py`. The pinned
  experiment AMI remains `ami-033ea4ff4a9c726dc`. Three earlier cloud lifecycle
  controls are reused on that stated basis; no new experiment VM was launched.
  Benchmark parameters and the existing worker identity were checked unchanged.
* Infrastructure build and 92 fresh Jest checks passed. Five optional CLI checks,
  311 backend tests and local builder/autonomy database fixtures were reused from
  the exact reviewed source. No model qualification was rerun: the existing 73-call
  campaign passes ten functional checks and two derived authority judgments after
  its retained runtime-feedback correction. These are not independent/human reviews
  or arbitrary-paper validation.

The lab cost policy reserves $10 per supported execution within the original
$100/seven-day paper defaults, with no AI-turn ceiling. Its approval expires
November 26, 2026. Reservations and price estimates are not measured charges or
guaranteed invoice ceilings. Shared worker, storage, deployment and subscription
allocations remain unknown. This release used zero new inference calls and zero
new experiment EC2 instances.

## Retained release failures and corrections

1. A benchmark diff collided with the worker deployment's `cdk.out` lock. The
   failed receipt was retained and the diff succeeded when run sequentially.
2. Native tool checks passed, but initial evidence packaging included compile
   caches/state and exceeded 20 MB. A fixed allowlist recovered the completed
   control's inputs, original requests/responses, outputs and receipts. The
   control was not executed again; original failure and excluded-file inventory
   are retained. Auth/config/state contents were excluded from the final archive.
3. A historical verifier expected browser-readable confirmation tables. Migration
   `202610230002` explicitly made those two tables private. The verifier was
   corrected; database permissions were not relaxed.
4. The manual polling hold survived activation because CloudFormation already
   declared the rule enabled and did not repair the drift. The fixed release
   helper explicitly enabled the exact held rule and checked its live state.
   Final verification confirms both autonomous and queue polling enabled.
5. The first final-audit insert used an unsupported outcome label. The existing
   evaluation schema accepts `passed`, `failed-substantive-review` and
   `failed-or-paused`; it was not relaxed. The corrected writer uses `passed` for
   the enumerated release checks, while the report explicitly identifies
   operational verification and the remaining authenticated-flow condition. The
   failed insert and already-verified original archive remain retained.

These are software/release-control findings. They are not scientific discrepancies.

## Public UI and remaining conditions

Native Chrome/Firefox checks covered the four-paper catalog, retained unresolved
queue details, explicit unavailable-assessment state, module navigation, themes
and the sign-in return path. Mobile views used 390×844 CSS pixels. Original light
catalog and dark methods PNGs were copied unchanged from native browser screenshot
downloads and hash-verified. Firefox desktop layout was visually inspected; exact
desktop CSS dimensions were not recorded. Initial viewport/zoom setup was corrected
before visual judgments. Concurrent Chrome activity interrupted further controls;
remaining checks were completed in a separate Firefox window.

Available browser contexts were logged out. **A real authenticated PDF upload,
confirmation, planning, builder execution and storage flow remains unverified in
this rollout.** No Google identity or user session was fabricated, and the native
software control is not represented as that request. Authenticated chat was not
exercised. Console errors, charts and data exports were not exhaustively audited;
frontend code was unchanged. These are explicitly conditional verification gaps.

No historical assessment was restarted or scientifically relabeled. Existing
unresolved claims retain their original findings and reasons. Future assessments
can use the builder; missing equipment/data and unsupported conditions may still
prevent a conclusive scientific finding.

## Evidence and commands

The [predeclared release protocol](experiment-builder-production-v2-protocol.json),
[machine-readable status](experiment-builder-production-v2-status.json),
[qualification inventory](experiment-builder-qualification-artifacts-v2.json) and
`experiment-builder-production-v2-artifacts.json` bind the retained evidence.
Original deployed ZIPs, successful/failed receipts, scoped diffs/deployment logs,
before/after parameter records, native control bytes and browser PNGs are retained
in private Supabase Storage with retrieval verification. Operational verification
is separately recorded in the existing prompt-evaluation table. It is not another
model-answer qualification or another set of 73 provider calls.

```bash
# Read-only production checks: verified fixed AWS/Supabase targets
python3 -B bin/verify-builder-v2-release.py activated
python3 -B bin/verify-builder-v2-release.py executor

# Existing completed controls are retrieved, never replayed implicitly
python3 -B bin/verify-builder-v2-release.py collect-native
```

Evaluator and reviewer: the same Codex AI implementation author, nonindependent.
No human review or new paper-claim assessment is claimed.
