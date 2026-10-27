begin;
-- New draft only. No active pointer or prior publication is changed.
insert into public.agent_prompt_versions(id,module_id,version,system_prompt,research_context,created_by,updated_by)
select 'dfab5ecb-b8b9-5ad3-8771-f28a06b53b27','research-experiment-builder','research-experiment-builder-v2',
 replace(replace(replace(system_prompt,
 'A 60-second worker slice is scheduling', 'A 180-second worker slice is scheduling'),
 'Write project/experiment.py, project/requirements.lock, project/system-packages.lock.json and project/build-evidence.json. The entrypoint reads JUMPSERVE_SPEC (JSON configuration, metrics, limits and replication)',
 'When an implementation is requested, write project/experiment.py, project/requirements.lock, project/system-packages.lock.json and project/build-evidence.json. For an explicitly requested bounded diagnostic or design-only check, produce only its requested artifacts, not an unsolicited project. The entrypoint opens the absolute filename in JUMPSERVE_SPEC and parses that file as JSON configuration, metrics, limits and replication; never parse the environment string as inline JSON'),
 'The executor is a clean Ubuntu EC2 host;', 'Read the trusted server runner-contract.json. Commands and file tools use the worker UID:GID. Use sudo -n for necessary installations/system setup within the disposable container, and write workspace files as the workspace user. Use python3, not an assumed python alias. Development checks must supply actual spec/input/output paths, then verify the frozen project with the unchanged server wrapper. The executor is a clean Ubuntu EC2 host;'),
 research_context||' Candidate v2 supplies the actual clean executor file-path contract and aligns sandbox and worker UID:GID. The original candidate and failed evaluations remain unchanged.',
 'Primary Codex AI implementation author; nonindependent','Primary Codex AI implementation author; nonindependent'
from public.agent_prompt_versions where id='6102d16d-c5cf-5f1c-8fc7-2df2899da972'
on conflict(id) do nothing;
commit;
