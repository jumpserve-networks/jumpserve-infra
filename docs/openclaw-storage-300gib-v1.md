# OpenClaw shared worker: 300-GiB online expansion

2026-10-28 UTC. The application owner requested 300 GB of builder storage;
the AWS provisioned target is **300 GiB**. The existing encrypted gp3 root
volume was expanded from 48 GiB, followed by the existing partition and XFS
filesystem. The running worker, authorization state and saved assessments were
preserved. No application release, instance replacement, reboot or evidence
deletion was performed.

AWS account `395567831870`, region `us-east-1` and JumpServe Supabase project
`regphejnlvfpyokpniny` were verified before changes. The fixed worker and volume
identities are recorded in `openclaw-worker-storage.json`. No active controller
or model dispatch existed before recovery; availability was `storage-low`.

The recovery snapshot was requested before modification:
`snap-002af2609269bc721`, encrypted, crash-consistent, original size 48 GiB.
At 03:54:57 UTC its state remained pending; backup completion is not claimed.
The volume had entered `optimizing` with target size 300 GiB. AWS permits the
partition/filesystem extension in that state; final background optimization
completion is not required to use the expanded capacity and is not claimed.

The grow command checked the EBS serial, root device and XFS mount before using
`growpart /dev/nvme0n1 1` and `xfs_growfs -d /`. Its retained output reports:

| Metric | Before | After |
| --- | ---: | ---: |
| Filesystem bytes | 51,459,895,296 | 322,042,834,944 |
| Available bytes | 518,094,848 | 269,209,628,672 |
| Used percentage | 99% | 17% |

The resulting free space is approximately **250.72 GiB**. OpenClaw remained
active and reported `ready` at 03:54:20 UTC. Assessment
`a3bad34f-a9b5-44bb-be46-e1800cf1cf89` automatically resumed with two active
turns and 18 retained controller turns (16 complete, two running) at 03:54:26.
Its original USD100 maximum, seven-day deadline and uncapped AI-turn policy
were preserved. This is infrastructure recovery, not a scientific finding;
paper experiments and measurements were still pending at that checkpoint.

## Configuration and commands

`openclaw-worker-storage.json` is the operational capacity target consumed by
the fixed-target helper. The EC2 CloudFormation **launch property remains
24 GiB deliberately**: changing that property replaces the authorized instance.
The existing template is not reconciled by replacing the host. The source
comment documents the operational target; these repository edits remain local
until a separate merge/release request.

From `jumpserve-infra`, after inspection and explicit storage authorization:

```sh
python3 -B bin/openclaw-storage.py snapshot
python3 -B bin/openclaw-storage.py expand
python3 -B bin/openclaw-storage.py status
python3 -B bin/openclaw-storage.py grow
python3 -B bin/openclaw-storage.py host-status
python3 -B bin/openclaw-storage.py verify
```

The helper preserves snapshot and growth command IDs and rejects blind replay.
Original receipts, host output and pricing response are under the ignored
`.test-artifacts/openclaw-storage-v1/` directory. AWS also retains the volume
modification and SSM command history. No database migration or application
prompt change is part of this operation.

Validation: helper/config syntax and `git diff --check` passed. The existing
OpenClaw infrastructure test passed, retaining its instance, encryption,
authorization and replacement-sensitive launch-property assertions. Production
checks verified the actual volume, filesystem growth, active service, ready
heartbeat and resumed existing claim identities. Review was performed by the
same Codex AI implementer; no human or independent scientific review is claimed.

## Costs

AWS Pricing GetProducts returned SKU `JG3KUJMBRGHV3N8G`, effective 2026-10-01,
for US East (N. Virginia) gp3 capacity at USD0.08 per GB-month. At a full-month
rate, capacity is estimated at **USD24.00/month**, an increase of
**USD20.16/month** over 48 GiB. Actual billing is prorated. Baseline 3000 IOPS
and 125 MiB/s provisioned throughput were preserved. Taxes, credits, compute
and snapshot storage are excluded. Measured charges, snapshot charges and
allocation of this shared infrastructure to individual papers remain unknown.
The price response and separate estimate are retained with the receipts.

Release follow-up, 2026-10-28 19:24 UTC: the fixed-target status check verified
the 300-GiB modification completed at 04:28:44 UTC and the encrypted recovery
snapshot is completed at 100%. The original worker and volume identities remain
unchanged. Earlier pending observations above are historical records, not the
current backup status. The source/configuration is included in the separately
authorized continuation release; the CloudFormation launch property stays fixed.

References: [AWS Linux filesystem extension instructions](https://docs.aws.amazon.com/ebs/latest/userguide/recognize-expanded-volume-linux.html),
[CloudFormation EBS replacement behavior](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-ec2-instance-ebs.html),
[AWS EBS billing rules](https://aws.amazon.com/ebs/pricing/).
