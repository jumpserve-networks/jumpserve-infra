-- Actual trigger and lease behavior. The enclosing harness rolls everything back.
set local role service_role;
do $$
declare
    target uuid := '55555555-0000-4000-8000-000000000002';
    value jsonb; visible jsonb; token uuid; phase text; count_before bigint; stamp timestamptz;
begin
    if (select count(*) from public.real_world_status_history where job_id='55555555-0000-4000-8000-000000000009') <> 1
        or exists(select 1 from public.real_world_status_history where job_id='55555555-0000-4000-8000-000000000009'
            and (started_at is not null or completed_at is not null)) then
        raise exception 'Legacy migration invented times or duplicated history';
    end if;
    value := jsonb_build_object('job_id',target,'owner','private-owner','created_at',1,'schema_version',1,
        'active','yes','deadline',2000000000,'status','provisioning','config','{}'::jsonb);
    visible := value - 'owner' - 'active';
    perform public.real_world_put_job(value,visible,true);
    perform public.real_world_put_job(value,visible,true);
    token := public.real_world_claim_job(target);
    perform public.real_world_put_job(value,visible,false,token);
    if (select count(*) from public.real_world_status_history where job_id=target) <> 1 then
        raise exception 'Retry or checkpoint duplicated history';
    end if;
    foreach phase in array array['bootstrapping','configuring','checking','starting','running','cleaning','completed'] loop
        value := value || jsonb_build_object('status',phase,'outcome','completed');
        visible := value - 'owner' - 'active';
        perform public.real_world_put_job(value,visible,false,token);
    end loop;
    if (select count(*) from public.real_world_status_history where job_id=target) <> 8
        or exists(select 1 from public.real_world_status_history where job_id=target
            and (started_at is null or completed_at is null or outcome<>'completed')) then
        raise exception 'Completed lifecycle lost timings';
    end if;
    if exists(select 1 from (
        select completed_at,lead(started_at) over(order by id) as next_start
        from public.real_world_status_history where job_id=target
    ) h where next_start is not null and completed_at<>next_start) then
        raise exception 'Completion and next start are not the same transition';
    end if;
    count_before := (select count(*) from public.real_world_status_history where job_id=target);
    update public.real_world_jobs set lease_until=clock_timestamp()-interval '1 second' where job_id=target;
    perform public.real_world_put_job(value || '{"status":"running"}',visible || '{"status":"running"}',false,token);
    if (select count(*) from public.real_world_status_history where job_id=target)<>count_before then
        raise exception 'Stale worker changed history';
    end if;

    foreach phase in array array['cancelled','failed'] loop
        target := gen_random_uuid();
        value := value || jsonb_build_object('job_id',target,'status','provisioning','outcome',null);
        perform public.real_world_put_job(value,value - 'owner' - 'active',true);
        token := public.real_world_claim_job(target);
        perform public.real_world_cancel_job(target);
        if (select count(*) from public.real_world_status_history where job_id=target)<>1 then
            raise exception 'Cancellation request alone changed stage';
        end if;
        value := value || jsonb_build_object('status','cleaning','outcome',phase);
        perform public.real_world_put_job(value,value - 'owner' - 'active',false,token);
        select completed_at into stamp from public.real_world_status_history where job_id=target and status='provisioning';
        if stamp is null or (select outcome from public.real_world_status_history where job_id=target and status='provisioning')<>phase then
            raise exception 'Interrupted step marked successful';
        end if;
        value := value || jsonb_build_object('status',phase);
        perform public.real_world_put_job(value,value - 'owner' - 'active',false,token);
        if (select count(*) from public.real_world_status_history where job_id=target)<>3
            or not exists(select 1 from public.real_world_status_history where job_id=target and status='cleaning'
                and outcome='completed' and started_at=stamp and completed_at is not null) then
            raise exception 'Cleanup completion missing after interruption';
        end if;
    end loop;
end $$;
reset role;
set local role anon;
set local request.jwt.claims='{}';
do $$ begin
    if (select count(*) from public.real_world_status_history where job_id='55555555-0000-4000-8000-000000000002')<>8 then
        raise exception 'Public timeline hidden by RLS';
    end if;
end $$;
reset role;
