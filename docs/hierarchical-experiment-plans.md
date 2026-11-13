# Hierarchical paper implementation plans

Migration `database/202611120001_hierarchical_experiment_plans.sql` adds the
`paper_experiment_steps_v3` request format. Plans store experiments, named stages,
and actionable leaf steps in the existing private JSONB plan column. No new table,
worker dispatch, execution permission or measurement run is introduced.

The migration preserves v1/v2 requests and flat saved plans. Their twelve-step
and 1200-character instruction limits remain. A hierarchical experiment may have
up to eight stages, eight actions in a stage, and twenty-four actions in total;
action instructions are at most 800 characters. Further nesting, mixed layouts,
empty stages, invented references, missing claims and duplicate claim checks are
rejected. Claim identities and supporting references belong to leaf actions.

Confirmation still atomically freezes the reviewed breakdown, exact prompt and
request, Google-linked owner, original deadline, cumulative spending reservation
and one provider-call identity. The finish operation requires the original
completed response and a source-bound plan. A v3 admission cannot finish with a
flat projection. Immutable history, owner deletion and uncertain-call fences are
unchanged. RLS and denial of anonymous/authenticated SQL writes remain in place;
generic prompt templates do not copy private paper content.

On a later explicitly authorized deployment, apply this migration after
`202611110005_reviewed_paper_evidence.sql` and before releasing the matching
frontend. The old app continues to submit flat formats during the transition.
No original confirmation, response or saved plan is rewritten or regenerated.
An unmigrated database rejects a v3 admission before confirmation or inference.
Feature implementation does not apply the migration to production.

Local verification uses the existing isolated PostgreSQL fixture:

```sh
python3 -B test/check_hierarchical_experiment_plans_database.py
```

This runs reviewed-evidence regressions, verifies unchanged-record hashes across
two applications of the migration, checks twenty shared JS/SQL acceptance and
rejection cases, and exercises actual SQL admission, persistence, privileges,
concurrency, limits, history and deletion. It makes no production database,
provider, worker or experiment calls. Browser-free live prompt development uses
`npm run eval:experiment-plan` in the frontend and freezes the generated hierarchy
with the exact input and original provider identity.
