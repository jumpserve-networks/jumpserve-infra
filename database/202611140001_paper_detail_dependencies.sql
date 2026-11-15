begin;

-- Optional, section-local prerequisite references. Historical records are untouched.
create or replace function public.research_assert_paper_dependencies(b jsonb) returns void
language plpgsql immutable set search_path='' as $$
declare section text;items jsonb;entry jsonb;begin
 if b is null then return;end if;
 foreach section in array array['access','experiment','data','validate'] loop
  items=b->'sections'->section;
  if jsonb_typeof(items) is distinct from 'array' then raise exception 'Four paper sections required';end if;
  if jsonb_array_length(items)>200 then raise exception 'Paper detail bound exceeded';end if;
  if exists(select 1 from jsonb_array_elements(items) e where jsonb_typeof(e->'id') is distinct from 'string') or
   (select count(*)<>count(distinct e->>'id') from jsonb_array_elements(items) e) then raise exception 'Unique paper detail identities required';end if;
  for entry in select value from jsonb_array_elements(items) loop
   if not entry ? 'depends_on' then continue;end if;
   if jsonb_typeof(entry->'depends_on') is distinct from 'array' then raise exception 'Dependency list required';end if;
   if jsonb_array_length(entry->'depends_on')>7 or exists(select 1 from jsonb_array_elements(entry->'depends_on') d where jsonb_typeof(d)<>'string') or
    (select count(*)<>count(distinct value) from jsonb_array_elements(entry->'depends_on')) then raise exception 'Bounded unique dependency references required';end if;
   if exists(select 1 from jsonb_array_elements_text(entry->'depends_on') d where d.value=entry->>'id' or not exists(select 1 from jsonb_array_elements(items) e where e->>'id'=d.value)) then raise exception 'Dependencies must reference other retained details in the same section';end if;
  end loop;
  -- UNION deduplicates reachability pairs, avoiding exponential path enumeration.
  if exists(with recursive edges as (
    select e->>'id' as item,d.value as prerequisite from jsonb_array_elements(items) e
    cross join lateral jsonb_array_elements_text(coalesce(e->'depends_on','[]'::jsonb)) d
   ), reach(item,prerequisite) as (
    select item,prerequisite from edges union select r.item,e.prerequisite from reach r join edges e on e.item=r.prerequisite
   ) select 1 from reach where item=prerequisite) then raise exception 'Paper detail dependencies cannot form cycles';end if;
 end loop;
end$$;
revoke all on function public.research_assert_paper_dependencies(jsonb) from public,anon,authenticated;
grant execute on function public.research_assert_paper_dependencies(jsonb) to service_role;

create or replace function public.research_guard_paper_dependencies() returns trigger
language plpgsql set search_path='' as $$begin
 if tg_table_name='research_experiment_plans' then perform public.research_assert_paper_dependencies(new.confirmed_breakdown);
 else perform public.research_assert_paper_dependencies(new.breakdown);end if;
 return new;
end$$;
revoke all on function public.research_guard_paper_dependencies() from public,anon,authenticated;

drop trigger if exists paper_detail_dependencies on public.research_paper_intakes;
create trigger paper_detail_dependencies before insert or update of breakdown on public.research_paper_intakes
 for each row execute function public.research_guard_paper_dependencies();
drop trigger if exists paper_detail_dependencies on public.research_paper_breakdown_reviews;
create trigger paper_detail_dependencies before insert on public.research_paper_breakdown_reviews
 for each row execute function public.research_guard_paper_dependencies();
drop trigger if exists paper_detail_dependencies on public.research_experiment_plans;
create trigger paper_detail_dependencies before insert or update of confirmed_breakdown on public.research_experiment_plans
 for each row execute function public.research_guard_paper_dependencies();

-- Preserve the existing review checks; only the optional item whitelist expands.
create or replace function public.research_review_paper_breakdown(p_actor uuid,p_study uuid,p_payload jsonb) returns jsonb
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
   if jsonb_typeof(entry) is distinct from 'object' or not entry ?& array['id','description','quote','page','citations','kind','label','criterion','specification'] or entry-array['id','description','quote','page','citations','kind','label','criterion','specification','depends_on']<>'{}'::jsonb or jsonb_typeof(entry->'id') is distinct from 'string' or jsonb_typeof(entry->'description') is distinct from 'string' or length(btrim(coalesce(entry->>'id',''))) not between 1 and 100 or entry->>'id'=any(seen) or
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

-- Match planningSources exactly, translating immutable IDs to current confirmed refs.
create or replace function public.research_experiment_plan_input(b jsonb) returns jsonb language sql immutable set search_path='' as $$
 select jsonb_build_object('phase','confirmed-paper-breakdown-v1','sections',jsonb_object_agg(section,
  coalesce((select jsonb_agg(jsonb_build_object('ref',section||'-'||n,'description',entry->'description','quote',entry->'quote','page',entry->'page') ||
   case when entry ? 'citations' then jsonb_build_object('citations',entry->'citations','kind',entry->'kind','label',entry->'label','criterion',entry->'criterion','specification',entry->'specification') else '{}'::jsonb end ||
   case when entry ? 'depends_on' then jsonb_build_object('depends_on',coalesce((
    select jsonb_agg(section||'-'||target.n order by dep.position)
    from jsonb_array_elements_text(entry->'depends_on') with ordinality dep(ref,position)
    join jsonb_array_elements(b->'sections'->section) with ordinality target(item,n) on target.item->>'id'=dep.ref
   ),'[]'::jsonb)) else '{}'::jsonb end order by n)
   from jsonb_array_elements(b->'sections'->section) with ordinality e(entry,n)),'[]'::jsonb))) ||
  case when b ? 'provenance' then jsonb_build_object('provenance',b->'provenance','implementation_choices',b->'implementation_choices','reported_values_origin','paper_reported') else '{}'::jsonb end
 from unnest(array['access','experiment','data','validate']) section
$$;

commit;
