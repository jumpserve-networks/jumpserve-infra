# JumpServe Infrastructure

AWS CDK infrastructure for the JumpServe frontend, benchmark API and AI tools.
No EC2 instance needs to run continuously for benchmarks.

## Architecture

- Amplify hosts the Next.js frontend at https://jumpserve.quaint-lab.org.
- API Gateway and Lambda launch one disposable EC2 instance per benchmark.
- Each instance boots a verified AMI, saves results to Supabase, streams logs to
  CloudWatch and terminates automatically after success or failure.
- Backend deployments briefly create an AMI builder and verification instances.
- The agent stack provides the AI tools independently of benchmark compute.

AWS account: `395567831870`; region: `us-east-1`.
The legacy `JumpServeEc2Stack` is removed from the CDK app so `deploy --all` cannot
recreate the permanent server, Elastic IP or SSH access.

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
