"""Evaluation and publication helpers shared by CI and prompt administration."""
from prompt import PromptVersion

BOOTSTRAP_ID = 'cabbe18a-cc70-482c-8883-81b515639e42'


def evaluation_snapshot(database, prompt_id=None, bootstrap_if_empty=False):
    settings = database.get('agent_prompt_settings', params={'select': 'active_version_id'})
    if len(settings) != 1:
        raise RuntimeError('Prompt database has not been initialized')
    active_id = settings[0]['active_version_id']
    candidate_id = prompt_id or active_id
    if candidate_id is None and bootstrap_if_empty:
        candidate_id = BOOTSTRAP_ID
    if candidate_id is None:
        raise RuntimeError('No active prompt; publish an evaluated draft first')
    records = database.get('agent_prompt_versions', params={'id': f'eq.{candidate_id}', 'select': '*'})
    if len(records) != 1:
        raise RuntimeError('Prompt version not found')
    return PromptVersion.from_record(records[0]), active_id


def publish_evaluated_prompt(database, prompt, expected_active_id, report, actor):
    # SQL independently verifies the exact content hash, cases, and current pointer.
    return database.rpc('publish_agent_prompt', {
        'p_version_id': prompt.id, 'p_expected_active_version_id': expected_active_id,
        'p_expected_content_sha256': prompt.content_sha256,
        'p_report': report, 'p_actor': actor,
    })
