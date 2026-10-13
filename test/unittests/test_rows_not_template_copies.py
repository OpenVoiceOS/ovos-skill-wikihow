"""No golden row may contain every fixed word of a template line in order.

A row that holds the words of a template line in order, with filler around them,
is the template with the slot filled and padding added. A hyphen counts as a word
break in one reading and as part of the word in the other, and a row must pass both.
"""
import json
import re
from pathlib import Path

import pytest
from padacioso import expand

ROOT = Path(__file__).resolve().parents[2]
LOCALES = sorted(d.name for d in (ROOT / "locale").iterdir() if (d / "wikihow.intent").exists())


def _tokens(text, keep_hyphen):
    pattern = r"[^\w'’\-]+" if keep_hyphen else r"[^\w'’]+"
    return [w for w in re.split(pattern, text.lower().replace("‌", " ")) if w]


def _is_subsequence(needle, haystack):
    words = iter(haystack)
    return all(word in words for word in needle)


@pytest.mark.parametrize("lang", LOCALES)
def test_no_row_holds_a_template_line_in_order(lang):
    lines = [line.strip() for line in
             (ROOT / "locale" / lang / "wikihow.intent").read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    forms = {form for line in lines for form in expand(line)}
    rows = [json.loads(line)["utterance"] for line in
            (ROOT / "test" / "end2end" / f"golden_utterances_{lang}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    copies = []
    for row in rows:
        for keep_hyphen in (True, False):
            row_words = _tokens(row, keep_hyphen)
            for form in forms:
                fixed = _tokens(form.replace("{query}", " "), keep_hyphen)
                if fixed and _is_subsequence(fixed, row_words):
                    copies.append((row, form))
    assert not copies, f"{lang}: rows that hold a template line in order: {copies[:5]}"
