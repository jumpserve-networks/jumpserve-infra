-- HTTP/2 error codes are unsigned32-bit values, larger than signed Postgres int.
begin;
alter table public.http2_study_measurements alter column error_code type bigint;
alter table public.http2_study_measurements add constraint http2_error_code_bounds check(error_code between 0 and 4294967295);
alter table public.http2_study_frame_measurements alter column error_code type bigint;
alter table public.http2_study_frame_measurements add constraint http2_frame_error_code_bounds check(error_code between 0 and 4294967295);
notify pgrst,'reload schema';
commit;
