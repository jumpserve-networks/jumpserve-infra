# Native experiment builder

This change adds an implementation-development stage to the existing autonomous
assessment controller. It is local and disabled by default. It has not been
deployed or evaluated with a live subscription model. No existing assessment is
automatically resumed by the migrations.

The operator's standing experiment authority is versioned separately in
`policies/experiment-action-policy-v1.json`. It covers necessary setup, retrieval,
installation, coding, compilation, debugging, supported provisioning, measurements
and cleanup within the assessment scope. Routine actions do not require another
user permission request. General commands and applicable programs are supported;
the policy does not restrict experiments to a named script or package catalog.

Planning and fresh reviews receive that authority alongside actual runner
contracts. The exact policy instruction and original-byte SHA256 are recorded in
builder requests. The worker verifies a supplied controller policy identity,
retains the original policy bytes with the runtime artifacts, and includes the
policy version/hash in its receipt. Source instructions cannot amend the grant.
Policy authority is distinct from available implementation and operational
readiness: unsupported capabilities remain implementation/resource gaps, rather
than requests to approve already-authorized routine actions. Cloud provisioning
uses the reviewed executor, so missing deployment or cost qualification is not
waived by this authority. Existing limits and the separate release requirement
remain in force.

When planning cannot find an implementation or required data, the controller can
enter `building`. Native OpenClaw 2026.10.5 uses read/write/edit/exec/process tools
in a per-claim Linux Docker container. It can retrieve accessible resources,
install tools, write code and run small development checks. Every Responses API
request is stored and admitted before inference. Native reasoning, function call
identities and tool results pass through without a chat-completions conversion.
The historical data-only runtime remains separate.

A scheduling slot is 60 seconds, not a turn ceiling. Its source checkpoint is
saved in private Storage and verified after retrieval. The stopped container's
writable filesystem retains installations between slots; stopping releases CPU
and memory. A worker restart can restore source from Storage. If the local
environment is lost, dependency locks permit rebuilding it; this does not reset
paper limits or erase failures. Terminal claims and paper stops retire their
container through a worker cleanup pass. Unknown provider or persistence outcomes
remain fenced until reconciliation. Only confirmed transient runtime failures
use the existing bounded backoff policy.

The builder cannot supply its own artifact identifiers. The server freezes the
original project ZIP, manifest and wrapper, derives the compiled candidate, and
registers an immutable source-specific package version. The source catalog is a
reuse aid; a candidate is not a validated capability. Other claims must examine
applicability and retain their own scientific criteria. Existing shared-campaign
coordination can reuse exactly matching acquisitions; shared observations never
become independent replications.

The Python entrypoint can orchestrate additional installed tools. Pip dependencies
need exact versions and SHA256 hashes; apt packages need exact versions. Project
sources are UTF-8, with 64 files, 1 MB expanded and 256 KB compressed limits.
Working checkpoints have a 128-file / 4 MB bound. Larger inputs remain explicit
dependencies. Archives reject traversal, duplicate paths, symlinks and oversized
members. Dependency environments belong outside the source workspace. The clean
executor reinstalls locks rather than inheriting the builder environment.

Fresh comprehension and critic calls inspect the protocol and original source
code before experiment admission. Large documents have hash-bound, paginated
readers with explicit delivery gates. Delivery is not proof of understanding or
independent scientific review. Review failures return actionable feedback to the
retained builder. A typed `blocker.json` pauses work for missing external inputs;
the builder does not spend indefinitely pretending equipment or data exist.

The `built-package-v1` executor uses the existing disposable credential-free EC2
package path: one t3.medium, standard credits, 8-GiB root, at most 1800 seconds,
3 MB returned output and 10 decimal GB sampled traffic. The independent reaper
and watchdog remain active. The new path has its own immutable function version
and server-owned policy; arbitrary custom-package admission stays separate.

The draft cost envelope proposes a $10 reservation per execution and has
`approved_for_lab_execution=false`; it refuses automatic cloud admission until
the operator retains operational validation and approves a versioned server
policy. This is a release-level check, not a per-paper user permission request.
Paper commitments remain
$100 and seven elapsed days, with no model-turn ceiling. The containing builder
turn reserves $1 for its first provider call; each additional native call reserves
$1. These are conservative commitments, not measured provider charges. Guest
traffic/output enforcement is sampled and can overshoot. This lab policy is not
adversarial metering or a guaranteed AWS invoice cap. Subscription allocation,
unallocated costs and unavailable charges remain unknown.

`/research-verification/experiment-queue?assessment=<id>` shows the building stage,
numbered native calls and bounded prompt/response fragments, including tool
history. Public reads use the existing protected-value projection; database
relations and original artifacts remain service-only. Reads never authorize
execution. Equipment, inaccessible data, unavailable kernel/hardware capabilities,
larger topologies and unsupported scientific decision rules can still leave
claims unresolved. Building/running code does not guarantee a conclusive finding.

## Local verification

The frozen protocols are `experiment-builder-validation-v1.json` and
`experiment-builder-live-evaluation-v1.json`. Local native tests use a synthetic
Responses transport and the real pinned OpenClaw/Node runtime and Linux Docker.
They are exposed development regressions, not held-out AI or paper validation.

```bash
# jumpserve-back-end
python3 -B -m unittest discover -s research_workflow/tests -p 'test_*.py'
python3 -B research_workflow/tests/check_experiment_builder_linux.py
python3 -B research_workflow/tests/check_generated_package_linux.py

# jumpserve-infra, with the isolated local Postgres fixture running
npm run test:research:builder
npm run test:research:autonomy
npm run test:research:executable-methods
npm run build
npm test -- --runInBand test/network-execution.test.ts test/research-workflow.test.ts

# jumpserve-front-end
npm test
npm run lint
npm run build
npm run verify:research:public-queue
```

The browser campaign builds an explicitly synthetic local API configuration.
Rebuild with the intended environment before using a subsequent production build.
Reports and original failed attempts remain under each repository's ignored
`.test-artifacts` directory. The lab test image's availability does not establish
production image availability or x86/ARM equivalence.

## Release conditions

The user must explicitly request release. Verify AWS account `395567831870` and
Supabase project `regphejnlvfpyokpniny` first. The connected Supabase MCP may
target a different project; it must not be used for these migrations.

1. Replay migrations `202610270001` through `202610270004` after the
   existing executable-methods migration. Keep the builder prompt unpublished.
2. Build/review a Linux image from the backend's `experiment-builder.Dockerfile`
   using a verified Ubuntu 22.04 base digest. Retain platform, image digest,
   Dockerfile, build logs and installed-package inventory. Check equivalence to
   the disposable executor's OS/architecture; do not substitute the local ARM
   smoke image as proof of production compatibility.
3. Through the existing audited SSM release path, explicitly run
   `bin/prepare-experiment-builder-host.sh` with that digest. It verifies the AWS
   account, installs Docker and sets the worker image. It does not replace the
   authorized host or activate paper admission. Restart/health-check the worker
   through the normal release process, retaining its separate ChatGPT grant.
4. Verify filesystem/exec host restrictions, source/lock installation, stopped
   container resume/retirement, actual cloud execution, ingestion and independent
   deadline cleanup. Review the current cost policy and guest egress behavior.
   Keep admission off if those operational checks fail.
5. Run the separately declared bounded live AI evaluation, including
   `experiment-action-policy-live-amendment-v1.json`. Publication requires the
   exact operator-policy hash and actual-answer judgments for routine autonomy
   and capability honesty; these development judgments do not replace the
   original checks or count as independent validation. Select and hash its
   two held-out inputs before candidate evaluation; reused/tuned inputs lose
   held-out status. Retain failed reports, actual answers, prompts, tool outputs,
   usage/cost availability and evaluator/reviewer identities and independence.
   Local synthetic tests cannot satisfy the publication RPC.
6. Publish only a passing prompt using the existing prompt/evaluation tables and
   guarded publication function. Then explicitly enable
   `researchExperimentBuilderEnabled=true` with OpenClaw and networking execution
   enabled. The function and policy hashes are passed separately from the
   arbitrary custom-package switch. Verify the deployed authenticated flow and
   public desktop/mobile status before reporting production readiness.

This is a lab runner. It is not a completed public multi-tenant execution service.
Host credentials stay outside generated-code containers, but a separate hardened
provisioning and metering design is required before exposing arbitrary workloads
to untrusted public users.
