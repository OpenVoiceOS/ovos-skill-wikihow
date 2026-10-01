"""Regression coverage for OpenVoiceOS/ovos-skill-wikihow#105 review finding
(knowledge/wiki/audits/gate-ledger/review-ovos-skill-wikihow-105.md).

``misc_blacklist.voc`` and ``weather.voc`` are veto vocabularies:
``match_common_query`` returns ``None`` before it ever looks for a "how to"
keyword when either file matches (see ``__init__.py``, the
``self.voc_match(phrase, "misc_blacklist") or self.voc_match(phrase,
"weather")`` guard). A bare or ambiguous entry in either file silently
withdraws the skill from ordinary questions in that language.

PR #105 added these files for eu-ES, gl-ES, it-IT and pt-PT by translating
the en-US entries word by word, and three of the new entries vetoed
ordinary how-to questions:

- eu-ES ``da`` ("is") is one of the most common Basque words and appears in
  most "how is X done" questions.
- gl-ES ``É`` ("is it"), once ASCII-folded by ``voc_match``, becomes ``e``,
  the Galician word for "and".
- pt-PT ``tempo`` in ``weather.voc`` means both "weather" and "time", so it
  vetoed any "how to ... time" question.
"""
import unittest

from ovos_utils.fakebus import FakeBus

from ovos_skill_wikihow import WikiHowSkill


def _make_skill():
    return WikiHowSkill(bus=FakeBus(), skill_id="test.wikihow")


class TestBlacklistDoesNotVetoOrdinaryQuestions(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.skill = _make_skill()

    def _assert_not_vetoed(self, lang, phrase):
        self.assertFalse(
            self.skill.voc_match(phrase, "misc_blacklist", lang=lang),
            f"{lang}: misc_blacklist.voc vetoed ordinary question {phrase!r}",
        )
        self.assertFalse(
            self.skill.voc_match(phrase, "weather", lang=lang),
            f"{lang}: weather.voc vetoed ordinary question {phrase!r}",
        )

    def _assert_vetoed(self, lang, phrase):
        self.assertTrue(
            self.skill.voc_match(phrase, "weather", lang=lang),
            f"{lang}: weather.voc did not veto weather question {phrase!r}",
        )

    def test_eu_es_ordinary_questions_not_vetoed(self):
        for phrase in [
            "nola egiten da ogia",       # was vetoed by bare "da"
            "nola egin ogia etxean",
            "nola prestatu kafea goizean",
        ]:
            self._assert_not_vetoed("eu-ES", phrase)

    def test_gl_es_ordinary_questions_not_vetoed(self):
        for phrase in [
            "como se fai o pan e o viño",  # was vetoed by "É" -> "e" ("and")
            "como facer pan",
            "como facer un bolo e un pan",
        ]:
            self._assert_not_vetoed("gl-ES", phrase)

    def test_pt_pt_ordinary_questions_not_vetoed(self):
        for phrase in [
            "como poupar tempo e dinheiro",  # was vetoed by weather "tempo"
            "como fazer pão",
            "como organizar o meu tempo",
        ]:
            self._assert_not_vetoed("pt-PT", phrase)

    def test_pt_pt_weather_questions_still_vetoed(self):
        for phrase in [
            "como está o tempo hoje",
            "como vai estar o tempo amanhã",
            "qual é a previsão do tempo para amanhã",
        ]:
            self._assert_vetoed("pt-PT", phrase)

    def test_it_it_ordinary_questions_not_vetoed(self):
        for phrase in [
            "come si fa il pane e la pizza",
            "come risparmiare tempo e denaro",
            "come cucinare la pasta",
        ]:
            self._assert_not_vetoed("it-IT", phrase)


class TestWikihowIntentBlacklistVetoesWordnet(unittest.TestCase):
    """``wikihow.blacklist`` words reach padatious as ``blacklisted_words``.

    CI run 34774266957 (attempt 1): padatious-medium matched
    "ask wordnet about word" to ``wikihow.intent`` with ``query="word"``. The
    score is near the medium threshold (0.597 on ovos-padatious 2.1.4a1), so
    the same test passed on the next attempt. The blacklist veto removes the
    match on every run.
    """

    @classmethod
    def setUpClass(cls):
        import tempfile
        from pathlib import Path

        from ovos_padatious import IntentContainer
        from ovos_spec_tools import expand

        locale = Path(__file__).resolve().parents[2] / "locale" / "en-US"

        def _lines(name):
            with open(locale / name, encoding="utf-8") as f:
                return [line.strip() for line in f
                        if line.strip() and not line.startswith("#")]

        samples = sorted({s for line in _lines("wikihow.intent") for s in expand(line)})
        # a <ref> line expands from another vocabulary; only literal words here
        words = [w for w in _lines("wikihow.blacklist") if not w.startswith("<")]
        cls._cache = tempfile.TemporaryDirectory()
        cls.container = IntentContainer(cls._cache.name)
        cls.container.add_intent("wikihow", samples, blacklisted_words=words)
        cls.container.train()

    @classmethod
    def tearDownClass(cls):
        cls._cache.cleanup()

    def test_wordnet_request_not_matched(self):
        match = self.container.calc_intent("ask wordnet about word")
        self.assertNotEqual(match.name, "wikihow",
                            f"wikihow.intent matched with conf {match.conf}")

    def test_wikihow_requests_still_matched(self):
        for phrase in ["search wikihow for tie a tie",
                       "what does wikihow say about knots"]:
            self.assertEqual(self.container.calc_intent(phrase).name, "wikihow", phrase)


if __name__ == "__main__":
    unittest.main()
