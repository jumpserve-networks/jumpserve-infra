# Cloud benchmark retirement

The owner authorized removal of the recovery disk, legacy real-world AWS backup
stores, old AMIs and deployment assets, cloud benchmark execution and custom
database monitoring on 2026-11-21.

`cloudBenchmarksRetired` selects a read-only benchmark stack. The shared API
origin, historical real-world GET routes and research assessment GET routes
retain their identities. Emulated and real-world launch, cancellation, ingest,
placement catalog and cloud-log endpoints are removed, together with the seven
execution/control Lambdas, their schedules, state machine, execution roles,
instance profiles and dedicated security group. The legacy DynamoDB table and
versioned S3 backup bucket require explicit deletion after CloudFormation
releases their retained resources.

The custom observability stack and AMI build workflow are retired. The website
keeps public benchmark history and replaces launch forms with local-execution
guidance. Supabase measurements, artifacts, authentication, assessment records,
scientific criteria, uncertain historical outcomes, website AI chat, hosting and
DNS remain intact. Recovery snapshots and historical logs remain private. A
historical database row marked running is not evidence of a live AWS execution;
retirement preserves its original status rather than fabricating completion.

`bin/retire-cloud-benchmarks.py` inventories fixed targets, renders only approved
removals against the actual deployed template, checks all change-set changes,
and saves private receipts under `.test-artifacts/cloud-benchmark-retirement-20261121`.
Disk removal requires its completed encrypted recovery snapshot. AMI removal
checks current instances, launch templates and Auto Scaling configurations.
Layer cleanup checks all retained Lambda versions. Asset cleanup preserves
current stack references, non-CDK objects and retirement audit templates, rejects
concurrent stack changes and only removes old unreferenced immutable hash assets.
The CDK bootstrap bucket and roles remain available for the website and read APIs.

The standalone skill and optional MCP sharing are documented in
`local-assessment-retirement-v1.md`. Their release is separate from this teardown.
