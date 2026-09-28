-- The default new-table guard installs an anonymous-read restriction. Keep its
-- real-user check for authenticated sessions, as in other public result modules.
begin;
do $public_reads$
declare relation text;
begin
  foreach relation in array array[
    'delay_study_campaigns','delay_study_configurations','delay_study_config_flows',
    'delay_study_trials','delay_study_flows','delay_study_samples','delay_study_cells',
    'delay_study_summaries','delay_study_papers','delay_study_claims',
    'delay_study_latency_trials','delay_study_latency_samples'
  ] loop
    execute format('drop policy if exists jumpserve_require_signed_in_user on public.%I', relation);
    execute format('create policy jumpserve_require_signed_in_user on public.%I as restrictive for all to authenticated
      using ((select auth.uid()) is not null and (select auth.jwt()->>''is_anonymous'') is distinct from ''true'')
      with check ((select auth.uid()) is not null and (select auth.jwt()->>''is_anonymous'') is distinct from ''true'')', relation);
  end loop;
end
$public_reads$;
notify pgrst, 'reload schema';
commit;
