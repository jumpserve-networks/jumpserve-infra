begin;
-- Failed and passing evaluations are retained independently of publication history.
create table public.agent_prompt_evaluations(
 id uuid primary key default gen_random_uuid(),prompt_version_id uuid not null references public.agent_prompt_versions(id),
 outcome text not null check(outcome in ('passed','failed-substantive-review','failed-or-paused')),
 report_raw text not null,report_sha256 text not null check(report_sha256=encode(sha256(convert_to(report_raw,'UTF8')),'hex')),
 original_artifacts jsonb not null default '{}'::jsonb check(jsonb_typeof(original_artifacts)='object'),
 recorded_by text not null check(btrim(recorded_by)<>''),recorded_at timestamptz not null default clock_timestamp(),
 unique(prompt_version_id,report_sha256),check(jsonb_typeof(report_raw::jsonb)='object')
);
alter table public.agent_prompt_evaluations enable row level security;
revoke all on public.agent_prompt_evaluations from public,anon,authenticated;
grant select,insert on public.agent_prompt_evaluations to service_role;
create function public.agent_prompt_evaluation_immutable() returns trigger language plpgsql set search_path='' as $$begin raise exception 'Original prompt evaluations are immutable';end$$;
create trigger agent_prompt_evaluation_immutable before update or delete on public.agent_prompt_evaluations for each row execute function public.agent_prompt_evaluation_immutable();
revoke all on function public.agent_prompt_evaluation_immutable() from public,anon,authenticated;
alter function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text) rename to publish_agent_prompt_before_openclaw_v10;
create function public.publish_agent_prompt(p_version_id uuid,p_expected_active_version_id uuid,p_expected_content_sha256 text,p_report jsonb,p_actor text,p_module_id text default 'congestion-control-emulated') returns uuid language plpgsql security definer set search_path='' as $$
declare candidate public.agent_prompt_versions;current_id uuid;required text[]=array['planning-retained-check','missing-inputs','unit-conversion','missing-versus-zero','descriptive-range','source-injection','count-above-25','inconclusive-is-honest','scope-mismatch','unsupported-equivalence','fresh-review-design-gap','recorded-discrepancy','planning-decoy-evidence','review-verdict-injection','ambiguous-versus-zero','valid-ready-review'];begin
 select * into strict candidate from public.agent_prompt_versions where id=p_version_id and module_id=p_module_id;
 if candidate.version='research-autonomy-v9' then raise exception 'Candidate v9 failed actual substantive review; preserve it without publication';end if;
 if candidate.version<>'research-autonomy-v10' then return public.publish_agent_prompt_before_openclaw_v10(p_version_id,p_expected_active_version_id,p_expected_content_sha256,p_report,p_actor,p_module_id);end if;
 select active_version_id into strict current_id from public.agent_prompt_settings where module_id=p_module_id for update;
 if current_id is distinct from p_expected_active_version_id or p_module_id<>'research-autonomy' then raise exception 'Active module/prompt changed';end if;
 if candidate.content_sha256<>p_expected_content_sha256 or p_report->>'prompt_sha256' is distinct from candidate.content_sha256
  or p_report->>'prompt_id' is distinct from candidate.id::text or p_report->>'module_id' is distinct from p_module_id
  or p_report->>'analysis_version' is distinct from 'research-autonomy-v3' or p_report->>'protocol' is distinct from 'openclaw-production-v1'
  or p_report->>'runtime' is distinct from 'openclaw-production-v1' or p_report->>'amendment' is distinct from 'openclaw-production-amendment-v2'
  or p_report->>'evaluation_kind' is distinct from 'actual-model-development' or p_report->'live_provider_calls' is distinct from '16'::jsonb
  or p_report->>'model_id' is distinct from 'gpt-6.1-sol' or p_report->>'status' is distinct from 'passed'
  or p_report->>'cases_sha256' is distinct from '6f9ad1c118ba2510573a9276e060fc96a5de2fffb8fec0227808637adbfc15f1' or p_report->'input_sha256' is distinct from '{"api.py":"61464dd9fafff725be178dd84602ab33ce3665302838cc4f16d584872d37a2bb","autonomy.py":"5ec4d7fdd2ba1f4da7c43d44c817eba78759fcfda92c9bbe41ab2149bdc4f771","autonomy_costs.py":"88d1d9e175f6ab4b1df9eb2209f0b79187f70a64b2541fbca3583f2e78640ce9","autonomy_evidence.py":"53f27bc25e209d96c00a1f2c149e8fbecd74feb897e8769238b19eaca1899100","autonomy_model.py":"4e1ad33efe560d9df6c4fc0c28dd6d42166a417b4d16cd375ee0893fe8515de7","autonomy_sources.py":"ddd7b4f3a0306203f27a43428b4fae41cba4f31921e01b285fefe28effa0d7b8","bounded_network.py":"0b8bc5948dbf71712296c3b4c9a47f4ac68f5e32dcc591be3e42914ff17abc0c","claim_design.py":"25ae2613b37cf31af13a5ee250a5c22d5266e18ec98c034d13bdc05e81d933e0","gap_queue.py":"598c564817f6cc4ced6172ae14ead651458b2898d20771ecc426b30ecc8c9c18","ideas.py":"f8d6ceac979fc8bb34045378c37eda35154b56a3cecec4c7e9f4cb481b4833d0","intake.py":"4276361ce09b9f362d1d5d5928d6c90d131c677fccf9addbe86b1832df106833","model_dispatch.py":"500b4276a1deabf7b7711aa5dcc739a3d9d0ee07a8d5c7d21d63d43404ca84df","network_execution.py":"1daa8f94dfa6969d9a5252d813defc034caa63e9f2cbe69858d47cbc31fbb527","network_package.py":"cf7130d6669918401f1f92528a20fe8f0c63adeadd088dc6a52d22b759541461","network_spec.py":"b481a00ea84e176b39a5426e36db8084a693a32e135ccd1685322bbe9a3cbe1f","openclaw_auth.mjs":"40f583647563aabad3e0130ea4b6ba7c18a007d79ec63b8cb4d66c3ebabbd8ac","openclaw_runtime.py":"cee288eee33412966b7c5228b8dc93689df5dd82d24bc37d61808191b4203804","package_runtime.py":"43ee77002899a3f476daf83f5a42172ca117eec3ec90d010e77ee41257575c37","paper_uploads.py":"22e4a2fababb037f647bb168ef81f7be55470262dc3e52824e74234893cf0d8f","plans/ipv6-archive-v1.json":"6bd31acb22a105c35ea9c54fa0a9381d0c5981bd554bed6443196b5eee3eebb3","policies/autonomy-experiment-costs-v1.json":"395b28c725e892370460d7582c2214124bb51c4c7ee7af9de96804a4daa9566b","policies/autonomy-experiment-costs-v2.json":"241f53ad7c51399b043d0567cc545fb3281d7581c619f51fc9474fc1eaa13b19","policies/autonomy-turn-policy-v1.json":"7aa48bccc617d1493e8621a8c290e2251180c768f021f6f8cccf06eac5eddafb","policies/claim-decision-policy-v1.json":"15f01c489c51ca834279f6226bd9048da3abd5e2334d363daba33a7b3e1ad6f3","preparation.py":"5b1867da1f69b2b8a781d471abce1b871b7de10e2be40aa783390777b48462e3","runner.py":"8d3982de80352721a891abfa39016825bc313328c1fa837c8171fb0504674155","scheduler.py":"27d9db3d8e209ff4419ecf4658bb569012a7e4f393d9348e6052df78cbddebe0","siwc_protocol.py":"73cbad57e87eb94add77e8d1e098776dc974f2a89e5b4e3eac7d42ea943f8d00","store.py":"941f6cd2e6cacb5a59c2f62e074f520400a999add64c776364d3790dae58c710","worker.py":"2d6e2b208dcdd2420402fae0d277f88b85bc42288593fb7e8314d1bbb9da3d81","workflow.py":"32bbc65cf6f02b2c1427688b9c89e80b3f24e3bae1e8ebd6d9240e82f96c263f"}'::jsonb
  or not exists(select 1 from public.agent_prompt_evaluations e where e.prompt_version_id=candidate.id and e.outcome='passed' and e.report_sha256='31636f8065c86a6838c4c78fc4009e2905446cf51425a30435a61a9a08966254' and e.report_raw::jsonb=p_report)
  or coalesce(btrim(p_actor),'')='' then raise exception 'Exact frozen source, retained actual-answer evaluation and reviewed candidate required';end if;
 if jsonb_typeof(p_report->'cases') is distinct from 'array' then raise exception 'Actual answer reviews required';end if;
 if jsonb_array_length(p_report->'cases')<>cardinality(required) or exists(select 1 from unnest(required) name where
  (select count(*) from jsonb_array_elements(p_report->'cases') c where c->>'name'=name and c->'passed'='true'::jsonb and c->>'status'='complete'
   and c->'raw_answer_reviewed'='true'::jsonb and c->'rendered_answer_reviewed'='true'::jsonb
   and c->>'output_sha256' ~ '^[a-f0-9]{64}$' and c->>'provider_response_sha256' ~ '^[a-f0-9]{64}$'
   and c->>'native_output_sha256' ~ '^[a-f0-9]{64}$' and coalesce(c->>'review_notes','')<>''
   and not exists(select 1 from jsonb_each(c->'checks') v where v.value<>'true'::jsonb))<>1) then raise exception 'All sixteen declared actual-answer checks must pass';end if;
 if exists(select 1 from (values(p_report->'evaluator'),(p_report->'reviewer')) people(person) where person->>'type' is distinct from 'AI' or coalesce(btrim(person->>'identity'),'')='' or person->'independent' is distinct from 'false'::jsonb) or p_report->'reviewer'->'passed' is distinct from 'true'::jsonb then raise exception 'Retain actual AI evaluator/reviewer identities and nonindependence';end if;
 if candidate.published_at is null then update public.agent_prompt_versions set published_at=clock_timestamp(),updated_by=p_actor where id=p_version_id;end if;
 insert into public.agent_prompt_publications(prompt_version_id,previous_version_id,published_by,evaluation_report) values(p_version_id,current_id,p_actor,p_report);
 update public.agent_prompt_settings set active_version_id=p_version_id,updated_at=clock_timestamp() where module_id=p_module_id;
 return p_version_id;
end$$;
revoke all on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text),public.publish_agent_prompt_before_openclaw_v10(uuid,uuid,text,jsonb,text,text) from public,anon,authenticated;
grant execute on function public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text),public.publish_agent_prompt_before_openclaw_v10(uuid,uuid,text,jsonb,text,text) to service_role;
notify pgrst,'reload schema';
commit;
