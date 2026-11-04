"""Is a wrong sound a common, explainable confusion? (Decision Log D64)

Pure function, no model: a substitution (the learner said /o/ where /ɔ̃/ was
expected) is NEAR when the (target, produced) pair is in CONFUSION_REASONS, a
short hand-written table of common French confusions, each with the reasons
that explain it (primary first). Any other pair is FAR. The UI shows the two
differently and, for near ones, says what is off.

"Near" means a CLOSE confusion that one fix corrects. Common but distant
confusions (ʁ -> l, ʁ -> ɡ) are deliberately left out and show as far. The
table is directional (the reason flips with the direction) and not validated
on learner data. Pairs that are missing (ʁ -> ɣ, i/e, u/o, b/v, ...) count as
far until added. Extending it is post-MVP work (Roadmap).

Phones are compared after normalisation: Unicode NFD (nasal vowels are base +
U+0303) and ASCII g -> ɡ (U+0261), since the G2P and the recognizers may use
either spelling.

Returns REASON CODES, not sentences: the wording belongs to the UI.
"""

import unicodedata

# Reason codes. The UI maps each to a sentence (frontend/src/learnerText.tsx).
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


def _norm(phone: str) -> str:
    return unicodedata.normalize("NFD", phone).replace("g", "ɡ")


# Key: (target, produced). Value: reasons, primary first.
_TABLE: dict[tuple[str, str], list[str]] = {
    # ---------------------------------------------------------------- oral vowels
    # /y/ - /u/   tu/tout, rue/roue, dessus/dessous
    ("y", "u"): [TOO_FAR_BACK],
    ("u", "y"): [TOO_FAR_FORWARD],
    # /y/ - /i/   vue/vie, lu/lit, pur/pire
    ("y", "i"): [NOT_ROUNDED],
    ("i", "y"): [OVER_ROUNDED],
    # /y/ - /ø/   du/deux, vu/vœu
    ("y", "ø"): [TOO_OPEN],
    ("ø", "y"): [NOT_OPEN_ENOUGH],
    # /ø/ - /œ/   jeûne/jeune
    ("ø", "œ"): [TOO_OPEN],
    ("œ", "ø"): [NOT_OPEN_ENOUGH],
    # /ə/ - /e/   le/les, de/des, ce/ces
    # French schwa is realised as a front rounded vowel (~[ø]/[œ]),
    # so the main difference from /e/ is lip rounding.
    ("ə", "e"): [NOT_ROUNDED],
    ("e", "ə"): [OVER_ROUNDED],
    # /e/ - /ɛ/   fée/fait, les/lait, j'irai/j'irais
    ("e", "ɛ"): [TOO_OPEN],
    ("ɛ", "e"): [NOT_OPEN_ENOUGH],
    # /o/ - /ɔ/   saute/sotte, paume/pomme
    ("o", "ɔ"): [TOO_OPEN],
    ("ɔ", "o"): [NOT_OPEN_ENOUGH],
    # /a/ - /ɑ/   patte/pâte (mostly merged)
    ("a", "ɑ"): [TOO_FAR_BACK],
    ("ɑ", "a"): [TOO_FAR_FORWARD],
    # --------------------------------------------------------------- nasal vowels
    # /ɑ̃/ - /ɔ̃/  vent/vont, sans/son, temps/ton
    # /ɔ̃/ is realised close to [õ]: rounded and closer than /ɑ̃/.
    ("ɑ̃", "ɔ̃"): [OVER_ROUNDED, NOT_OPEN_ENOUGH],
    ("ɔ̃", "ɑ̃"): [NOT_ROUNDED, TOO_OPEN],
    # /ɛ̃/ - /ɑ̃/  vin/vent, pin/pan, main/ment
    ("ɛ̃", "ɑ̃"): [TOO_FAR_BACK],
    ("ɑ̃", "ɛ̃"): [TOO_FAR_FORWARD],
    # /ɛ̃/ - /œ̃/  brin/brun (mostly merged)
    ("ɛ̃", "œ̃"): [OVER_ROUNDED],
    ("œ̃", "ɛ̃"): [NOT_ROUNDED],
    # Nasal vs oral   bon/bonne, plein/pleine, an/Anne
    ("ɔ̃", "ɔ"): [MISSING_NASALITY],
    ("ɔ", "ɔ̃"): [EXTRA_NASALITY],
    # /ɔ̃/ is realised close to [õ], so its usual oral substitute is /o/
    # (bonjour said [boʒuʁ]).
    ("ɔ̃", "o"): [MISSING_NASALITY],
    ("o", "ɔ̃"): [EXTRA_NASALITY],
    ("ɛ̃", "ɛ"): [MISSING_NASALITY],
    ("ɛ", "ɛ̃"): [EXTRA_NASALITY],
    ("ɑ̃", "a"): [MISSING_NASALITY],
    ("a", "ɑ̃"): [EXTRA_NASALITY],
    ("œ̃", "œ"): [MISSING_NASALITY],
    ("œ", "œ̃"): [EXTRA_NASALITY],
    # ----------------------------------------------------------------- semivowels
    # /ɥ/ - /w/   huit/ouïe, lui/Louis
    ("ɥ", "w"): [TOO_FAR_BACK],
    ("w", "ɥ"): [TOO_FAR_FORWARD],
    # /ɥ/ - /j/
    ("ɥ", "j"): [NOT_ROUNDED],
    ("j", "ɥ"): [OVER_ROUNDED],
    # ----------------------------------------------------------------- consonants
    # /ʁ/ - /r/   apical trill instead of the uvular R: an older / regional
    # French variant, never changes meaning. The fix is where the tongue works.
    ("ʁ", "r"): [WRONG_PLACE],
    ("r", "ʁ"): [WRONG_PLACE],
    # /ʁ/ - /z/   (northern Vietnamese "r" = [z])
    ("ʁ", "z"): [WRONG_PLACE],
    ("z", "ʁ"): [WRONG_PLACE],
    # Left out on purpose: ʁ/l (rit/lit) and ʁ/ɡ (rare/gare) are common but
    # distant (place AND manner differ); they show as far until the UI has a
    # third level for "common but not close" (post-MVP).
    # /s/ - /ʃ/   sou/chou, sang/chant, ce/chez
    # French /ʃ ʒ/ also have lip protrusion -> rounding as secondary reason.
    ("ʃ", "s"): [WRONG_PLACE, NOT_ROUNDED],
    ("s", "ʃ"): [WRONG_PLACE, OVER_ROUNDED],
    # /z/ - /ʒ/   case/cage, rase/rage
    ("ʒ", "z"): [WRONG_PLACE, NOT_ROUNDED],
    ("z", "ʒ"): [WRONG_PLACE, OVER_ROUNDED],
    # Voicing pairs
    # /s/ - /z/   poisson/poison, basse/base, douce/douze
    ("s", "z"): [EXTRA_VOICING],
    ("z", "s"): [MISSING_VOICING],
    # /ʃ/ - /ʒ/   chou/joue
    ("ʃ", "ʒ"): [EXTRA_VOICING],
    ("ʒ", "ʃ"): [MISSING_VOICING],
    # /p/ - /b/   pain/bain, poisson/boisson
    ("p", "b"): [EXTRA_VOICING],
    ("b", "p"): [MISSING_VOICING],
    # /t/ - /d/   thé/dé
    ("t", "d"): [EXTRA_VOICING],
    ("d", "t"): [MISSING_VOICING],
    # /k/ - /ɡ/   coût/goût, car/gare, classe/glace
    ("k", "ɡ"): [EXTRA_VOICING],
    ("ɡ", "k"): [MISSING_VOICING],
    # /f/ - /v/   fou/vous, neuf/neuve, vif/vive
    ("f", "v"): [EXTRA_VOICING],
    ("v", "f"): [MISSING_VOICING],
}

CONFUSION_REASONS: dict[tuple[str, str], list[str]] = {
    (_norm(target), _norm(produced)): reasons for (target, produced), reasons in _TABLE.items()
}


def near_reasons(target: str, produced: str) -> list[str] | None:
    """Reasons (primary first) when (target, produced) is a known common
    confusion, `[]` when both are spellings of the same sound (g / ɡ),
    `None` otherwise (a far substitution).

    Only meant for two DIFFERENT phones from a substitution op."""
    a, b = _norm(target), _norm(produced)
    if a == b:
        return []
    reasons = CONFUSION_REASONS.get((a, b))
    return list(reasons) if reasons is not None else None
