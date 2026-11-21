-- Owner-directed migration to Claude/Codex local skills, 2026-11-20.
-- Preserve original records, provider identities, scientific gates and read
-- projections. Retire service admission through the former hosted controllers.
-- A future authenticated bundle-import API must have its own narrow grant.
do $$
declare fn regprocedure;
begin
 for fn in select p.oid::regprocedure from pg_proc p
  where p.pronamespace='public'::regnamespace and p.proname in (
   'research_paper_intake', 'research_experiment_plan',
   'research_experiment_scripts_control', 'research_step_commands_control',
   'research_terminal_commands_control', 'research_paper_quality_control',
   'research_paper_agent_control', 'research_paper_background_control'
  )
 loop
  execute format('revoke execute on function %s from service_role',fn);
 end loop;
end $$;
