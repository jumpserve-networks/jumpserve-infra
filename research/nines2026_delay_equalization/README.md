# NINeS 2026 research infrastructure

This directory prepares disposable infrastructure for the user-authorized paper
reproduction. It does not deploy JumpServe or change its existing stacks.

- AWS account: `395567831870`; region: `us-east-1`.
- Private evidence bucket: `jumpserve-nines2026-395567831870-us-east-1`.
- Research instance role: SSM access and access only to this evidence bucket.
  Workers receive no Supabase or AWS access keys in user data.
- Builder: one `c7i.4xlarge`, no inbound security-group rules, encrypted 100 GiB
  volume deleted with instance, IMDSv2 required, termination on shutdown.
- Three-hour-per-boot termination timer limits abandoned builder cost.
- The builder has completed and terminated. `resources.json` records the reusable
  AMI and eight campaign workers launched on 2026-09-28 at 00:34–00:40 UTC.
- Collection finished at 04:08:02 UTC: all 820 trials were valid and finalized in
  Supabase. All eight workers terminated automatically after uploading evidence;
  `termination-evidence.json` records the verified EC2 states. The AMI, snapshot
  and private S3 evidence remain available for reproducibility.
- Workers are `c7i.large` instances with two vCPUs, one sequential trial at a time,
  no inbound access, encrypted disposable disks, and a six-hour shutdown failsafe.
  They terminate after uploading their final evidence. These non-burstable
  research workers avoid CPU-credit confounding; they do not change the instance
  choices offered in the Real World Tests module.
- Google BBRv3 kernel commit: `90210de4b779d40496dee0b89081780eeddf2a60`
  (Linux 6.13.7). This is an explicit reproduction dependency, not a claim that
  the authors used this unreported kernel version.
- The same kernel exposes `bbr` (BBRv3) and a separately registered `bbr1` (BBRv1).
  `build/cca-sha256.txt` in S3 records the final BBR sources, `.config`, and
  `bzImage` after enabling BBRv1 and x2APIC. The older `kernel-sha256.txt` is an
  intermediate build record; use the final `cca-sha256.txt` for campaign provenance.
  `artifact-hashes.json` pins the worker code, preflight, protocol and 820-trial
  manifest. Frozen code is stored under `code/v1/` in the evidence bucket.
- Each worker passed the preflight before collection. Results are uploaded under
  `campaigns/nines2026-balanced-v1/worker-N/`; the backend experiment controller
  imports actual receiver measurements into normalized Supabase tables.

`worker.sh` stops after an invalid or failed trial, preserves evidence, and shuts
down. Do not silently rerun or exclude failed trials. The two pilot trials use a
separate prefix and are excluded from the frozen campaign. Preserve the AMI,
kernel provenance and evidence bucket for reproducibility; terminate workers.

Do not run experiment workloads until the active kernel, CCA implementations,
traffic direction, shaping and measurement validity checks pass. Keep build
provenance and trial manifests with the measurement data. Terminate disposable
instances at completion; preserve evidence needed for reproducibility.
