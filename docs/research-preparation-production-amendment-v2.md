# Production artifact audit correction v2

Frozen before the read-only follow-up on 2026-10-07. Preserve the original v1
protocol, verifier source at infrastructure revision 599805d and failed report
`.test-artifacts/research-release/20261007T221548717353Z/production-server-report.json`.

That report passed deployment byte identities, authentication denial and the two
scheduled synthetic controls. Its preparation fixture retained twenty jobs: six
awaiting review, fourteen manual, with no failed or active jobs. It passed six
complete runs, 1,152 separately stored and matched published/observed cells,
unchanged protocols and fifteen imported assessments, and public leakage checks.
Its final artifact audit called `store.artifact_bytes` with the default 256,000
byte queue-input bound. The original registered manifest is 1,452,605 bytes;
prepared-plan reads already declare a separate 4,000,000 byte maximum in the
released implementation. The audit stopped at the bound check before downloading
that artifact. This is not evidence of a failed experiment or altered stored hash.

Correction: use the already declared 4 MB compiled-plan bound only for the
operator artifact audit. Do not change runtime/input bounds or deployed code.
Run `python3 -B bin/verify-research-production.py --preparation-followup` against
the same retained fixture, without creating studies, enqueueing, retrying jobs,
changing reviews or repeating computation. Check all completed states, matched
cells and fourteen retrieved artifact hashes. Compare protocol document/hash
and every assessment field against the original retained compiled plan. Confirm
the reported user workspace still matches its original zero-record counts.

All prior results remain retained. The follow-up is a corrected exposed release
audit, not a fresh experiment, independent validation, or legitimate Google
request. Capture available bounded CloudWatch REPORT samples and retained run
usage, distinguishing partial invocation coverage from complete accounting.
Missing charges remain null. Existing production browser evidence passes six
groups and is reusable because the frontend application bytes are unchanged.
