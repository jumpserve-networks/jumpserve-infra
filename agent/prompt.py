"""Versioned prompt snapshots. Production text comes exclusively from Supabase."""
from dataclasses import dataclass
import hashlib
from uuid import UUID
from modules import EMULATED_MODULE, CHAT_MODULES


class PromptUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class PromptVersion:
    id: str
    version: str
    system_prompt: str
    research_context: str
    content_sha256: str
    module_id: str = EMULATED_MODULE

    @property
    def text(self):
        return self.system_prompt + '\n\n' + self.research_context

    @classmethod
    def from_record(cls, record):
        try:
            values = {name: record[name] for name in ('id', 'version', 'system_prompt', 'research_context')}
            if any(not isinstance(value, str) or not value.strip() for value in values.values()):
                raise ValueError('Empty prompt field')
            UUID(values['id'])
            values['module_id'] = record.get('module_id', EMULATED_MODULE)
            if values['module_id'] not in CHAT_MODULES:
                raise ValueError('Unsupported prompt module')
            digest = hashlib.sha256((values['system_prompt'] + '\n\n' + values['research_context']).encode()).hexdigest()
            if record.get('content_sha256') != digest:
                raise ValueError('Prompt checksum mismatch')
            return cls(**values, content_sha256=digest)
        except (KeyError, TypeError, ValueError) as exc:
            raise PromptUnavailable('Invalid database prompt version') from exc


def load_active_prompt(database, module_id=EMULATED_MODULE):
    # Read on every request: warm Lambdas must observe newly published versions.
    records = database.get('rpc/get_active_agent_prompt', params={'p_module_id': module_id})
    if not isinstance(records, list) or len(records) != 1:
        raise PromptUnavailable('Exactly one published prompt must be active')
    if not records[0].get('published_at'):
        raise PromptUnavailable('Active prompt has not been published')
    prompt = PromptVersion.from_record(records[0])
    if prompt.module_id != module_id:
        raise PromptUnavailable('Prompt belongs to another module')
    return prompt
