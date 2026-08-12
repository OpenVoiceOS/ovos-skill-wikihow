"""Regression coverage for a silent common-query self-blacklist bug.

Live incident (ser9, 2026-08-12): "how to boil an egg" was answered by the
wolfie (WolframAlpha) skill via the common-query pipeline instead of wikihow,
with no error anywhere. Root cause: ``locale/en-US/misc_blacklist.voc``
shipped a bare ``how`` entry (added in PR #49 / commit 16d9c5b, 2025-04-11,
"avoid matching on how_to and time related queries") alongside legitimate
multi-word entries like ``how long``. ``match_common_query`` bails out on
``self.voc_match(phrase, "misc_blacklist")`` *before* ever extracting a
keyword or hitting the network -- and since almost every canonical "how to
X" utterance contains the word "how", wikihow silently withdrew from
common-query arbitration for essentially all of its own target queries. It
never produced a ``question:query.response`` with an answer at all, so
wolfie (or any other competing skill) won by default, not by merit.

NOTE: this fix does NOT change the reported incident's final outcome.
wolfie's common-query confidence is a fixed 0.8, wikihow's is a fixed 0.7,
so wolfie's answer still wins arbitration for "how to boil an egg" after
this fix -- wikihow now competes instead of being silently absent, but it
still loses on confidence. Whether that's the intended, permanent design
(PR #49 was deliberately trying to keep wikihow out of "how to" queries'
common-query path for some reason not documented in that PR) or whether
wikihow's confidence should be shaped per-query is an open design question
left to the maintainer; this PR does not attempt to force a different
winner.

The MiniCroft ``Session`` created by ``ovoscope.get_minicroft`` does not,
by default, include ``ovos-common-query-pipeline-plugin`` in its pipeline
(that plugin is opt-in via platform-recommends config, not the bare
mycroft.conf default) -- so the session pipeline is set explicitly here to
include it, otherwise the utterance is handled by ``ovos-fallback-pipeline-
plugin`` instead and the common-query bug this suite targets is never
exercised at all.

F1 -- stop hijack on a lost common-query candidacy (PR #88 review finding):
``match_common_query`` wrote ``self.session_results[sess.session_id]``
*before* common-query arbitration ran, and ``can_stop``/``stop_session``
only checked *presence* of that key, not whether wikihow's candidate had
actually been picked. Before this PR, the bare "how" entry in
``misc_blacklist.voc`` vetoed almost every "how to X" utterance before
``match_common_query`` ever ran, so this dormant bug was unreachable on
dev. Once #88 let wikihow actually compete (and lose, since wolfie's fixed
0.8 confidence beats wikihow's fixed 0.7 for every such query), wikihow
would falsely claim it could stop -- and *did* stop -- sessions it never
answered in. ``TestStopHijackOnLostCandidacy`` below is the regression
test for that: run "how to boil an egg" (wolfie wins), then send a stop in
the same session, and assert wikihow's own
``ovos-skill-wikihow.openvoiceos.stop.response`` reports
``result: False`` since it was never the selected candidate.
"""
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

WIKIHOW_ID = "ovos-skill-wikihow.openvoiceos"
WOLFIE_ID = "ovos-skill-wolfie.openvoiceos"
LANG = "en-US"

UTTERANCE = "how to boil an egg"
WOLFIE_CANNED_ANSWER = "Boiling an egg takes about ten minutes."

# Mirrors the default ovos-config mycroft.conf pipeline order, with
# ovos-common-query-pipeline-plugin inserted in the position it is shipped
# at in ovos_config/recommends/platform/linux.conf (after adapt-medium,
# before the fallback tiers) -- it is NOT present in the bare mycroft.conf
# default pipeline at all.
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
    "title": "Boil an Egg",
    "url": "https://www.wikihow.com/Boil-an-Egg",
    "intro": "Boiling an egg is a simple way to prepare a nutritious snack.",
    "n_steps": 1,
    "steps": [
        {"number": 1, "summary": "Put the egg in boiling water for ten minutes.",
         "description": "Then place it in cold water to stop cooking.", "picture": None},
    ],
}


def _assert_skills_loaded(minicroft, skill_ids):
    """Fail with a clear message, not a bare KeyError, if a skill silently
    failed to load into the MiniCroft.

    ``minicroft.plugin_skills`` only contains skills that loaded
    successfully -- a load failure (missing/broken dependency, plugin
    entry-point mismatch, transient install issue) is otherwise swallowed
    by the skill loader and only surfaces later as a confusing
    ``KeyError`` when a test indexes into ``plugin_skills`` by skill_id.
    Surfacing it here, right after boot, makes a genuinely missing
    dependency (e.g. ``ovos-skill-wolfie`` not resolving from the ``test``
    extra) immediately diagnosable instead of looking like an arbitration
    bug in this test suite.
    """
    loaded = set(minicroft.plugin_skills)
    missing = [sid for sid in skill_ids if sid not in loaded]
    assert not missing, (
        f"skill(s) failed to load into MiniCroft: {missing!r} "
        f"(loaded: {sorted(loaded)!r}) -- check that every dependency "
        f"those skills need is actually pulled in by this repo's "
        f"pyproject.toml [test] extra, and that the skill's plugin "
        f"entry point still resolves in the current environment"
    )


class TestCommonQueryArbitration(TestCase):
    """MiniCroft with wikihow AND wolfie loaded as a real competitor.

    wolfie is loaded (not just wikihow) because the second test below
    asserts BOTH skills actually submit a common-query candidate for this
    utterance -- that is the real shape of the live incident (two skills
    genuinely competing), not just wikihow answering in isolation.

    Both skills' network calls are stubbed for determinism/offline running;
    what is under test is routing/arbitration, not the scrapers themselves.
    """

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([WIKIHOW_ID, WOLFIE_ID])
        _assert_skills_loaded(cls.minicroft, [WIKIHOW_ID, WOLFIE_ID])
        cls.wikihow = cls.minicroft.plugin_skills[WIKIHOW_ID].instance
        cls.wolfie = cls.minicroft.plugin_skills[WOLFIE_ID].instance
        cls.wikihow.get_how_to = lambda query, num=1: dict(_FAKE_HOW_TO)
        cls.wolfie._get_answer = lambda utterance, lang: WOLFIE_CANNED_ANSWER
        cls.bus = cls.minicroft.bus

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def _capture(self, utterance):
        session = Session(f"e2e-{abs(hash(utterance))}")
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

    def test_wikihow_offers_a_candidate_answer_for_how_to_query(self):
        """Regression for the silent misc_blacklist self-rejection bug.

        wikihow must reach the point of returning an answer candidate to the
        common-query pipeline for a canonical "how to X" query, even with a
        competing common-query skill (wolfie) loaded. Before the fix,
        ``misc_blacklist`` (bare "how" entry) silently vetoed this before
        wikihow ever tried.
        """
        msgs = self._capture(UTTERANCE)
        wikihow_responses = [
            m for m in msgs
            if m.msg_type == "question:query.response"
            and m.data.get("skill_id") == WIKIHOW_ID
        ]
        self.assertTrue(wikihow_responses, "wikihow never responded to the common query at all")
        answered = [m for m in wikihow_responses if m.data.get("answer")]
        self.assertTrue(
            answered,
            f"wikihow responded but never offered an answer candidate: {wikihow_responses!r}"
        )
        self.assertEqual(answered[0].data["answer"], _FAKE_HOW_TO["intro"])

    def test_both_skills_submit_common_query_candidates(self):
        """Candidate-set assertion: does NOT pin who wins arbitration.

        This only asserts both wikihow and wolfie actually reach the
        common-query pipeline as competing candidates, each with a captured
        confidence value, for the utterance from the live incident. Which
        one the pipeline ultimately picks is a separate, legitimate
        arbitration decision (see module docstring) that this test
        deliberately does not pin -- pinning it would hardcode wolfie's
        confidence value, which lives in a different repo and can change
        independently of this one.
        """
        msgs = self._capture(UTTERANCE)
        candidates = {}
        for m in msgs:
            if m.msg_type != "question:query.response":
                continue
            if not m.data.get("answer"):
                continue
            candidates[m.data["skill_id"]] = m.data.get("conf")

        self.assertIn(WIKIHOW_ID, candidates, f"wikihow did not submit a candidate: {candidates!r}")
        self.assertIn(WOLFIE_ID, candidates, f"wolfie did not submit a candidate: {candidates!r}")
        self.assertIsInstance(candidates[WIKIHOW_ID], (int, float),
                               f"wikihow candidate has no captured confidence: {candidates[WIKIHOW_ID]!r}")
        self.assertIsInstance(candidates[WOLFIE_ID], (int, float),
                               f"wolfie candidate has no captured confidence: {candidates[WOLFIE_ID]!r}")


class TestStopHijackOnLostCandidacy(TestCase):
    """Regression coverage for the F1 stop-hijack finding (PR #88 review).

    wolfie wins arbitration for "how to boil an egg" (0.8 vs wikihow's
    fixed 0.7), so wikihow is never selected and never speaks. A stop sent
    in that same session must NOT be reported as handled by wikihow --
    before the fix, ``can_stop``/``stop_session`` keyed on mere presence in
    ``self.session_results`` (written unconditionally by
    ``match_common_query`` before arbitration), so wikihow claimed
    ``result: True`` for a session it never actually answered in.
    """

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([WIKIHOW_ID, WOLFIE_ID])
        _assert_skills_loaded(cls.minicroft, [WIKIHOW_ID, WOLFIE_ID])
        cls.wikihow = cls.minicroft.plugin_skills[WIKIHOW_ID].instance
        cls.wolfie = cls.minicroft.plugin_skills[WOLFIE_ID].instance
        cls.wikihow.get_how_to = lambda query, num=1: dict(_FAKE_HOW_TO)
        cls.wolfie._get_answer = lambda utterance, lang: WOLFIE_CANNED_ANSWER
        cls.bus = cls.minicroft.bus

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def test_wikihow_does_not_claim_stop_for_a_session_it_lost(self):
        session = Session(f"e2e-stop-{abs(hash(UTTERANCE))}")
        session.lang = LANG
        session.pipeline = list(_PIPELINE)

        # 1) ask the how-to question; wolfie should win arbitration
        utt_msg = Message("recognizer_loop:utterance",
                           {"utterances": [UTTERANCE], "lang": LANG},
                           {"session": session.serialize(), "source": "A", "destination": "B"})
        ask_capture = CaptureSession(
            self.minicroft,
            eof_msgs=["ovos.utterance.speak", "ovos.intent.unmatched"],
        )
        ask_capture.capture(utt_msg, timeout=30)
        ask_msgs = ask_capture.finish()

        candidates = {
            m.data["skill_id"]: m.data.get("conf")
            for m in ask_msgs
            if m.msg_type == "question:query.response" and m.data.get("answer")
        }
        self.assertIn(WOLFIE_ID, candidates)
        self.assertIn(WIKIHOW_ID, candidates)
        self.assertGreater(candidates[WOLFIE_ID], candidates[WIKIHOW_ID],
                            "test assumes wolfie wins arbitration over wikihow")

        # 2) send a stop in the SAME session and capture wikihow's own
        #    stop.response -- this is what the F1 fix guards.
        stop_msg = Message("mycroft.stop", {},
                            {"session": session.serialize(), "source": "A", "destination": "B"})
        stop_capture = CaptureSession(
            self.minicroft,
            eof_msgs=[f"{WIKIHOW_ID}.stop.response"],
        )
        stop_capture.capture(stop_msg, timeout=30)
        stop_msgs = stop_capture.finish()

        wikihow_stop_responses = [
            m for m in stop_msgs if m.msg_type == f"{WIKIHOW_ID}.stop.response"
        ]
        self.assertTrue(wikihow_stop_responses,
                         "wikihow never emitted a stop.response for the stop request")
        self.assertFalse(
            wikihow_stop_responses[0].data.get("result"),
            "wikihow claimed it handled stop for a session it never won/spoke in: "
            f"{wikihow_stop_responses[0].data!r}"
        )
