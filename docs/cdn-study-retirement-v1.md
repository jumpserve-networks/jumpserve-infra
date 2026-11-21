# CDN cache study retirement

On 2026-11-20 the owner explicitly authorized destruction of the August 2026 CDN
cache-demand experiment infrastructure. The owner subsequently excluded Cloudflare
and Fastly after their account sessions were found unavailable. Preserve that
exception: do not remove their Workers, services, TLS subscriptions or DNS records
under this retirement.

The authorized AWS targets are the two isolated CloudFront distributions and
the retained S3 origin, represented by these existing stacks:

- `jumpserve-cloudfront-exploratory`
- `jumpserve-cloudfront-do-origin`
- `jumpserve-cdn-origin`

Their dedicated cache/header policies, certificates, endpoint DNS records and
certificate-validation records belong to the same deletion. The owner explicitly
authorized emptying and deleting the origin bucket, including every object
version, delete marker and unfinished multipart upload. Its historical retention
policy does not prevent this owner-directed destruction.

The original DigitalOcean origin Droplet was already absent, as were its
snapshots. Its orphaned `jumpserve-neutral-origin` firewall, SSH key and empty
resource tag were deleted after verifying their original identities and absence
of remaining Droplet/tag attachments. Do not describe the previously absent
Droplet as a newly executed deletion.

`bin/destroy-cdn-study.py` is a fixed-target operator procedure. It validates the
AWS account, study project tags, stack resource types and physical identities
against a private frozen inventory before deletion. It waits for origin-stack
removal before purging its retained bucket and for all stack deletions before
removing residual DNS. Current records must match the original DNS snapshot;
Fastly records and the shared hosted zone remain intact.

Private receipts in `.test-artifacts/cdn-study-destruction-20261120` record the
original resource metadata, submitted deletion identities and actual readback.
`verify` requires completed stack removals, absence of the bucket and distributions,
certificates and selected DNS, and 404 responses for the exact DigitalOcean
resources. It also checks that unrelated CloudFront aliases/origins and retained
DNS records are unchanged and that the JumpServe homepage and a shared assessment
still load. A submitted deletion alone is not completion.

Historical experiment notes describe the former deployment and must not be
treated as evidence that the retired targets still exist. This procedure does
not modify the frozen scientific protocols or other JumpServe modules.
