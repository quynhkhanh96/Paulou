"""How close is a wrong sound to the right one? (Decision Log D64)

Pure function, no model: a substitution (the learner said /o/ where /ɔ̃/ was
expected) is either NEAR (one or two articulatory features differ: the learner
is on the right track) or FAR (anything else). The UI shows the two
differently and, for near ones, says which feature is off.

The distance is a small hand-written feature comparison over the French
phoneme inventory (IPA as produced by the G2P and the recognizers, nasal
vowels as base + U+0303):

- vowels: height (0 close .. 4 open), backness (0 front, 1 central, 2 back),
  lip rounding, nasality. distance = 0.5 * |height difference| + one point for
  each of backness, rounding and nasality that differs. NEAR when <= 2.
- consonants: place, manner, voicing. distance = number of features that
  differ. NEAR when <= 1.
- a vowel against a consonant, or a phone missing from the tables, is FAR.

The tables and thresholds are first-draft values (from the alignment-lab UX
prototype), not tuned on learner data. They are the part most likely to need
revisiting; keeping them here, away from the UI, lets them be tested and
changed in one place.

Returns REASON CODES, not sentences: the wording belongs to the UI.
"""

import unicodedata

NASAL = "̃"

# [height 0 close .. 4 open, backness 0 front / 1 central / 2 back, rounded, nasal]
_VOWELS: dict[str, tuple[int, int, int, int]] = {
    "i": (0, 0, 0, 0),
    "y": (0, 0, 1, 0),
    "u": (0, 2, 1, 0),
    "e": (1, 0, 0, 0),
    "ø": (1, 0, 1, 0),
    "o": (1, 2, 1, 0),
    "ə": (2, 1, 1, 0),
    "ɛ": (3, 0, 0, 0),
    "œ": (3, 0, 1, 0),
    "ɔ": (3, 2, 1, 0),
    "a": (4, 0, 0, 0),
    "ɑ": (4, 2, 0, 0),
    "ɛ" + NASAL: (3, 0, 0, 1),
    "œ" + NASAL: (3, 0, 1, 1),
    "ɔ" + NASAL: (3, 2, 1, 1),
    "ɑ" + NASAL: (4, 2, 0, 1),
}

# (place, manner, voiced). Place is an arbitrary ordinal label: only equality is used.
_CONSONANTS: dict[str, tuple[int, str, int]] = {
    "p": (0, "stop", 0),
    "b": (0, "stop", 1),
    "t": (2, "stop", 0),
    "d": (2, "stop", 1),
    "k": (5, "stop", 0),
    "ɡ": (5, "stop", 1),
    "g": (5, "stop", 1),  # ASCII g is the same sound as ɡ (U+0261)
    "f": (1, "fricative", 0),
    "v": (1, "fricative", 1),
    "s": (2, "fricative", 0),
    "z": (2, "fricative", 1),
    "ʃ": (3, "fricative", 0),
    "ʒ": (3, "fricative", 1),
    "m": (0, "nasal", 1),
    "n": (2, "nasal", 1),
    "ɲ": (4, "nasal", 1),
    "ŋ": (5, "nasal", 1),
    "l": (2, "lateral", 1),
    "ʁ": (6, "fricative", 1),
    "r": (2, "trill", 1),
    "j": (4, "approximant", 1),
    "w": (7, "approximant", 1),
    "ɥ": (8, "approximant", 1),
    "h": (9, "fricative", 0),
}

VOWEL_NEAR_MAX = 2.0
CONSONANT_NEAR_MAX = 1

# Reason codes. The UI maps each to a sentence (frontend/src/learnerText.ts).
MISSING_NASALITY = "missing_nasality"
EXTRA_NASALITY = "extra_nasality"
NOT_ROUNDED = "not_rounded"
OVER_ROUNDED = "over_rounded"
TOO_FAR_BACK = "too_far_back"
TOO_FAR_FORWARD = "too_far_forward"
NOT_OPEN_ENOUGH = "not_open_enough"
TOO_OPEN = "too_open"
MISSING_VOICING = "missing_voicing"
EXTRA_VOICING = "extra_voicing"
WRONG_PLACE = "wrong_place"
WRONG_MANNER = "wrong_manner"


def _key(phone: str) -> str:
    return unicodedata.normalize("NFD", phone)


def near_reasons(canonical: str, decoded: str) -> list[str] | None:
    """`None` when `decoded` is NOT near `canonical` (a far substitution);
    otherwise the list of features that differ, possibly empty (two symbols
    for the same sound, e.g. `g` and `ɡ`).

    Only meant for two DIFFERENT phones from a substitution op."""
    a, b = _key(canonical), _key(decoded)

    if a in _VOWELS and b in _VOWELS:
        x, y = _VOWELS[a], _VOWELS[b]
        distance = 0.5 * abs(x[0] - y[0]) + (x[1] != y[1]) + (x[2] != y[2]) + (x[3] != y[3])
        if distance > VOWEL_NEAR_MAX:
            return None
        reasons: list[str] = []
        if x[3] and not y[3]:
            reasons.append(MISSING_NASALITY)
        if not x[3] and y[3]:
            reasons.append(EXTRA_NASALITY)
        if x[2] and not y[2]:
            reasons.append(NOT_ROUNDED)
        if not x[2] and y[2]:
            reasons.append(OVER_ROUNDED)
        if x[1] < y[1]:
            reasons.append(TOO_FAR_BACK)
        if x[1] > y[1]:
            reasons.append(TOO_FAR_FORWARD)
        if y[0] < x[0]:
            reasons.append(NOT_OPEN_ENOUGH)
        if y[0] > x[0]:
            reasons.append(TOO_OPEN)
        return reasons

    if a in _CONSONANTS and b in _CONSONANTS:
        x, y = _CONSONANTS[a], _CONSONANTS[b]
        distance = (x[0] != y[0]) + (x[1] != y[1]) + (x[2] != y[2])
        if distance > CONSONANT_NEAR_MAX:
            return None
        reasons = []
        if x[2] and not y[2]:
            reasons.append(MISSING_VOICING)
        if not x[2] and y[2]:
            reasons.append(EXTRA_VOICING)
        if x[0] != y[0]:
            reasons.append(WRONG_PLACE)
        if x[1] != y[1]:
            reasons.append(WRONG_MANNER)
        return reasons

    return None
