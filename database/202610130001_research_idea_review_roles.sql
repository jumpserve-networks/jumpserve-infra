-- Preserve the original four migrations; require distinct review invocations.
begin;
alter table public.research_idea_readiness add constraint research_idea_distinct_review_roles
 check(comprehension_run_id <> critic_run_id);
notify pgrst,'reload schema';
commit;
