# JumpServe Infrastructure

AWS CDK infrastructure for the JumpServe frontend, benchmark API and AI tools.
No EC2 instance needs to run continuously for benchmarks.

## Architecture

- Amplify hosts the Next.js frontend at https://jumpserve.quaint-lab.org.
- API Gateway and Lambda launch disposable EC2 machines for each test module.
- Each instance boots a verified AMI, saves results to Supabase, streams logs to
  CloudWatch and terminates automatically after success or failure.
- Backend deployments briefly create an AMI builder and verification instances.
- The agent stack provides the AI tools independently of benchmark compute.

AWS account: `395567831870`; region: `us-east-1`.
The legacy `JumpServeEc2Stack` is removed from the CDK app so `deploy --all` cannot
recreate the permanent server, Elastic IP or SSH access.

## Real-world congestion-control tests

`lib/real-world-tests.ts` adds authenticated `/real-world/*` endpoints to the
existing benchmark API, a Step Functions lifecycle, DynamoDB job/configuration
storage, private versioned S3 reports, and an independent five-minute reaper.
Both evidence stores use retain policies. The real-world EC2 role has SSM access
only; it has no Supabase service key. Worker mutations and terminations target
resources tagged `Project=JumpServeRealWorld`.

Each test creates its own VPC/network resources in the selected Regions and a
fresh server, bottleneck, and 1–16 receivers. WireGuard forces test TCP/ACKs
through the bottleneck. Machine placement uses the live AWS Region/AZ/type
catalog and supports compatible enabled Local Zones. Unavailable/opt-in zones
are explained; Wavelength networking and other AWS partitions are not silently
substituted. CCAs are stock Linux CUBIC/BBR/Reno. Resources are removed on success,
failure, or cancellation; status remains `cleaning` until removal is confirmed.
There is a 45-minute job deadline and independent 60-minute instance shutdown.

The runtime belongs to `jumpserve-back-end/real_world`. `real-world-runtime.json`
pins its Git revision; CI checks out that exact commit into `.runtime-backend`
and tests it before synthesis. For local builds/tests/synthesis, use:

```bash
export REAL_WORLD_RUNTIME_PATH=/path/to/jumpserve-back-end/real_world
npm run build
npm test -- --runInBand
```

For deployments, use the pinned checkout, update the revision when changing the
runtime, and deploy the benchmark stack before publishing the frontend module.
No new frontend environment variable is needed. A deployment provisions the
control plane only; EC2 machines are allocated by individual test requests.
The backend's `real_world/README.md` documents routing, lifecycle, units,
authentication, costs, and evidence limitations in detail.

## Running Benchmarks

Ephemeral benchmarks launched through the API shut down after either success or
failure. Instances use `InstanceInitiatedShutdownBehavior=terminate`, so the
bootstrap's exit trap terminates the instance even if installation fails before
AWS CLI is available. Status updates have timeouts and cannot prevent shutdown.

Experiment metadata remains in `benchmark_jobs.config`. Only
`netem_multi_bottleneck.py` receives the experiment metadata CLI flags; the other
runners do not support them.

Run `npm test -- --runInBand` for the launcher and bootstrap lifecycle regression
tests, which mock cloud calls and operating-system shutdown.

Multi-bottleneck requests must include `topology` (`parking-lot` or `dumbbell`),
`bottleneck_rates_mbit` and `bottleneck_buffers_kbytes` (two-number arrays).
Dumbbell also requires `client_groups`: two positive group sizes summing to
`num_clients`. The launcher rejects incomplete configurations before creating a
job or starting EC2. Older saved multi-bottleneck configurations need these fields
filled in; no topology is chosen implicitly. Single-bottleneck runners continue
using `bottleneck_all_client_rate_mbit`, `bottleneck_buffer_kbytes` and the metrics
source flags. Multi-bottleneck does not accept those CLI flags.

Current multi-bottleneck runner limitations: stored snapshots contain throughput
but no RTT/cwnd/in-flight measurements. Parking-lot currently applies only the
first link's rate and buffer. These limitations are also shown in the frontend.

To check generated commands against all four real backend argument parsers:

```bash
JUMPSERVE_BACKEND_CHECKOUT=/path/to/jumpserve-back-end npm test -- --runInBand
```

Without that checkout, the five CLI contract cases are skipped; launcher and
lifecycle tests still run normally.

### Prebuilt benchmark AMIs

`ami/build.py` provisions a disposable Ubuntu 22.04 builder, installs networking
tools and the CloudWatch agent, and checks out a **specific backend commit**.
It checks all four runners and a network namespace with a netem queue before
creating a private, encrypted EBS-backed AMI. The builder has a temporary SSM-only
role, with no access to the Supabase secret, SSH key or benchmark data. The script
verifies provisioning through SSM, then terminates its own builder and removes
its temporary IAM role/profile after success or failure. The AMI and snapshot
are retained.

Image sealing runs in a separate systemd service **after cloud-final finishes**.
It resets cloud-init, the machine ID and SSH host keys before stopping the builder.
This ordering matters: an earlier AMI approach was reverted because new instances
did not execute their own user data.

Preview a build using the current source AMI, benchmark subnet/security group and
a full backend commit SHA:

```bash
python3 -B ami/build.py \
  --profile default --region us-east-1 \
  --base-ami <canonical-ubuntu-22.04-ami-id> \
  --subnet-id <benchmark-subnet-id> \
  --security-group-id <benchmark-security-group-id> \
  --backend-commit <full-40-character-commit-sha>
```

The preview only reads AWS metadata. Add `--apply` to create the builder and AMI.
Expect EC2 runtime and ongoing snapshot storage charges. The result is written to
`cdk.out/benchmark-ami.json`. A successful build does **not** switch the launcher.
Use `npm run test:ami` for the builder tests; they mock all AWS operations.

For a live smoke test, run `npm run build` followed by `node ami/verify.cjs`.
This launches two small benchmark instances using the built image and candidate
launcher code: one successful run and one deliberate runner failure. It checks
saved status/results, fresh startup logs and automatic termination, and writes
`cdk.out/benchmark-ami-verification.json`. It uses the service key in memory for
the normal job API operations; it does not change the deployed Lambda.
After deployment, `node ami/verify.cjs --live-api` runs one successful job through
the public benchmark API and checks the same results and shutdown behavior.

After verifying the AMI with fresh benchmark instances, select it through the
benchmark stack parameter:

```bash
npm run cdk:benchmark -- deploy JumpServeBenchmarkStack --profile default \
  --parameters JumpServeBenchmarkStack:BenchmarkAmiId=<verified-ami-id>
```

CloudFormation retains the selected parameter on later deployments. Setting
`BenchmarkAmiId` to an empty string restores the base Ubuntu installation path.
The AMI ID and `BENCHMARK_IMAGE_MODE` must change together; setting only `AMI_ID`
in an older launcher still runs its installation script.

The standalone `cdk:benchmark` entry point synthesizes only this stack; it does
not require building the unrelated agent layer. Preview with
`npm run cdk:benchmark -- diff JumpServeBenchmarkStack --profile default`.

The benchmark log endpoint returns the latest 200 events by default so repeated
UI polling advances past installation output. An explicit forward cursor uses
the CloudWatch `nextToken` request parameter.
JWTs and Supabase secret API tokens are redacted in log API responses so older
shell-traced logs do not expose those values through the viewer. This does not
modify stored CloudWatch logs or revoke previously exposed credentials.

Prebuilt instances configure a new job-specific CloudWatch stream, validate the
image manifest, and run the baked backend without apt, pip, downloads or Git
operations. Their existing exit trap still terminates them after success or
failure. Credentials and job configuration are supplied at launch, outside the
image. The image manifest records the backend commit, build time and kernel;
`/etc/jumpserve-image-packages.txt` records installed package versions.

Rebuild and verify an AMI for backend or dependency updates. Background apt timers
are disabled to avoid package activity during benchmarks; rebuild regularly from
an updated Canonical base image for security updates. Keep the last verified AMI
for rollback, and remove superseded AMIs and snapshots through a separate review.

## Automated backend deployment

The backend repository's `Deploy benchmark AMI` workflow calls
[`.github/workflows/benchmark-ami.yml`](.github/workflows/benchmark-ami.yml).
Pushes to backend `main` rebuild the image, except changes confined to Markdown
or `experiments/`. Run that workflow manually on `main` to refresh OS packages
without a backend code change. Builds are serialized and do not cancel an
already running deployment.

The workflow:

1. Checks out the exact infrastructure workflow commit and runs local tests.
2. Uses GitHub OIDC to obtain temporary credentials for
   `JumpServeBenchmarkImageBuilder`. Only the backend repository's `main` branch
   can assume this role. No backend AWS access-key secrets are required.
3. Builds from the current Canonical Ubuntu 22.04 image with the triggering
   backend commit pinned. The builder has only temporary SSM permissions.
4. Verifies both a successful benchmark and an intentional runner failure,
   including saved results, no startup installation and automatic termination.
5. Rejects outdated commits, then updates only `BenchmarkAmiId` using the
   deployed CloudFormation template and preserving every other parameter.
6. Verifies a real request through the deployed benchmark API. If that check
   fails or is interrupted, restores the previous image, provided the selected
   image still belongs to this deployment.
7. Cleans up recorded builder and test instances and temporary IAM resources.
   It uploads image IDs and verification reports, never credentials or raw logs.

Cleanup checkpoints allow an always-run step to recover from cancellation.
A transient builder timer also stops compute after 45 minutes if the runner
becomes unavailable. A hard runner loss can still require manual cleanup of
stopped volumes or temporary IAM resources using the saved checkpoint:

```bash
python3 -B ami/cleanup.py --profile default
```

AMIs and snapshots are retained, including failed candidates, for diagnosis and
rollback; their storage still incurs charges. Remove obsolete images through a
separate review. This workflow does not rotate or delete existing credentials.

## Application modules

The frontend's post-login module chooser groups the current benchmark launcher,
run explorers, and AI chat under **Congestion Control Emulated Tests**
(`congestion-control-emulated`). Its module home is
`/modules/congestion-control-emulated`; existing tool and API URLs remain valid.
The catalog and route ownership are defined in the frontend's
`lib/test-modules.ts`. Selection is a navigation concern, not an authorization
boundary or a new parameter accepted by the current benchmark API.

**Congestion Control Real World Tests** (`congestion-control-real-world`) is
planned and disabled in the chooser. Before enabling it or future CDN modules,
provide explicit runner orchestration, data ownership, and API integration for
that module. The existing benchmark stack, emulated result queries, and agent
prompt configuration continue to serve emulated congestion-control tests; they
must not silently process a different kind of experiment. This navigation change
requires no infrastructure deployment or database migration.

## AI experiment explanations

`compare_runs` now returns `comparison_validity` before any algorithm-effect
interpretation: complete recorded configurations must match apart from the CCA,
with homogeneous BBR and CUBIC competition in supported single-bottleneck runners.
It lists differing configuration fields and unavailable provenance, and returns
descriptive CUBIC-minus-BBR FCT differences in seconds only for matching settings.
Two runs supply only one parent-run observation per algorithm. The tool does not
invent replication confidence intervals or trial pairing from client/snapshot
counts, run order, or timestamps. These deterministic tool checks complement the
database-managed research prompt; the migration seed remains immutable.

The active system prompt and research context live in Supabase's
`public.agent_prompt_versions` table. Every chat request loads one complete
published version through `get_active_agent_prompt`; a warm Lambda sees changes
on its next request. There is no hardcoded prompt fallback. Missing/invalid
configuration or a database error returns HTTP 503 before calling the model.

Each successful answer is saved in `public.agent_answers`, including its prompt
version ID, model ID and analysis version. Saving the answer and conversation
history is atomic. Existing historical answers retain their original history;
we do not retroactively assign prompt versions to them.

### Editing and publishing prompts

1. Open the JumpServe Supabase project (`regphejnlvfpyokpniny`). Check
   `agent_prompt_settings.active_version_id` for the current version.
2. Create a draft with a new UUID and unique `version`, copying `system_prompt`
   and `research_context` from the current version. Fill in `created_by` and
   `updated_by`. The database sets timestamps and the content checksum. You can
   also clone a version with:

   ```bash
   python3 -B bin/agent-prompts.py draft --from-id <version-uuid> --version <new-version> --actor <your-name>
   ```

3. Edit the draft's text and set `updated_by` in the Supabase Table Editor. Published rows are
   immutable; corrections always use a new draft.
   For file-based edits, use `bin/agent-prompts.py edit --id <uuid> --file <json>
   --expected-sha256 <current-checksum> --actor <name>`. The JSON contains
   `version`, `system_prompt` and `research_context`; the update rejects stale
   checksums and published versions.
4. Run the [Publish Agent Prompt workflow](https://github.com/jumpserve-networks/jumpserve-infra/actions/workflows/agent-prompt.yml)
   on `main`, supplying the draft UUID. It runs unit tests and the eight live
   Bedrock evaluations, stores the report, then atomically activates the exact
   evaluated content. Publishing fails if the draft or active version changed
   during evaluation. This makes billed Bedrock calls.
5. The next chat request uses the new version without an application deployment.
   The response includes `answer_id`, `prompt_version_id` and `prompt_version`.

To roll back, run the same workflow with a previous published version's UUID.
It is re-evaluated against the current model/analysis before activation. Every
activation records the previous version, actor, timestamp and full evaluation
report in `agent_prompt_publications`. Model grading is a regression check, not
proof of scientific correctness; review the saved answers as well.

Prompt text, publication RPCs and answer audit records are inaccessible to
`anon` and ordinary `authenticated` clients. Administration uses Supabase
Dashboard privileges or the backend service role. The model's tools have no
prompt-editing or publishing capability. Database owners can override database
permissions and must follow the publication workflow too.

### Initial database setup

Apply the additive migration **before** deploying the new agent:

```bash
python3 -B bin/agent-prompts.py migrate
python3 -B bin/agent-prompts.py list
```

These scoped commands use `SUPABASE_ACCESS_TOKEN` or the existing macOS Supabase
CLI login and verify the configured JumpServe project. `migrate` checks the
existing session schema, creates the prompt tables/functions, and imports
`database/seed-agent-prompt.json` as a draft. That file is a migration snapshot
of the previously deployed prompt; editing it does not update the live prompt.
The first infrastructure deployment evaluates and publishes this seed if no
version is active. Later deployments evaluate the database's active version.
They never replace edited database prompts with a repository copy.

`agent/run_analysis.py` calculates summaries without a language model:

- Configured delay contributes once to RTT for the documented runners; it is
  not a measurement of the entire unloaded path. Unknown/conflicting provenance
  leaves the interpretation unavailable.
- RTT zero placeholders are excluded and counted. Throughput/queue zeros remain
  valid when supported; non-finite, negative and missing values are counted.
- Queue delay comes from the stored backlog/capacity estimate, not RTT subtraction.
  RTT below configured added delay and negative metrics produce explicit warnings.
- Both sample and interval-weighted throughput means have named windows. The
  old nonzero-only mean is labelled diagnostic. Fairness uses all clients and
  identical complete intervals at one shared bottleneck, including zeros; it is
  explicitly not isolated concurrent-transfer fairness.
- Snapshot queries paginate through server-imposed page caps. A 100,000-row
  safety cap per client is reported as incomplete and disables full-run fairness.

The sanitized fixture `test/fixtures/run-2352.json` contains public numeric run
measurements only, with no credentials, conversations, or user identifiers.
Use `npm run test:agent` for deterministic calculations and mocked query tests.
The deployment workflow runs all Python/Jest tests, then eight opt-in Bedrock
answer evaluations before deployment to main. Cases cover #2352 twice, correcting
an earlier mistaken answer, CUBIC, BBRv3 uncertainty, inconsistent measurements,
unsupported multi-bottleneck metrics and a missing client. It uses the same
model ID and database prompt as production, with only a fixture results tool.
The model cannot start EC2 or access production sessions or run data. The test
harness reads prompt configuration and writes publication metadata only when
explicitly requested (or when bootstrapping the first active prompt). Model answers and a
separate model-based assessment are saved as the `agent-answer-evaluation`
artifact; review these alongside deterministic tests, since model grading is
not a guarantee of correctness for every future answer.

To run the answer evaluation locally with AWS account 395567831870 credentials
and `strands-agents`, `httpx`, and `boto3` installed:

```bash
python3 -B test/evaluate_agent.py --live
```

This makes billed Bedrock calls and reads the active database prompt using the
existing Supabase service-key secret. Without `--live`, the script refuses to
run. To test a draft locally, add `--prompt-id <uuid>`; add `--publish --actor
<name>` only when ready to activate it after all cases pass.

Database integration tests require an isolated PostgreSQL database named
`jumpserve_prompt_test` and `PROMPT_TEST_DATABASE_URL` pointing to it. Run
`npm run test:agent:database`; all test schema and data changes roll back. CI
provides an isolated PostgreSQL 17 service for this check.

## Supabase table access

`database/202609200002_authenticated_table_access.sql` protects all 16 application
tables in JumpServe (`regphejnlvfpyokpniny`). It enables RLS, removes anonymous
schema/table/column/sequence/RPC access, and adds a restrictive signed-in-user
policy. Supabase anonymous-auth sessions are also denied. Researchers retain
read access to measurements; existing benchmark/session policies and the
server-only prompt permissions remain in place. Trusted backend writers keep
their `service_role` access.

An event trigger enables RLS on new public tables, including partitions and
tables created with `CREATE TABLE AS` or `SELECT INTO`. New tables have no
permissive policy: migrations must explicitly define their intended access.
Default grants no longer expose new objects anonymously. Existing public views
use the caller's permissions. Supabase-managed auth, storage, realtime, and
extension schemas retain their platform-managed configuration.

Run the local regression suite with `npm run test:database:rls` and an isolated
`jumpserve_prompt_test` database (optionally set `PROMPT_TEST_DATABASE_URL`). It
checks anonymous rejection, signed-in reads/config/session operations, backend
writes, independent column grants, view behavior, migration idempotency, and new
tables. Fixtures, roles, and DDL roll back. CI runs it alongside the prompt tests.

The operator command is pinned to JumpServe. It reads `SUPABASE_ACCESS_TOKEN` or
the Supabase CLI login from the macOS keychain without printing credentials:

```bash
python3 -B bin/supabase-rls.py
python3 -B bin/supabase-rls.py --apply
python3 -B bin/supabase-rls.py --verify
python3 -B bin/supabase-rls.py --http-check /path/to/jumpserve-front-end/.env.local
```

`--apply` applies only this migration and runs role-based checks before committing;
any failed check aborts the transaction. `--verify` uses temporary test objects
and rolls back. The HTTP check uses only the frontend's public configuration and
requests no row data. Production verification on 2026-09-20 confirmed RLS on all
16 tables, authenticated/backend access, and HTTP 401 / SQLSTATE 42501 for every
anonymous table request. This migration contains no experiment-data changes.

## CI/CD and configuration

- Infrastructure `main`: GitHub Actions runs `cdk deploy --all`; pull requests
  run `cdk diff --all`.
- Frontend `main`: Amplify builds and deploys through its webhook.
- Backend `main`: builds, verifies and selects a new benchmark AMI as above.

The infrastructure deployment still uses its existing `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` GitHub secrets. The backend workflow no longer reads
those secrets or `EC2_INSTANCE_ID`; existing secret values are not removed by
this change.

AWS Secrets Manager holds `jumpserve/github-token` for Amplify and
`jumpserve/supabase-service-key` for benchmark status/results. Neither belongs
in source control or AMI snapshots.

## Development

```bash
npm ci
npm run build
npm test -- --runInBand
npm run test:ami
npm run cdk:benchmark -- diff JumpServeBenchmarkStack --profile default
```

The full app also needs the agent Python layer; see `.github/workflows/deploy.yml`
for its build steps. Deploying the standalone benchmark app does not require it.

## Project structure

- `bin/jumpserve-infra.ts`: full CDK app, without the legacy EC2 stack.
- `bin/benchmark.ts`: standalone benchmark CDK app.
- `lib/benchmark-orchestrator-stack.ts`: API, Lambda, ephemeral compute roles.
- `lib/benchmark-image-pipeline.ts`: GitHub OIDC provider and scoped image role.
- `ami/`: image building, verification, guarded promotion/rollback and cleanup.
- `test/`: launcher, lifecycle, IAM and AMI regression tests.
