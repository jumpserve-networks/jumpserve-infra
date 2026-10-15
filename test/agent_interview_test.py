import copy
import json
from unittest.mock import patch
from agent_ideas_test import FakeDatabase, PROMPT_OBJECT, USER, request, response
from unittest import TestCase
import research_ideas as ideas
import idea_interview as interview


class InterviewAgent(TestCase):
    def setUp(self):
        self.prompt = copy.copy(PROMPT_OBJECT)
        self.prompt.version = interview.PROMPT_VERSION
        self.prompt.system_prompt = json.dumps(dict(schema="idea-task-prompts-v1",review="REVIEW_ONLY_CANARY",interview="INTERVIEW_ONLY_CANARY"))
        self.prompt.research_context = "Shared research context"
        self.patch = patch.object(ideas, "load_active_prompt", return_value=self.prompt)
        self.patch.start(); self.addCleanup(self.patch.stop)

    def ask(self, **changes):
        return dict(request("planning"), interview_version=interview.VERSION, **changes)

    def reply(self, **changes):
        result = response(dict(dict(summary="The CDN question leaves treatment assignment unspecified.",
            question="For your 60-second CDN window, how will you assign objects to zero or one prior request?",
            field="design"), **changes))
        result["output"]["message"]["content"][0]["toolUse"]["name"] = interview.CHANNEL
        return result

    def test_interview_routes_one_question_and_cannot_approve_or_edit(self):
        db = FakeDatabase(); seen = []
        def invoke(system, messages, **options):
            seen.append((system, messages, options)); return self.reply()
        result = ideas.handle(self.ask(), USER, db, invoke)
        self.assertEqual(result["run"]["status"], "complete")
        self.assertEqual(result["run"]["output"]["verdict"], "needs-clarification")
        self.assertEqual(len(result["run"]["output"]["questions"]), 1)
        self.assertEqual(db.rpc_calls[-1][1]["p_provenance"]["provider_message"]["content"][0]["toolUse"]["input"]["field"], "design")
        self.assertFalse(db.rpc_calls[-1][1]["p_provenance"]["tool_events"][0]["executed"])
        self.assertEqual(seen[0][2], dict(interview=True))
        self.assertIn("INTERVIEW_ONLY_CANARY",seen[0][0]);self.assertNotIn("REVIEW_ONLY_CANARY",seen[0][0])
        self.assertEqual(interview.system_text(self.prompt),"REVIEW_ONLY_CANARY\n\nShared research context")
        self.assertEqual(json.loads(seen[0][1][-1]["content"][0]["text"])["packet"], db.packet["document"])
        self.assertEqual([call[0] for call in db.rpc_calls], ["research_begin_idea_run", "research_finish_idea_run"])

    def test_wrong_fields_extra_actions_and_focus_mismatch_are_retained_invalid(self):
        for changes in (dict(field="run_experiment"), dict(field="metrics"), dict(verdict="ready"), dict(question="")):
            db = FakeDatabase()
            result = ideas.handle(self.ask(preferred_field="design"), USER, db, lambda *_, **__: self.reply(**changes))
            self.assertEqual(result["run"]["status"], "invalid-output")
            self.assertIsNotNone(db.rpc_calls[-1][1]["p_raw"])

    def test_reviews_and_older_prompts_refuse_interview_before_model(self):
        for body in (dict(request("critic"), interview_version=interview.VERSION), self.ask(preferred_field="execute")):
            with self.assertRaises(ValueError): ideas.handle(body, USER, FakeDatabase(), lambda *_: self.fail("Invoked"))
        self.prompt.version = "research-ideas-v2"
        with self.assertRaises(ideas.AuthError): ideas.handle(self.ask(), USER, FakeDatabase(), lambda *_: self.fail("Invoked"))

    def test_history_can_be_bounded_without_losing_original_run_inputs(self):
        db = FakeDatabase()
        db.history = [{"role": role, "content": [{"text": "x" * 13000}]} for role in ("user", "assistant")]
        ideas.handle(self.ask(), USER, db, lambda *_, **__: self.reply())
        self.assertEqual(db.rpc_calls[0][1]["p_provenance"]["omitted_history_messages"], 2)
        self.assertEqual(len(db.history), 2)
        self.assertEqual(db.rpc_calls[0][1]["p_provenance"]["history_messages"], 0)
