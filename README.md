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
