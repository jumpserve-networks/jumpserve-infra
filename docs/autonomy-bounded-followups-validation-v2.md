# Correction: application attempts and evaluation windows

This supersedes the **interpretation and release condition** in the v1 report.
The original report, protocols, raw answers, failures, and artifact inventory are
retained unchanged. No original strict test result is relabeled as passing.

The application has always permitted **25 model attempts per claim**, within
**$100 shared conservative commitments per paper and seven days elapsed**.
Read-only evidence requests consume attempts and can continue beyond turn two.
The runtime has no two-turn completion condition. Earlier valid attempts,
commitments and deadlines remain counted when work resumes.

The two-turn condition was introduced by the evaluator. Failing to finish in
that short observation window did **not** demonstrate an application failure
within its authorized limits. Using it as the release blocker was a mistake.
Those two authorized reads establish safe intermediate handling; they neither
establish eventual completion nor justify claiming failure to finish within 25
attempts. The old producer also did not rebuild the controller's evolving
recent-turn history, so its trajectory was not equivalent to full application
orchestration.

The correction adds a versioned trajectory policy and migration
`202610190009_application_trajectory_guard.sql`. It replaces the short-window
publication condition while retaining the earlier source, scientific safety,
answer-review and private-access requirements. A short evaluation can report
`incomplete-evaluation`; it cannot be called a completed trajectory or an
application attempt-limit stop. Valid progress can continue to 25 total attempts.
Actual source/evidence problems or exhausted resources must retain an honest
unresolved label and reason. An honest resource stop is a valid bounded workflow
outcome, not evidence that a scientific claim was reproduced or disproved.

Local regressions check four-turn completion, incomplete evaluation after two
safe reads, honest attempt-limit handling only at 25, unchanged paper/time/cost
limits, preservation of earlier attempt numbering and continued safety checks.
The actual Postgres suite additionally checks publication accepts a synthetic
four-turn trajectory, rejects a two-attempt authorization and incomplete
publication evidence, and retains existing atomic budget/25-attempt/deadline
checks. These are development tests with synthetic AI outputs; they do not
establish live model completion.

A live trajectory evaluated with the correct limits remains **pending**.
Publication still requires its actual evidence and review; the old two-turn
failure is no longer the reason for that verification gap. This correction ran
no new billable model calls and performed no production mutation or deployment.
Original usage remains 20 calls, $9.45 conservative reservations, $1.99
token-based charge estimates and unavailable invoice charges.

See [amendment v7](autonomy-bounded-followups-amendment-v7.md),
[the corrected policy](../test/autonomy-trajectory-policy-v1.json),
[the machine-readable correction](autonomy-bounded-followups-validation-v2.json)
and [the preserved original report](autonomy-bounded-followups-validation-v1.md).

Reproduce the focused local checks in `jumpserve-infra`:

```sh
python3 -B -m unittest discover -s test -p 'autonomy_trajectory_policy_test.py' -v
npm run test:research:autonomy
```

The SQL command uses the existing isolated Postgres fixture on port 54477, not
production Supabase. The fixed-target release check now reports pending
verification under the application limits rather than failure of a two-turn
application requirement. Its default check remains local and makes no cloud
requests.
