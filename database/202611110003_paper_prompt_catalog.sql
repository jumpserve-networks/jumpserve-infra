begin;

-- These are immutable snapshots of templates actually admitted for paper
-- assessment. They are not agent-chat publications or evaluation approvals.
create table public.research_paper_prompt_versions (
 id uuid primary key default gen_random_uuid(),
 version text not null unique,
 instructions text not null check(length(instructions) between 1 and 40000),
 input_template jsonb not null check(jsonb_typeof(input_template)='object'),
 request_configuration jsonb not null check(jsonb_typeof(request_configuration)='object'),
 content_sha256 text not null unique check(content_sha256 ~ '^[a-f0-9]{64}$'),
 created_at timestamptz not null,
 check(version='paper-assessment-'||content_sha256)
);
create table public.research_paper_prompt_uses (
 study_id uuid primary key references public.research_paper_intakes(study_id),
 prompt_version_id uuid not null references public.research_paper_prompt_versions(id),
 request_sha256 text not null check(request_sha256 ~ '^[a-f0-9]{64}$'),
 recorded_at timestamptz not null
);
create index paper_prompt_uses_version on public.research_paper_prompt_uses(prompt_version_id);
alter table public.research_paper_prompt_versions enable row level security;
alter table public.research_paper_prompt_uses enable row level security;
revoke all on public.research_paper_prompt_versions,public.research_paper_prompt_uses from public,anon,authenticated,service_role;
grant select on public.research_paper_prompt_versions,public.research_paper_prompt_uses to service_role;
create trigger paper_prompt_version_immutable before update or delete on public.research_paper_prompt_versions for each row execute function public.research_immutable();
create trigger paper_prompt_use_immutable before update or delete on public.research_paper_prompt_uses for each row execute function public.research_immutable();

create function public.research_record_paper_prompt(p_study uuid,p_request jsonb,p_observed_at timestamptz)
returns uuid language plpgsql security definer set search_path='' as $$
declare configuration jsonb;input_value jsonb;template jsonb;content jsonb;hash text;request_hash text;
 version public.research_paper_prompt_versions;usage public.research_paper_prompt_uses;begin
 if jsonb_typeof(p_request) is distinct from 'object' or
  jsonb_typeof(p_request->'instructions') is distinct from 'string' or length(p_request->>'instructions') not between 1 and 40000 or
  jsonb_typeof(p_request->'input') is distinct from 'string' or p_observed_at is null or
  exists(select 1 from jsonb_object_keys(p_request) k where k not in ('instructions','input','model','background','store','reasoning','max_output_tokens','text'))
 then raise exception 'A bounded paper request with separate instructions and input is required';end if;
 input_value=(p_request->>'input')::jsonb;
 if jsonb_typeof(input_value) is distinct from 'object' or
  input_value->>'source' is distinct from 'Original PDF text, in PDF page order' or
  jsonb_typeof(input_value->'pages') is distinct from 'array' or
  exists(select 1 from jsonb_object_keys(input_value) k where k not in ('source','pages'))
 then raise exception 'The original page-text input boundary could not be verified';end if;
 configuration=p_request-array['input','instructions'];
 -- Never copy the uploaded paper, title, account, source locations or answers
 -- to the template catalogue. The complete original request stays private.
 template='{"source":"Original PDF text, in PDF page order","pages":[{"page":"{{pdf_page_number}}","text":"{{original_extracted_page_text}}"}]}'::jsonb;
 content=jsonb_build_object('instructions',p_request->>'instructions','input_template',template,'request_configuration',configuration);
 hash=encode(sha256(convert_to(content::text,'UTF8')),'hex');
 request_hash=encode(sha256(convert_to(p_request::text,'UTF8')),'hex');
 insert into public.research_paper_prompt_versions(version,instructions,input_template,request_configuration,content_sha256,created_at)
  values('paper-assessment-'||hash,p_request->>'instructions',template,configuration,hash,p_observed_at)
  on conflict(content_sha256) do nothing;
 select * into strict version from public.research_paper_prompt_versions where content_sha256=hash;
 if version.instructions is distinct from p_request->>'instructions' or version.input_template is distinct from template or version.request_configuration is distinct from configuration
 then raise exception 'Recorded prompt identity conflicts with its content';end if;
 insert into public.research_paper_prompt_uses(study_id,prompt_version_id,request_sha256,recorded_at)
  values(p_study,version.id,request_hash,p_observed_at) on conflict(study_id) do nothing;
 select * into strict usage from public.research_paper_prompt_uses where study_id=p_study;
 if usage.prompt_version_id<>version.id or usage.request_sha256<>request_hash then raise exception 'Assessment already records a different original prompt';end if;
 return version.id;
end $$;

-- Link historical requests without updating immutable terminal intakes/events.
-- Recorded timestamps come from the original retained request event.
do $$declare row record;begin
 for row in select i.study_id,i.request,coalesce((select min(e.created_at) from public.research_paper_intake_events e
  where e.study_id=i.study_id and e.snapshot->'request'=i.request),i.updated_at) as observed_at
  from public.research_paper_intakes i where i.request is not null order by observed_at,i.study_id loop
  perform public.research_record_paper_prompt(row.study_id,row.request,row.observed_at);
 end loop;
end $$;

create function public.research_capture_paper_prompt() returns trigger
language plpgsql security definer set search_path='' as $$begin
 if new.request is null then return new;end if;
 if tg_op='UPDATE' and new.request is not distinct from old.request then return new;end if;
 perform public.research_record_paper_prompt(new.study_id,new.request,new.updated_at);
 return new;
end $$;
-- The original intake admission, exact request and version link commit together
-- before Next.js (or the operator CLI) can submit a model request.
create trigger paper_intake_prompt_capture after insert or update on public.research_paper_intakes
 for each row execute function public.research_capture_paper_prompt();
revoke all on function public.research_record_paper_prompt(uuid,jsonb,timestamptz),public.research_capture_paper_prompt() from public,anon,authenticated,service_role;
notify pgrst,'reload schema';
commit;
