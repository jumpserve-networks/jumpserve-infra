# JumpServe Infrastructure

AWS CDK (TypeScript) infrastructure for the JumpServe project. Manages deployment of the frontend (AWS Amplify) and backend (EC2) resources.

## Architecture

```
jumpserve-infra (this repo)
├── AmplifyStack    → Hosts Next.js frontend, auto-deploys on push to main
└── Ec2Stack        → Ubuntu 22.04 t3.medium for network benchmarking
```

- **Frontend**: [jumpserve-networks/jumpserve-front-end](https://github.com/jumpserve-networks/jumpserve-front-end) → AWS Amplify
- **Backend**: [jumpserve-networks/jumpserve-back-end](https://github.com/jumpserve-networks/jumpserve-back-end) → EC2 instance

## Live Resources

| Resource | Details |
|----------|---------|
| Frontend URL | https://main.d24jvguj7brnkj.amplifyapp.com |
| Amplify App ID | `d24jvguj7brnkj` |
| EC2 Elastic IP | `3.215.213.116` |
| EC2 Instance ID | `i-0f62a10b6c2eff2e8` |
| AWS Account | `395567831870` |
| AWS Region | `us-east-1` |
| AWS CLI Profile | `dna-lab` |

## SSH into the EC2 Instance

```bash
ssh -i ~/.ssh/id_rsa ubuntu@3.215.213.116
```

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

SSH into the instance, then:

```bash
# View available options
sudo python3 /home/ubuntu/jumpserve-back-end/netem_cubic_benchmark_hotnets.py --help

# Example: run a 2-client benchmark
sudo python3 /home/ubuntu/jumpserve-back-end/netem_cubic_benchmark_hotnets.py \
  --num-clients 2 \
  --client-delays-ms 10,60 \
  --client-ccas cubic,bbr \
  --client-file-sizes-mbytes 50,35 \
  --bottleneck-all-client-rate-mbit 100 \
  --bottleneck-buffer-kbytes 125

# Run a batch of scenarios from a queue file
cd /home/ubuntu/jumpserve-back-end
sudo python3 run_queue.py                        # runs queues/default.yaml
sudo python3 run_queue.py staggered-start        # runs queues/staggered-start.yaml
sudo python3 run_queue.py --list                 # list available queue files
```

## CI/CD

### This repo (jumpserve-infra)
- Push to `main` → GitHub Actions runs `cdk deploy --all`
- PRs against `main` → GitHub Actions runs `cdk diff --all`

### Frontend (jumpserve-front-end)
- Push to `main` → Amplify automatically builds and deploys (via webhook)

### Backend (jumpserve-back-end)
- Push to `main` → GitHub Actions sends an SSM command to the EC2 instance to `git pull`

## GitHub Secrets

| Repo | Secret | Purpose |
|------|--------|---------|
| `jumpserve-infra` | `AWS_ACCESS_KEY_ID` | CDK deploy |
| `jumpserve-infra` | `AWS_SECRET_ACCESS_KEY` | CDK deploy |
| `jumpserve-back-end` | `AWS_ACCESS_KEY_ID` | SSM deploy command |
| `jumpserve-back-end` | `AWS_SECRET_ACCESS_KEY` | SSM deploy command |
| `jumpserve-back-end` | `EC2_INSTANCE_ID` | Target EC2 instance |

## AWS Secrets Manager

| Secret | Purpose |
|--------|---------|
| `jumpserve/github-token` | GitHub PAT for Amplify repo webhook |

## Prerequisites

- [AWS CLI](https://aws.amazon.com/cli/) configured with profile `dna-lab`
- [AWS CDK](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html) (`npm install -g aws-cdk`)
- [GitHub CLI](https://cli.github.com/) (`gh`) authenticated

## CDK Commands

```bash
# Synthesize CloudFormation templates
npx cdk synth --all --profile dna-lab

# Preview changes
npx cdk diff --all --profile dna-lab

# Deploy all stacks
npx cdk deploy --all --require-approval never --profile dna-lab

# Deploy a single stack
npx cdk deploy JumpServeEc2Stack --require-approval never --profile dna-lab
npx cdk deploy JumpServeAmplifyStack --require-approval never --profile dna-lab

# Destroy all stacks (careful!)
npx cdk destroy --all --profile dna-lab
```

## Project Structure

```
jumpserve-infra/
├── bin/jumpserve-infra.ts          # CDK app entry point
├── lib/
│   ├── amplify-stack.ts            # Amplify app + branch config
│   └── ec2-stack.ts                # EC2 instance, security group, EIP, key pair
├── .github/workflows/deploy.yml    # CI/CD for CDK deploy
├── cdk.json                        # CDK context (Supabase vars, SSH CIDR, etc.)
├── package.json
└── tsconfig.json
```
