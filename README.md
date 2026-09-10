# Paulou

![Paulou hero image](docs/assets/hero.jpg)

A French pronunciation practice app: users input any sentence they want to practice — not just pre-scripted content — and the app breaks it down into rhythmic chunks, then into word- and phoneme-level units, with liaison-aware guidance and speech assessment feedback at each level.

---

## Why Paulou

Most pronunciation apps (Duolingo, Babbel, ELSA Speak) only let users practice sentences the app already provides. Paulou lets users type in *their own* sentences — a presentation script, a real conversation they need to prepare for, a sentence they got wrong last week — and get the same level of structured practice as if it were curated content.

Two design bets follow from that:

- **Liaison as a first-class citizen.** French liaison (the way word-final consonants resurface before a following vowel, e.g. *les amis* → /le.z‿a.mi/) is one of the hardest things for learners to internalize, and most tools treat it as a footnote in feedback text rather than something structurally modeled and drilled. Paulou treats a liaison pair as its own unit of practice and scoring, distinct from single-word units.
- **Custom speech assessment instead of an off-the-shelf API.** Commercial pronunciation-scoring APIs (Azure Pronunciation Assessment was evaluated first) don't expose a way to control the phoneme sequence being scored against, and their French support lacks phoneme-level detail (no `NBestPhonemes`, no syllable breakdown for `fr-FR`). Liaison specifically is a known weak point even by Microsoft's own admission. Paulou instead builds a phoneme-level scoring pipeline (GOP-based) with full control over the reference phoneme sequence, so liaison can be scored deliberately rather than hoped for.

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
[5] Speech Assessment      — GOP scoring (substitution) + free phone recognition
                              (insertion/deletion), merged into calibrated feedback
```

| Stage | Folder | What it does |
|---|---|---|
| Sentence parsing | [`stages/parsing/`](stages/parsing/) | LLM-based chunking into rhythmic groups |
| G2P | [`stages/g2p/`](stages/g2p/) | Word → phonemes (Lexique383 + eSpeak-ng fallback) |
| POS tagging | [`stages/pos/`](stages/pos/) | Needed to apply liaison rules correctly |
| Liaison rules | [`stages/liaison/`](stages/liaison/) | Obligatoire / interdite / facultative rule engine |
| Unit assembly | [`stages/assembly/`](stages/assembly/) | Groups words into `single` or `liaison_group` `PronunciationUnit`s |
| TTS | [`stages/tts/`](stages/tts/) | Sentence-level synthesis with word-boundary timestamps |
| GOP scoring | [`stages/speech_assessment/gop/`](stages/speech_assessment/gop/) | Forced-align + goodness-of-pronunciation, catches substitutions |
| Free decoding | [`stages/speech_assessment/free_decode/`](stages/speech_assessment/free_decode/) | Unconstrained phone recognition, catches insertions/deletions (liaison dropped or added) |
| Merge + calibration + feedback | [`stages/speech_assessment/`](stages/speech_assessment/) | Combines both branches into a calibrated score and human-readable feedback |

Every model-backed or externally-dependent stage (parser, G2P source, TTS provider, GOP scorer, free-phone decoder) is defined as a `Protocol` interface and resolved through a small registry, so alternative implementations can be swapped via config without touching the pipeline or other stages — this is what lets `stages/speech_assessment/gop/kaldi_gop.py` and `gopft_gop.py` coexist and be compared directly (see `experiments/`). Pure, deterministic logic (liaison rules, unit assembly, alignment, merging, calibration, feedback templates) is kept as plain functions — no abstraction layer, since there's no real expectation of swapping these.

The core pipeline (`core/`, `stages/`, `pipeline.py`) is plain Python with no dependency on any UI layer. It's callable directly from a notebook or test, and a thin `backend/api/` (FastAPI) wraps it for the eventual frontend — the pipeline itself has no knowledge that a backend or frontend exists.

---

## Key design decisions

| Decision | Why | Backing |
|---|---|---|
| Custom GOP pipeline instead of Azure Pronunciation Assessment | Azure gives no control over the reference phoneme sequence and lacks phoneme-level detail for `fr-FR`; liaison handling is unverifiable | — |
| Two parallel branches (GOP forced-align + free phone recognition) instead of one model | Forced-align GOP is strong at catching substitutions but structurally blind to insertion/deletion, which is exactly where liaison errors show up | `experiments/runners/compare_gop_scorers.py` |
| Liaison modeled as its own `PronunciationUnit` type, not a word-level footnote | Liaison is a resyllabification phenomenon — scoring and drilling it as two separate words loses the thing being taught | — |
| Unsupervised percentile/z-score calibration, not a supervised regressor | No labeled French pronunciation dataset exists (unlike English's speechocean762); building one is deferred until there's real usage data to justify it | — |
| Sentence-level TTS synthesis (not per-chunk or per-unit) | Preserves natural prosody and in-context liaison; chunks/units are sliced from one audio pass via timestamps, not synthesized separately | — |
| Rule-based liaison detection (not a learned model) | Sufficient because MVP content is either app-authored or short user sentences; a purely rule-based approach is known to break down on unconstrained free-form input (this is a known, accepted limitation — see below) | — |

---

## Current status

**Build order steps 1–2 (Roadmap) are implemented and tested.** Steps 3+ (sentence parser, TTS, GOP scorer, free-phone recognizer) are still at the design stage — decided in the Architecture Spec, not yet built.

**Implemented so far:**
- **Pure functions** (step 1): liaison rule engine (`stages/liaison/rule_engine.py`), unit assembly (`stages/assembly/unit_assembler.py`), calibration (`stages/speech_assessment/calibration.py`), feedback templating (`stages/speech_assessment/feedback.py` — scoped to `single` units for MVP, see Decision Log D19).
- **G2P + POS tagging** (step 2): `stages/g2p/lexique_espeak.py` (Lexique383 lookup + eSpeak-ng fallback) and `stages/pos/spacy_tagger.py` (spaCy `fr_core_news_sm`).
- Core data models added incrementally as each stage needs them (`core/models.py`): `LiaisonDecision`, `PronunciationUnit`, `PhoneScore`, `UnitResult`. `Sentence`, `Chunk`, `Attempt` not needed yet.
- 53 tests passing (46 fast unit tests, 7 model tests requiring the real spaCy model) — see `tests/README.md`.

**Known data/tooling gaps, not yet resolved:**
- The real Lexique383 database isn't wired in yet — G2P currently reads from a small hand-written fixture dictionary. Whoever wires in the real corpus will need to adapt the lexicon loader to its actual column format.
- The native-French-corpus GOP calibration statistics (Decision Log D11) haven't been produced yet — `calibrate_score` takes the stats table as a parameter rather than embedding real numbers.

**Next up (build order step 3):** Sentence parser (LLM-based chunking) + TTS.

**Highest-priority open question, to be resolved early:**
- **Canonicalizer bias in the free phone recognition branch.** The planned insertion/deletion branch relies on a wav2vec2-based free decoder reporting what the user *actually* said rather than "correcting" it toward canonical French — a documented failure mode in mispronunciation detection literature. Before investing further in that branch, a small diagnostic set (native / substitution / deletion / insertion recordings) needs to be run through the model to check which behavior it exhibits.

**Known limitations (by design, not oversight):**
- Liaison detection is rule-based (`stages/liaison/rule_engine.py`), which is expected to be incomplete on unconstrained free-form input containing rare vocabulary, proper nouns, or borrowed words. This is an accepted MVP tradeoff (Decision Log D4), deferred post-MVP.
- **Confirmed, not just theoretical:** the POS tagger (spaCy `fr_core_news_sm`) mistags "content" (adjective, "happy") as `ADV` even in a full, grammatically correct sentence, which causes the liaison rule engine's "très/trop + ADJ" obligatoire pattern to miss real liaison for this specific word. Locked in as a known limitation for now — see the decision log's POS tagging entry.
- French support in the underlying acoustic models and tooling generally lags English; several components under consideration (e.g. `fr_kaldi-rhasspy`, `Cnam-LMSSC/wav2vec2-french-phonemizer`) are community-maintained rather than officially supported at the scale of their English equivalents.

---

## Getting started

*Steps below reflect what's actually built and tested right now (build order steps 1–2 — see [Current status](#current-status)). Everything under "not yet built" is aspirational, kept here as a placeholder for later stages — see the [Roadmap](docs/roadmap.md) for the build order.*

```bash
# clone and install
git clone https://github.com/quynhkhanh96/paulou.git
cd paulou                                    # repo root (docs/, this README, SETUP.md, the paulou/ package)
pip install -r requirements-dev.txt
python -m spacy download fr_core_news_sm     # separate step — see SETUP.md if this fails

# move into the package to run tests (no packaging / pip install -e . set up yet)
cd paulou

# fast suite — pure functions + G2P dict lookup, no models needed
pytest tests/unit -v

# model-backed suite — loads the real spaCy model, slower
pytest tests/model -v -m model
```

**Not yet built** (kept as a placeholder for later build-order steps):

```bash
# tests/contract doesn't exist yet — will hold invariant tests once
# stochastic stages (sentence parser, TTS) are built
pytest tests/contract

# run an experiment (compares candidate implementations for a stage)
python experiments/runners/compare_gop_scorers.py
```

Kaldi setup (required for the `kaldi` GOP scorer implementation) has its own quirks — see [`docs/kaldi_setup.md`](docs/kaldi_setup.md) *(TODO)*.

Qualitative review notebooks (chunking quality, audio playback, GOP alignment visualization, canonicalizer bias diagnostics) live in `experiments/notebooks/`.

---

## Repo structure

```
Paulou/                        # repo root
  docs/
    assets/
  README.md                    # this file
  SETUP.md                     # local dev setup (venv, dependencies, running tests)
  requirements-dev.txt
  .gitignore
  paulou/                      # the actual Python package
    core/                      # data models, interfaces (Protocol), registry — built incrementally as stages need them
    stages/                    # one subfolder per pipeline stage, swappable implementations
      liaison/                 # implemented — rule engine
      assembly/                # implemented — unit assembly
      speech_assessment/       # implemented — calibration, feedback (single units only for MVP, D19)
      g2p/                     # implemented — fixture lexicon + eSpeak-ng fallback (real Lexique383 not wired in yet)
      pos/                     # implemented — spaCy fr_core_news_sm
      parsing/                 # not yet built (build order step 3)
      tts/                     # not yet built (build order step 3)
    pipeline.py                # not yet built — PaulouPipeline orchestration entry point
    backend/                   # not yet built — FastAPI app, DB models/repository, background jobs
    frontend/                  # not yet built — client app (TBD)
    tests/
      unit/                    # implemented — fast, pure functions + G2P dict lookup
      model/                   # implemented — slow, loads the real spaCy model
      fixtures/                # implemented — g2p_golden.tsv (fixture lexicon)
      contract/                # not yet built
      api/                     # not yet built (no backend yet)
      db/                      # not yet built (no backend yet)
    experiments/                # not yet built — implementation comparisons, diagnostic sets, review notebooks
```

---

## Contributing

This is primarily a personal research and learning project, built alongside a PhD. Issues and PRs are welcome, but response times may be slow, especially through end of 2026.

---

## License

[Functional Source License (FSL)](https://fsl.software/) — converts automatically to Apache License 2.0 two years after each version's release. Source is public and free to read, use, and modify for non-competing purposes; see [LICENSE](LICENSE) for full terms.

---

## Acknowledgments & references

- [Lexique383](http://www.lexique.org/) — open French phonetic/lexical database
- [eSpeak NG](https://github.com/espeak-ng/espeak-ng) — fallback grapheme-to-phoneme synthesis
- [fr_kaldi-rhasspy](https://github.com/rhasspy/kaldi-french) — open French Kaldi acoustic model
- [gop-ft](https://github.com/JazminVidal/gop-ft) — PyTorch reimplementation of Kaldi GOP-DNN
- [Cnam-LMSSC/wav2vec2-french-phonemizer](https://huggingface.co/Cnam-LMSSC/wav2vec2-french-phonemizer) — free French phoneme recognition
- Cao et al., *GOP-CTC-AF: Alignment-Free Goodness of Pronunciation*, Interspeech 2024
- Parikh et al., 2025 — follow-up improvements to alignment-free GOP