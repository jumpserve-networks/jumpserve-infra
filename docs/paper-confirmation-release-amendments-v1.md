# PDF confirmation release amendments, 2026-10-24

This is an operational follow-up to `paper-confirmation-release-v1.md` and its
historical pending-status receipt. Original protocols, evaluation attempts,
deployment failures and database observations are retained. No scientific paper
finding is changed by this release.

The five exposed development extraction cases passed through native OpenClaw
2026.10.5, Node 24.16.0 and `gpt-6.1-sol`. The implementer examined every actual
raw and rendered answer; this is nonindependent AI review, with no human review
or held-out generalization claim. Original requests and responses are retained
privately with verified hashes. See `paper-confirmation-live-review-v1.json` and
`paper-confirmation-private-artifact-v1.json`. The active published v10 prompt
pointer did not change. The additional intake instruction and schema are
versioned in the implementation and each stored request.

While new admission and scheduled polling were held, the existing AWS worker
was found to have a full 24-GiB root filesystem: only 20 KiB remained. Its model
spool occupied about 19 GiB. A crash-consistent rollback snapshot
`snap-0137a98c3c03a2028` was retained, and encrypted root volume
`vol-0993b9127ac7a8231` was expanded in place to 48 GiB. The XFS filesystem then
reported 24 GiB free, 51% used. SSM and OpenClaw services restarted successfully.
No evidence files, historical outcomes or native grants were deleted or moved.
The worker instance remains `i-087f1493809643115`. Its 34 deployed source files
were subsequently verified against the release manifest.

The operational volume increase is intentionally separate from the EC2
CloudFormation block-device property: changing that property would replace the
instance. The current instance's capacity is 48 GiB; its original launch
template still declares 24 GiB. Capacity monitoring and an evidence-preserving
spool retention policy remain operational follow-ups. This recovery creates
additional storage and snapshot costs; measured charges and their allocation
are unavailable, not zero.

All temporary repair SSH rules, private Instance Connect Endpoints and their
security groups were removed and deletion verified, including the endpoint
that was still pending in the original release protocol. The last recovery
receipt is `.test-artifacts/paper-worker-repair/20261024T170216259759Z/receipt.json`.
The 18 old model dispatches whose outcomes were unknown before release remain
unknown. They were all historical, without active leases; they were not replayed
or relabeled to permit the update.

The first benchmark-stack deployment completed, but its strict post-deployment
guard detected an unrelated mutable Ubuntu image lookup changing from
`ami-02a9cdd4e98bc3c78` to `ami-0d6dd9e8265d48906`. No package experiment was
admitted while this was observed. A corrective deployment pins and restores
the original package image. The independent active benchmark image
`ami-0808d1157e26c65cb` and other benchmark parameters stayed unchanged. A
concurrent CDK output-directory lock failure is also retained; subsequent CDK
operations were sequential. Corrective deployment receipt
`20261024T170626505395Z` passed the parameter guard.

The bounded production browser control uses the original public IPv6 PDF,
SHA-256 `f6378fb3de19aa8d3204f4d3a2028f95497f334862a5298aa6678ef1b816290b`,
2,183,602 bytes. This control may confirm only the retained “Published absolute
folded metrics” claim and run its archived-data check. It does not authorize a
new Internet measurement or EC2 experiment. Browser file-tool workspace access
was unavailable, so the browser fetched the legally public original PDF,
verified its hash and assigned those bytes to the real file input. Subsequent
upload, review and confirmation use the ordinary application and a legitimate
existing Google session. Codex performs the release control; this must not be
described as human assessment review. It remains separate from earlier
scientific assessments. The read-only `control-snapshot` helper accepts only
the fixed control's local identity and exact PDF hash/filename; it verifies
stored prompt and response hashes and preserves missing responses as missing.

The AWS worker's own OpenClaw refresh returned `invalid_grant` after disk
recovery. Its native reconnect flow is separate from the successful local
evaluation grant; copying credentials between them is not a release procedure.
Admission and the schedule must remain held until the worker's native catalog
check succeeds. The final production receipt records whether that gate and the
authenticated browser control completed.
