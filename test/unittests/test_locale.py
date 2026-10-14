"""
Tests for the en-US intent definitions and the {query} pronoun slot-value
exclusion (OVOS-INTENT-2 §4.3).
"""
import os
import unittest

from ovos_spec_tools import expand

LOCALE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "locale", "en-US",
)


def _lines(name):
    with open(os.path.join(LOCALE, name)) as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]


def _samples(name):
    out = []
    for line in _lines(name):
        out.extend(expand(line))
    return out


class TestIntentAnchoring(unittest.TestCase):
    """Every wikihow.intent template must name wikihow so the open {query}
    slot cannot swallow utterances another skill should own."""

    def test_every_wikihow_sample_is_keyword_anchored(self):
        for sample in _samples("wikihow.intent"):
            self.assertIn("wiki", sample,
                          f"un-anchored template would over-grab: {sample!r}")

    def test_howto_templates_carry_query_slot(self):
        for line in _lines("howto.intent"):
            self.assertIn("{query}", line,
                          f"how-to template lost its query slot: {line!r}")


class TestPronounSlotExclusion(unittest.TestCase):
    """query.blacklist keeps anaphoric pronouns out of the {query} slot."""

    def _blacklist(self):
        return [w.lower() for w in _samples("query.blacklist")]

    def test_pronouns_excluded_from_query(self):
        excluded = self._blacklist()
        for word in ("he", "she", "it", "they", "him", "her", "them", "this",
                     "that", "one"):
            self.assertIn(word, excluded)


if __name__ == "__main__":
    unittest.main()
