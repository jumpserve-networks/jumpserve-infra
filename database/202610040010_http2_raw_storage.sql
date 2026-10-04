-- Preserve byte-exact research originals privately; browser policies cannot read/write them.
begin;
insert into storage.buckets(id,name,public)
values('http2-study-artifacts','http2-study-artifacts',false)
on conflict(id) do update set public=false;
drop policy if exists http2_originals_browser_deny on storage.objects;
create policy http2_originals_browser_deny on storage.objects as restrictive
for all to anon,authenticated
using(bucket_id<>'http2-study-artifacts')
with check(bucket_id<>'http2-study-artifacts');
commit;
