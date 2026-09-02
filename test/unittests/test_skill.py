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


class TestExtractKeyword(unittest.TestCase):
    def test_extracts_query_from_how_to_utterance(self):
        skill = _make_skill()
        self.assertEqual(skill.extract_keyword("how do i make coffee", "en-US"),
                         "make coffee")

    def test_extracts_query_from_polite_how_to_openers(self):
        # OpenVoiceOS/ovos-skill-wikihow#92: polite openers like "could you
        # please tell me how to X" fell through un-anchored, so the CQ
        # keyword extractor never even considered them.
        skill = _make_skill()
        for utterance, expected in [
            ("could you please tell me how to boil an egg", "boil an egg"),
            ("can you tell me how to boil an egg", "boil an egg"),
            ("can you explain how to tie a tie", "tie a tie"),
            ("could you please explain how to tie a tie", "tie a tie"),
            ("please show me how to boil an egg", "boil an egg"),
            ("show me how to boil an egg", "boil an egg"),
            ("i want to know how to boil an egg", "boil an egg"),
            ("i need to learn how to tie a tie", "tie a tie"),
        ]:
            self.assertEqual(skill.extract_keyword(utterance, "en-US"), expected,
                             f"failed to extract query from: {utterance!r}")


class TestHandleIntent(unittest.TestCase):
    def test_missing_result_speaks_failure(self):
        skill = _make_skill()
        skill.speak_dialog = MagicMock()
        skill.get_how_to = MagicMock(return_value=None)
        skill.handle_how_to_intent(Message("t", {"query": "tie a tie"}))
        skill.speak_dialog.assert_called_with("howto.failure")


if __name__ == "__main__":
    unittest.main()
