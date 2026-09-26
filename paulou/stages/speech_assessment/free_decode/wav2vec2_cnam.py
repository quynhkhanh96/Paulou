"""FreePhoneRecognizer backed by Cnam-LMSSC/wav2vec2-french-phonemizer.

Implements the real Stage B model (Decision Log D36/D37/D42's
FreePhoneRecognizer Protocol, core/interfaces.py) — the model used for the
first real canonicalizer-bias results (chat discussion; see Decision Log
for the D-number once filed).

Phoneme-set compatibility (verified against the model's real vocab.json,
not assumed): character-level IPA with Unicode combining marks as
SEPARATE tokens (e.g. the nasal-vowel combining tilde "̃" has its own id)
— the SAME decomposed convention already handled for Piper's synthesis
input (D43), just in the opposite direction: the model's DECODED output is
RECOMPOSED back into Lexique400's grouped-phoneme convention
(`LexiqueEspeakG2P._segment_ipa`, D30) before comparison via
`align_phonemes` (D38). See `_wav2vec2_ctc_common.py` for the shared CTC
decoding logic (also used by wav2vec2_bofenghuang.py) and its own
docstring for the flagged design choices: `audio: bytes` is raw WAV file
bytes, resampled internally to this model's required 16kHz (Piper's own
diagnostic audio, D43, is 22050Hz); a CTC-collapsed phone's confidence is
the MEAN of its frames' confidences (consistent with D33/D40's existing
MEAN-aggregation precedent).

NOT registered as a TTSProvider or any other stage — this is speech
RECOGNITION, the opposite direction from Piper's synthesis (which remains
`experiments/`-only tooling per D43, not a pipeline stage).
"""

from core.registry import register
from stages.speech_assessment.free_decode._wav2vec2_ctc_common import (
    Wav2Vec2CTCPhoneRecognizerBase,
    ctc_collapse,
    recompose_combining_marks,
)


@register("free_decoder", "wav2vec2_cnam")
class Wav2Vec2CnamPhoneRecognizer(Wav2Vec2CTCPhoneRecognizerBase):
    def __init__(self, model_name: str = "Cnam-LMSSC/wav2vec2-french-phonemizer"):
        super().__init__(model_name)


if __name__ == "__main__":
    # Sanity-check the shared pure functions with synthetic data -- no
    # model, no network needed. Uses the real vocab layout confirmed
    # against Cnam-LMSSC's actual vocab.json (chat discussion).
    id2label = {0: "|", 5: "œ", 6: "̃", 7: "e", 8: "ʁ", 9: "o", 58: "[PAD]"}
    blank_id, delimiter_id = 58, 0

    # Simulates raw CTC frames for "un héros" native (no liaison): a few
    # repeated frames per phone (typical CTC behavior), word delimiter
    # between "un" and "héros", blank frames at the boundaries.
    frame_ids =        [58, 5, 5, 6, 58,  0, 58, 7, 7, 8, 9, 9, 58]
    frame_confidences = [.9,.8,.85,.7,.9, .95,.9,.8,.75,.9,.85,.8,.9]
    ms_per_frame = 20.0

    phones, confidences, boundaries = ctc_collapse(
        frame_ids, frame_confidences, ms_per_frame, blank_id, delimiter_id, id2label
    )
    print("after ctc_collapse:", phones)
    assert phones == ["œ", "̃", "e", "ʁ", "o"], phones

    final_phones, final_confidences, final_boundaries = recompose_combining_marks(
        phones, confidences, boundaries
    )
    print("after recompose_combining_marks:", final_phones)
    assert final_phones == ["œ̃", "e", "ʁ", "o"], final_phones
    print("confidences:", final_confidences)
    print("boundaries (ms):", final_boundaries)
    print("Matches canonical_phonemes' grouped form for un_héros native -- OK")