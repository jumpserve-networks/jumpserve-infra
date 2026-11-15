begin;

-- A reviewed projection never edits the original terminal plan, response,
-- confirmation, scientific instructions, criteria, model counts or limits.
create table if not exists public.research_experiment_plan_link_reviews (
 id uuid primary key,study_id uuid not null unique references public.research_experiment_plans(study_id),
 owner_id uuid not null,base_revision integer not null check(base_revision>0),provider_response_id text not null,
 keep_validation_steps jsonb not null,plan jsonb not null,changes jsonb not null,
 original_request_sha256 text not null,original_response_sha256 text not null,
 reason text not null check(length(btrim(reason)) between 1 and 2000),reviewer_type text not null check(reviewer_type in ('AI','human')),
 created_at timestamptz not null default clock_timestamp()
);
alter table public.research_experiment_plan_link_reviews enable row level security;
revoke all on public.research_experiment_plan_link_reviews from public,anon,authenticated,service_role;
grant select on public.research_experiment_plan_link_reviews to service_role;
drop trigger if exists assessment_active on public.research_experiment_plan_link_reviews;
create trigger assessment_active before insert on public.research_experiment_plan_link_reviews for each row execute function public.research_require_active_assessment();
drop trigger if exists plan_link_review_immutable on public.research_experiment_plan_link_reviews;
create trigger plan_link_review_immutable before update or delete on public.research_experiment_plan_link_reviews for each row execute function public.research_immutable();

create or replace function public.research_review_experiment_plan_links(p_actor uuid,p_study uuid,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare p public.research_experiment_plans;r public.research_experiment_plan_link_reviews;
 raw_plan jsonb;candidate jsonb;selection jsonb;action record;occurrences integer;changes jsonb='[]';seen text[]='{}';
 ref text;selected_experiment integer;selected_stage integer;selected_step integer;output text;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_actor is null or public.research_assessment_deleted(p_study) or not exists(
  select 1 from auth.users u join auth.identities a on a.user_id=u.id where u.id=p_actor and not coalesce(u.is_anonymous,true) and a.provider='google'
 ) then raise exception 'Verified active Google owner required';end if;
 select * into p from public.research_experiment_plans where study_id=p_study for update;
 if p.study_id is null or p.owner_id<>p_actor or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private paper assessment not found';end if;
 if jsonb_typeof(p_payload) is distinct from 'object' or octet_length(p_payload::text)>20000 or
  not p_payload ?& array['review_id','base_revision','keep_validation_steps','reason','reviewer_type'] or
  p_payload-array['review_id','base_revision','keep_validation_steps','reason','reviewer_type']<>'{}'::jsonb or
  jsonb_typeof(p_payload->'reason') is distinct from 'string' or length(btrim(p_payload->>'reason')) not between 1 and 2000 or
  coalesce(p_payload->>'reviewer_type','') not in ('AI','human') then raise exception 'Bounded explicit operator review required';end if;
 select * into r from public.research_experiment_plan_link_reviews where id=(p_payload->>'review_id')::uuid;
 if found then
  if r.study_id<>p_study or r.owner_id<>p_actor or r.base_revision is distinct from (p_payload->>'base_revision')::integer or
   r.keep_validation_steps is distinct from p_payload->'keep_validation_steps' or r.reason is distinct from p_payload->>'reason' or r.reviewer_type is distinct from p_payload->>'reviewer_type'
  then raise exception 'Review identity conflicts with its original content';end if;return to_jsonb(r);
 end if;
 if p.status<>'failed' or p.plan is not null or p.revision is distinct from (p_payload->>'base_revision')::integer or
  (p.reason is distinct from 'The experiment steps could not be verified against the confirmed paper sections.' and coalesce(p.reason,'') not like 'More than one step is assigned to validate-%') or
  p.provider_response_id is null or p.response->>'id' is distinct from p.provider_response_id or p.response->>'status' is distinct from 'completed' or
  p.request->'text'->'format'->>'name' is distinct from 'paper_experiment_steps_v3' or
  (p.response->'text'->'format'->>'type'='json_schema' and p.response->'text'->'format'->>'name' is distinct from 'paper_experiment_steps_v3')
 then raise exception 'An unchanged failed hierarchical plan and completed original response are required';end if;
 if jsonb_typeof(p_payload->'keep_validation_steps') is distinct from 'array' then raise exception 'Explicit validation-step selections required';end if;
 if jsonb_array_length(p_payload->'keep_validation_steps') not between 1 and 32 then raise exception 'Bounded validation-step selections required';end if;
 if exists(select 1 from jsonb_array_elements(p.response->'output') o cross join lateral jsonb_array_elements(o->'content') c where o->>'type'='message' and c->>'type'='refusal') then raise exception 'Refused responses cannot be reviewed as plans';end if;
 select string_agg(c.part->>'text','' order by o.position,c.position) into output
 from jsonb_array_elements(p.response->'output') with ordinality o(item,position)
 cross join lateral jsonb_array_elements(case when o.item->>'type'='message' then o.item->'content' else '[]'::jsonb end) with ordinality c(part,position)
 where c.part->>'type'='output_text';
 raw_plan=output::jsonb;candidate=raw_plan;
 if raw_plan is null or jsonb_typeof(raw_plan->'experiments') is distinct from 'array' or octet_length(raw_plan::text)>250000 then raise exception 'Bounded retained plan output required';end if;
 for selection in select value from jsonb_array_elements(p_payload->'keep_validation_steps') loop
  if jsonb_typeof(selection) is distinct from 'object' or not selection ?& array['claim_ref','experiment','stage','step'] or
   selection-array['claim_ref','experiment','stage','step']<>'{}'::jsonb or jsonb_typeof(selection->'claim_ref') is distinct from 'string' or
   exists(select 1 from unnest(array['experiment','stage','step']) key where jsonb_typeof(selection->key) is distinct from 'number' or coalesce(selection->>key,'') !~ '^[1-8]$')
  then raise exception 'Select an existing dedicated step per duplicated claim';end if;
  ref=selection->>'claim_ref';selected_experiment=(selection->>'experiment')::integer;selected_stage=(selection->>'stage')::integer;selected_step=(selection->>'step')::integer;
  if ref=any(seen) or raw_plan->'experiments'->(selected_experiment-1)->'stages'->(selected_stage-1)->'steps'->(selected_step-1)->>'validation_ref' is distinct from ref then raise exception 'Retain one existing duplicated claim assignment';end if;
  seen=array_append(seen,ref);occurrences=0;
  for action in
   select e.n as experiment,s.n as stage,a.n as step from jsonb_array_elements(raw_plan->'experiments') with ordinality e(item,n)
   cross join lateral jsonb_array_elements(e.item->'stages') with ordinality s(item,n)
   cross join lateral jsonb_array_elements(s.item->'steps') with ordinality a(item,n) where a.item->>'validation_ref'=ref order by e.n,s.n,a.n
  loop
   occurrences=occurrences+1;
   if (action.experiment,action.stage,action.step) is distinct from (selected_experiment,selected_stage,selected_step) then
    candidate=jsonb_set(candidate,array['experiments',(action.experiment-1)::text,'stages',(action.stage-1)::text,'steps',(action.step-1)::text,'validation_ref'],'null'::jsonb,false);
    changes=changes||jsonb_build_array(jsonb_build_object('experiment',action.experiment,'stage',action.stage,'step',action.step,'from',ref,'to',null));
   end if;
  end loop;
  if occurrences<2 then raise exception 'Only duplicate validation links can be reviewed';end if;
 end loop;
 if not public.research_valid_experiment_plan(candidate,p.confirmed_breakdown) then raise exception 'The reviewed plan must pass all existing source, claim, layout and size checks';end if;
 if exists(select 1 from jsonb_array_elements(candidate->'experiments') e where not e ? 'stages') then raise exception 'Retain the original hierarchical layout';end if;
 insert into public.research_experiment_plan_link_reviews(id,study_id,owner_id,base_revision,provider_response_id,keep_validation_steps,plan,changes,original_request_sha256,original_response_sha256,reason,reviewer_type)
 values((p_payload->>'review_id')::uuid,p_study,p_actor,p.revision,p.provider_response_id,p_payload->'keep_validation_steps',candidate,changes,
  encode(sha256(convert_to(p.request::text,'UTF8')),'hex'),encode(sha256(convert_to(p.response::text,'UTF8')),'hex'),p_payload->>'reason',p_payload->>'reviewer_type') returning * into r;
 insert into public.research_audit_events(study_id,actor_id,action,details) values(p_study,p_actor,'review-experiment-plan-links',jsonb_build_object(
  'review_id',r.id,'method','duplicate-validation-links','original_revision',p.revision,'changes',changes,'original_response_preserved',true,'confirmed_scope_preserved',true,'new_model_calls',0,'experiments_started',0,'limits_preserved',true));
 return to_jsonb(r);
end$$;
revoke all on function public.research_review_experiment_plan_links(uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.research_review_experiment_plan_links(uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
