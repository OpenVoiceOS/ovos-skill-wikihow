"""
Unit tests for WikiHowSkill.

Uses FakeBus and a stubbed WikiHow backend -- no network, no OVOS daemon.
"""
import unittest
from unittest.mock import MagicMock

from ovos_bus_client.message import Message
from ovos_utils.fakebus import FakeBus


def _make_skill():
    from ovos_skill_wikihow import WikiHowSkill
    skill = WikiHowSkill(bus=FakeBus(), skill_id="test.wikihow")
    skill.wikihow = MagicMock()
    return skill


class TestSkillInit(unittest.TestCase):
    def test_keyword_matcher_registered_for_en(self):
        skill = _make_skill()
        self.assertIn("en", skill.kw_matchers)

    def test_query_blacklist_loaded_for_en(self):
        skill = _make_skill()
        self.assertIn("en", skill.query_blacklists)
        self.assertIn("it", skill.query_blacklists["en"])


class TestBlacklist(unittest.TestCase):
    def test_bare_pronoun_is_blacklisted(self):
        skill = _make_skill()
        self.assertTrue(skill.is_blacklisted_query("it", "en-US"))
        self.assertTrue(skill.is_blacklisted_query("THEM", "en-US"))

    def test_real_subject_is_not_blacklisted(self):
        skill = _make_skill()
        self.assertFalse(skill.is_blacklisted_query("tie a tie", "en-US"))

    def test_empty_query_is_not_blacklisted(self):
        skill = _make_skill()
        self.assertFalse(skill.is_blacklisted_query("", "en-US"))


class TestExtractKeyword(unittest.TestCase):
    def test_extracts_query_from_how_to_utterance(self):
        skill = _make_skill()
        self.assertEqual(skill.extract_keyword("how do i make coffee", "en-US"),
                         "make coffee")

    def test_pronoun_query_left_unresolved(self):
        skill = _make_skill()
        # the {query} slot value is the bare pronoun "it" -> refused (§4.3)
        self.assertIsNone(skill.extract_keyword("steps for it", "en-US"))


class TestHandleIntent(unittest.TestCase):
    def test_blacklisted_query_speaks_failure(self):
        skill = _make_skill()
        skill.speak_dialog = MagicMock()
        skill.get_how_to = MagicMock()
        skill.handle_how_to_intent(Message("t", {"query": "it"}))
        skill.speak_dialog.assert_called_with("howto.failure")
        skill.get_how_to.assert_not_called()

    def test_missing_result_speaks_failure(self):
        skill = _make_skill()
        skill.speak_dialog = MagicMock()
        skill.get_how_to = MagicMock(return_value=None)
        skill.handle_how_to_intent(Message("t", {"query": "tie a tie"}))
        skill.speak_dialog.assert_called_with("howto.failure")


if __name__ == "__main__":
    unittest.main()
