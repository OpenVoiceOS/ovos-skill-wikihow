"""End-to-end coverage for wikihow's real common-query dispatch path.

``howto.intent`` (under ``locale/<lang>/``) is NOT a directly-registered
intent file: it only feeds ``register_kw_xtract``'s internal Padacioso
keyword matcher, which ``match_common_query`` (decorated with
``@common_query``) uses to decide whether an utterance is a "how to X"
question before it ever touches the network. None of the other e2e suites
in this repo send an utterance through a MiniCroft whose session pipeline
actually includes ``ovos-common-query-pipeline-plugin`` and then assert on
the resulting ``question:query.response`` for a plain, uncontested "how to"
utterance -- ``test_golden_utterances.py`` and ``test_intents_en_us.py``
both pin the *padatious* ``wikihow.intent`` handler instead, which is a
different code path with its own locale file, and
``test_common_query_arbitration.py`` targets a specific arbitration
regression (misc_blacklist self-veto / stop hijack) with a competing skill
loaded, not the base "does wikihow claim its own surface" question.

This suite closes that gap: single-skill MiniCroft, common-query pipeline
included, wikihow's network call stubbed (repo convention, see
``test_common_query_arbitration.py`` and ``test_golden_utterances.py``),
several natural "how to" phrasings asserted to produce a wikihow
``question:query.response`` candidate with a real answer, and one
utterance wikihow must NOT claim.

Note on PR #93 (open draft, not merged into dev as of this suite): that PR
proposes additional polite openers ("could you please tell me how to...",
"can you explain how to...") in ``howto.intent``. Since it is unmerged,
those new templates are not present on dev and asserting them here would
make this suite red against dev today. The phrasings below instead cover
three *already-shipped* templates from ``locale/en-US/howto.intent``
("how do i", "tell me how to", "what are the steps to"), including "tell
me how to" -- a polite opener already on dev -- so the positive assertions
hold against current dev. If/when #93 merges, its new templates would be
natural additions to this list.

``golden_utterances.jsonl`` rows are keyed by ``intent_type: padatious``
against ``wikihow.intent`` (see ``test_golden_utterances.py``'s docstring)
and have no field for "which pipeline plugin should claim this" -- there is
no common-query marker in the org's golden-row schema to add rows under, so
this dedicated test file is the coverage for the common-query surface, not
an addition to the golden corpus.
"""
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

WIKIHOW_ID = "ovos-skill-wikihow.openvoiceos"
LANG = "en-US"

# Mirrors test_common_query_arbitration.py's pipeline: the default
# ovos-config mycroft.conf pipeline order with
# ovos-common-query-pipeline-plugin inserted where platform-recommends
# ships it (it is NOT present in the bare mycroft.conf default at all).
_PIPELINE = [
    "ovos-stop-pipeline-plugin-high",
    "ovos-converse-pipeline-plugin",
    "ovos-ocp-pipeline-plugin-high",
    "ovos-padatious-pipeline-plugin-high",
    "ovos-adapt-pipeline-plugin-high",
    "ovos-m2v-pipeline-high",
    "ovos-ocp-pipeline-plugin-medium",
    "ovos-fallback-pipeline-plugin-high",
    "ovos-stop-pipeline-plugin-medium",
    "ovos-adapt-pipeline-plugin-medium",
    "ovos-common-query-pipeline-plugin",
    "ovos-fallback-pipeline-plugin-medium",
    "ovos-fallback-pipeline-plugin-low",
]

_FAKE_HOW_TO = {
    "title": "Tie a Tie",
    "url": "https://www.wikihow.com/Tie-a-Tie",
    "intro": "Tying a tie is a classic skill worth mastering.",
    "n_steps": 1,
    "steps": [
        {"number": 1, "summary": "Drape the tie around your neck.",
         "description": "Wide end on the right, hanging lower than the narrow end.",
         "picture": None},
    ],
}

# (utterance, howto.intent template it should exercise)
POSITIVE_UTTERANCES = [
    ("how do i tie a tie", "how (can|do|should|would) i {query}"),
    ("tell me how to tie a shoelace", "tell me how to {query}"),
    ("what are the steps to change a tire", "what are the steps (for|to) {query}"),
]

NEGATIVE_UTTERANCE = "what time is it"


class TestCommonQueryHowToSurface(TestCase):
    """Real dispatch through the common-query pipeline, single skill loaded."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([WIKIHOW_ID])
        loaded = set(cls.minicroft.plugin_skills)
        assert WIKIHOW_ID in loaded, (
            f"wikihow failed to load into MiniCroft (loaded: {sorted(loaded)!r})"
        )
        cls.wikihow = cls.minicroft.plugin_skills[WIKIHOW_ID].instance
        # stub the network-touching backend call, same convention as
        # test_common_query_arbitration.py -- routing/arbitration is under
        # test here, not the pywikihow scraper itself.
        cls.wikihow.get_how_to = lambda query, num=1: dict(_FAKE_HOW_TO)
        cls.bus = cls.minicroft.bus

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def _capture(self, utterance):
        session = Session(f"e2e-cq-{abs(hash(utterance))}")
        session.lang = LANG
        session.pipeline = list(_PIPELINE)
        msg = Message("recognizer_loop:utterance",
                       {"utterances": [utterance], "lang": LANG},
                       {"session": session.serialize(), "source": "A", "destination": "B"})
        capture = CaptureSession(
            self.minicroft,
            eof_msgs=["ovos.utterance.speak", "ovos.intent.unmatched"],
        )
        capture.capture(msg, timeout=30)
        return capture.finish()

    def _wikihow_candidates(self, msgs):
        return [
            m for m in msgs
            if m.msg_type == "question:query.response"
            and m.data.get("skill_id") == WIKIHOW_ID
            and m.data.get("answer")
        ]

    def test_positive_phrasings_are_claimed_via_common_query(self):
        for utterance, template in POSITIVE_UTTERANCES:
            with self.subTest(utterance=utterance, template=template):
                msgs = self._capture(utterance)
                candidates = self._wikihow_candidates(msgs)
                self.assertTrue(
                    candidates,
                    f"{utterance!r} (howto.intent template {template!r}) was never "
                    f"claimed by {WIKIHOW_ID} via common-query -- no "
                    f"question:query.response with an answer was seen"
                )
                self.assertEqual(candidates[0].data["answer"], _FAKE_HOW_TO["intro"])

    def test_unrelated_utterance_is_not_claimed(self):
        msgs = self._capture(NEGATIVE_UTTERANCE)
        candidates = self._wikihow_candidates(msgs)
        self.assertFalse(
            candidates,
            f"{NEGATIVE_UTTERANCE!r} was incorrectly claimed by {WIKIHOW_ID} via "
            f"common-query: {candidates!r}"
        )
