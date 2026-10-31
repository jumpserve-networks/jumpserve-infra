begin;
-- Compare retries using the same typed representation PostgreSQL stores.
-- Timestamp offsets/precision can differ across service sessions without
-- changing the instant. Raw original bytes and hashes remain separate records.
do $migration$ declare definition text;old text;begin
 definition=pg_get_functiondef('public.research_append(uuid,uuid,text,jsonb)'::regprocedure);
 old='declare target_table text; columns text; result jsonb; prior jsonb; begin';
 if strpos(definition,old)=0 then raise exception 'Unexpected research append declaration';end if;
 definition=replace(definition,old,'declare target_table text; columns text; result jsonb; prior jsonb; normalized_record jsonb; begin');
 old=$old$p_record=(p_record-'created_at'-'study_id')||jsonb_build_object('study_id',p_study);$old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected research append identity binding';end if;
 definition=replace(definition,old,old||$new$
 execute format('select to_jsonb(jsonb_populate_record(null::public.%I,$1))-''created_at''',target_table) into normalized_record using p_record;
 if exists(select 1 from jsonb_object_keys(p_record) k where not (normalized_record ? k)) then raise exception 'Unsupported research record fields';end if;
 p_record=normalized_record;
$new$);
 execute definition;
end $migration$;
notify pgrst,'reload schema';
commit;
