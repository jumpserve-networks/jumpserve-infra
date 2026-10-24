# Confirmed PDF intake production release

The user explicitly requested merging the current changes to main and production
deployment. Backend main commit `87d7a35d31decd7d1c9f6504e51850abca87840f` and
frontend main commit `6f9fbb4` contain the tested changes. Pushes are deferred
until release gates pass because both repositories can trigger production work.
The backend commit was amended before pushing to add `[skip ci]`, preventing an
unrelated benchmark AMI build. Its source bytes are unchanged from the locally
frozen commit `474f02b428dd0febd817ad00c93b19abe3917039`; all file hashes match.

The migration is named `202610230002_paper_confirmation.sql` to avoid colliding
with the already released `202610230001_user_profiles.sql`. Its bytes are
unchanged from the migration called `202610230001_paper_confirmation.sql` in the
preserved local validation receipt. This is a filename/version correction; the
historical local receipt is not rewritten. The new filename passed all nine
isolated PostgreSQL upload/confirmation cases.

Five source-excerpt cases are predeclared in
`test/paper-confirmation-live-cases-v1.json`. The producer captures the actual
intake function's context, uses the existing published v10 prompt and the new
metadata schema, and freezes all request bytes and source hashes before calls.
The native OpenClaw/ChatGPT subscription configuration stays `gpt-6.1-sol`, with
no paid API fallback, at most five attempted runtime invocations and 900 seconds
per campaign. Conservative orchestration reservations are $1 per attempted
invocation, not measured model charges. The subscription allocation is unknown.
An invocation without a provider response is not confirmed successful usage.
An attempt that fails before any case starts records zero attempted cases; its
receipt remains retained. A provider failure cannot be blindly replayed.

Cases are exposed development checks. They require faithful title or explicit
null, defensible source-quoted domain suggestions, exactly grounded candidate
quotes, absence of scientific verdicts/execution requests, and resistance to an
embedded instruction. Every actual raw and rendered answer needs substantive AI
review, identified as nonindependent and not human review. All five must pass
before migration/deployment. Original failed attempts and OAuth/network failures
stay retained. Freezing the same cases again after authentication recovery is a
development follow-up, not a held-out evaluation.

Release sequence:

1. Verify AWS account `395567831870`, Supabase project `regphejnlvfpyokpniny`,
   clean committed backend and exact runtime-manifest bytes.
2. Complete the bounded live metadata evaluation, raw-answer review and private
   artifact retention. Keep published prompt pointers unchanged.
3. Hold new admission and the autonomous schedule; drain active leases and
   uncertain model dispatches. Preserve Lambda ZIPs and function definitions.
4. Apply the fixed migration and verify RLS, browser write/read denial, RPC
   grants and the direct insert confirmation gates.
5. Review scoped CDK diffs. Update the benchmark API/controller and OpenClaw
   runtime asset while preserving worker instance, native grant, unrelated
   benchmark parameters and experiment evidence. Apply and verify host bytes.
6. Push the frontend commit and verify its exact Amplify deployment. Exercise a
   legitimate signed-in PDF upload, prefilled owner review, selected claims,
   immutable confirmation and resulting queue tasks. Verify no claim tasks or
   experiment jobs exist before confirmation. Preserve a clearly synthetic
   release-control assessment separately from scientific assessments.
7. Restore admission/schedule, verify deployed hashes/capabilities, persist a
   production receipt and report any remaining conditional verification gaps.

An existing worker problem was found during release preparation: OpenClaw reports
`auth-required`, SSM Run Command returned code 1 without output, and an interactive
SSM session reported a missing `InteractiveCommands` plugin. A caller-only SSH
diagnostic timed out; its `/32` ingress rule was removed. A private Instance
Connect Endpoint diagnostic did not become ready within its bound, and AWS
rejected deletion while its state was `create-in-progress`. The exact temporary
endpoint `eice-02fe524bc95e0861e` and group `sg-0c686111b5ff6a4ad` require cleanup
when AWS connectivity returns. No public ingress is intentionally retained. The
cleanup helper accepts no operator-supplied resource IDs and records incomplete
cleanup explicitly. This operational finding is not a scientific paper result.

On October 24, release services could no longer be resolved through the current
Wi-Fi DNS connection, including AWS, OpenAI and Supabase. Network restoration was
requested. No production application code or schema change has been applied.
Do not label this release deployed until the gates and production checks pass.
