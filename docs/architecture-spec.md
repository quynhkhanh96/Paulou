# Paulou — Architecture Spec

Working design reference — more detailed and more frequently updated than the repo README. The README is the public-facing summary; this note is the internal spec: full data models, stage interfaces, and folder layout. When this note and the README disagree, this note is the source of truth until the README is next synced.

---

## Pipeline overview

```
User input (sentence)
        │
        ▼
[1] Sentence Parser        — splits into rhythmic chunks (groupe rythmique)
        │
        ▼
[2] Chunk Analyzer         — G2P, POS tagging, liaison rules, unit assembly
        │
        ▼
[3] TTS                    — one synthesis pass per sentence, sliced by timestamp
        │
        ▼
[4] Practice UI            — chunk-level and unit-level drilling
        │
        ▼
[5] Speech Assessment      — single free-decode + 3-way alignment
                              (Decision Log D36-D47); implemented and
                              run end to end (D48, D50). Section 5
                              (redesigned) below is the current spec.
```

---

## Data model

```python
Sentence { text: str, chunks: list[Chunk] }          # no id (D48)
Chunk    { text: str, units: list[PronunciationUnit] }  # field is `units`; no id, ipa_full or stress_syllable (D48)
ReferenceAudio {                                        # D48
    audio: bytes                                        # one full-sentence TTS pass (format: pipeline.AUDIO_FORMAT = "mp3")
    chunk_spans: list[tuple[int, int]]                  # (start_ms, end_ms) per chunk
    unit_spans: dict[str, tuple[int, int]]              # keyed by sentence-unique unit id
}

PronunciationUnit {
    id: str
    type: Literal["single", "liaison_group", "elision_group"]
    words: list[str]              # 1 word if single, 2+ if liaison_group or elision_group
    ipa: str
    syllables: list[str]
    liaison_consonant: str | None # only set for liaison_group (e.g. "z", "t", "n") — None for elision_group (no consonant added, see 2c-bis)
    note: str                     # human-readable pedagogical note
    scoring_focus: Literal["phoneme_accuracy", "liaison_presence_and_continuity", "elision_correctness"]
}
# Note: unit ids are `c{chunk}_unit_{n}` after `analyze_sentence` (chunk-local `unit_{n}` inside `assemble_units`)

WordTiming {
    word: str
    start_ms: int
    end_ms: int
}

PhoneScore {
    phone: str
    raw_gop: float
    calibrated_score: int         # 0-100, via percentile/z-score (see D11 in decision log)
    start_ms: int                 # from forced-alignment; used to group scores back into PronunciationUnits (D20)
    end_ms: int
}

LiaisonDecision {
    between: tuple[str, str]      # the two words being evaluated
    applies: bool
    consonant: str | None
    rule_type: Literal["obligatoire", "interdite", "facultative"]
}

AlignmentOp {                    # D37
    op_type: Literal["match", "substitution", "insertion", "deletion"]
    unit_id: str
    canonical_phoneme: str | None   # None only for insertion
    decoded_phoneme: str | None     # None only for deletion
    confidence: float | None        # None only for deletion
    start_ms: int | None            # None only for deletion
    end_ms: int | None
}

ScoredAlignmentOp { op: AlignmentOp, accuracy_score: int }     # D40

UnitResult {
    unit_id: str
    calibrated_score: int          # MEAN of scored_ops' accuracy_score (D40)
    scored_ops: list[ScoredAlignmentOp]
    feedback_text: str             # from generate_feedback (D41)
}

Attempt {
    id: str
    user_id: str
    unit_id: str
    audio_url: str
    result: UnitResult
    timestamp: datetime
}
```

---

## Stage-by-stage spec

### 1. Sentence Parser
- **Input:** raw sentence text
- **Output:** `list[str]` (chunk texts)
- **Implementation:** LLM call (Gemini API, GeminiSentenceParser — Decision Log D27), prompted to split by rhythmic group (groupe rythmique), not punctuation
- **Nature:** Nature: stochastic — the same sentence can produce different chunks on different runs (observed, D50)
- **Interface:**
  ```python
  class SentenceParser(Protocol):
      def parse(self, sentence: str) -> list[str]: ...
  ```

### 2. Chunk Analyzer (composite stage — several sub-modules)

**2a. Word G2P**
- **Input:** single word
- **Output:** `tuple[list[str], str]` — phonemes, source (`"dict"` or `"espeak"`)
- **Implementation:** Lexique400 (Decision Log D30) (primary, dictionary lookup) → eSpeak-ng (fallback for out-of-dictionary words: rare words, proper nouns). The registered class needs its lexicon passed as a constructor kwarg `(lexicon=load_lexique400(path))`; `PaulouPipeline` does this through `stage_kwargs` (D48)
- **Nature:** deterministic lookup
- **Interface:**
  ```python
  class G2PProvider(Protocol):
      def phonemize(self, word: str) -> tuple[list[str], str]: ...
  ```

**2b. POS tagging**
- **Input:** full sentence
- **Output:** `list[tuple[str, str]]` — (word, POS tag)
- **Implementation:** spaCy (`fr_core_news`) or Stanza
- **Nature:** model-based but stable/mature; needed to apply liaison rules correctly (rules are POS-pattern based, e.g. determiner+noun, pronoun clitic+verb)

**2c. Liaison rule engine**
- **Input:** `list[tuple[word, POS]]`
- **Output:** `list[LiaisonDecision]`
- **Nature:** pure, deterministic — no interface/registry needed (see D12 in decision log)
- **Rule categories:**
  - **Obligatoire** (hard rule, always applies): determiner+noun, pronoun clitic+verb, adjective before noun, monosyllabic preposition+word, number+noun, très/trop+adjective
  - **Interdite** (hard rule + closed list, never applies): after "et", before h-aspiré words (closed list of ~dozens of words), before "onze"/"oui"/"uhlan"-type words, after a singular noun acting as subject
  - **Facultative:** not predicted — both variants (with/without liaison) are generated, and the scoring layer accepts either. Never used to teach one variant as "correct."
- **Liaison consonant mapping:** s/x/z → /z/, t/d → /t/, n → /n/, r → /ʁ/ (rare), p → /p/ (rare), f → /v/ (rare, irregular)
- **Known limitation:** rule-based approach is expected to be incomplete on unconstrained free-form input (see D4 in decision log)

**2c-bis. Elision detection** (added post-MVP-scoping, not in the original stage list — see Decision Log D28)
- **Input:** a single word
- **Output:** `list[str] | None` — the elided form's phoneme(s) if recognized, else `None`
- **Nature:** pure, deterministic closed-list lookup — no rule engine, no interface/registry (see D12, D28)
- **What it covers:** the small closed set of French clitics that drop their final vowel before a vowel-initial word, marked orthographically with an apostrophe: le/la/de/je/me/te/se/ne/que/ce → l'/d'/j'/m'/t'/s'/n'/qu'/c'.
- **Distinct from liaison:** no consonant is added (elision only removes a vowel); it's not a "decision" the way `LiaisonDecision` is — seeing the elided orthographic form in the tokenized text is itself proof the fusion already happened. Confirmed to never conflict with liaison on the same word (elided words have no liaison-capable final consonant).
- **Distinct from enchaînement:** enchaînement (see Glossary) is NOT modeled — it requires knowing whether a word's final consonant is already pronounced, which needs G2P output rather than orthography/POS alone, unlike elision and liaison (both decidable pre-G2P). Deferred.

**2d. Unit assembly**
- **Input:** words with phonemes + `list[LiaisonDecision]`
- **Output:** `list[PronunciationUnit]`
- **Nature:** pure — sequential grouping logic. At each word, checks elision first (2c-bis) — if the word is a recognized elided clitic, merges it with the next word into an `elision_group`, regardless of any liaison decision at that position (an elided word never has a usable liaison consonant, so this never actually overrides a real liaison merge — see Decision Log D28). Otherwise, where a liaison decision applies, merges into a `liaison_group` (recomputing combined IPA with the liaison consonant inserted, setting `scoring_focus="liaison_presence_and_continuity"`); otherwise the word stands alone as `single` (`scoring_focus="phoneme_accuracy"`).
- **Why separate from 2c:** the rule engine answers a linguistic question ("is there liaison here"); the assembler answers a data-structuring question (grouping, combined IPA, scoring_focus assignment). Testing each independently: rule engine tested with linguistic cases, assembler tested by feeding synthetic `LiaisonDecision`s and asserting structure, without needing the real rules.

### 3. TTS
- **Input:** full sentence text, target rate
- **Output:** `tuple[bytes, list[WordTiming]]` — audio + word-boundary timestamps
- **Implementation:** two registered providers — `AzureTTSProvider` (`azure_neural`, needs AZURE_SPEECH_KEY/REGION) and `EdgeTTSProvider` (`edge_tts`, unofficial, no key; the `PipelineConfig` default) — Decision Log D31. One synthesis pass per sentence (D5); `edge_tts` has an optional `timing_offset_ms` (D49)
- **Slow playback:** separate synthesis pass via SSML `<prosody rate="0.7">`, not time-stretching (see D6)
- **Caching:** keyed by `hash(text + voice_id + rate)` (see D7)
- **Interface:**
  ```python
  class TTSProvider(Protocol):
      def synthesize(self, text: str, rate: float = 1.0) -> tuple[bytes, list[WordTiming]]: ...
  ```
**3b. Span location** (`stages/tts/timing_alignment.py::locate_spans`, pure, D48)
- **Input:** `Sentence`, `list[WordTiming]`
- **Output:** `(chunk_spans, unit_spans)` in the TTS audio's timeline
- **Mechanism:** compares normalized character streams (lowercase, letters and digits only), not words; strict — `ValueError` if the streams differ. Word-granular: a TTS token spanning two units gives both the same span.
- **Known accuracy issue:** provider word windows can end before the word does (D49); cut with `slice_audio` after any needed offset.

### 4. Practice UI
- Two levels: chunk-level (listen + record the whole chunk) and unit-level (drill down to a single `PronunciationUnit`, shown with IPA + syllable breakdown + stress marking)
- Not yet built — see Roadmap note

### 5. Speech Assessment (composite stage — two parallel branches + merge)

> **SUPERSEDED by Decision Log D36.** The two-branch design below (5a–5f)
> is kept here for historical reference only — it is no longer the active
> design. The replacement (single free-decode + 3-way Levenshtein
> alignment pipeline) is not yet specced in detail: `AlignmentOp` schema
> and the confidence-based scoring mechanism are open design questions
> (see Roadmap). Do not implement against the sub-stages below.

**5a. GOP scorer (Branch 1 — substitution detection)**
- **Input:** `audio: bytes, canonical_phonemes: list[str]` — accepted at **any granularity**: a single `PronunciationUnit`, a full `Chunk`, or a full `Sentence`. The scorer itself is granularity-agnostic; forced-alignment only needs an audio signal and a reference phoneme sequence, regardless of how long that sequence is (Decision Log D20).
- **Output:** `list[PhoneScore]` for the whole span passed in, each with phoneme identity, raw GOP, and time boundaries (start/end) from the forced-alignment.
- **Recommended usage:** call once per chunk or per sentence (not once per unit) to preserve surrounding acoustic context for alignment — same rationale as sentence-level TTS synthesis (D5): coarticulation means neighboring phones (including across a liaison boundary) affect each other, so aligning with full context is more accurate than aligning small isolated spans.
- **Mechanism:** forced-align audio to the canonical phoneme sequence, then at each aligned position take the full softmax distribution from the acoustic model: `GOP = log P(canonical) − log P(best_match)`. `best_match` is available "for free" from this computation — equivalent to Azure's `NBestPhonemes` without extra cost.
- **Candidate implementations:**
  - `KaldiGOPScorer` — Kaldi GOP-DNN, using `fr_kaldi-rhasspy` (open French acoustic model, WER 3.23%, trained on Common Voice + M-AILabs + Voxforge) or a self-trained model. Low compute cost (forced-align is lighter than free decoding), but high ops cost (no REST/serving layer, requires custom wrapper, complex C++ packaging).
  - `GopFtScorer` — PyTorch reimplementation of the same GOP-DNN formula (`gop-ft`, JazminVidal), easier to deploy than raw Kaldi. **Caveat:** only provides the method/code, not a pretrained French acoustic model — the French model still needs to be converted from Kaldi format. Raw GOP score scale differs from Kaldi's even with the same formula (implementation-dependent) — **percentile calibration (5c) must be recomputed separately per implementation, not shared.**
- **Known limitation:** forced-align is bound to the expected phone count/order — good at catching substitutions, structurally blind to insertion/deletion. This is why Branch 2 exists.
- **Interface:**
  ```python
  class GOPScorer(Protocol):
      def score(self, audio: bytes, canonical_phonemes: list[str]) -> list[PhoneScore]: ...
  ```

**5a-2. Phoneme-to-unit grouping (new step, per Decision Log D20)**
- **Input:** `list[PhoneScore]` (flat, for a whole chunk/sentence) + the `list[PronunciationUnit]` that chunk/sentence was assembled into (stage 2d)
- **Output:** per-unit `list[PhoneScore]`, i.e. each `PronunciationUnit` gets just the slice of the flat list that belongs to it
- **Nature:** pure function — groups by phoneme sequence order (and time boundaries once fixed), no model involved
- **Where it sits:** runs after 5a and before 5e (the GOP-branch + free-decode-branch merge). Not a replacement for 5e — a preparatory step that turns one flat GOP call's output into the per-unit shape 5e expects.

**5b. Free phone recognizer (Branch 2 — insertion/deletion detection)**
- **Input:** `audio: bytes`
- **Output:** `tuple[list[str], list[list[float]]]` — decoded phone sequence + posterior distributions per position
- **Mechanism:** unconstrained CTC decoding (no reference-sequence constraint), producing the actual number of phones heard (fewer/more than expected if a sound was dropped/added)
- **Candidate implementation:** `Cnam-LMSSC/wav2vec2-french-phonemizer` (HuggingFace, MIT license), fine-tuned from `wav2vec2-base-fr-voxpopuli-v2` on Common Voice v13 French, outputs IPA directly via CTC
- **Critical unresolved risk:** canonicalizer bias — see D10 in decision log. **Do not build further on this branch until the diagnostic set validation is done.**
- **Mitigation direction:** retain full posterior distribution (not just argmax) to inform the alignment step of the model's confidence
- **Interface:**
  ```python
  class FreePhoneRecognizer(Protocol):
      def decode(self, audio: bytes) -> tuple[list[str], list[list[float]]]: ...
  ```

**5c. Alignment (Levenshtein DEL/INS classification)**
- **Input:** `canonical_phones: list[str], decoded_phones: list[str]`
- **Output:** `list[AlignmentOp]` (DEL/INS/match)
- **Nature:** pure function, classic Levenshtein alignment

**5d. Calibration**
- **Input:** `raw_gop: float, phone: str`
- **Output:** `score: int` (0–100)
- **Mechanism:** unsupervised percentile/z-score normalization (see D11 in decision log)
  1. Offline: run GOP on a native French corpus (e.g. Common Voice fr) → compute mean/std (or percentile breakpoints) per phone
  2. Runtime: `z = (raw_gop − mean[phone]) / std[phone]`, `score = 100 × CDF_normal(z)`
  3. Deploy as a small in-memory lookup table (a few dozen KB)
- **Known limitation:** rare phones in the corpus → unstable mean/std; needs a fallback (backoff to a broader phone class, e.g. grouping nasal vowels) when sample size is too small
- **Nature:** pure function

**5e. Merge (combining Branch 1 + Branch 2 into one result)**
- **Input:** `gop_scores: list[PhoneScore], alignment_ops: list[AlignmentOp]`
- **Output:** `UnitResult`
- **Nature:** pure function
- **Not yet designed in detail** — how the two branches' outputs combine into one coherent feedback signal is an open design task (see Roadmap note)

**5f. Feedback templating**
- **Input:** `UnitResult`
- **Output:** `feedback_text: str`
- **Mechanism:** threshold-based template lookup (see table below), not raw score display.
- **Nature:** pure function

| Score range | Feedback template (single) | Feedback template (liaison) |
|---|---|---|
| 85–100 | "Good pronunciation!" | "Smooth liaison, right rhythm" |
| 60–84 | "Close, watch the [X] sound" | "Liaison present but slightly separated" |
| <60 | "The [X] sound needs work, try the slow sample" | "Missing the /z/ liaison, or a pause between words" |

### 5 (redesigned) — Single free-decode + 3-way alignment pipeline (Decision Log D36)

Replaces stages 5a–5f above in their entirety. Implemented: `align_phonemes` (D38), `score_alignment_op` + `calibrate_score` (D39), `merge_to_unit_result` / `merge_chunk_results` (D40), `generate_feedback` (D41), `score_chunk` (D42), and two real `FreePhoneRecognizers` (D45; `wav2vec2_cnam` is the default, D47). Calibration statistics (`phone_stats`) from a native corpus do not exist yet (D11/D24).

**5b'. Free Phone Recognizer** (implemented, D45: `wav2vec2_cnam` and `wav2vec2_bofenghuang`, sharing `stages/speech_assessment/free_decode/_wav2vec2_ctc_common.py`; default `wav2vec2_cnam` per D47)
- **Input:** `audio: bytes`
- **Output:** `tuple[list[str], list[float], list[tuple[int, int]]]` —
  decoded phone sequence, per-position confidence (the decoder's own
  top-1 probability at that position — since the decoded phone at
  position j is itself the argmax of position j's distribution, this
  equals the max of the full posterior; no need to carry the full
  distribution), and per-position `(start_ms, end_ms)` boundaries.
- **Simplified from the original stage 5b signature** (`tuple[list[str],
  list[list[float]]]`, full posterior per position): once insertion
  scoring was decided to reuse plain confidence rather than posterior
  entropy, nothing downstream needs more than one float per position. No
  implementation existed yet when this was simplified, so it's a free
  edit, not a breaking change.
- **Interface:**
  ```python
  class FreePhoneRecognizer(Protocol):
      def decode(self, audio: bytes) -> tuple[list[str], list[float], list[tuple[int, int]]]: ...
  ```
- **Mechanism:** CTC greedy decode, repeated frames collapsed, blank/delimiter dropped, combining marks recomposed, confidence = MEAN over a phone's frames; audio resampled to 16 kHz.

**5c'. Alignment** (`stages/speech_assessment/align.py::align_phonemes`) — IMPLEMENTED
- **Input:** `canonical_phonemes: list[str], unit_ids: list[str]` (parallel
  array — `unit_ids[i]` is the `PronunciationUnit.id` owning
  `canonical_phonemes[i]`), plus the three parallel outputs of
  `FreePhoneRecognizer.decode()`.
- **Output:** `list[AlignmentOp]`, one per operation in canonical order.
- **Mechanism:** classic Levenshtein DP, equal weights
  (sub_cost=del_cost=ins_cost=1). Backtrace tie-break order: diagonal
  (match/substitution) > deletion > insertion — deterministic by
  construction, and this ordering makes a single real mispronunciation
  resolve as one substitution rather than a cheaper-looking
  deletion+insertion pair for the same event.
- **unit_id attribution:** match/substitution/deletion inherit the
  `unit_ids` entry of the canonical phoneme they consume. insertion (no
  canonical counterpart) attaches to the preceding op's unit_id by
  convention (product decision — surfacing "an extra sound was added
  here" matters more than pinpointing which word); an insertion before
  anything else attaches to the first unit.
- Replaces D20's count-based phoneme-to-unit grouping outright — counting
  no longer works once insertions/deletions can change sequence length.

**5d'. Scoring** (`stages/speech_assessment/scoring.py::score_alignment_op`) — IMPLEMENTED
- **Input:** one `AlignmentOp`, plus `phone_stats`/`fallback_phone_class`.
- **Output:** `accuracy_score: int` (0–100), wrapped with the `AlignmentOp`
  into a `ScoredAlignmentOp`.
- **Mechanism, per op_type:**
  - `match`: `calibrate_score` (Decision Log D11), reused verbatim — only
    the input renamed from `raw_gop` to `raw_value`.
  - `substitution` / `insertion`: `100 * (1 - confidence)` — not
    calibrated, since native speech has no substitutions/insertions to
    build a reference distribution from.
  - `deletion`: always `0`.

**5e'. Merge** (`stages/speech_assessment/merge.py::merge_to_unit_result`) — IMPLEMENTED
- **Input:** `unit_id: str, ops: list[AlignmentOp]` (all sharing that
  unit_id — checked), plus `phone_stats`/`fallback_phone_class`.
- **Output:** `UnitResult`, `calibrated_score` = MEAN of every op's
  `accuracy_score` (Decision Log D33's choice, carried over unchanged).
- `feedback_text` is produced by `generate_feedback` (5f') inside `merge_to_unit_result`.

**5f'. Feedback** (`stages/speech_assessment/feedback.py::generate_feedback`) — IMPLEMENTED
- **Input:** `calibrated_score: int` (unit's MEAN, from 5e'),
  `scored_ops: list[ScoredAlignmentOp]`.
- **Output:** `feedback_text: str`.
- **Mechanism:** an overview sentence (D32's 85/60/0 boundaries, applied to
  `calibrated_score`) always comes first — even for a unit with a single,
  purely structural op. Then, if present: one sentence naming all
  deletions, one naming all insertions, one naming all substitutions (in
  that order) — each stated explicitly (which sound was missing/extra/
  wrong), not bucketed by score. Finally, D32's bracket-grouped sentences
  (good/close/needs-work) apply ONLY to `match` ops — substitution/
  insertion/deletion bypass bracketing entirely, since alignment already
  gives more specific information than a score bracket would preserve.
- See Decision Log D41.
---

## Codebase structure

```
Paulou/                                    # repo root
├── README.md
├── SETUP.md †                             # local dev setup
├── LICENSE [ ]                            # FSL text with Change Date / Change License still to fill in
├── requirements-dev.txt †
├── .env.example †                         # GEMINI_API_KEY, AZURE_SPEECH_KEY / AZURE_SPEECH_REGION
├── .gitignore †
├── docs/
│   ├── assets/hero.jpg †
│   ├── roadmap.md                         # = paulou-roadmap.md in the Project
│   └── pipeline_cli.md (new)              # installation + commands to test the whole pipeline (D50)
└── paulou/                                # the Python package; run everything from here
    ├── pipeline.py (new)                  # PaulouPipeline, AUDIO_FORMAT, _STAGE_MODULES (D48)
    │
    ├── core/
    │   ├── __init__.py
    │   ├── models.py                      # LiaisonDecision, PronunciationUnit, AlignmentOp, ScoredAlignmentOp,
    │   │                                  #   UnitResult, WordTiming, Chunk, Sentence, ReferenceAudio (last 3: D48);
    │   │                                  #   RawPhoneScore / PhoneScore kept dormant (D36/D37)
    │   ├── interfaces.py                  # Protocols: SentenceParser, G2PProvider, TTSProvider, FreePhoneRecognizer;
    │   │                                  #   GOPScorer dormant (D36)
    │   ├── registry.py                    # register(), build(), is_registered() (new)
    │   └── config.py (new)                # PipelineConfig: parser, g2p, tts, free_decoder (D48)
    │
    ├── data/                              # [git-ignored]
    │   └── Lexique400.tsv †               # download separately (D30)
    │
    ├── stages/
    │   ├── __init__.py
    │   ├── parsing/
    │   │   ├── __init__.py
    │   │   └── gemini_parser.py           # GeminiSentenceParser, register("parser", "gemini") (D27)
    │   ├── chunk_analyzer/                # stage 2 (D29)
    │   │   ├── __init__.py
    │   │   ├── chunk_analyzer.py          # analyze_chunk(): POS -> liaison -> G2P -> assemble
    │   │   ├── g2p/
    │   │   │   ├── __init__.py
    │   │   │   └── lexique_espeak.py      # LexiqueEspeakG2P, register("g2p", "lexique_espeak");
    │   │   │                              #   load_lexique400() now public (D48)
    │   │   ├── pos/
    │   │   │   ├── __init__.py
    │   │   │   └── spacy_tagger.py        # spaCy fr_core_news_sm, plain class (D26)
    │   │   ├── liaison/
    │   │   │   ├── __init__.py
    │   │   │   └── rule_engine.py         # pure; obligatoire / interdite / facultative (D4, D21, D22)
    │   │   ├── elision/
    │   │   │   ├── __init__.py
    │   │   │   └── elision.py             # pure; closed-list clitics (D28)
    │   │   └── assembly/
    │   │       ├── __init__.py
    │   │       └── unit_assembler.py      # pure; single / liaison_group / elision_group (D23)
    │   ├── tts/                           # stage 3
    │   │   ├── __init__.py
    │   │   ├── azure_tts.py               # AzureTTSProvider, register("tts", "azure_neural")
    │   │   ├── edge_tts_provider.py       # EdgeTTSProvider, register("tts", "edge_tts");
    │   │   │                              #   async stream() instead of stream_sync(), timing_offset_ms (D49)
    │   │   ├── caching.py                 # CachingTTSProvider, hash(text|voice|rate) (D7)
    │   │   ├── audio_slicing.py           # slice_audio(): padding + fades (D5)
    │   │   └── timing_alignment.py (new)  # locate_spans(): chunk/unit spans from word timings (D48)
    │   └── speech_assessment/             # stage 5 (D36-D42)
    │       ├── __init__.py
    │       ├── align.py                   # align_phonemes(): 3-way Levenshtein (D38)
    │       ├── scoring.py                 # score_alignment_op() (D39)
    │       ├── calibration.py             # PhoneStats, calibrate_score() (D11, D24)
    │       ├── merge.py                   # merge_to_unit_result(), merge_chunk_results() (D40);
    │       │                              #   calls generate_feedback
    │       ├── feedback.py                # generate_feedback() (D41)
    │       ├── speech_assessment.py       # score_chunk() (D42)
    │       └── free_decode/ †
    │           ├── __init__.py            # imports both recognizers so @register runs (D45)
    │           ├── _wav2vec2_ctc_common.py   # resample, ctc_collapse, recompose_combining_marks, base class
    │           ├── wav2vec2_cnam.py          # register("free_decoder", "wav2vec2_cnam")  <- default (D47)
    │           └── wav2vec2_bofenghuang.py   # register("free_decoder", "wav2vec2_bofenghuang")
    │
    ├── tests/                             # pass/fail only, runs in CI (D16)
    │   ├── __init__.py
    │   ├── Test.md                        # README.md references tests/README.md: check which name is right
    │   ├── unit/                          # fast, no network / models
    │   │   ├── test_liaison_rules.py
    │   │   ├── test_elision.py
    │   │   ├── test_unit_assembler.py
    │   │   ├── test_g2p.py
    │   │   ├── test_alignment.py
    │   │   ├── test_scoring.py
    │   │   ├── test_calibration.py
    │   │   ├── test_merge.py
    │   │   ├── test_feedback_templates.py
    │   │   ├── test_speech_assessment.py
    │   │   ├── test_audio_slicing.py
    │   │   ├── test_tts_caching.py
    │   │   ├── test_registry.py (new)
    │   │   ├── test_timing_alignment.py (new)
    │   │   ├── test_edge_tts_provider.py (new)   # fake stream; hang regression
    │   │   ├── test_pipeline.py (new)            # stub stages
    │   │   └── test_pipeline_cli.py (new)        # stub pipeline; needs ffmpeg + soundfile
    │   ├── model/                         # loads the real spaCy model
    │   │   ├── test_pos_tagger.py
    │   │   └── test_chunk_analyzer.py
    │   ├── contract/                      # real Gemini / Azure / edge-tts
    │   │   ├── test_chunking_invariants.py
    │   │   ├── test_tts_provider_contract.py
    │   │   └── test_edge_tts_provider_contract.py
    │   ├── fixtures/
    │   │   ├── g2p_golden.tsv
    │   │   └── diagnostic_audio/ †        # promoted 12-case audio + metadata.json, committed (D43)
    │   ├── api/ [ ]
    │   └── db/ [ ]
    │
    ├── experiments/                       # never in CI (D16)
    │   ├── __init__.py
    │   ├── README.md †
    │   ├── requirements-experiments.txt †
    │   ├── diagnostic_set/ †              # D43 / D44
    │   │   ├── __init__.py
    │   │   ├── cases.py                   # 12 cases (Tranche 1 + 2)
    │   │   ├── CASES.md
    │   │   ├── perturbation.py
    │   │   ├── piper_phonemes.py
    │   │   ├── build_diagnostic_audio.py
    │   │   └── *.onnx, *.onnx.json        # [git-ignored] Piper voice
    │   ├── runners/
    │   │   ├── __init__.py
    │   │   ├── canonicalizer_bias_check.py †   # D46
    │   │   ├── compare_free_decoder.py †       # D45-D47
    │   │   └── pipeline_cli.py (new)           # analyze / reference / timings / selftest / score (D50)
    │   ├── notebooks/ [ ]
    │   └── results/
    │       ├── canonicalizer_bias/ †      # *.json + RESULTS.md committed (D47)
    │       ├── diagnostic_set/ †          # *.wav git-ignored, metadata.json committed
    │       └── pipeline_cli/              # *.mp3 / *.wav git-ignored, *.json committed
    │
    ├── backend/ [ ]                       # FastAPI: api/ (routers, schemas, dependencies, main), db/, tasks/ (D13-D15)
    └── frontend/ [ ]
```

### Registry pattern (example)

```python
# core/registry.py
_REGISTRY: dict[str, dict[str, type]] = {}

def register(stage: str, key: str):
    def wrapper(cls):
        _REGISTRY.setdefault(stage, {})[key] = cls
        return cls
    return wrapper

def build(stage: str, key: str, **kwargs):
    return _REGISTRY[stage][key](**kwargs)
```

```python
# stages/speech_assessment/gop/kaldi_gop.py
@register("free_decoder", "wav2vec2_cnam")
class KaldiGOPScorer:
    def score(self, audio, canonical_phonemes): ...
```

```python
# core/config.py
@dataclass
class PipelineConfig:
    parser: str = "gemini"
    g2p: str = "lexique_espeak"
    tts: str = "edge_tts"
    free_decoder: str = "wav2vec2_cnam"
```

Switching implementations (e.g. Kaldi → `gop-ft`) requires changing one config value — no other code changes.

### Orchestrator (example)

```python
# pipeline.py
class PaulouPipeline:
    def __init__(self, config, phone_stats, fallback_phone_class=None,
                 tts_cache_dir=None, stage_kwargs=None): ...   # stages built lazily

    def analyze_sentence(self, text: str) -> Sentence: ...
    def synthesize_reference(self, sentence: Sentence, rate: float = 1.0) -> ReferenceAudio: ...
    def score_attempt(self, units: list[PronunciationUnit], audio: bytes) -> list[UnitResult]: ...
    @staticmethod
    def slice_reference(reference: ReferenceAudio, span: tuple[int, int]) -> bytes: ...
```

`PaulouPipeline` only accepts/returns plain data models — no HTTP, DB, or UI awareness. Notebooks call it directly; the backend wraps it in a thin API layer (see D13 in decision log).
Note: `_STAGE_MODULES` (the (stage, key) -> module map used so a registered implementation's module gets imported) and `stage_kwargs`.

### API design note (tentative — see D15 in decision log)
`POST /attempts` is planned to return `{attempt_id, status: "processing"}` immediately, with scoring run as a background job and the result retrieved via polling or a WebSocket push — pending latency benchmarking of the GOP/free-decode pipeline.