begin;
-- Retain rejected provider calls without inventing absent raw/rendered answers.
alter function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text) rename to publish_agent_prompt_before_rejected_turn_review;
create function public.publish_agent_prompt(p_version_id uuid,p_expected_active_version_id uuid,p_expected_content_sha256 text,p_report jsonb,p_actor text,p_module_id text default $$congestion-control-emulated$$) returns uuid language plpgsql security definer set search_path='' as $body$
declare trajectory jsonb:=p_report->'trajectory_report'; count_attempts integer;
begin
 if exists(select 1 from public.agent_prompt_versions where id=p_version_id and version=$$research-autonomy-v8$$) then
  if p_report->>'trajectory_policy_sha256' is distinct from 'df3ae18ae4fa467e1ec6197a8694e3d0d5531211155c1f5013a070bc8b367bbb'
   or trajectory->>'version' is distinct from 'autonomy-trajectory-evaluation-v1'
   or trajectory->'limits' is distinct from '{"max_attempts_per_claim":25,"max_paper_committed_cents":10000,"max_elapsed_seconds":604800}'::jsonb
   or trajectory->>'status' is distinct from 'complete'
   or trajectory->'reviewer'->'passed' is distinct from 'true'::jsonb
   or trajectory->'input_sha256' is distinct from p_report->'input_sha256'
   or coalesce(p_report->>'trajectory_report_sha256','') !~ '^[a-f0-9]{64}$'
   or coalesce(trajectory->>'reason','')=''
   or coalesce(trajectory->>'attempts_used','') !~ '^(0|[1-9][0-9]?)$'
   or coalesce(trajectory->>'committed_cents','') !~ '^(0|[1-9][0-9]{0,4})$'
   or jsonb_typeof(trajectory->'cases') is distinct from 'array'
   or trajectory->'checks' is distinct from '{"exact_prompts_retained":true,"scoped_reads":true,"evidence_decisions":true,"authorization_preserved":true,"no_unknown_call_replay":true}'::jsonb
   then raise exception 'Reviewed trajectory under original 25-attempt/$100/seven-day limits is required; a short evaluation window is incomplete, not workflow failure'; end if;
  count_attempts:=(trajectory->>'attempts_used')::integer;
  if count_attempts not between 0 and 25 or (trajectory->>'committed_cents')::integer>10000
   or jsonb_array_length(trajectory->'cases')<>count_attempts
   or coalesce(trajectory->>'terminal_status','') not in ('assessed','external-blocker','attempt-limit','budget-limit','deadline')
   or (trajectory->>'terminal_status'='attempt-limit' and count_attempts<>25)
   or exists(select 1 from jsonb_array_elements(trajectory->'cases') with ordinality a(c,n) where c->'number' is distinct from to_jsonb(n) or c->'passed' is distinct from 'true'::jsonb or ((c->>'status'='complete' and c->'raw_answer_reviewed'='true'::jsonb and c->'rendered_answer_reviewed'='true'::jsonb) or (c->>'status'='provider-rejected' and c->>'failure_code'='ThrottlingException' and c->'no_answer_received'='true'::jsonb and c->'failure_reviewed'='true'::jsonb and c->'provider_attempt_not_replayed'='true'::jsonb and c->'raw_answer_reviewed'='false'::jsonb and c->'rendered_answer_reviewed'='false'::jsonb and c->>'provider_response_sha256'='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855' and coalesce(c->>'failure_sha256','') ~ '^[a-f0-9]{64}$')) is not true)
   or (trajectory->>'terminal_status'='assessed' and (coalesce(trajectory->'cases'->(-1)->'output'->>'action','')<>'assess' or coalesce(trajectory->'cases'->(-1)->'output'->>'assessment_label','') not in ('reproduced','discrepant') or trajectory->'cases'->(-1)->'output'->'coverage_complete' is distinct from 'true'::jsonb))
   then raise exception 'Preserve all attempts and an honest terminal reason; intermediate reads are neither final assessments nor attempt exhaustion'; end if;
 end if;
 -- This is the v7 safety/source/answer guard, preceding the short-window guard.
 return public.publish_agent_prompt_before_autonomy_completion(p_version_id,p_expected_active_version_id,p_expected_content_sha256,p_report,p_actor,p_module_id);
end $body$;
revoke all on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text),public.publish_agent_prompt_before_rejected_turn_review(uuid,uuid,text,jsonb,text,text) from public,anon,authenticated;
grant execute on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text),public.publish_agent_prompt_before_rejected_turn_review(uuid,uuid,text,jsonb,text,text) to service_role;
notify pgrst,$$reload schema$$;
commit;
