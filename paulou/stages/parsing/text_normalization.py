"""Text normalization before parsing (Decision Log D68).

Pure, deterministic logic -- no Protocol/registry wrapper (Decision Log D12).

Turns the sentence the learner typed into the sentence as it is SPOKEN, in
written words, so that every later stage sees words it can handle:
- the liaison rules, elision lookup and G2P all work on written words:
  "21 ans" has to reach them as "vingt et un ans" for "un‿ans" to be
  considered at all;
- elision detection only recognizes the ASCII apostrophe U+0027
  (stages/chunk_analyzer/elision/elision.py), so "J’ai" (U+2019, what phone
  keyboards and word processors type) would otherwise be missed;
- `locate_spans` (D48) is strict: the TTS must read exactly the text the
  analyzer saw, so digits must not be left for the TTS to expand itself.

The result is what the learner sees and practises (D68), and what the TTS
reads.

Order of the rules matters, most specific first: apostrophes,
abbreviations, times ("14 h 30"), ordinals ("1er"), percentages, decimals
("3,5"), grouped thousands ("10 000"), then any remaining integer.

KNOWN GAPS (D68, accepted for MVP, checked by hand only):
- Gender of "un" before a noun is only fixed for a short list of common
  feminine nouns (`_FEMININE_NOUNS`); "21 pommes" gives "vingt et un pommes".
- Not covered: dates ("07/11/2026"), currencies ("5 €"), phone numbers,
  Roman numerals ("XXe siècle"), negative numbers, units ("5 km"), and
  abbreviations not in `_ABBREVIATIONS`. Digits inside these are still read
  as plain integers, which is usually understandable but not always idiomatic.
- Years are read the standard way ("mille neuf cent quatre-vingt-dix-neuf"),
  not the also-common "dix-neuf cent ...".

VERSION NOTE: verified against num2words==0.5.14 (lang="fr"). Its French
output already uses "et" where French does ("vingt et un", "soixante et
onze") and hyphens elsewhere ("vingt-six"); an update could change the
spelling and so the words shown to the learner.
"""

import re
import unicodedata

from num2words import num2words

# Apostrophe look-alikes, all mapped to U+0027.
_APOSTROPHES = "’‘ʼ´`′"
_APOSTROPHE_TABLE = str.maketrans({ch: "'" for ch in _APOSTROPHES})

# Abbreviation -> spoken form. Matched as a whole token (see
# `_ABBREVIATION_RE`); the case of the first letter follows the position in
# the sentence (`_match_case`), not this table.
_ABBREVIATIONS: dict[str, str] = {
    "M.": "monsieur",
    "MM.": "messieurs",
    "Mme": "madame",
    "Mme.": "madame",
    "Mmes": "mesdames",
    "Mlle": "mademoiselle",
    "Mlles": "mesdemoiselles",
    "Dr": "docteur",
    "Dr.": "docteur",
    "Pr": "professeur",
    "Pr.": "professeur",
    "n°": "numéro",
    "N°": "numéro",
    "etc.": "et cetera",
}

# Longest first so "Mme." wins over "Mme", "MM." over "M.".
_ABBREVIATION_RE = re.compile(
    r"(?<![\w.])("
    + "|".join(re.escape(a) for a in sorted(_ABBREVIATIONS, key=len, reverse=True))
    + r")(?!\w)"
)

# Common feminine nouns that follow a number; "un" becomes "une" before
# them ("1 heure" -> "une heure", "21 fois" stays masculine-agnostic but
# "21 minutes" -> "vingt et une minutes").
_FEMININE_NOUNS: frozenset[str] = frozenset(
    {
        "heure", "heures", "minute", "minutes", "seconde", "secondes",
        "semaine", "semaines", "année", "années", "fois", "personne",
        "personnes", "page", "pages", "place", "places", "chose", "choses",
        "fille", "filles", "femme", "femmes", "voiture", "voitures",
        "pomme", "pommes", "journée", "journées", "nuit", "nuits",
        "chambre", "chambres", "classe", "classes", "langue", "langues",
    }
)

_TIME_RE = re.compile(r"(?<![\w,.])(\d{1,2})\s?h(?:\s?(\d{2}))?(?!\w)")
_ORDINAL_RE = re.compile(r"(?<![\w,.])(\d+)(er|re|ère|ème|e)(?!\w)")
_PERCENT_RE = re.compile(r"(?<![\w,.])(\d+(?:,\d+)?)\s?%")
_DECIMAL_RE = re.compile(r"(?<![\w,.])(\d+),(\d+)(?![\d,])")
# Thousands grouped with a space, a no-break space or a narrow no-break space.
_GROUPED_RE = re.compile(r"(?<![\w,.])\d{1,3}(?:[   ]\d{3})+(?![\d,])")
_INTEGER_RE = re.compile(r"\d+")
_NEXT_WORD_RE = re.compile(r"\s*([^\W\d_]+)")


def _match_case(spoken: str, text: str, start: int) -> str:
    """Capitalize `spoken` when it starts the sentence or follows . ! ? …"""
    before = text[:start].rstrip()
    if not before or before[-1] in ".!?…":
        return spoken[:1].upper() + spoken[1:]
    return spoken


def _feminine(words: str) -> str:
    """'vingt et un' -> 'vingt et une'; 'un' -> 'une'; other numbers unchanged."""
    if words == "un" or words.endswith((" un", "-un")):
        return words + "e"
    return words


def _cardinal(digits: str, next_word: str | None = None) -> str:
    words = num2words(int(digits), lang="fr")
    if next_word is not None and next_word.lower() in _FEMININE_NOUNS:
        words = _feminine(words)
    return words


def _decimal(int_part: str, frac_part: str) -> str:
    """'3', '05' -> 'trois virgule zéro cinq' (leading zeros read one by one)."""
    stripped = frac_part.lstrip("0")
    zeros = len(frac_part) - len(stripped)
    pieces = [_cardinal(int_part), "virgule"] + ["zéro"] * zeros
    if stripped:
        pieces.append(_cardinal(stripped))
    return " ".join(pieces)


def _time(match: re.Match) -> str:
    hours, minutes = int(match.group(1)), match.group(2)
    if hours > 24 or (minutes is not None and int(minutes) > 59):
        return match.group(0)  # not a time; left for the integer rule
    hour_words = _feminine(num2words(hours, lang="fr"))
    spoken = f"{hour_words} {'heure' if hours <= 1 else 'heures'}"
    if minutes is not None and int(minutes) > 0:
        spoken += " " + _feminine(num2words(int(minutes), lang="fr"))
    return spoken


def _ordinal(match: re.Match) -> str:
    number, suffix = int(match.group(1)), match.group(2)
    if number == 1:
        return "première" if suffix in ("re", "ère") else "premier"
    if suffix in ("er", "re", "ère"):
        return match.group(0)  # "2er" is not an ordinal; left as is
    return num2words(number, lang="fr", to="ordinal")


def _percent(match: re.Match) -> str:
    amount = match.group(1)
    if "," in amount:
        int_part, frac_part = amount.split(",")
        return f"{_decimal(int_part, frac_part)} pour cent"
    return f"{_cardinal(amount)} pour cent"


def _integer(match: re.Match) -> str:
    following = _NEXT_WORD_RE.match(match.string, match.end())
    return _cardinal(match.group(0), following.group(1) if following else None)


def normalize_for_speech(text: str) -> str:
    """Rewrite `text` the way it is spoken, in written words (D68).

    Idempotent: normalizing an already normalized sentence returns it
    unchanged. Whitespace is collapsed and the ends stripped.
    """
    text = unicodedata.normalize("NFC", text).translate(_APOSTROPHE_TABLE).strip()
    starts_with_digit = text[:1].isdigit()

    text = _ABBREVIATION_RE.sub(
        lambda m: _match_case(_ABBREVIATIONS[m.group(1)], m.string, m.start()), text
    )
    text = _TIME_RE.sub(_time, text)
    text = _ORDINAL_RE.sub(_ordinal, text)
    text = _PERCENT_RE.sub(_percent, text)
    text = _DECIMAL_RE.sub(lambda m: _decimal(m.group(1), m.group(2)), text)
    text = _GROUPED_RE.sub(lambda m: re.sub(r"\D", "", m.group(0)), text)
    text = _INTEGER_RE.sub(_integer, text)

    text = re.sub(r"\s+", " ", text).strip()
    if starts_with_digit:
        # "21 ans plus tard" -> "Vingt et un ans plus tard": a number that
        # started the sentence is capitalized like any first word.
        text = text[:1].upper() + text[1:]
    return text
