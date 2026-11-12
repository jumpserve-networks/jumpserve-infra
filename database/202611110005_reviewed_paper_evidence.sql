begin;

-- Original terminal intakes remain immutable. Operator document reviews are
-- separately versioned evidence, not new model calls or experiment executions.
create table public.research_paper_breakdown_reviews (
 id uuid primary key,study_id uuid not null references public.research_paper_intakes(study_id),owner_id uuid not null,
 revision integer not null,base_revision integer not null,original_revision integer not null,
 breakdown jsonb not null,reason text not null,reviewer_type text not null check(reviewer_type in ('AI','human')),
 method text not null default 'operator_document_review' check(method='operator_document_review'),
 prompt_version_id uuid not null references public.research_paper_prompt_versions(id),
 original_breakdown_sha256 text not null,model_calls integer not null default 0 check(model_calls=0),
 reserved_cents integer not null default 0 check(reserved_cents=0),created_at timestamptz not null default clock_timestamp(),
 unique(study_id,revision),check(revision=base_revision+1),check(original_revision<=base_revision)
);
alter table public.research_paper_breakdown_reviews enable row level security;
revoke all on public.research_paper_breakdown_reviews from public,anon,authenticated,service_role;
grant select on public.research_paper_breakdown_reviews to service_role;
create trigger assessment_active before insert or update on public.research_paper_breakdown_reviews for each row execute function public.research_require_active_assessment();
create trigger breakdown_reviews_immutable before update or delete on public.research_paper_breakdown_reviews for each row execute function public.research_immutable();

create function public.research_assert_paper_citations(citations jsonb,paper jsonb,minimum integer default 1) returns void
language plpgsql set search_path='' as $$declare c jsonb;source text;begin
 if jsonb_typeof(citations) is distinct from 'array' then raise exception 'Retained citations required';end if;
 if jsonb_array_length(citations)<minimum or jsonb_array_length(citations)>12 then raise exception 'Citation bounds exceeded';end if;
 if (select count(*)<>count(distinct value) from jsonb_array_elements(citations)) then raise exception 'Duplicate citation';end if;
 for c in select value from jsonb_array_elements(citations) loop
  if jsonb_typeof(c) is distinct from 'object' or not c ?& array['quote','page'] or c-array['quote','page']<>'{}'::jsonb or jsonb_typeof(c->'quote') is distinct from 'string' or length(btrim(c->>'quote')) not between 1 and 800 or jsonb_typeof(c->'page') is distinct from 'number' then raise exception 'Exact quote and PDF page required';end if;
  select p->>'text' into source from jsonb_array_elements(paper->'pages') p where p->'page'=c->'page';
  if source is null or position(c->>'quote' in source)=0 then raise exception 'Citation does not match retained original page text';end if;
 end loop;
end$$;

create function public.research_review_paper_breakdown(p_actor uuid,p_study uuid,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare i public.research_paper_intakes;r public.research_paper_breakdown_reviews;b jsonb;entry jsonb;choice jsonb;section text;seen text[]='{}';current_revision integer;prompt uuid;content jsonb;hash text;now_at timestamptz=clock_timestamp();begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_actor is null or public.research_assessment_deleted(p_study) or
  not exists(select 1 from auth.users u join auth.identities a on a.user_id=u.id where u.id=p_actor and not coalesce(u.is_anonymous,true) and a.provider='google') then raise exception 'Verified active Google owner required';end if;
 select * into i from public.research_paper_intakes where study_id=p_study for update;
 if i.study_id is null or i.owner_id<>p_actor or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private assessment not found';end if;
 select * into r from public.research_paper_breakdown_reviews where id=(p_payload->>'review_id')::uuid;
 if found then
  if r.study_id<>p_study or r.owner_id<>p_actor or r.base_revision<>(p_payload->>'base_revision')::integer or r.breakdown-'review' is distinct from (p_payload->'breakdown')-'review' or r.reason is distinct from p_payload->>'reason' or
   r.reviewer_type is distinct from p_payload->>'reviewer_type' or not exists(select 1 from public.research_paper_prompt_versions where id=r.prompt_version_id and instructions=p_payload->>'instructions') then raise exception 'Review identity conflicts with its original content';end if;
  return to_jsonb(r);
 end if;
 if i.status<>'ready' or i.paper_text is null then raise exception 'A ready original extraction and retained page text are required';end if;
 if exists(select 1 from public.research_experiment_plans where study_id=p_study) then raise exception 'Confirmed scope is frozen; preserve its original evidence and criteria';end if;
 select coalesce(max(revision),i.revision) into current_revision from public.research_paper_breakdown_reviews where study_id=p_study;
 if current_revision is distinct from (p_payload->>'base_revision')::integer then raise exception 'The reviewed version changed; reload before applying a correction';end if;
 b=p_payload->'breakdown';
 if jsonb_typeof(b) is distinct from 'object' or octet_length(b::text)>250000 or
  (b-array['sections','policy_sha256','provenance','implementation_choices','reported_values_origin','review']) is distinct from (i.breakdown-array['sections','policy_sha256','provenance','implementation_choices','reported_values_origin','review']) or
  b->>'reported_values_origin' is distinct from 'paper_reported' or jsonb_typeof(b->'sections') is distinct from 'object' or (b->'sections')-array['access','experiment','data','validate']<>'{}'::jsonb
 then raise exception 'Preserve original source identity, page coverage and reported-result separation';end if;
 if jsonb_typeof(p_payload->'instructions') is distinct from 'string' or length(p_payload->>'instructions') not between 1 and 40000 or
  b->>'policy_sha256' is distinct from encode(sha256(convert_to(p_payload->>'instructions','UTF8')),'hex') or
  length(btrim(coalesce(p_payload->>'reason',''))) not between 1 and 2000 or coalesce(p_payload->>'reviewer_type','') not in ('AI','human') then raise exception 'Record bounded review instructions, reviewer and reason';end if;
 foreach section in array array['access','experiment','data','validate'] loop
  if jsonb_typeof(b->'sections'->section) is distinct from 'array' then raise exception 'All four reviewed sections required';end if;
  if jsonb_array_length(b->'sections'->section)>8 then raise exception 'Section bound exceeded';end if;
  for entry in select value from jsonb_array_elements(b->'sections'->section) loop
   if jsonb_typeof(entry) is distinct from 'object' or not entry ?& array['id','description','quote','page','citations','kind','label','criterion','specification'] or entry-array['id','description','quote','page','citations','kind','label','criterion','specification']<>'{}'::jsonb or jsonb_typeof(entry->'id') is distinct from 'string' or jsonb_typeof(entry->'description') is distinct from 'string' or length(btrim(coalesce(entry->>'id',''))) not between 1 and 100 or entry->>'id'=any(seen) or
    length(btrim(coalesce(entry->>'description',''))) not between 1 and 400 or coalesce(entry->>'kind','') not in ('requirement','experiment_specification','reported_result','claim','limitation') then raise exception 'Bounded uniquely identified evidence details required';end if;
   if section='experiment' and entry->>'kind'<>'experiment_specification' or entry->>'kind'='experiment_specification' and section<>'experiment' or entry->>'kind'='claim' and section<>'validate' or entry->>'kind'='reported_result' and section<>'data' then raise exception 'Preserve specification, claim and reported-result roles';end if;
   if entry->'label' is distinct from 'null'::jsonb and (jsonb_typeof(entry->'label') is distinct from 'string' or length(btrim(entry->>'label')) not between 1 and 120) then raise exception 'Bounded label required';end if;
   if entry->>'kind'='experiment_specification' then
    if jsonb_typeof(entry->'specification') is distinct from 'object' or not (entry->'specification') ?& array['setup','conditions','procedure','comparisons'] or (entry->'specification')-array['setup','conditions','procedure','comparisons']<>'{}'::jsonb or exists(select 1 from jsonb_each(entry->'specification') t where jsonb_typeof(t.value)<>'string' or length(btrim(t.value#>>'{}')) not between 1 and 600 or btrim(t.value#>>'{}') !~ '[.!?]$') then raise exception 'Complete bounded experiment specification required';end if;
   elsif entry->'specification' is distinct from 'null'::jsonb then raise exception 'Only experiments have specifications';end if;
   seen=array_append(seen,entry->>'id');
   perform public.research_assert_paper_citations(entry->'citations',i.paper_text);
   if entry->'quote' is distinct from entry->'citations'->0->'quote' or entry->'page' is distinct from entry->'citations'->0->'page' then raise exception 'Primary citation must agree with retained supporting evidence';end if;
   if entry->>'kind'='claim' then
    if jsonb_typeof(entry->'criterion') is distinct from 'object' or not (entry->'criterion') ?& array['metric','comparison','target','acceptance','tolerance'] or (entry->'criterion')-array['metric','comparison','target','acceptance','tolerance']<>'{}'::jsonb or
     coalesce(entry->'criterion'->>'acceptance','') not in ('paper_defined','needs_definition') or
     exists(select 1 from unnest(array['metric','comparison','target']) key where jsonb_typeof(entry->'criterion'->key) is distinct from 'string' or length(btrim(coalesce(entry->'criterion'->>key,''))) not between 1 and 300) or
     (entry->'criterion'->'tolerance' is distinct from 'null'::jsonb and (jsonb_typeof(entry->'criterion'->'tolerance') is distinct from 'string' or length(btrim(entry->'criterion'->>'tolerance')) not between 1 and 200)) then raise exception 'Every claim needs its own bounded criterion';end if;
   elsif entry->'criterion' is distinct from 'null'::jsonb then raise exception 'Only claim details have criteria';end if;
  end loop;
 end loop;
 if cardinality(seen)>32 or jsonb_typeof(b->'provenance') is distinct from 'object' or not (b->'provenance') ?& array['classification','statement','citations'] or (b->'provenance')-array['classification','statement','citations']<>'{}'::jsonb or coalesce(b->'provenance'->>'classification','') not in ('synthetic','simulated','reported_empirical','unspecified') then raise exception 'Document provenance required';end if;
 if b->'provenance'->>'classification'='unspecified' then
  if b->'provenance'->'statement' is distinct from 'null'::jsonb or b->'provenance'->'citations' is distinct from '[]'::jsonb then raise exception 'Unknown provenance cannot assert unsupported evidence';end if;
 else
  if jsonb_typeof(b->'provenance'->'statement') is distinct from 'string' or length(btrim(coalesce(b->'provenance'->>'statement',''))) not between 1 and 400 then raise exception 'Document provenance statement required';end if;
  perform public.research_assert_paper_citations(b->'provenance'->'citations',i.paper_text);
 end if;
 if jsonb_typeof(b->'implementation_choices') is distinct from 'array' then raise exception 'Unresolved implementation choices required';end if;
 if jsonb_array_length(b->'implementation_choices')>8 then raise exception 'Implementation choice bound exceeded';end if;
 for choice in select value from jsonb_array_elements(b->'implementation_choices') loop
  if jsonb_typeof(choice) is distinct from 'object' or not choice ?& array['name','reason','citations'] or choice-array['name','reason','citations']<>'{}'::jsonb or jsonb_typeof(choice->'name') is distinct from 'string' or jsonb_typeof(choice->'reason') is distinct from 'string' or length(btrim(coalesce(choice->>'name',''))) not between 1 and 120 or length(btrim(coalesce(choice->>'reason',''))) not between 1 and 400 then raise exception 'Bounded implementation choice required';end if;
  perform public.research_assert_paper_citations(choice->'citations',i.paper_text);
 end loop;
 if (select count(*)<>count(distinct lower(btrim(value->>'name'))) from jsonb_array_elements(b->'implementation_choices')) then raise exception 'Duplicate implementation choice';end if;
 content=jsonb_build_object('instructions',p_payload->>'instructions','input_template',jsonb_build_object('source','{{retained_original_pdf_text}}','breakdown','{{original_phase_one_breakdown}}','review_findings','{{operator_document_review}}'),'request_configuration',jsonb_build_object('review_method','operator_document_review','reviewer_type',p_payload->>'reviewer_type','model_api_calls',0));
 hash=encode(sha256(convert_to(content::text,'UTF8')),'hex');
 insert into public.research_paper_prompt_versions(version,instructions,input_template,request_configuration,content_sha256,created_at)
  values('paper-assessment-'||hash,p_payload->>'instructions',content->'input_template',content->'request_configuration',hash,now_at) on conflict(content_sha256) do nothing;
 select id into strict prompt from public.research_paper_prompt_versions where content_sha256=hash;
 b=jsonb_set(b,'{review}',jsonb_build_object('id',p_payload->>'review_id','revision',current_revision+1,'reviewed_at',now_at,'reason',p_payload->>'reason','reviewer_type',p_payload->>'reviewer_type'));
 insert into public.research_paper_breakdown_reviews(id,study_id,owner_id,revision,base_revision,original_revision,breakdown,reason,reviewer_type,prompt_version_id,original_breakdown_sha256,created_at)
 values((p_payload->>'review_id')::uuid,p_study,p_actor,current_revision+1,current_revision,i.revision,b,p_payload->>'reason',p_payload->>'reviewer_type',prompt,encode(sha256(convert_to(i.breakdown::text,'UTF8')),'hex'),now_at) returning * into r;
 insert into public.research_audit_events(study_id,actor_id,action,details) values(p_study,p_actor,'review-paper-breakdown',jsonb_build_object('review_id',r.id,'revision',r.revision,'original_preserved',true,'model_api_calls',0,'experiments_started',0));
 return to_jsonb(r);
end$$;

create or replace function public.research_experiment_plan_input(b jsonb) returns jsonb language sql immutable set search_path='' as $$
 select jsonb_build_object('phase','confirmed-paper-breakdown-v1','sections',jsonb_object_agg(section,
  coalesce((select jsonb_agg(jsonb_build_object('ref',section||'-'||n,'description',entry->'description','quote',entry->'quote','page',entry->'page') ||
   case when entry ? 'citations' then jsonb_build_object('citations',entry->'citations','kind',entry->'kind','label',entry->'label','criterion',entry->'criterion','specification',entry->'specification') else '{}'::jsonb end order by n)
   from jsonb_array_elements(b->'sections'->section) with ordinality e(entry,n)),'[]'::jsonb))) ||
  case when b ? 'provenance' then jsonb_build_object('provenance',b->'provenance','implementation_choices',b->'implementation_choices','reported_values_origin','paper_reported') else '{}'::jsonb end
 from unnest(array['access','experiment','data','validate']) section
$$;

-- Remaining definitions are explicit replacements of the prior planning
-- functions, preserving legacy snapshots and original call/budget semantics.
create or replace function public.research_valid_experiment_plan(p jsonb,b jsonb) returns boolean language plpgsql immutable set search_path='' as $$
declare e jsonb;s jsonb;r text;refs text[];expected text[];covered text[]='{}';claims text[];checked text[]='{}';check_ref text;begin
 if jsonb_typeof(p) is distinct from 'object' or p-array['experiments']<>'{}'::jsonb or jsonb_typeof(p->'experiments') is distinct from 'array' then return false;end if;
 if jsonb_array_length(p->'experiments')>8 then return false;end if;
 select array_agg(v->>'ref') into refs from jsonb_each(public.research_experiment_plan_input(b)->'sections') t, jsonb_array_elements(t.value) v;
 select coalesce(array_agg('experiment-'||n),'{}'::text[]) into expected from jsonb_array_elements(b->'sections'->'experiment') with ordinality t(v,n);
 select coalesce(array_agg(v->>'ref'),'{}'::text[]) into claims from jsonb_array_elements(public.research_experiment_plan_input(b)->'sections'->'validate') v where v->>'kind'='claim';
 for e in select value from jsonb_array_elements(p->'experiments') loop
  if jsonb_typeof(e) is distinct from 'object' or e-array['title','experiment_refs','steps','open_questions']<>'{}'::jsonb or jsonb_typeof(e->'title') is distinct from 'string' or length(btrim(e->>'title')) not between 1 and 200 or
   jsonb_typeof(e->'experiment_refs') is distinct from 'array' or jsonb_typeof(e->'steps') is distinct from 'array' or jsonb_typeof(e->'open_questions') is distinct from 'array' then return false;end if;
  if jsonb_array_length(e->'experiment_refs') not between 1 and 8 or jsonb_array_length(e->'steps') not between 1 and 12 or jsonb_array_length(e->'open_questions')>12 then return false;end if;
  for r in select jsonb_array_elements_text(e->'experiment_refs') loop
   if r is null or not r=any(expected) or r=any(covered) then return false;end if;covered=array_append(covered,r);
  end loop;
  if exists(select 1 from jsonb_array_elements(e->'open_questions') q where jsonb_typeof(q)<>'string' or length(btrim(q#>>'{}')) not between 1 and 400) then return false;end if;
  for s in select value from jsonb_array_elements(e->'steps') loop
   if jsonb_typeof(s) is distinct from 'object' or s-array['title','instructions','basis','source_refs','validation_ref']<>'{}'::jsonb or jsonb_typeof(s->'title') is distinct from 'string' or length(btrim(s->>'title')) not between 1 and 160 or
    jsonb_typeof(s->'instructions') is distinct from 'string' or length(btrim(s->>'instructions')) not between 1 and 1200 or coalesce(s->>'basis','') not in ('paper','proposed') or jsonb_typeof(s->'source_refs') is distinct from 'array' then return false;end if;
   if jsonb_array_length(s->'source_refs')>32 or s->>'basis'='paper' and jsonb_array_length(s->'source_refs')=0 then return false;end if;
   if exists(select 1 from jsonb_array_elements(s->'source_refs') source_ref where jsonb_typeof(source_ref.value) is distinct from 'string') or
    exists(select 1 from jsonb_array_elements_text(s->'source_refs') source_ref where not source_ref.value=any(coalesce(refs,'{}'::text[]))) or
    (select count(*)<>count(distinct value) from jsonb_array_elements_text(s->'source_refs')) then return false;end if;
   check_ref=s->>'validation_ref';
   if check_ref is not null then
    if not check_ref=any(claims) or check_ref=any(checked) or not (s->'source_refs') ? check_ref then return false;end if;checked=array_append(checked,check_ref);
   end if;
  end loop;
 end loop;
 return cardinality(covered)=cardinality(expected) and (cardinality(expected)=0 or cardinality(checked)=cardinality(claims));
end$$;

create or replace function public.research_experiment_plan(p_operation text,p_actor uuid,p_study uuid,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare i public.research_paper_intakes;p public.research_experiment_plans;w public.research_autonomy_workflows;
 b jsonb;entry jsonb;original jsonb;section text;seen text[];spent bigint=0;calls bigint=0;request jsonb;configuration jsonb;template jsonb;content jsonb;hash text;prompt uuid;review_revision integer;review_breakdown jsonb;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_actor is null or not exists(select 1 from auth.users u join auth.identities a on a.user_id=u.id where u.id=p_actor and not coalesce(u.is_anonymous,true) and a.provider='google') then raise exception 'Verified Google owner required';end if;
 if public.research_assessment_deleted(p_study) then raise exception 'Assessment not found';end if;
 select * into i from public.research_paper_intakes where study_id=p_study for update;
 if i.study_id is null or i.owner_id<>p_actor or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private paper assessment not found';end if;
 select * into p from public.research_experiment_plans where study_id=p_study for update;
 if p.study_id is null then
  select revision,breakdown into review_revision,review_breakdown from public.research_paper_breakdown_reviews where study_id=p_study order by revision desc limit 1;
  if found then i.revision=review_revision;i.breakdown=review_breakdown;end if;
 end if;
 if p_operation='confirm' then
  if i.status<>'ready' then raise exception 'Phase one must be ready before confirmation';end if;
  b=p_payload->'confirmed_breakdown';
  if p.study_id is not null then
   if p.intake_revision is distinct from (p_payload->>'intake_revision')::integer or p.confirmed_breakdown is distinct from b then raise exception 'Phase one was already confirmed with different information';end if;
   return to_jsonb(p)||'{"admitted":false}'::jsonb;
  end if;
  if i.revision is distinct from (p_payload->>'intake_revision')::integer then raise exception 'The phase-one revision changed; reload and review it before confirming';end if;
  if jsonb_typeof(b) is distinct from 'object' or b-array['sections'] is distinct from i.breakdown-array['sections'] or jsonb_typeof(b->'sections') is distinct from 'object' or (b->'sections')-array['access','experiment','data','validate']<>'{}'::jsonb then raise exception 'Confirm the original four-section breakdown';end if;
  foreach section in array array['access','experiment','data','validate'] loop
   if jsonb_typeof(b->'sections'->section) is distinct from 'array' then raise exception 'Review all four sections';end if;
   seen='{}';
   for entry in select value from jsonb_array_elements(b->'sections'->section) loop
    select value into original from jsonb_array_elements(i.breakdown->'sections'->section) where value->>'id'=entry->>'id';
    if original is null or entry-array['description'] is distinct from original-array['description'] or jsonb_typeof(entry->'description') is distinct from 'string' or length(btrim(entry->>'description')) not between 1 and 400 or entry->>'id'=any(seen) then raise exception 'Only inclusion and descriptions may change; retain original quotes and PDF pages';end if;
    seen=array_append(seen,entry->>'id');
   end loop;
  end loop;
  if i.deadline_at<=clock_timestamp() then raise exception 'The original assessment deadline has expired';end if;
  request=nullif(p_payload->'request','null'::jsonb);
  if jsonb_array_length(b->'sections'->'experiment')=0 then
   if request is not null then raise exception 'No model call is needed when no experiments are confirmed';end if;
   insert into public.research_experiment_plans(study_id,owner_id,intake_revision,confirmed_breakdown,deadline_at,status,plan,reason,reserved_cents,model_calls)
    values(p_study,p_actor,i.revision,b,i.deadline_at,'ready','{"experiments":[]}','No experiments were included in the confirmed sections.',0,0) returning * into p;
   return to_jsonb(p)||'{"admitted":false}'::jsonb;
  end if;
  if jsonb_typeof(request) is distinct from 'object' or request->>'model' is distinct from 'gpt-5.4-mini-2026-03-17' or request->'background' is distinct from 'true'::jsonb or request->'store' is distinct from 'true'::jsonb or
   jsonb_typeof(request->'instructions') is distinct from 'string' or length(request->>'instructions') not between 1 and 40000 or jsonb_typeof(request->'input') is distinct from 'string' or
   octet_length(request::text)>160000 or exists(select 1 from jsonb_object_keys(request) k where k not in ('model','instructions','input','background','store','reasoning','max_output_tokens','text')) then raise exception 'A bounded server-side planning request is required';end if;
  if (request->>'input')::jsonb is distinct from public.research_experiment_plan_input(b) or coalesce(request->'text'->'format'->>'name','') not in ('paper_experiment_steps_v1','paper_experiment_steps_v2') then raise exception 'Plan only from the exact confirmed sections';end if;
  select * into w from public.research_autonomy_workflows where study_id=p_study;
  if found then
   spent=w.committed_cents;select coalesce(sum(attempts),0) into calls from public.research_autonomy_tasks where study_id=p_study;
   if w.max_spend_cents is not null and spent+i.reserved_cents+100>w.max_spend_cents then raise exception 'The original assessment spending limit does not admit planning';end if;
  end if;
  if not public.autonomy_budget_allows('research_assessment',spent+i.reserved_cents,calls+i.model_calls,100,1) then raise exception 'The assessment budget does not admit this planning call';end if;
  insert into public.research_experiment_plans(study_id,owner_id,intake_revision,confirmed_breakdown,deadline_at,status,submit_token,request,reserved_cents,model_calls,policy_snapshot,reason)
   values(p_study,p_actor,i.revision,b,i.deadline_at,'submitting',gen_random_uuid(),request,100,1,public.autonomy_assessment_budget_terms(),'Submitting experiment implementation planning.') returning * into p;
  -- Catalogue only a generic template/configuration. The confirmed content,
  -- full request, response and usage remain private and linked to this study.
  configuration=request-array['input','instructions'];
  template='{"phase":"confirmed-paper-breakdown-v1","sections":{"access":"{{confirmed_access_details_with_source_quotes}}","experiment":"{{confirmed_experiment_details_with_source_quotes}}","data":"{{confirmed_data_details_with_source_quotes}}","validate":"{{confirmed_validate_details_with_source_quotes}}"}}'::jsonb;
  content=jsonb_build_object('instructions',request->>'instructions','input_template',template,'request_configuration',configuration);
  hash=encode(sha256(convert_to(content::text,'UTF8')),'hex');
  insert into public.research_paper_prompt_versions(version,instructions,input_template,request_configuration,content_sha256,created_at)
   values('paper-assessment-'||hash,request->>'instructions',template,configuration,hash,p.confirmed_at) on conflict(content_sha256) do nothing;
  select id into strict prompt from public.research_paper_prompt_versions where content_sha256=hash;
  insert into public.research_experiment_plan_prompt_uses values(p_study,prompt,encode(sha256(convert_to(request::text,'UTF8')),'hex'),p.confirmed_at);
  return to_jsonb(p)||'{"admitted":true}'::jsonb;
 end if;
 if p.study_id is null then raise exception 'Confirm phase one before planning';end if;
 if p.submit_token is distinct from (p_payload->>'token')::uuid then raise exception 'Original planning call token required';end if;
 if p_operation='submitted' then
  if p.provider_response_id is not null then
   if p.provider_response_id is distinct from p_payload->>'response_id' then raise exception 'Original provider identity cannot change';end if;return to_jsonb(p);
  end if;
  if p.status not in ('submitting','uncertain') or coalesce(p_payload->>'response_id','') !~ '^resp_[A-Za-z0-9_-]{1,200}$' then raise exception 'Original submitting planning call required';end if;
  update public.research_experiment_plans set status='processing',provider_response_id=p_payload->>'response_id',response=p_payload->'response',reason='Preparing implementation steps.' where study_id=p_study returning * into p;return to_jsonb(p);
 end if;
 if p.status in ('ready','failed','cancelled') then return to_jsonb(p);end if;
 if p_operation='uncertain' then
  if p.provider_response_id is not null then return to_jsonb(p);end if;
  update public.research_experiment_plans set status='uncertain',reason=left(p_payload->>'reason',2000) where study_id=p_study returning * into p;return to_jsonb(p);
 end if;
 if p_operation='finish' then
  if p.status<>'processing' or p.provider_response_id is distinct from p_payload->>'response_id' or p_payload->'response'->>'id' is distinct from p.provider_response_id or p_payload->'response'->>'status' is distinct from 'completed' or not public.research_valid_experiment_plan(p_payload->'plan',p.confirmed_breakdown) then raise exception 'Verified original response and complete source-bound plan required';end if;
  update public.research_experiment_plans set status='ready',plan=p_payload->'plan',response=p_payload->'response',reason=null where study_id=p_study returning * into p;return to_jsonb(p);
 end if;
 if p_operation in ('failed','cancel') then
  if p_operation='cancel' and (p.provider_response_id is null or p_payload->'response'->>'id' is distinct from p.provider_response_id or p_payload->'response'->>'status' is distinct from 'cancelled') then raise exception 'Confirmed provider cancellation required';end if;
  if p.status='uncertain' then raise exception 'Reconcile the uncertain provider call before stopping';end if;
  update public.research_experiment_plans set status=case when p_operation='cancel' then 'cancelled' else 'failed' end,response=coalesce(p_payload->'response',response),reason=left(p_payload->>'reason',2000) where study_id=p_study returning * into p;return to_jsonb(p);
 end if;
 raise exception 'Unknown experiment planning operation';
end$$;
revoke all on function public.research_assert_paper_citations(jsonb,jsonb,integer) from public,anon,authenticated,service_role;
revoke all on function public.research_review_paper_breakdown(uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.research_review_paper_breakdown(uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
