begin;
-- Add review context without changing original sources, terminal decisions,
-- reservations, rounds, deadlines or uncertain submission identities.
create index if not exists research_quality_workflow_events on public.research_paper_quality_events(workflow_id,id);
create or replace function public.research_quality_review_context(w public.research_paper_quality_workflows) returns jsonb language sql stable set search_path='' as $$
 with reviews as (
  select distinct on (c.position) c.position,e.snapshot
  from public.research_paper_quality_calls c
  join public.research_paper_quality_events e on e.workflow_id=c.workflow_id
   and e.kind='research_paper_quality_workflows' and e.snapshot->>'current_call_id'=c.id::text
   and e.snapshot->>'status' in ('repair_pending','approved','needs_attention') and e.snapshot->'review' is not null
  where c.workflow_id=w.id and c.kind='review' and c.status='completed'
  order by c.position,e.id desc
 ), findings as (
  select r.position,'review' as kind,f.value,f.ordinality from reviews r cross join lateral jsonb_array_elements(r.snapshot->'review'->'findings') with ordinality f
  union all
  select r.position,'check' as kind,f.value,f.ordinality from reviews r cross join lateral jsonb_array_elements(r.snapshot->'checks'->'findings') with ordinality f
 )
 select jsonb_build_object(
  'version','paper-quality-context-v1',
  'generation_instructions',w.original_request->'instructions','generation_input',w.original_request->'input',
  'reference_map',coalesce((select jsonb_object_agg(s.key||'-'||d.ordinality,d.value->>'id')
   from jsonb_each(case when jsonb_typeof(w.source_json->'confirmed_breakdown'->'sections')='object' then w.source_json->'confirmed_breakdown'->'sections' else '{}'::jsonb end) s
   cross join lateral jsonb_array_elements(s.value) with ordinality d),'{}'::jsonb),
  'finding_ledger',coalesce((select jsonb_agg(jsonb_build_object('key',kind||'-'||position||':'||(value->>'id'),'finding',value) order by position,kind,ordinality) from findings),'[]'::jsonb),
  'prior_resolutions',coalesce(w.review->'resolutions','[]'::jsonb),
  'previous_candidate',(select (c.request->>'input')::jsonb->'previous_output' from public.research_paper_quality_calls c where c.workflow_id=w.id and c.kind='repair' and c.status='completed' order by c.position desc limit 1)
 )
$$;
create or replace function public.research_quality_result(workflow uuid) returns jsonb language sql stable set search_path='' as $$
 select to_jsonb(w)||jsonb_build_object('call',(select to_jsonb(c) from public.research_paper_quality_calls c where c.id=w.current_call_id and c.workflow_id=w.id),'admitted',false,'review_context',public.research_quality_review_context(w)) from public.research_paper_quality_workflows w where w.id=workflow
$$;

-- Preserve validation of frozen v1 responses, including already submitted calls.
do $$declare body text;begin
 if to_regprocedure('public.research_valid_quality_review_v1(jsonb)') is null then
  select prosrc into strict body from pg_proc where oid='public.research_valid_quality_review(jsonb)'::regprocedure;
  execute 'create function public.research_valid_quality_review_v1(v jsonb) returns boolean language plpgsql immutable set search_path='''' as '||quote_literal(body);
 end if;
end$$;
create or replace function public.research_valid_quality_review(v jsonb) returns boolean language plpgsql immutable set search_path='' as $$
declare r jsonb;begin
 if not (v ? 'resolutions') then return public.research_valid_quality_review_v1(v);end if;
 if not public.research_valid_quality_review_v1(v-'resolutions') or jsonb_typeof(v->'resolutions') is distinct from 'array' or jsonb_array_length(v->'resolutions')>128 then return false;end if;
 if (select count(*)<>count(distinct value->>'key') from jsonb_array_elements(v->'resolutions')) then return false;end if;
 for r in select value from jsonb_array_elements(v->'resolutions') loop
  if jsonb_typeof(r) is distinct from 'object' or not r ?& array['key','status','evidence'] or r-array['key','status','evidence']<>'{}'::jsonb or exists(select 1 from jsonb_each(r) where jsonb_typeof(value)<>'string') or length(btrim(r->>'key')) not between 1 and 100 or coalesce(r->>'status','') not in ('resolved','open','dismissed') or length(btrim(r->>'evidence')) not between 1 and 2000 then return false;end if;
 end loop;
 return true;
exception when others then return false;
end$$;
create or replace function public.research_valid_quality_resolutions(report jsonb,context jsonb) returns boolean language plpgsql immutable set search_path='' as $$
begin
 if not public.research_valid_quality_review(report) or jsonb_typeof(report->'resolutions') is distinct from 'array' or context->>'version' is distinct from 'paper-quality-context-v1' or jsonb_typeof(context->'finding_ledger') is distinct from 'array' or jsonb_array_length(report->'resolutions')<>jsonb_array_length(context->'finding_ledger') then return false;end if;
 if exists(select 1 from jsonb_array_elements(context->'finding_ledger') f where not exists(select 1 from jsonb_array_elements(report->'resolutions') r where r->>'key'=f->>'key')) then return false;end if;
 if report->>'decision'='pass' and exists(select 1 from jsonb_array_elements(context->'finding_ledger') f join jsonb_array_elements(report->'resolutions') r on r->>'key'=f->>'key' where f->'finding'->>'severity'='blocking' and r->>'status'='open') then return false;end if;
 return true;
exception when others then return false;
end$$;

-- Patch exact qualified anchors. All other privacy, sandbox, budget, deadline,
-- admission, cancellation and original-response checks remain unchanged.
do $$
declare body text;old_text text;new_text text;patch jsonb;begin
 select prosrc into strict body from pg_proc where oid='public.research_paper_quality_control(text,uuid,uuid,jsonb)'::regprocedure;
 for patch in select value from jsonb_array_elements(jsonb_build_array(
  jsonb_build_array(
   $old$if p_operation='admit' then$old$,
   $new$if p_operation='context' then return public.research_quality_result(w.id);end if;
 if p_operation='admit' then$new$),
  jsonb_build_array(
   $old$hash,cost,public.autonomy_assessment_budget_terms(),w.deadline_at) returning * into c;$old$,
   $new$hash,cost,public.autonomy_assessment_budget_terms()||jsonb_build_object('quality_context',coalesce(p_payload->>'review_context_version'='paper-quality-context-v1',false)),w.deadline_at) returning * into c;$new$),
  jsonb_build_array(
   $old$if c.kind='repair' then
   if input->'original_input'$old$,
   $new$if c.policy_snapshot->'quality_context'='true'::jsonb or input ? 'review_context' or request->'text'->'format'->>'name'='paper_quality_review_v2' then
   if input->'review_context' is distinct from public.research_quality_review_context(w) then raise exception 'The complete original generation contract, canonical references and cumulative findings are required';end if;
   if c.kind='review' and request->'text'->'format'->>'name' is distinct from 'paper_quality_review_v2' then raise exception 'New reviews require explicit prior-finding resolutions';end if;
   if c.kind='repair' and input->'prior_resolutions' is distinct from coalesce(w.review->'resolutions','[]'::jsonb) then raise exception 'Retain the previous finding resolutions during repair';end if;
  end if;
  if c.kind='repair' then
   if input->'original_input'$new$),
  jsonb_build_array(
   $old$if request->'text'->'format'->>'name' is distinct from 'paper_quality_review_v1' then$old$,
   $new$if coalesce(request->'text'->'format'->>'name','') not in ('paper_quality_review_v1','paper_quality_review_v2') then$new$),
  jsonb_build_array(
   $old$report=p_payload->'review';$old$,
   $new$report=p_payload->'review';
  if c.request->'text'->'format'->>'name'='paper_quality_review_v2' and not public.research_valid_quality_resolutions(report,(c.request->>'input')::jsonb->'review_context') then raise exception 'Every earlier finding needs evidence and open blockers cannot pass';end if;$new$),
  jsonb_build_array(
   $old$'findings','{{prior_quality_findings}}')$old$,
   $new$'findings','{{prior_quality_findings}}','review_context','{{private_original_contract_reference_map_and_cumulative_findings}}','prior_resolutions','{{private_prior_resolutions}}')$new$)
 )) loop
  old_text=patch->>0;new_text=patch->>1;
  if position(new_text in body)>0 then continue;end if;
  if position(old_text in body)=0 or length(body)-length(replace(body,old_text,''))<>length(old_text) then raise exception 'Review context migration needs one exact qualified control anchor';end if;
  body=replace(body,old_text,new_text);
 end loop;
 execute 'create or replace function public.research_paper_quality_control(p_operation text,p_actor uuid,p_workflow uuid,p_payload jsonb default ''{}'') returns jsonb language plpgsql security definer set search_path='''' as '||quote_literal(body);
end$$;
revoke all on function public.research_quality_review_context(public.research_paper_quality_workflows),public.research_quality_result(uuid),public.research_valid_quality_review_v1(jsonb),public.research_valid_quality_review(jsonb),public.research_valid_quality_resolutions(jsonb,jsonb),public.research_paper_quality_control(text,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.research_paper_quality_control(text,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
