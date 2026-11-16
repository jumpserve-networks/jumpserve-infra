begin;
-- Keep the provider schema, prompt, TypeScript and SQL hierarchy bounds aligned:
-- 8 stages x 8 independently implementable actions = at most 64 actions.
-- The old aggregate 24-action cap rejected otherwise bounded granular plans.
-- This changes organizational capacity only: exact source/claim coverage,
-- instruction limits and the legacy 12-action flat contract remain enforced.
-- Existing failed calls are NOT rewritten or retried. A completed response with
-- duplicate validation assignments still needs the explicit immutable link review.
-- Confirmation, original output, deadlines, reservations and model-call counts
-- remain unchanged. No inference, worker or experiment is dispatched.
create or replace function public.research_valid_flat_experiment_plan(p jsonb,b jsonb) returns boolean language plpgsql immutable set search_path='' as $$
declare e jsonb;s jsonb;r text;refs text[];expected text[];covered text[]='{}';claims text[];checked text[]='{}';check_ref text;begin
 if jsonb_typeof(p) is distinct from 'object' or p-array['experiments']<>'{}'::jsonb or jsonb_typeof(p->'experiments') is distinct from 'array' then return false;end if;
 if jsonb_array_length(p->'experiments')>8 then return false;end if;
 select array_agg(v->>'ref') into refs from jsonb_each(public.research_experiment_plan_input(b)->'sections') t, jsonb_array_elements(t.value) v;
 select coalesce(array_agg('experiment-'||n),'{}'::text[]) into expected from jsonb_array_elements(b->'sections'->'experiment') with ordinality t(v,n);
 select coalesce(array_agg(v->>'ref'),'{}'::text[]) into claims from jsonb_array_elements(public.research_experiment_plan_input(b)->'sections'->'validate') v where v->>'kind'='claim';
 for e in select value from jsonb_array_elements(p->'experiments') loop
  if jsonb_typeof(e) is distinct from 'object' or e-array['title','experiment_refs','steps','open_questions']<>'{}'::jsonb or jsonb_typeof(e->'title') is distinct from 'string' or length(btrim(e->>'title')) not between 1 and 200 or
   jsonb_typeof(e->'experiment_refs') is distinct from 'array' or jsonb_typeof(e->'steps') is distinct from 'array' or jsonb_typeof(e->'open_questions') is distinct from 'array' then return false;end if;
  if jsonb_array_length(e->'experiment_refs') not between 1 and 8 or jsonb_array_length(e->'steps') not between 1 and 64 or jsonb_array_length(e->'open_questions')>12 then return false;end if;
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

create or replace function public.research_valid_experiment_plan(p jsonb,b jsonb) returns boolean
language plpgsql immutable set search_path='' as $$
declare e jsonb;stage jsonb;action jsonb;actions jsonb;experiments jsonb='[]';layout text;current_layout text;begin
 if jsonb_typeof(p) is distinct from 'object' or p-array['experiments']<>'{}'::jsonb or jsonb_typeof(p->'experiments') is distinct from 'array' then return false;end if;
 if jsonb_array_length(p->'experiments')>8 then return false;end if;
 for e in select value from jsonb_array_elements(p->'experiments') loop
  if jsonb_typeof(e) is distinct from 'object' then return false;end if;
  current_layout=case when e ? 'stages' then 'hierarchical' else 'flat' end;
  if layout is not null and layout<>current_layout then return false;end if;layout=current_layout;
  if current_layout='hierarchical' then
   if e-array['title','experiment_refs','stages','open_questions']<>'{}'::jsonb or jsonb_typeof(e->'stages') is distinct from 'array' then return false;end if;
   if jsonb_array_length(e->'stages') not between 1 and 8 then return false;end if;
   actions='[]'::jsonb;
   for stage in select value from jsonb_array_elements(e->'stages') loop
    if jsonb_typeof(stage) is distinct from 'object' or stage-array['title','steps']<>'{}'::jsonb or jsonb_typeof(stage->'title') is distinct from 'string' or
     length(btrim(stage->>'title')) not between 1 and 160 or jsonb_typeof(stage->'steps') is distinct from 'array' then return false;end if;
    if jsonb_array_length(stage->'steps') not between 1 and 8 then return false;end if;
    for action in select value from jsonb_array_elements(stage->'steps') loop
     if jsonb_typeof(action) is distinct from 'object' or not action ? 'validation_ref' or jsonb_typeof(action->'validation_ref') not in ('null','string') or
      jsonb_typeof(action->'instructions') is distinct from 'string' or length(btrim(action->>'instructions')) not between 1 and 800 then return false;end if;
    end loop;
    actions=actions||(stage->'steps');
   end loop;
   if jsonb_array_length(actions)>64 then return false;end if;
   experiments=experiments||jsonb_build_array((e-'stages')||jsonb_build_object('steps',actions));
  else
   -- Preserve the historical bound instead of expanding old flat contracts.
   if jsonb_typeof(e->'steps') is distinct from 'array' then return false;end if;
   if jsonb_array_length(e->'steps') not between 1 and 12 then return false;end if;
   experiments=experiments||jsonb_build_array(e);
  end if;
 end loop;
 return public.research_valid_flat_experiment_plan(jsonb_build_object('experiments',experiments),b);
end$$;

revoke all on function public.research_valid_flat_experiment_plan(jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.research_valid_flat_experiment_plan(jsonb,jsonb) to service_role;
revoke all on function public.research_valid_experiment_plan(jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.research_valid_experiment_plan(jsonb,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
