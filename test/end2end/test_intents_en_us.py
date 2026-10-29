"""End-to-end intent-routing tests for the en-US WikiHow skill.

Boots an in-process MiniCroft with the skill loaded and feeds it real
utterances, asserting where each one routes and how the {query} slot is
filled. The network lookup is stubbed so the suite is deterministic and
offline.
"""
import time
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_spec_tools import canonical_intent_topic
from ovoscope.routing import PIPELINE, TALLY, get_prototype_minicroft

SKILL_ID = "ovos-skill-wikihow.openvoiceos"
LANG = "en-US"
WIKIHOW_INTENT = f"{SKILL_ID}:wikihow"


class _RoutingTest(TestCase):
    """Shared MiniCroft harness with a stubbed WikiHow backend."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_prototype_minicroft([SKILL_ID], lang=LANG)
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
        fired = []
        self.bus.on("message", lambda raw: fired.append(
            Message.deserialize(raw).msg_type))
        # ovos-workshop dispatches intent handlers on the canonical topic
        # (".intent" suffix stripped) since 9.3.13a1 - mirror the same
        # canonicalization the skill's register_intent_file uses so this
        # listener tracks the real contract instead of a hardcoded guess.
        canonical_topic = canonical_intent_topic(f"{SKILL_ID}:wikihow.intent")
        self.bus.on(canonical_topic,
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
        TALLY.assert_routed(utterance, WIKIHOW_INTENT, fired)
        return intents, spoken


class TestWikiHowIntentRouting(_RoutingTest):
    def test_search_wikihow_for_topic(self):
        intents, _ = self._run("search wikihow for tie a tie")
        self.assertIn(("wikihow.intent", "tie a tie"), intents)

    def test_search_wikihow_for_topic_alt_slot(self):
        intents, _ = self._run("search wikihow for planting tomatoes")
        self.assertIn(("wikihow.intent", "planting tomatoes"), intents)

    def test_search_wiki_how_no_for(self):
        intents, _ = self._run("search wiki how bake bread")
        self.assertIn(("wikihow.intent", "bake bread"), intents)

    def test_find_topic_on_wikihow(self):
        intents, _ = self._run("find make coffee on wikihow")
        self.assertIn(("wikihow.intent", "make coffee"), intents)

    def test_look_up_topic_on_wiki_how(self):
        intents, _ = self._run("look up how to fold a paper airplane on wiki how")
        self.assertIn(("wikihow.intent", "how to fold a paper airplane"), intents)

    def test_find_topic_on_wiki_how(self):
        intents, _ = self._run("find changing a tire on wiki how")
        self.assertIn(("wikihow.intent", "changing a tire"), intents)

    def test_what_does_wikihow_say_about_topic(self):
        intents, _ = self._run("what does wikihow say about tie a tie")
        self.assertIn(("wikihow.intent", "tie a tie"), intents)

    def test_what_does_wiki_how_think_about_topic(self):
        intents, _ = self._run("what does wiki how think about boiling an egg")
        self.assertIn(("wikihow.intent", "boiling an egg"), intents)

    def test_what_does_wikihow_say_about_topic_alt_slot(self):
        intents, _ = self._run("what does wikihow say about setting up a tent")
        self.assertIn(("wikihow.intent", "setting up a tent"), intents)

