"""FreePhoneRecognizer backed by bofenghuang/phonemizer-wav2vec2-ctc-french.

Second Nhóm A candidate (chat discussion) — "inspired by" Cnam-LMSSC per
its own model card, trained with the SAME ground-truth phonemizer
convention (Python `phonemizer` package, `EspeakBackend("fr-fr")`,
word-separated/phone-unseparated), confirmed by fetching its real
vocab.json: character-level IPA, combining marks as separate tokens — same
as Cnam-LMSSC, so it reuses the identical shared CTC logic
(`_wav2vec2_ctc_common.py`) with no changes.

Known difference from Cnam-LMSSC (not expected to matter for French):
missing a few IPA symbols outside the French inventory (ɣ, ɨ, ɾ, β) that
Cnam-LMSSC's vocab happens to include. Every phoneme needed by the
diagnostic set (D43/D44) is present in both.

Unlike Cnam-LMSSC, this model's card publishes no PER/benchmark numbers —
flagged in the chat discussion as a real difference worth weighing, not
just a vocabulary question, when comparing the two via
experiments/runners/compare_free_decoder.py.
"""

from core.registry import register
from stages.speech_assessment.free_decode._wav2vec2_ctc_common import (
    Wav2Vec2CTCPhoneRecognizerBase,
)


@register("free_decoder", "wav2vec2_bofenghuang")
class Wav2Vec2BofenghuangPhoneRecognizer(Wav2Vec2CTCPhoneRecognizerBase):
    def __init__(self, model_name: str = "bofenghuang/phonemizer-wav2vec2-ctc-french"):
        super().__init__(model_name)