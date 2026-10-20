# Bounded autonomous follow-ups: implementation and validation

Local implementation reviewed on 2026-10-19. **Production was not changed.**
The request-size and cost-admission changes pass local verification. The new AI
prompt remains unpublished: its predeclared two-turn completion follow-up did
not reach a final assessment. Read-only intermediate steps were safe, but do
not satisfy that completion criterion. Publication and deployment are blocked.

## Implemented behavior

Planning receives a versioned check index, complete-data calculation summaries
and references to retained evidence. It no longer embeds every measurement or
the previous candidate's entire protocol. Selected fresh reviews receive the
complete selected protocol; large protocols require all hashed fragments before
readiness. The model can request bounded, claim-scoped evidence pages. Original
data, exact prompts, read requests/results, answers and failures remain retained.
The 96,000-byte request limit is unchanged; excessive inputs stop explicitly.

Coverage accumulates across compatible frozen checks. The arithmetic controller
matches exact source/configuration/observation/metric/unit identities, examines
valid cells in partial runs and preserves earlier discrepancies when subsequent
runs agree. Missing, invalid and ambiguous observations remain distinct from
recorded zero. Decimal comparisons and server-side numeric-to-text projection
avoid a float conversion before the controller. Every proposed conclusive
finding still requires original claim coverage, original inputs, frozen decision
rules and stored comprehension/critic reviews. Shared inputs/implementations do
not provide independent correctness validation.

A private recovery RPC resumes only known pre-dispatch context-size failures,
once per implementation, retaining original costs, deadline, attempts and reviews.
It never replays an uncertain provider call or experiment launch. Queue cards
show retained check progress separately from scientific coverage.

The first newly admitted autonomous networking runner is `bounded-tcp-v1`:
actual TCP exchanges over `127.0.0.1` with controlled application delay. It accepts
only payload bytes (1–65,536), exchanges (1–16) and delay (0–20 ms). Its dedicated
immutable Lambda version has 128 MB memory, a five-second timeout and 512 MB
ephemeral storage. It has log permissions only, no Supabase secret or experiment
cloud permissions, opens no remote targets and creates no EC2 machines. Internal
deadlines/socket timeouts and cleanup provide additional bounds. The server
checks the qualified version, deployed resource configuration and policy hash.
Uncertain dispatch is retained and never reinvoked under the same identity.

One cent per invocation is a conservative compute/request reservation with
headroom. It is not an invoice charge. The policy expires 2026-11-19; an expired
or mismatched policy blocks admission. Shared orchestration/storage use the
existing separate paper commitment. Lifetime storage, taxes, unallocated costs
and total AWS invoices are not hard capped by this estimate. Existing EC2 and
custom-package networking runners still need separate enforceable cost policies
before autonomous spending is enabled for them. Paper defaults remain $100 in
conservative commitments, seven days and 25 model attempts per claim.

## Evidence and results

| Check | Observed result | Scope |
| --- | --- | --- |
| Backend suite | 161 passed | Includes six archived numerical checks/1,152 cells, coverage, missingness, decimal/pagination bounds, prior partial discrepancy preservation and real local TCP cleanup |
| Frontend suite | 187 passed | Includes v1/v2 compatibility, missing/invalid progress and scoped navigation |
| Infrastructure suite | 93 passed, no skipped checks | Actual backend checkout supplied; held rollout, immutable version, resource and IAM assertions |
| Type/build/lint | Both builds passed; lint zero errors | One pre-existing `auth-button.tsx:153` navigation warning |
| Actual local Postgres campaign | 11 groups passed | Ownership/RLS/browser denial, limits, atomic parallel reservations, once-only recovery preserving legacy reviews, publication guards, raw and parsed TCP persistence |
| Browser campaign | Seven groups passed | Real components/HTTP/local SQL; synthetic auth/provider/Storage. Desktop 1365 px and mobile 390 px, light/dark, unavailable/invalid states, prompt history, editor units and real Next login-return paths |
| Final live v8 original cases | Eight of nine strict checks passed | Exposed development cases; no held-out or independent review |
| Corrected completion follow-up | Failed its final two-turn criterion | First read inspected the controlled check; second read requested its measurements. Both authorized; no final assessment |

Final v8 frozen requests ranged from 16,462 to 59,620 bytes. The complete
1,152-cell assessment request was 29,991 bytes. These are measured fixture
sizes, not a guarantee that every future paper fits. Server full-data processing
stops explicitly above 100,000 records or 32 MB; evidence pages are at most
10,000 bytes, and an oversized single row requires the original artifact.

The archived absolute cells from Figures 13a/b, 14a/b and 15a/b numerically agree
under the retained conditions. This is reanalysis of recorded data with shared
upstream parsing and frozen inputs. It does not validate Internet behavior today,
raw-pcap completeness, causal claims or the whole paper. A deliberately changed
partial run verifies preservation of discrepancies in software; it is not a new
finding against the paper. New local TCP timings are host-local measurements;
repeated exchanges share host/process/connection. No inferential interval or
Internet/CDN generalization is supported.

The database networking check stored four measurements from two real local TCP
exchanges and verified the original response bytes after retrieval. AWS transport,
Google identity, source retrieval and Storage were explicit fixtures in that
campaign. This proves the local integration, not execution in a deployed Lambda
or a provider-to-production-Supabase round trip. UI components were bundled with
explicit auth/navigation fixtures; a separate fresh production Next build checked
anonymous canonical/alias routes and sign-in return paths. No legitimate Google
session was used for these new changes. No new export/browser-chart claim is made.

## Model evaluation history and limitations

All 20 provider calls used the fixed Bedrock model
`us.anthropic.claude-opus-4-6-v1`, temperature zero and 4,096 maximum output tokens,
with no provider retries. Original AWS CLI stdout, canonical SDK messages,
rendered typed answers, exact requests and usage are retained. Original provider
HTTP bytes are unavailable; CLI stdout is not described as HTTP wire evidence.
The primary Codex AI implementer inspected raw structured and rendered answers.
There was no human, independent or held-out validation.

1. Original v7: five of eight strict checks passed. Unnecessary reads and an
   exhausted-budget choice failed strict criteria. Original bytes remain intact.
2. Corrective v8: eight of nine original strict checks passed. Budget/phase
   action constraints prevent those two invalid choices in the pipeline.
3. Amendment v4 explicitly tuned the ninth criterion after evaluation to accept
   safe intermediate reading. The reviewed report preserves its original failure
   and does not call it independent validation or a final decision.
4. A new completion protocol fixed criteria before further calls. Its first
   producer regenerated random fixture IDs and correctly failed authorization
   against the old frozen prompt. This test-setup failure is retained separately.
5. The corrected campaign froze fixture and prompt together. Two authorized
   reads succeeded, but the second answer remained intermediate. It failed the
   unchanged completion criterion. No further calls were made after the maximum
   20-call campaign allowance. The prompt remains unpublished; a new migration
   and release gate reject publication with this failed report.

One CDN blocker answer asked broadly about equipment/credentials. It demonstrates
refusal to treat loopback as Internet evidence, not a complete CDN protocol or a
claim that observer credentials are required. Completion within two turns is a
declared development check, not proof that the 25-attempt application workflow
can never finish. Its later final judgment remains unverified.

Known token-based conservative charge estimates total **$1.99**; aggregate
conservative reservations total **$9.45**, below the amended $10 cap. Usage is
present for all 20 calls, including failed evaluation cases. Measured invoice
charges are unavailable. Local compute, private storage and shared infrastructure
charges are unallocated, not zero. No actual AWS networking experiment was run.

Earlier failing database/browser runs remain archived, including sandbox-denied
SQL, invalid fixture budgets, missing reviewed idea setup, the new runner's SQL
allowlist/JSON precedence corrections and an alias check against a stale user dev
server on port 6001. The fresh isolated build on 6002 passed; the user's dev
server was left untouched. Final tests are development regressions, not samples
from a population, and no confidence interval for their pass rate is appropriate.

## Reproduction and release

Use the commands and guarded rollout in [the implementation guide](autonomy-bounded-followups-implementation-v1.md).
The [machine-readable report](autonomy-bounded-followups-validation-v1.json)
lists exact report paths, hashes, source profile and remaining conditions. The
[artifact inventory](autonomy-bounded-followups-artifacts-v1.json) binds successful,
failed and superseded campaigns, raw fixture artifacts, source revisions and
screenshots. Local ZIP retrieval/member hashes are checked. Upload to private
Supabase Storage and remote hash verification are release steps and were not run.

No migration, prompt publication, commit, push, merge or deployment occurred.
Production release readiness is **blocked by the completion evaluation**, with
additional conditional checks for real cloud execution, remote Storage and an
authenticated end-to-end request. Scientific coverage remains the limited
archived reanalysis and host-local measurement scope described above.
