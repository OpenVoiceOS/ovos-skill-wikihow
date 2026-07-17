"""End-to-end intent-routing tests for the en-US WikiHow skill.

Boots an in-process MiniCroft with the skill loaded and feeds it real
utterances through the padatious pipeline, asserting where each one routes and
how the {query} slot is filled. The network lookup is stubbed so the suite is
deterministic and offline.
"""
import time
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import get_minicroft

SKILL_ID = "ovos-skill-wikihow.openvoiceos"
LANG = "en-US"
PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padatious-pipeline-plugin-medium",
]


class _RoutingTest(TestCase):
    """Shared MiniCroft harness with a stubbed WikiHow backend."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID])
        cls.skill = cls.minicroft.plugin_skills[SKILL_ID].instance
        # keep the suite offline and deterministic; routing is what we assert
        cls.skill.wikihow.search = lambda *args, **kwargs: []
        cls.bus = cls.minicroft.bus

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def _run(self, utterance):
        """Emit ``utterance`` and collect the intent + speak messages it yields."""
        intents = []
        spoken = []
        self.bus.on(f"{SKILL_ID}:wikihow.intent",
                    lambda m: intents.append(("wikihow.intent", m.data.get("query"))))
        self.bus.on("speak",
                    lambda m: spoken.append(m.data.get("utterance", "")))
        session = Session(f"e2e-{abs(hash(utterance))}")
        session.lang = LANG
        session.pipeline = PIPELINE
        self.bus.emit(Message("recognizer_loop:utterance",
                              {"utterances": [utterance], "lang": LANG},
                              {"session": session.serialize()}))
        time.sleep(3)
        return intents, spoken


class TestWikiHowIntentRouting(_RoutingTest):
    def test_search_wikihow_for_topic(self):
        intents, _ = self._run("search wikihow for tie a tie")
        self.assertIn(("wikihow.intent", "tie a tie"), intents)

    def test_find_topic_on_wikihow(self):
        intents, _ = self._run("find make coffee on wikihow")
        self.assertIn(("wikihow.intent", "make coffee"), intents)

    def test_what_does_wikihow_say_about_topic(self):
        intents, _ = self._run("what does wikihow say about tie a tie")
        self.assertIn(("wikihow.intent", "tie a tie"), intents)
