"""Shared logic for wav2vec2-CTC FreePhoneRecognizer implementations that
use a character-level, espeak-derived IPA vocabulary (combining marks as
separate tokens) -- confirmed true of BOTH Cnam-LMSSC/wav2vec2-french-
phonemizer and bofenghuang/phonemizer-wav2vec2-ctc-french by fetching their
real vocab.json files (chat discussion), not assumed from family
resemblance alone.

Deliberately NOT a Protocol/registry-wrapped stage itself (Decision Log
D12) -- it's an implementation detail shared between two (so far) actual
registered stages (wav2vec2_cnam.py, wav2vec2_bofenghuang.py), each of
which keeps its own file/class/registry entry per Codebase Conventions
("a file with multiple candidate implementations should be split... so
the registry decorator per file stays easy to find").

See wav2vec2_cnam.py's module docstring for the full rationale behind the
resampling, MEAN-confidence, and recompose-combining-marks design choices
-- not repeated here.
"""

import io
import unicodedata

import numpy as np
import soundfile as sf
import torch
from transformers import AutoModelForCTC, AutoProcessor

_MODEL_SAMPLE_RATE = 16_000  # required by both models -- see their model cards


def resample(waveform: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Linear-interpolation resample -- adequate for CTC phone recognition,
    not audio-quality-critical (unlike Piper's TTS output, D43/D44). Kept
    dependency-free (no torchaudio/resampy).
    """
    if orig_sr == target_sr:
        return waveform
    duration_s = len(waveform) / orig_sr
    target_len = round(duration_s * target_sr)
    orig_x = np.linspace(0.0, duration_s, num=len(waveform), endpoint=False)
    target_x = np.linspace(0.0, duration_s, num=target_len, endpoint=False)
    return np.interp(target_x, orig_x, waveform).astype(np.float32)


def ctc_collapse(
    frame_ids: list[int],
    frame_confidences: list[float],
    ms_per_frame: float,
    blank_id: int,
    delimiter_id: int,
    id2label: dict[int, str],
) -> tuple[list[str], list[float], list[tuple[int, int]]]:
    """Standard CTC collapsing: merge consecutive identical frame ids into
    one symbol, drop the blank and word-delimiter tokens. Pure function --
    unit-testable with synthetic frame data, no model needed (see
    wav2vec2_cnam.py's __main__ block).

    Confidence for a merged span is the MEAN of its frames' confidences
    (flagged design choice, chat discussion).
    """
    phones: list[str] = []
    confidences: list[float] = []
    boundaries: list[tuple[int, int]] = []

    span_id: int | None = None
    span_start = 0
    span_confidences: list[float] = []

    def flush(end_frame: int) -> None:
        if span_id is None or span_id == blank_id or span_id == delimiter_id:
            return
        phones.append(id2label[span_id])
        confidences.append(sum(span_confidences) / len(span_confidences))
        boundaries.append((
            round(span_start * ms_per_frame),
            round(end_frame * ms_per_frame),
        ))

    for i, frame_id in enumerate(frame_ids):
        if frame_id != span_id:
            flush(end_frame=i)
            span_id = frame_id
            span_start = i
            span_confidences = []
        span_confidences.append(frame_confidences[i])
    flush(end_frame=len(frame_ids))

    return phones, confidences, boundaries


def recompose_combining_marks(
    phones: list[str], confidences: list[float], boundaries: list[tuple[int, int]]
) -> tuple[list[str], list[float], list[tuple[int, int]]]:
    """Merge a standalone Unicode combining-mark token into the PRECEDING
    phone -- the exact inverse of, and using the same check as,
    `LexiqueEspeakG2P._segment_ipa` (D30): `unicodedata.combining(ch)`.
    Pure function, unit-testable without a model.
    """
    merged_phones: list[str] = []
    merged_confidences: list[float] = []
    merged_boundaries: list[tuple[int, int]] = []

    for phone, confidence, (start_ms, end_ms) in zip(phones, confidences, boundaries):
        is_combining_mark = len(phone) == 1 and unicodedata.combining(phone)
        if is_combining_mark and merged_phones:
            merged_phones[-1] += phone
            prev_start, _ = merged_boundaries[-1]
            merged_boundaries[-1] = (prev_start, end_ms)
            merged_confidences[-1] = (merged_confidences[-1] + confidence) / 2
        else:
            merged_phones.append(phone)
            merged_confidences.append(confidence)
            merged_boundaries.append((start_ms, end_ms))

    return merged_phones, merged_confidences, merged_boundaries


class Wav2Vec2CTCPhoneRecognizerBase:
    """Shared implementation for a HuggingFace wav2vec2-CTC model using a
    character-level espeak-IPA vocab. Vendor-specific files (wav2vec2_cnam.py,
    wav2vec2_bofenghuang.py) subclass this, set their own `model_name`
    default, and carry their own `@register("free_decoder", ...)` decorator
    -- the decorator must stay on the concrete class per file (Codebase
    Conventions), not here.
    """

    def __init__(self, model_name: str):
        self._processor = AutoProcessor.from_pretrained(model_name)
        self._model = AutoModelForCTC.from_pretrained(model_name)
        self._model.eval()

        vocab = self._processor.tokenizer.get_vocab()
        self._id2label = {token_id: token for token, token_id in vocab.items()}
        self._blank_id = self._processor.tokenizer.pad_token_id
        delimiter_token = self._processor.tokenizer.word_delimiter_token
        self._delimiter_id = vocab[delimiter_token]

    def decode(self, audio: bytes) -> tuple[list[str], list[float], list[tuple[int, int]]]:
        waveform, sample_rate = sf.read(io.BytesIO(audio), dtype="float32", always_2d=False)
        if waveform.ndim > 1:
            waveform = waveform.mean(axis=1)  # downmix to mono, if needed
        waveform = resample(waveform, sample_rate, _MODEL_SAMPLE_RATE)

        inputs = self._processor(
            waveform, sampling_rate=_MODEL_SAMPLE_RATE, return_tensors="pt"
        )
        with torch.no_grad():
            logits = self._model(**inputs.to(self._model.device)).logits[0]

        probs = torch.softmax(logits, dim=-1)
        frame_confidences, frame_ids = probs.max(dim=-1)
        frame_ids_list = frame_ids.tolist()
        frame_confidences_list = frame_confidences.tolist()

        num_frames = len(frame_ids_list)
        audio_duration_ms = len(waveform) / _MODEL_SAMPLE_RATE * 1000
        ms_per_frame = audio_duration_ms / num_frames if num_frames else 0.0

        phones, confidences, boundaries = ctc_collapse(
            frame_ids_list, frame_confidences_list, ms_per_frame,
            self._blank_id, self._delimiter_id, self._id2label,
        )
        return recompose_combining_marks(phones, confidences, boundaries)