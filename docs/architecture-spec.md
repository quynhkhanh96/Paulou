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
[5] Speech Assessment      — SUPERSEDED design shown; see Decision Log
                              D36 for the current direction (single
                              free-decode + 3-way alignment), not yet
                              fully specced.
```

---

## Data model

```python
Sentence {
    id: str
    text: str
    chunks: list[Chunk]
}

Chunk {
    id: str
    text: str
    ipa_full: str
    stress_syllable: str          # rhythmic stress falls on the chunk's final syllable
    pronunciation_units: list[PronunciationUnit]
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

UnitResult {
    unit_id: str
    calibrated_score: int
    phone_scores: list[PhoneScore] | None      # populated for "single" units
    alignment_ops: list[AlignmentOp] | None    # populated for "liaison_group" units (DEL/INS/match)
    feedback_text: str
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
- **Implementation:** LLM call (Claude API), prompted to split by rhythmic group (groupe rythmique), not punctuation
- **Nature:** stochastic — cannot be unit-tested for exact output; validated via contract/invariant tests + qualitative notebook review (see Testing Conventions note)
- **Interface:**
  ```python
  class SentenceParser(Protocol):
      def parse(self, sentence: str) -> list[str]: ...
  ```

### 2. Chunk Analyzer (composite stage — several sub-modules)

**2a. Word G2P**
- **Input:** single word
- **Output:** `tuple[list[str], str]` — phonemes, source (`"dict"` or `"espeak"`)
- **Implementation:** Lexique383 (primary, dictionary lookup) → eSpeak-ng (fallback for out-of-dictionary words: rare words, proper nouns)
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
- **Implementation:** Azure Neural TTS (fr-FR), one synthesis pass per sentence (see D5 in decision log). Chunk-level and unit-level audio clips are sliced from this single pass via timestamps, with silence padding + fade-in/out at cut points.
- **Slow playback:** separate synthesis pass via SSML `<prosody rate="0.7">`, not time-stretching (see D6)
- **Caching:** keyed by `hash(text + voice_id + rate)` (see D7)
- **Interface:**
  ```python
  class TTSProvider(Protocol):
      def synthesize(self, text: str, rate: float = 1.0) -> tuple[bytes, list[WordTiming]]: ...
  ```

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
- **Mechanism:** threshold-based template lookup (see table below), not raw score display
- **Nature:** pure function

| Score range | Feedback template (single) | Feedback template (liaison) |
|---|---|---|
| 85–100 | "Good pronunciation!" | "Smooth liaison, right rhythm" |
| 60–84 | "Close, watch the [X] sound" | "Liaison present but slightly separated" |
| <60 | "The [X] sound needs work, try the slow sample" | "Missing the /z/ liaison, or a pause between words" |

---

## Codebase structure

```
paulou/
  core/
    models.py            # Sentence, Chunk, PronunciationUnit, LiaisonDecision, UnitResult, Attempt
    interfaces.py         # Protocol definitions for swappable stages
    registry.py            # register()/build() factory pattern
    config.py              # PipelineConfig — selects active implementation per stage
  stages/
    parsing/
      gemini_parser.py      # GeminiSentenceParser implements SentenceParser (Decision Log D27)
    chunk_analyzer/         # stage 2's sub-modules, nested here (Decision Log D29) —
                             # was previously flat under stages/, inconsistent with
                             # how speech_assessment/ nests its own sub-modules
      g2p/
        lexique_espeak.py    # LexiqueEspeakG2P implements G2PProvider
      pos/
        spacy_tagger.py
      liaison/
        rule_engine.py        # pure function, no registry
      elision/
        elision.py             # pure function, no registry (stage 2c-bis, Decision Log D28)
      assembly/
        unit_assembler.py     # pure function, no registry
    tts/
      azure_tts.py           # implements TTSProvider
    speech_assessment/
      free_decode/
        wav2vec2_cnam.py      # implements FreePhoneRecognizer
      align.py                # pure — Levenshtein DEL/INS
      merge.py                # pure — not yet designed in detail
      calibration.py          # pure
      feedback.py             # pure
  pipeline.py             # PaulouPipeline — single orchestration entry point
  backend/
    api/
      routers/               # sentences.py, attempts.py, progress.py
      schemas.py             # Pydantic DTOs, separate from core/models.py (see D14)
      dependencies.py
      main.py
    db/
      models.py              # SQLAlchemy ORM, separate from core/models.py
      repository.py
      migrations/
    tasks/
      tts_pregenerate.py     # background job for pre-generating TTS for common sentences
  frontend/                  # not yet started
  tests/                     # see Testing Conventions note
  experiments/               # see Experiment Log note
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
@register("gop_scorer", "kaldi")
class KaldiGOPScorer:
    def score(self, audio, canonical_phonemes): ...
```

```python
# core/config.py
@dataclass
class PipelineConfig:
    parser: str = "gemini"
    g2p: str = "lexique_espeak"
    tts: str = "azure_neural"
    gop_scorer: str = "kaldi"
    free_decoder: str = "wav2vec2_cnam"
```

Switching implementations (e.g. Kaldi → `gop-ft`) requires changing one config value — no other code changes.

### Orchestrator (example)

```python
# pipeline.py
class PaulouPipeline:
    def __init__(self, config: PipelineConfig):
        self.parser = build("parser", config.parser)
        self.g2p = build("g2p", config.g2p)
        self.tts = build("tts", config.tts)
        self.gop_scorer = build("gop_scorer", config.gop_scorer)
        self.free_decoder = build("free_decoder", config.free_decoder)

    def analyze_sentence(self, text: str) -> Sentence: ...
    def score_attempt(self, unit: PronunciationUnit, audio: bytes) -> UnitResult: ...
```

`PaulouPipeline` only accepts/returns plain data models — no HTTP, DB, or UI awareness. Notebooks call it directly; the backend wraps it in a thin API layer (see D13 in decision log).

### API design note (tentative — see D15 in decision log)
`POST /attempts` is planned to return `{attempt_id, status: "processing"}` immediately, with scoring run as a background job and the result retrieved via polling or a WebSocket push — pending latency benchmarking of the GOP/free-decode pipeline.