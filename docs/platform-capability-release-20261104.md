# November 4 capability kernel production release

The owner explicitly requested deployment of the prepared capability acquisition
kernel and Slack operations v2. This is an operator bootstrap upgrade of frozen
controller code, not an ordinary autonomous self-update certificate.

The protected source PRs were infrastructure
[#59](https://github.com/jumpserve-networks/jumpserve-infra/pull/59) and backend
[#30](https://github.com/jumpserve-networks/jumpserve-back-end/pull/30). Their exact
merged revisions passed Platform validation:

- Infrastructure: `f162271a8adf98c694257668b8ed2afe59cc819b`.
- Backend: `1a8e96e2c86692506a2bde72ecdcd516a83eaab1`.
- Supervisor bundle: `99f1c035629e16587b81b3fd8286bbaf3dea2e4b59191c020f9cecdf125e929f`.

Qualification passed 116 supervisor tests, 133 database checks and 22 release
tests. The new forward migrations are `202611040002_platform_slack_controls.sql`
and `202611040003_supervisor_capabilities.sql`; production function-body hashes,
service-only RPC privileges, private table grants and RLS matched the qualified
database. The previously applied Slack migration remains unchanged.

The fixed host is `i-087f1493809643115`, account `395567831870`, `us-east-1`.
Installation SSM command `6554486c-2f28-450f-a5aa-9971f0374b1b` verified the bundle
and retained rollback source. Readback command
`03d3bbee-6a42-48bc-9033-f05c5ffeb643` verified the actual process working directory,
source files, unchanged research worker PID and EC2 instance-role credentials.
No interactive AWS credentials were installed in the services.

Deployment operation `c825b1ad-da34-4a1c-a207-2d8604a5cda1` has an immutable install
intent, the original SSM receipt, an exact installed manifest, a confirmed
operation and a verified release. Its verification explicitly records
`mode=explicit-operator-bootstrap`. The private, byte-verified qualification
artifact is `48447758-971b-5ada-9edd-15e5f67f7305`; no private storage URL or
credential belongs in this document. Supabase event
`f5e4d910-c8dd-5c3d-a55e-d4ed21fa0d02` exposes the rollout in Platform Updates.
Admissions were restored to `paused=false`, with automatic releases enabled.
Original category budgets, assessment deadlines and source hashes were retained.

Live task `5217ddb0-3379-5aea-b7e5-132e677b02a8` requests a read-only sandbox
resource-diagnostics capability through the native coding turn. Its request,
linked implementation, qualified self-installation, installed activation and
parent resumption must each be observed before claiming that complete path.
Queueing the canary or a fresh heartbeat is not that proof. Existing unresolved
research calls remain fenced and no fresh scientific measurement is claimed by
this deployment.
