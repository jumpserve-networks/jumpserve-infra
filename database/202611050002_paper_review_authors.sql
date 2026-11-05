begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));

-- Keep extracted byline evidence unchanged. Owner-confirmed bibliographic
-- corrections join the existing private, append-only review revision history.
alter function public.research_paper_review(text,uuid,uuid,jsonb) rename to research_paper_review_before_authors_v1;
revoke all on function public.research_paper_review_before_authors_v1(text,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
create function public.research_paper_review(p_operation text,p_actor uuid,p_study uuid,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare r public.research_paper_reviews;names jsonb;original_revision integer;begin
 if p_operation='authors-capability' then
  if p_actor is null or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private paper review not found';end if;
  return jsonb_build_object('version','paper-review-authors-v1');
 end if;
 if p_operation<>'confirm' or not p_payload?'authors' then
  return public.research_paper_review_before_authors_v1(p_operation,p_actor,p_study,p_payload);
 end if;
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_actor is null or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private paper review not found';end if;
 select * into strict r from public.research_paper_reviews where study_id=p_study for update;
 names=p_payload->'authors';
 if jsonb_typeof(names) is distinct from 'array' or jsonb_array_length(names)>100 then raise exception 'Supply up to 100 author names';end if;
 if exists(select 1 from jsonb_array_elements(names) v where jsonb_typeof(v) is distinct from 'string' or
  length(btrim(v#>>'{}')) not between 1 and 200 or (v#>>'{}')~'[[:cntrl:]<>@]' or (v#>>'{}')~*'https?://|www\.|\.pdf\M')
  then raise exception 'Supply bounded author names without contact details or URLs';end if;
 select coalesce(jsonb_agg(btrim(value#>>'{}') order by ordinality),'[]') into names from jsonb_array_elements(names) with ordinality;
 if r.status='confirmed' then
  if r.metadata->'owner_authors'->>'version' is distinct from 'paper-review-authors-v1' or r.metadata->'owner_authors'->'names' is distinct from names
   or r.metadata->'owner_authors'->>'confirmed_by' is distinct from p_actor::text
   or r.metadata->'owner_authors'->'request_revision' is distinct from p_payload->'revision' then raise exception 'Paper authors were already confirmed with different information';end if;
  return public.research_paper_review_before_authors_v1(p_operation,p_actor,p_study,(p_payload-'authors')||jsonb_build_object('revision',r.metadata->'owner_authors'->'delegated_revision'));
 end if;
 if r.status<>'ready' or r.revision is distinct from (p_payload->>'revision')::integer then raise exception 'Paper preparation changed or is incomplete; reload the review';end if;
 original_revision=r.revision;
 update public.research_paper_reviews set metadata=metadata||jsonb_build_object('owner_authors',jsonb_build_object(
  'version','paper-review-authors-v1','names',names,'confirmed_by',p_actor,'request_revision',original_revision,'delegated_revision',original_revision+1)),
  revision=revision+1,updated_at=clock_timestamp() where study_id=p_study returning * into r;
 -- The existing confirmation guards still validate selection, title, domain,
 -- authorization, funding and deadline. Any refusal rolls back this edit too.
 return public.research_paper_review_before_authors_v1(p_operation,p_actor,p_study,(p_payload-'authors')||jsonb_build_object('revision',r.revision));
end$$;
revoke all on function public.research_paper_review(text,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.research_paper_review(text,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
