"""``wikihow.required`` holds the keywords a request must contain for ``wikihow.intent``.

A general how-to question names no service, so it goes to common query. Only a
request that names wikihow reaches ``wikihow.intent``.

Two readings of "whole word" exist for punctuation: the spec-tools helper deletes
punctuation, the m2v engine splits at it. A keyword, a golden row and a template
form must pass both.
"""
import json
import re
from pathlib import Path

import pytest
from ovos_spec_tools import expand
from ovos_spec_tools.resources import required_keywords_reject

ROOT = Path(__file__).resolve().parents[2]
LOCALES = sorted(d.name for d in (ROOT / "locale").iterdir() if (d / "wikihow.intent").exists())

# Golden rows that keep the speaker's short name for the service, which no keyword covers.
ROWS_REJECTED_BY_REQUIRED = {
    "fa-IR": {"ویکی راجع به پیتزا چه نظری دارد"},
    "pl-PL": {"powiedz, a co wiki mówi na temat pizzy"},
    "ru-RU": {"скажи, пожалуйста, а что Вики думает насчёт пиццы"},
}
# Template lines of the locale that name the service by its short name only.
LINES_WITHOUT_KEYWORD = {
    "ru-RU": {"Что говорит Вики о том, {query}", "поиск Wiki {query}", "что Вики думает о {query}"},
}


def _keywords(lang):
    path = ROOT / "locale" / lang / "wikihow.required"
    assert path.exists(), f"{lang}: wikihow.required is missing"
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def _words(text):
    return re.sub(r"[^\w]+", " ", text.lower()).split()


def _split_rule_accepts(utterance, keywords):
    words = " ".join(_words(utterance))
    return any(f" {' '.join(_words(k))} " in f" {words} " for k in keywords)


def _accepted_by_both(utterance, keywords):
    return _split_rule_accepts(utterance, keywords) and not required_keywords_reject(utterance, keywords)


@pytest.mark.parametrize("lang", LOCALES)
def test_locale_has_plain_keywords(lang):
    keywords = _keywords(lang)
    assert keywords, f"{lang}: wikihow.required is empty"
    assert not [k for k in keywords if re.search(r"[{}()\[\]<>|]", k)], f"{lang}: keywords must be plain words"


@pytest.mark.parametrize("lang", LOCALES)
def test_every_golden_positive_names_a_keyword(lang):
    keywords = _keywords(lang)
    rows = [json.loads(line) for line in
            (ROOT / "test" / "end2end" / f"golden_utterances_{lang}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    missing = {r["utterance"] for r in rows if r["intent_label"] == "wikihow.intent"
               and not _accepted_by_both(r["utterance"], keywords)}
    assert missing == ROWS_REJECTED_BY_REQUIRED.get(lang, set()), (
        f"{lang}: golden rows without a required keyword: {sorted(missing)}")


@pytest.mark.parametrize("lang", LOCALES)
def test_every_template_form_names_a_keyword(lang):
    keywords = _keywords(lang)
    lines = [line.strip() for line in
             (ROOT / "locale" / lang / "wikihow.intent").read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    without = {line for line in lines
               if not all(_accepted_by_both(form.replace("{query}", "x"), keywords) for form in expand(line))}
    assert without == LINES_WITHOUT_KEYWORD.get(lang, set()), (
        f"{lang}: template lines with a form that names no keyword: {sorted(without)}")
