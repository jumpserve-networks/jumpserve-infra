begin;

create table public.research_studies (
 id uuid primary key, title text not null check(length(title) between 1 and 300),
 paper_url text not null, domain text not null, scope text not null,
 origin_module text, created_at timestamptz not null default clock_timestamp()
);
create table public.research_study_owners (
 study_id uuid primary key references public.research_studies(id), owner_id uuid not null
);
create table public.research_sources (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 citation text not null, source_url text, retrieved_url text, kind text not null,
 role text not null, retrieved_version text, sha256 text check(sha256 ~ '^[a-f0-9]{64}$'),
 byte_count bigint check(byte_count>=0), access_status text not null,
 review_status text not null check(review_status in ('complete-review','partial-review','retrieved-unreviewed','unavailable-full-text')),
 review_definition text not null, examined text not null, unexamined text not null,
 retrieval_attempts jsonb not null, reviewer jsonb not null, findings text not null,
 limitations text not null, created_at timestamptz not null default clock_timestamp(), unique(study_id,id)
);
create table public.research_claims (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 source_id uuid not null, location text not null, description text not null,
 claim_type text not null check(claim_type in ('numerical','algorithm','association','causal','generalization','operational','theory','standard')),
 scope jsonb not null, metrics jsonb not null, priority integer not null check(priority between 1 and 5),
 created_at timestamptz not null default clock_timestamp(), unique(study_id,id),
 foreign key(study_id,source_id) references public.research_sources(study_id,id)
);
create table public.research_protocols (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 version integer not null check(version>0), supersedes_id uuid,
 document jsonb not null check(jsonb_typeof(document)='object'),
 sha256 text not null check(sha256 ~ '^[a-f0-9]{64}$'),
 frozen_at timestamptz not null, registration_kind text not null check(registration_kind in ('prospective','retrospective-import')),
 amendment_reason text, created_at timestamptz not null default clock_timestamp(), unique(study_id,id),
 foreign key(study_id,supersedes_id) references public.research_protocols(study_id,id),
 check((supersedes_id is null and version=1) or (supersedes_id is not null and version>1 and amendment_reason is not null and length(amendment_reason)>0))
);
create table public.research_configurations (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 identity text not null, details jsonb not null, input_versions jsonb not null,
 requested_resources jsonb not null, created_at timestamptz not null default clock_timestamp(), unique(study_id,id)
);
create table public.research_campaigns (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 protocol_id uuid not null, followup_of uuid, title text not null,
 stage text not null check(stage in ('pilot','main','follow-up','retrospective-import')),
 experiment_type text not null check(experiment_type in ('reanalysis','author-implementation','independent-check','new-measurement','broader-validation','source-review')),
 adapter text not null, planned_units integer not null check(planned_units>=0),
 coverage_limits text not null, created_at timestamptz not null default clock_timestamp(), unique(study_id,id),
 foreign key(study_id,protocol_id) references public.research_protocols(study_id,id),
 foreign key(study_id,followup_of) references public.research_campaigns(study_id,id)
);
create table public.research_claim_checks (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 claim_id uuid not null, campaign_id uuid not null, method text not null,
 applicability text not null check(applicability in ('applicable','inapplicable')),
 rationale text not null, created_at timestamptz not null default clock_timestamp(), unique(study_id,id),
 foreign key(study_id,claim_id) references public.research_claims(study_id,id),
 foreign key(study_id,campaign_id) references public.research_campaigns(study_id,id)
);
create table public.research_runs (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 campaign_id uuid not null, configuration_id uuid,
 status text not null check(status in ('complete','partial','failed','excluded','invalid')),
 reason text, started_at timestamptz not null, ended_at timestamptz not null,
 analysis_version text not null, input_sha256 text, output_sha256 text,
 requested_resources jsonb not null, actual_resources jsonb not null, usage jsonb not null,
 provenance jsonb not null, created_at timestamptz not null default clock_timestamp(), unique(study_id,id),
 foreign key(study_id,campaign_id) references public.research_campaigns(study_id,id),
 foreign key(study_id,configuration_id) references public.research_configurations(study_id,id),
 check(ended_at>=started_at), check(status='complete' or (reason is not null and length(reason)>0)),
 check(input_sha256 is null or input_sha256 ~ '^[a-f0-9]{64}$'),
 check(output_sha256 is null or output_sha256 ~ '^[a-f0-9]{64}$')
);
create table public.research_published_values (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 source_id uuid not null, location text not null, observation_id text not null,
 configuration_identity text not null, metric text not null, units text not null,
 value numeric, status text not null check(status in ('recorded','missing','invalid','ambiguous')),
 reason text, extraction text not null, created_at timestamptz not null default clock_timestamp(), unique(study_id,id),
 foreign key(study_id,source_id) references public.research_sources(study_id,id),
 check((status='recorded' and value is not null) or (status<>'recorded' and value is null and reason is not null and length(reason)>0)),
 check(value is null or value not in ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric))
);
create table public.research_measurements (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 run_id uuid not null, published_id uuid, observation_id text not null,
 configuration_identity text not null, metric text not null, units text not null,
 value numeric, status text not null check(status in ('recorded','missing','invalid','ambiguous','excluded')),
 reason text, details jsonb not null, created_at timestamptz not null default clock_timestamp(), unique(study_id,id),
 foreign key(study_id,run_id) references public.research_runs(study_id,id),
 foreign key(study_id,published_id) references public.research_published_values(study_id,id),
 unique(run_id,observation_id,configuration_identity,metric),
 check((status='recorded' and value is not null) or (status<>'recorded' and value is null and reason is not null and length(reason)>0)),
 check(value is null or value not in ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric))
);
create table public.research_summaries (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 run_id uuid not null, metric text not null, units text not null, statistics jsonb not null,
 interval_kind text not null check(interval_kind in ('none','descriptive','confidence','unsupported')),
 uncertainty_method text not null, planned integer not null check(planned>=0), unexpected integer not null check(unexpected>=0),
 recorded integer not null check(recorded>=0), missing integer not null check(missing>=0),
 invalid integer not null check(invalid>=0), ambiguous integer not null check(ambiguous>=0),
 excluded integer not null check(excluded>=0), created_at timestamptz not null default clock_timestamp(), unique(study_id,id),
 foreign key(study_id,run_id) references public.research_runs(study_id,id),
 check(recorded+missing+invalid+ambiguous+excluded=planned+unexpected)
);
create table public.research_assessments (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 claim_id uuid not null, campaign_id uuid, supersedes_id uuid,
 label text not null check(label in ('reproduced','discrepant','inconclusive','untested')),
 tested_conditions jsonb not null, evidence jsonb not null check(jsonb_typeof(evidence)='array'),
 justification text not null, limitations text not null, reviewer jsonb not null,
 created_at timestamptz not null default clock_timestamp(), unique(study_id,id), unique(study_id,claim_id,id),
 foreign key(study_id,claim_id) references public.research_claims(study_id,id),
 foreign key(study_id,campaign_id) references public.research_campaigns(study_id,id),
 foreign key(study_id,claim_id,supersedes_id) references public.research_assessments(study_id,claim_id,id),
 check(label in ('inconclusive','untested') or jsonb_array_length(evidence)>0)
);
create table public.research_gaps (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 claim_id uuid not null, assessment_id uuid, supersedes_id uuid,
 status text not null check(status in ('open','blocked','planned','resolved','stopped','inapplicable')),
 reason text not null, next_check text not null, required_inputs jsonb not null,
 dependencies jsonb not null, feasibility text not null, estimated_cost_usd numeric check(estimated_cost_usd>=0 and estimated_cost_usd not in ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 cost_basis text not null, decision_rule text not null, stopping_rule text not null,
 priority integer not null check(priority between 1 and 5), campaign_id uuid,
 created_at timestamptz not null default clock_timestamp(), unique(study_id,id), unique(study_id,claim_id,id),
 foreign key(study_id,claim_id) references public.research_claims(study_id,id),
 foreign key(study_id,claim_id,assessment_id) references public.research_assessments(study_id,claim_id,id),
 foreign key(study_id,claim_id,supersedes_id) references public.research_gaps(study_id,claim_id,id),
 foreign key(study_id,campaign_id) references public.research_campaigns(study_id,id)
);
create table public.research_reviews (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 scope text not null check(scope in ('scientific','software','model-evaluation')),
 status text not null check(status in ('passed','failed','conditional')), reviewer jsonb not null,
 judgments jsonb not null, limitations text not null,
 created_at timestamptz not null default clock_timestamp(), unique(study_id,id)
);
create table public.research_publications (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 version integer not null check(version>0), status text not null check(status in ('published','withdrawn')),
 scientific_review_id uuid not null, software_review_id uuid not null, record_ids jsonb not null,
 reason text not null, created_at timestamptz not null default clock_timestamp(), unique(study_id,version),
 foreign key(study_id,scientific_review_id) references public.research_reviews(study_id,id),
 foreign key(study_id,software_review_id) references public.research_reviews(study_id,id)
);
create table public.research_artifacts (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 sha256 text not null check(sha256 ~ '^[a-f0-9]{64}$'), byte_count bigint not null check(byte_count>=0),
 storage_path text not null, media_type text not null, provenance jsonb not null,
 verified_at timestamptz not null, created_at timestamptz not null default clock_timestamp(), unique(study_id,id)
);
create table public.research_audit_events (
 id bigint generated always as identity primary key, study_id uuid not null references public.research_studies(id),
 actor_id uuid not null, action text not null, details jsonb not null,
 created_at timestamptz not null default clock_timestamp()
);

create function public.research_immutable() returns trigger language plpgsql set search_path='' as $$
begin raise exception 'Research evidence is append-only; create a versioned amendment'; end $$;

-- This read-only helper reveals only membership in the CURRENT published snapshot.
create function public.research_visible(p_study uuid,p_table text,p_id uuid)
returns boolean language sql stable security definer set search_path='' as $$
 select coalesce((select status='published' and
  (p_table='studies' or p_table='publications' or (record_ids->p_table) ? p_id::text)
 from public.research_publications where study_id=p_study order by version desc limit 1),false)
$$;
revoke all on function public.research_visible(uuid,text,uuid) from public;
grant execute on function public.research_visible(uuid,text,uuid) to anon,authenticated,service_role;

do $$ declare t text; begin
 foreach t in array array['studies','study_owners','sources','claims','protocols','configurations','campaigns','claim_checks','runs','published_values','measurements','summaries','assessments','gaps','reviews','publications','artifacts','audit_events'] loop
  execute format('alter table public.%I enable row level security','research_'||t);
  execute format('revoke all on public.%I from public,anon,authenticated','research_'||t);
  execute format('grant all on public.%I to service_role','research_'||t);
  execute format('create trigger research_append_only before update or delete on public.%I for each row execute function public.research_immutable()','research_'||t);
  execute format('drop policy if exists jumpserve_require_signed_in_user on public.%I','research_'||t);
  if t not in ('study_owners','artifacts','audit_events') then
   execute format('grant select on public.%I to anon,authenticated','research_'||t);
   execute format('create policy research_published_read on public.%I for select to anon,authenticated using(public.research_visible(%s,%L,id))','research_'||t,case when t='studies' then 'id' else 'study_id' end,t);
   execute format('create policy research_deny_browser_writes on public.%I as restrictive for all to anon,authenticated using(true) with check(false)','research_'||t);
  end if;
 end loop;
end $$;
grant usage,select on sequence public.research_audit_events_id_seq to service_role;
create index research_assessment_history on public.research_assessments(study_id,claim_id,created_at desc);
create index research_gap_history on public.research_gaps(study_id,claim_id,created_at desc);
create index research_run_campaign on public.research_runs(study_id,campaign_id);
create index research_publication_current on public.research_publications(study_id,version desc);

create function public.research_create_study(p_actor uuid,p_id uuid,p_document jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare existing public.research_studies; begin
 perform pg_advisory_xact_lock(hashtextextended(p_id::text,0));
 select * into existing from public.research_studies where id=p_id;
 if found then
  if not exists(select 1 from public.research_study_owners where study_id=p_id and owner_id=p_actor) then raise exception 'Study not found'; end if;
  if (to_jsonb(existing)-'created_at'-'id') is distinct from p_document then raise exception 'Request ID already used for different paper details'; end if;
  return to_jsonb(existing);
 end if;
 insert into public.research_studies(id,title,paper_url,domain,scope,origin_module)
 values(p_id,p_document->>'title',p_document->>'paper_url',p_document->>'domain',p_document->>'scope',p_document->>'origin_module') returning * into existing;
 insert into public.research_study_owners values(p_id,p_actor);
 insert into public.research_audit_events(study_id,actor_id,action,details) values(p_id,p_actor,'intake',jsonb_build_object('request_id',p_id));
 return to_jsonb(existing);
end $$;

create function public.research_evidence_manifest(p_study uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare manifest jsonb='{}'; t text; ids jsonb; begin
 foreach t in array array['sources','claims','protocols','configurations','campaigns','claim_checks','runs','published_values','measurements','summaries','assessments','gaps'] loop
  execute format('select coalesce(jsonb_agg(id::text order by id),''[]''::jsonb) from public.%I where study_id=$1','research_'||t) into ids using p_study;
  manifest=manifest||jsonb_build_object(t,ids);
 end loop;
 return manifest;
end $$;

-- Only the server can call this transactional writer. All kinds are allowlisted.
create function public.research_append(p_study uuid,p_actor uuid,p_kind text,p_record jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare target_table text; columns text; result jsonb; prior jsonb; begin
 perform pg_advisory_xact_lock(hashtextextended(p_study::text,0));
 if not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Study not found'; end if;
 if p_kind not in ('sources','claims','protocols','configurations','campaigns','claim_checks','runs','published_values','measurements','summaries','assessments','gaps','reviews','artifacts') then raise exception 'Unsupported record kind'; end if;
 target_table='research_'||p_kind;
 p_record=(p_record-'created_at'-'study_id')||jsonb_build_object('study_id',p_study);
 execute format('select to_jsonb(r)-''created_at'' from public.%I r where id=$1',target_table) into prior using (p_record->>'id')::uuid;
 if prior is not null then
  if p_kind='reviews' then
   if jsonb_set(prior,'{judgments}',(prior->'judgments')-'evidence_snapshot') is distinct from jsonb_set(p_record,'{judgments}',(p_record->'judgments')-'evidence_snapshot') then raise exception 'Review ID already used; preserve original and amend'; end if;
  elsif prior is distinct from p_record then raise exception 'Record ID already used; preserve original and amend'; end if;
  return prior;
 end if;
 if p_kind='reviews' then p_record=jsonb_set(p_record,'{judgments,evidence_snapshot}',public.research_evidence_manifest(p_study)); end if;
 select string_agg(quote_ident(c.column_name),',' order by c.ordinal_position) into columns from information_schema.columns c where c.table_schema='public' and c.table_name=target_table and c.column_name<>'created_at';
 execute format('insert into public.%I(%s) select %s from jsonb_populate_record(null::public.%I,$1) returning to_jsonb(%I.*)',target_table,columns,columns,target_table,target_table) into result using p_record;
 insert into public.research_audit_events(study_id,actor_id,action,details) values(p_study,p_actor,'append:'||p_kind,jsonb_build_object('id',p_record->>'id'));
 return result;
end $$;

create function public.research_publish(p_study uuid,p_actor uuid,p_id uuid,p_scientific uuid,p_software uuid,p_reason text,p_withdraw boolean default false)
returns jsonb language plpgsql security definer set search_path='' as $$
declare scientific public.research_reviews; software public.research_reviews; manifest jsonb='{}'; t text; ids jsonb; next_version integer; result jsonb; begin
 perform pg_advisory_xact_lock(hashtextextended(p_study::text,0));
 if not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Study not found'; end if;
 select to_jsonb(r) into result from public.research_publications r where id=p_id and study_id=p_study;
 if result is not null then
  if (result->>'scientific_review_id')::uuid<>p_scientific or (result->>'software_review_id')::uuid<>p_software or result->>'reason'<>p_reason or (result->>'status'='withdrawn')<>p_withdraw then raise exception 'Publication request changed'; end if;
  return result;
 end if;
 select * into scientific from public.research_reviews where study_id=p_study and id=p_scientific and scope='scientific';
 select * into software from public.research_reviews where study_id=p_study and id=p_software and scope='software';
 if scientific.id is null or software.id is null or scientific.status<>'passed' or software.status<>'passed' then raise exception 'Passed scientific and software reviews required'; end if;
 if not p_withdraw then
  if not exists(select 1 from public.research_claims where study_id=p_study) then raise exception 'At least one sourced claim is required'; end if;
  if software.judgments->'release_blockers' is null or jsonb_typeof(software.judgments->'release_blockers')<>'object' then raise exception 'Release check results required'; end if;
  foreach t in array array['database','backend','frontend','provenance','access_control'] loop
   if software.judgments->'release_blockers'->t is distinct from 'true'::jsonb then raise exception 'Release-blocking check did not pass: %',t; end if;
  end loop;
  if scientific.judgments->'scope_and_limits_reviewed' is distinct from 'true'::jsonb then raise exception 'Scientific scope review required'; end if;
  if exists(select 1 from public.research_claims c
    left join lateral (select a.label from public.research_assessments a where a.study_id=c.study_id and a.claim_id=c.id order by a.created_at desc,a.id desc limit 1) a on true
    left join lateral (select g.status,g.reason from public.research_gaps g where g.study_id=c.study_id and g.claim_id=c.id order by g.created_at desc,g.id desc limit 1) g on true
    where c.study_id=p_study and coalesce(a.label,'untested') in ('inconclusive','untested') and (g.status is null or g.status='resolved' or length(g.reason)=0)) then raise exception 'Every unresolved claim needs a current evidence-gap record'; end if;
  if scientific.judgments->'evidence_snapshot' is distinct from public.research_evidence_manifest(p_study) or software.judgments->'evidence_snapshot' is distinct from public.research_evidence_manifest(p_study) then raise exception 'Evidence changed after review; new scientific and software reviews required'; end if;
  foreach t in array array['sources','claims','protocols','configurations','campaigns','claim_checks','runs','published_values','measurements','summaries','assessments','gaps','reviews'] loop
   execute format('select coalesce(jsonb_agg(id::text order by id),''[]''::jsonb) from public.%I where study_id=$1','research_'||t) into ids using p_study;
   manifest=manifest||jsonb_build_object(t,ids);
  end loop;
 end if;
 select coalesce(max(version),0)+1 into next_version from public.research_publications where study_id=p_study;
 insert into public.research_publications(id,study_id,version,status,scientific_review_id,software_review_id,record_ids,reason)
 values(p_id,p_study,next_version,case when p_withdraw then 'withdrawn' else 'published' end,p_scientific,p_software,manifest,p_reason) returning to_jsonb(research_publications.*) into result;
 insert into public.research_audit_events(study_id,actor_id,action,details) values(p_study,p_actor,case when p_withdraw then 'withdraw' else 'publish' end,jsonb_build_object('version',next_version));
 return result;
end $$;

create function public.research_append_bundle(p_study uuid,p_actor uuid,p_records jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare entry jsonb; counts jsonb='{}'; kind text; begin
 if jsonb_typeof(p_records)<>'array' or jsonb_array_length(p_records)>30010 then raise exception 'Invalid record bundle'; end if;
 perform pg_advisory_xact_lock(hashtextextended(p_study::text,0));
 for entry in select value from jsonb_array_elements(p_records) loop
  kind=entry->>'kind';
  perform public.research_append(p_study,p_actor,kind,entry->'record');
  counts=jsonb_set(counts,array[kind],to_jsonb(coalesce((counts->>kind)::integer,0)+1));
 end loop;
 return counts;
end $$;

revoke all on function public.research_immutable() from public,anon,authenticated;
revoke all on function public.research_create_study(uuid,uuid,jsonb) from public,anon,authenticated;
revoke all on function public.research_append(uuid,uuid,text,jsonb) from public,anon,authenticated;
revoke all on function public.research_publish(uuid,uuid,uuid,uuid,uuid,text,boolean) from public,anon,authenticated;
revoke all on function public.research_append_bundle(uuid,uuid,jsonb) from public,anon,authenticated;
revoke all on function public.research_evidence_manifest(uuid) from public,anon,authenticated;
grant execute on function public.research_create_study(uuid,uuid,jsonb),public.research_append(uuid,uuid,text,jsonb),public.research_publish(uuid,uuid,uuid,uuid,uuid,text,boolean) to service_role;
grant execute on function public.research_append_bundle(uuid,uuid,jsonb) to service_role;
grant execute on function public.research_evidence_manifest(uuid) to service_role;
insert into storage.buckets(id,name,public) values('research-workflow-raw','research-workflow-raw',false);
create policy research_private_raw on storage.objects as restrictive for all to anon,authenticated
 using(bucket_id<>'research-workflow-raw') with check(bucket_id<>'research-workflow-raw');
notify pgrst,'reload schema';
commit;
