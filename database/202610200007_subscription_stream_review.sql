-- Append-only review of one demonstrated stream-parser rejection. Local only.
begin;
alter table public.research_subscription_recoveries drop constraint research_subscription_recoveries_reserved_overhead_cents_check;
alter table public.research_subscription_recoveries add constraint research_subscription_recoveries_overhead_check check(reserved_overhead_cents in (0,1000));
create or replace function public.research_subscription_recovery_guard() returns trigger language plpgsql as $$
declare r public.research_subscription_calls; d jsonb;
begin
 if tg_op<>'INSERT' then raise exception 'Subscription recovery receipts are append only'; end if;
 select * into strict r from public.research_subscription_calls where id=new.rejected_call_id;
 if r.pilot_id<>new.pilot_id or r.response_raw is null or r.response_sha256<>new.rejection_sha256 then
  raise exception 'Exact retained provider response identity required';
 end if;
 if r.status='failed' and r.http_status=400 and new.reserved_overhead_cents=1000 then
  d=convert_from(r.response_raw,'UTF8')::jsonb;
  if d->'error'->>'type'='invalid_request_error' and d->'error'->>'param'='input' and
     d->'error'->>'message'=$m$Response input messages must contain the word 'json' in some form to use 'text.format' of type 'json_object'.$m$ then return new; end if;
 elsif r.status='invalid-output' and r.http_status=200 and new.reserved_overhead_cents=0 and
       r.response_sha256='4f8223fdd0ce705119c837d57940489cf34ec3058861a5f1f4e1891dd8ce3025' and
       convert_from(new.protocol_raw,'UTF8')::jsonb->>'id'='openclaw-ipv6-subscription-pilot-v9' and
       new.receipt->>'stream_parser'='siwc-streamed-output-items-v1' then
  return new;
 end if;
 raise exception 'This receipt does not authorize an unknown or different provider failure';
end $$;
commit;
