"""End-to-end intent routing tests for the en-US locale.

Each canonical utterance is fired through a real MiniCroft and asserted to
route to the expected intent handler and produce a spoken response. The article
text itself depends on live search results, so assertions cover the intent
binding and the presence of a ``speak`` response, not the dialog content.
"""
import unittest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-wikihow.openvoiceos"


class TestWikiHowIntentsEnUS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID])

    @classmethod
    def tearDownClass(cls):
        cls.minicroft.stop()

    def _run(self, text):
        session = Session("test-session")
        session.pipeline = [
            "ovos-adapt-pipeline-plugin-high",
            "ovos-padatious-pipeline-plugin-high",
            "ovos-adapt-pipeline-plugin-medium",
            "ovos-padatious-pipeline-plugin-medium",
            "ovos-adapt-pipeline-plugin-low",
        ]
        utterance = Message(
            "recognizer_loop:utterance",
            {"utterances": [text], "lang": "en-US"},
            {"session": session.serialize(), "source": "A", "destination": "B"},
        )
        capture = CaptureSession(self.minicroft)
        capture.capture(utterance, timeout=30)
        return capture.finish()

    def _assert_intent(self, text, intent_file):
        messages = self._run(text)
        types = [m.msg_type for m in messages]
        self.assertIn(f"{SKILL_ID}:{intent_file}", types)
        self.assertTrue(any("speak" in t for t in types))

    def test_search_wikihow_for_query(self):
        self._assert_intent("search wikihow for tie a tie", "wikihow.intent")

    def test_search_wiki_how_query(self):
        self._assert_intent("search wiki how tie a tie", "wikihow.intent")

    def test_what_does_wikihow_say_about_query(self):
        self._assert_intent("what does wikihow say about tie a tie", "wikihow.intent")

    def test_what_does_wiki_how_think_about_query(self):
        self._assert_intent("what does wiki how think about tie a tie", "wikihow.intent")


if __name__ == "__main__":
    unittest.main()
