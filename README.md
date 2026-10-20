# Paulou

![Paulou hero image](docs/assets/hero.jpg)

A French pronunciation practice app: users input any sentence they want to practice — not just pre-scripted content — and the app breaks it down into rhythmic chunks, then into word- and phoneme-level units, with liaison-aware guidance and speech assessment feedback at each level.

---

## Why Paulou

Most pronunciation apps (Duolingo, Babbel, ELSA Speak) only let users practice sentences the app already provides. Paulou lets users type in *their own* sentences — a presentation script, a real conversation they need to prepare for, a sentence they got wrong last week — and get the same level of structured practice as if it were curated content.

Two design bets follow from that:

- **Liaison as a first-class citizen.** French liaison (the way word-final consonants resurface before a following vowel, e.g. *les amis* → /le.z‿a.mi/) is one of the hardest things for learners to internalize, and most tools treat it as a footnote in feedback text rather than something structurally modeled and drilled. Paulou treats a liaison pair as its own unit of practice and scoring, distinct from single-word units.
- **Custom speech assessment instead of an off-the-shelf API.** Commercial pronunciation-scoring APIs (Azure Pronunciation Assessment was evaluated first) don't expose a way to control the phoneme sequence being scored against, and their French support lacks phoneme-level detail (no `NBestPhonemes`, no syllable breakdown for `fr-FR`). Liaison specifically is a known weak point even by Microsoft's own admission. Paulou instead builds a custom phoneme-level scoring pipeline — a single free-decode + 3-way alignment pass (Decision Log D36) — with full control over the reference phoneme sequence, so liaison can be scored deliberately rather than hoped for.

See [Key design decisions](#key-design-decisions) for the reasoning behind each major choice, with links to the experiments backing them.

---

## Architecture

```
User input (sentence)
        │
        ▼
[1] Sentence Parser        — splits into rhythmic chunks (groupe rythmique)
        │
        ▼
[2] Chunk Analyzer         — G2P, liaison rules, assembles PronunciationUnits
        │
        ▼
[3] TTS                    — one synthesis pass per sentence, sliced by timestamp
        │
        ▼
[4] Practice UI            — chunk-level and unit-level drilling
        │
        ▼
[5] Speech Assessment      — single free-decode + 3-way alignment pipeline
                              (Decision Log D36); implemented end to end;
                              real recognizers in free_decode/ (D45),
                              bias check run (D47)
```

| Stage | Folder | What it does |
|---|---|---|
| Sentence parsing | [`stages/parsing/`](stages/parsing/) | LLM-based chunking into rhythmic groups (Gemini API, Decision Log D27) |
| G2P | [`stages/chunk_analyzer/g2p/`](stages/chunk_analyzer/g2p/) | Word → phonemes (Lexique400 + eSpeak-ng fallback, Decision Log D30) |
| POS tagging | [`stages/chunk_analyzer/pos/`](stages/chunk_analyzer/pos/) | Needed to apply liaison rules correctly |
| Liaison rules | [`stages/chunk_analyzer/liaison/`](stages/chunk_analyzer/liaison/) | Obligatoire / interdite / facultative rule engine |
| Elision detection | [`stages/chunk_analyzer/elision/`](stages/chunk_analyzer/elision/) | Closed-list lookup for elided clitics (l', d', j', ...) — distinct from liaison, Decision Log D28 |
| Unit assembly | [`stages/chunk_analyzer/assembly/`](stages/chunk_analyzer/assembly/) | Groups words into `single`, `liaison_group`, or `elision_group` `PronunciationUnit`s |
| TTS | [`stages/tts/`](stages/tts/) | Sentence-level synthesis with word-boundary timestamps — two swappable providers (Azure Neural, edge-tts, Decision Log D31), plus caching (D7), span location (`timing_alignment.py`, D48) and chunk/unit audio slicing (D5) |
| Speech Assessment | [`stages/speech_assessment/`](stages/speech_assessment/) | Single free-decode + 3-way alignment pipeline (Decision Log D36), replacing the earlier two-branch GOP/free-decode split. Pure functions implemented and tested: `align.py` (3-way Levenshtein, D38), `scoring.py` (per-op-type accuracy score, D39), `merge.py` (MEAN aggregation, D40), `feedback.py` (structural-error + bracket phrasing, D41), `calibration.py` (kept, renamed from GOP-specific naming, D39). Chunk-level orchestration also implemented: `speech_assessment.py::score_chunk` (D42), tested via a stub `FreePhoneRecognizer`. Real recognizers: `free_decode/` (`wav2vec2_cnam` default, D45/D47). Canonicalizer-bias check run (D47). |
| Pipeline | [`pipeline.py`](pipeline.py) | `PaulouPipeline`: `analyze_sentence`, `synthesize_reference`, `score_attempt` (D48); `core/config.py::PipelineConfig` selects implementations |

Every model-backed or externally-dependent stage (parser, G2P source, TTS provider, free-phone recognizer) is defined as a `Protocol` interface and resolved through a small registry, so alternative implementations can be swapped via config without touching the pipeline or other stages — this is what lets `stages/tts/azure_tts.py` and `edge_tts_provider.py` coexist today (Decision Log D31). The GOP-scorer swappability example (`kaldi_gop.py`/`gopft_gop.py`) no longer applies — see Decision Log D36; the swappable interface for Speech Assessment going forward is `FreePhoneRecognizer` alone — its signature was simplified per Decision Log D37 to `decode(audio) -> tuple[list[str], list[float], list[tuple[int, int]]]` (phones, per-position confidence, per-position time boundaries), dropping the originally-specced full posterior vector once nothing downstream needed more than one float per position. Pure, deterministic logic (liaison rules, unit assembly, alignment, merging, calibration, feedback templates) is kept as plain functions — no abstraction layer, since there's no real expectation of swapping these.

The core pipeline (`core/`, `stages/`, `pipeline.py`) is plain Python with no dependency on any UI layer. It's callable directly from a notebook or test, and a thin `backend/api/` (FastAPI) wraps it for the eventual frontend — the pipeline itself has no knowledge that a backend or frontend exists.

---

## Key design decisions

| Decision | Why | Backing |
|---|---|---|
| Custom phoneme-level pipeline instead of Azure Pronunciation Assessment | Azure gives no control over the reference phoneme sequence and lacks phoneme-level detail for `fr-FR`; liaison handling is unverifiable | — |
| ~~Two parallel branches (GOP forced-align + free phone recognition)~~ — **superseded, Decision Log D36** | Reversed in favor of a single free-decode + 3-way Levenshtein alignment pipeline (substitution + insertion + deletion in one pass) — faster to build and control for MVP, and matches the pattern used by other current open-source pronunciation tools (OpenPronounce, Echoic) | — |
| Liaison modeled as its own `PronunciationUnit` type, not a word-level footnote | Liaison is a resyllabification phenomenon — scoring and drilling it as two separate words loses the thing being taught | — |
| Unsupervised percentile/z-score calibration, not a supervised regressor | No labeled French pronunciation dataset exists (unlike English's speechocean762); building one is deferred until there's real usage data to justify it | — |
| Sentence-level TTS synthesis (not per-chunk or per-unit) | Preserves natural prosody and in-context liaison; chunks/units are sliced from one audio pass via timestamps, not synthesized separately | — |
| Rule-based liaison detection (not a learned model) | Sufficient because MVP content is either app-authored or short user sentences; a purely rule-based approach is known to break down on unconstrained free-form input (this is a known, accepted limitation — see below) | — |

---

## Current status

**The whole pipeline is implemented and has been run end to end with real components (Gemini, Lexique400 + eSpeak, edge-tts, wav2vec2) on a command line — see [docs/pipeline_cli.md](docs/pipeline_cli.md).** What is missing for a trustworthy MVP: native-corpus calibration statistics, a few findings from the first real runs (Roadmap), and the UI.

**Implemented so far:**
- **Pure functions** (step 1): liaison rule engine (`stages/chunk_analyzer/liaison/rule_engine.py`), elision detection (`stages/chunk_analyzer/elision/elision.py`, Decision Log D28), unit assembly (`stages/chunk_analyzer/assembly/unit_assembler.py`), calibration (`stages/speech_assessment/calibration.py`), feedback templating (`stages/speech_assessment/feedback.py` — redesigned in D32 to apply uniformly to every unit type, not just `single` as D19 originally scoped it).
- **G2P + POS tagging** (step 2): `stages/chunk_analyzer/g2p/lexique_espeak.py` (Lexique400 lookup, Decision Log D30, + eSpeak-ng fallback) and `stages/chunk_analyzer/pos/spacy_tagger.py` (spaCy `fr_core_news_sm`).
- **Sentence parser + TTS** (step 3): `stages/parsing/gemini_parser.py` (Gemini API, Decision Log D27); TTS has TWO swappable providers — `stages/tts/azure_tts.py` (official Azure SDK) and `stages/tts/edge_tts_provider.py` (unofficial, no API key needed, Decision Log D31) — plus `stages/tts/caching.py` (hash-based cache, D7) and `stages/tts/audio_slicing.py` (chunk/unit clip extraction with silence padding + fade, D5).
> **Superseded by Decision Log D36** — the item below describes work built
> against the abandoned two-branch (GOP + free-decode) design. It is kept
> here as an accurate historical record of what was built and tested, not
> as current architecture. None of it is confirmed to carry forward
> unchanged into the single-pipeline redesign.
- **Speech Assessment orchestration/plumbing** (step 4, "Stage A" — real GOP model is "Stage B", not started): `stages/speech_assessment/calibration.py` and `feedback.py` (feedback redesigned in Decision Log D32 — groups phones by score bracket instead of naming only the weakest, and now applies uniformly to every unit type, not just `single`), `phoneme_grouping.py` (5a-2, D20), `merge.py` (5e, MEAN aggregation, D33), and `speech_assessment.py` (orchestrates GOP → calibration → grouping → merge into a `UnitResult` per unit, D34/D35). `PronunciationUnit` gained a `phonemes: list[str]` field to support this (not in the Architecture Spec's original schema). Optional-silence (`SIL`) handling between units is implemented but its correctness depends on a real GOPScorer's alignment behavior — unverified (D35). Tested throughout with a simulated stub GOPScorer, not a real acoustic model.
- **Speech Assessment, redesigned pipeline** (Decision Log D36–D42) — the item above describes work built against the abandoned two-branch design, kept as an accurate historical record, not current architecture. The actual current pipeline: `core/models.py` gained `AlignmentOp` and `ScoredAlignmentOp`, replacing `RawPhoneScore`/`PhoneScore` (dormant, not deleted — D37); `stages/speech_assessment/align.py::align_phonemes` (3-way Levenshtein — substitution/insertion/deletion in one pass, D38); `scoring.py::score_alignment_op` (per-op-type accuracy scoring, D39); `calibration.py` kept and reused, `raw_gop` renamed to `raw_value` since GOP no longer exists (D39); `merge.py::merge_to_unit_result` and `merge_chunk_results` (MEAN aggregation carried over from the old design, plus grouping a chunk's ops by unit, D40); `feedback.py::generate_feedback` (structural-error sentences plus D32's bracket phrasing for matches, D41); and `speech_assessment.py::score_chunk` (chunk-level orchestration wiring a `FreePhoneRecognizer` through the above, tested via a stub — no real model needed, D42). `core/interfaces.py::FreePhoneRecognizer` is the real (simplified, D37) Protocol; `GOPScorer` is now explicitly dormant there.
- **Free-phone recognizers** (Decision Log D45): `stages/speech_assessment/free_decode/` — `wav2vec2_cnam` (default) and `wav2vec2_bofenghuang`, sharing `_wav2vec2_ctc_common.py`. **Diagnostic set and canonicalizer-bias check** (Decision Log D43–D47): `experiments/diagnostic_set/`, `experiments/runners/canonicalizer_bias_check.py` and `compare_free_decoder.py`, results under `experiments/results/`.
- **Pipeline orchestration** (Decision Log D48): `pipeline.py::PaulouPipeline`, `core/config.py::PipelineConfig`, and span location (`stages/tts/timing_alignment.py::locate_spans`). edge-tts hang fix and timing offset (D49); manual end-to-end CLI (`experiments/runners/pipeline_cli.py`, D50).
- Core data models added incrementally as each stage needs them (`core/models.py`): `LiaisonDecision`, `PronunciationUnit`, `AlignmentOp`, `ScoredAlignmentOp`, `UnitResult`, `WordTiming`, `Chunk`, `Sentence`, `ReferenceAudio` (`RawPhoneScore`/`PhoneScore` kept dormant, not deleted). `Attempt` not needed yet.
- <!-- TODO: fill in counts from a fresh run of the unit/model/contract suites -->Tests: fast unit suite (now also covering `test_registry`, `test_timing_alignment`, `test_pipeline`, `test_pipeline_cli`, `test_edge_tts_provider`), model tests requiring the real spaCy model, and contract tests requiring real Gemini/Azure credentials — see `tests/README.md`. (The edge-tts contract test file needs no credential but is run separately — see that file's own notes.)

**Known data/tooling gaps, not yet resolved:**
- `pipeline.py` wires Lexique400 (Decision Log D30) through `stage_kwargs` (D48); the plain `LexiqueEspeakG2P` constructor still loads the small hand-written fixture. The 33MB file itself isn't committed to the repo (git-ignored), so it must be downloaded separately — see SETUP.md.
- The native-French-corpus calibration statistics (Decision Log D11) haven't been produced yet — `calibrate_score` takes the stats table as a parameter rather than embedding real numbers. Originally scoped for GOP values, now feeds `match`-op confidence calibration instead (Decision Log D39); the math is unchanged. Until then, the CLI uses placeholder statistics and says so (D50).

**Next up:** triage the findings from the first real runs (Roadmap), run the native-corpus calibration, then latency benchmarking and the UI. The canonicalizer-bias diagnostic (D10) is done: see D47 for the result and its caveat.

**Known limitations (by design, not oversight):**
- Liaison detection is rule-based (`stages/chunk_analyzer/liaison/rule_engine.py`), which is expected to be incomplete on unconstrained free-form input containing rare vocabulary, proper nouns, or borrowed words. This is an accepted MVP tradeoff (Decision Log D4), deferred post-MVP.
- **Confirmed, not just theoretical:** the POS tagger (spaCy `fr_core_news_sm`) mistags "content" (adjective, "happy") as `ADV` even in a full, grammatically correct sentence, which causes the liaison rule engine's "très/trop + ADJ" obligatoire pattern to miss real liaison for this specific word. Locked in as a known limitation for now — see the decision log's POS tagging entry.
- Liaison across chunk boundaries is not modeled, and some obligatoire liaisons (e.g. "ont acheté") were not predicted in the first real run; optional schwa is scored as a deletion. See Roadmap.
- French support in the underlying acoustic models and tooling generally lags English; the default `FreePhoneRecognizer` (`Cnam-LMSSC/wav2vec2-french-phonemizer`) is community-maintained rather than officially supported at the scale of its English equivalents.

---

## Getting started

*Steps below reflect what's actually built and tested right now — see [Current status](#current-status) and the [Roadmap](docs/roadmap.md).*

```bash
# clone and install
git clone https://github.com/quynhkhanh96/paulou.git
cd paulou                                    # repo root (docs/, this README, SETUP.md, the paulou/ package)
pip install -r requirements-dev.txt
python -m spacy download fr_core_news_sm     # separate step — see SETUP.md if this fails
cp .env.example .env                         # then fill in GEMINI_API_KEY / Azure Speech key — see SETUP.md

# move into the package to run tests (no packaging / pip install -e . set up yet)
cd paulou

# fast suite — pure functions + G2P dict lookup, no models needed
pytest tests/unit -v

# model-backed suite — loads the real spaCy model, slower
pytest tests/model -v -m model

# contract suite — calls the real Gemini + Azure APIs, needs credentials
pytest tests/contract -v --ignore=tests/contract/test_edge_tts_provider_contract.py

# edge-tts contract — no credential needed, but run separately (see tests/README.md — can hang on restrictive networks)
pytest tests/contract/test_edge_tts_provider_contract.py -v

# whole pipeline with real components: see docs/pipeline_cli.md
```

Comparing free-phone-recognizer candidates on the diagnostic set:

```bash
python -m experiments.runners.compare_free_decoder --recognizers wav2vec2_cnam wav2vec2_bofenghuang
```

Qualitative review notebooks (chunking quality, audio playback, alignment
visualization) are planned under `experiments/notebooks/` — not yet built.

---

## Repo structure

```
Paulou/                                # repo root
├── docs/
│   ├── assets/
│   └── pipeline_cli.md                # running the whole pipeline end to end (D50)
├── README.md                          # this file
├── SETUP.md                           # local dev setup (venv, dependencies, running tests)
├── requirements-dev.txt
├── .env.example                       # GEMINI_API_KEY, AZURE_SPEECH_KEY/REGION — copy to .env at this same level
├── .gitignore
└── paulou/                            # the actual Python package
    ├── core/                          # data models, interfaces (Protocol), registry — built incrementally as stages need them
    │   └── config.py                  # PipelineConfig — selects the implementation per stage (D48)
    ├── stages/                        # one subfolder per pipeline stage, swappable implementations
    │   ├── parsing/                   # implemented — Gemini API sentence parser (Decision Log D27)
    │   ├── chunk_analyzer/            # stage 2's sub-modules, nested here (Decision Log D29)
    │   │   ├── liaison/               # implemented — rule engine
    │   │   ├── elision/               # implemented — closed-list clitic detection (Decision Log D28)
    │   │   ├── assembly/              # implemented — unit assembly
    │   │   ├── g2p/                   # implemented — Lexique400 lookup (D30) + eSpeak-ng fallback; test fixture used by default, real DB via from_lexique400() (not committed, .gitignore)
    │   │   └── pos/                   # implemented — spaCy fr_core_news_sm
    │   ├── speech_assessment/         # pure functions implemented (D36-D41): align.py, scoring.py,
    │   │                              #   merge.py, feedback.py, calibration.py; orchestration
    │   │                              #   implemented (D42): speech_assessment.py::score_chunk;
    │   │                              #   free_decode/ implemented (D45)
    │   └── tts/                       # implemented — Azure Neural + edge-tts providers, caching, audio slicing,
    │                                  #   timing_alignment.py (D5/D7/D31/D48)
    ├── pipeline.py                    # PaulouPipeline (D48)
    ├── backend/                       # not yet built — FastAPI app, DB models/repository, background jobs
    ├── frontend/                      # not yet built — client app (TBD)
    ├── tests/
    │   ├── unit/                      # implemented — fast, pure functions + G2P dict lookup
    │   ├── model/                     # implemented — slow, loads the real spaCy model
    │   ├── contract/                  # implemented — calls the real Gemini API, needs GEMINI_API_KEY
    │   ├── fixtures/                  # implemented — g2p_golden.tsv (fixture lexicon)
    │   ├── api/                       # not yet built (no backend yet)
    │   └── db/                        # not yet built (no backend yet)
    └── experiments/                   # diagnostic_set/, runners/ (incl. pipeline_cli.py), results/ implemented;
                                       #   notebooks/ not yet
```

---

## Contributing

This is primarily a personal research and learning project, built alongside a PhD. Issues and PRs are welcome, but response times may be slow, especially through end of 2026.

---

## License

[Functional Source License (FSL)](https://fsl.software/) — converts automatically to Apache License 2.0 two years after each version's release. Source is public and free to read, use, and modify for non-competing purposes; see [LICENSE](LICENSE) for full terms.

---

## Acknowledgments & references

- [Lexique400](http://www.lexique.org/) — open French phonetic/lexical database (Decision Log D30 — supersedes the originally-planned Lexique383)
- [eSpeak NG](https://github.com/espeak-ng/espeak-ng) — fallback grapheme-to-phoneme synthesis
- [Azure Neural TTS](https://azure.microsoft.com/en-us/products/ai-services/text-to-speech) — official TTS provider (Decision Log D5/D6/D7)
- [edge-tts](https://github.com/rany2/edge-tts) — unofficial, no-API-key TTS provider added alongside Azure (Decision Log D31)
- [Cnam-LMSSC/wav2vec2-french-phonemizer](https://huggingface.co/Cnam-LMSSC/wav2vec2-french-phonemizer) — free French phoneme recognition (default free decoder, D47)
- bofenghuang's wav2vec2 French phoneme CTC model — the compared alternative free decoder (`wav2vec2_bofenghuang`, D45)
- [Piper](https://github.com/rhasspy/piper) (MIT) — local TTS, used only to generate the diagnostic audio (D43)
- [OpenPronounce](https://github.com/Halleck45/OpenPronounce) and [Echoic](https://github.com/xialeistudio/echoic) — open-source pronunciation-assessment tools whose free-decode + alignment approach informed Decision Log D36's redesign