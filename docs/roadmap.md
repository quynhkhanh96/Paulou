# Paulou — Roadmap / Backlog

Forward-looking list of what's not done yet — deferred decisions, open design questions, and build order. Complements the Decision Log (which explains decisions already made) and Architecture Spec (which describes the target design). Update by moving items between sections as they progress, not by deleting — a completed item can move to a "Done" section or just get linked to its Decision Log entry.

---

## MVP scope note

Decision Log D36 replaced the old Branch 1/Branch 2 split: MVP uses a single free-decode + 3-way alignment pipeline for Speech Assessment, covering substitution AND insertion/deletion in one pass. The pipeline now runs end to end with real components (D48, D50) on a command line; what remains before an MVP is trustworthy is real calibration data, the findings below, and the UI.

---

## Done

- **Pure functions** — liaison rule engine, elision, unit assembly, alignment (D38), scoring (D39), merge (D40), feedback (D41), calibration math (D11/D24).
- **G2P + POS tagging** (D26, D30), **sentence parser** (D27), **TTS providers + cache + slicing** (D5-D7, D31).
- **Diagnostic audio set and canonicalizer-bias check** (D10 -> D43-D47): resolved with a documented caveat; `wav2vec2_cnam` is the default free decoder.
- **Real `FreePhoneRecognizer` implementations** (D45): Cnam-LMSSC and bofenghuang.
- **Merge logic** (was an open design question; resolved by D40) and **feedback** (D41).
- **`PipelineConfig`, `PaulouPipeline`, span location** (D48); **edge-tts hang fix** (D49); **manual end-to-end CLI** (D50, `docs/pipeline_cli.md`).

---

## MVP-BLOCKING

**1. Native-corpus calibration (`phone_stats`)** (D11, D24)
- Run the free-phone recognizer over a native French corpus (e.g. Common Voice fr) to get per-phone mean/std of the match-op confidence. Until then every score is computed from placeholder statistics (D50), so unit scores are not meaningful.
- Also settles `min_sample_size` (D24's placeholder of 30) and the `fallback_phone_class` groupings.
- Owner/status: not started; next after the findings below are triaged.

**2. Findings from the first real end-to-end runs (D50)** — each needs a diagnosis, some need a design decision. Reproduce with `docs/pipeline_cli.md`.
- **Liaisons the pipeline does not predict.** On "Les enfants ont acheté des pommes." the TTS (and a human reading) says "enfants‿ont" [z] and "ont‿acheté" [t]; neither is in the canonical sequence, so each is scored as an `insertion`. To diagnose: (a) "enfants‿ont" fell across a chunk boundary (Gemini split "Les enfants" / "ont acheté"), and `analyze_chunk` evaluates each chunk alone, so liaison across chunk boundaries is not modeled at all; (b) "ont‿acheté" is inside one chunk, so check the rule engine (AUX + participle) and the POS tags; (c) D23's greedy left-to-right resolution drops the second boundary of a chain. Design question: should the parser avoid splitting inside a liaison, or should units be allowed to cross chunks?
- **Optional schwa.** Lexique gives "acheté" as [aʃəte]; natural speech (and TTS) usually drops the schwa, which is scored as a `deletion` of `ə` (score 0). Needs a decision, e.g. treat schwa as an optional phoneme in `align_phonemes` (D38's equal-weight Levenshtein has no notion of optional phones).
- **Parser non-determinism.** The same sentence gave 3 chunks on one run and 2 on another. Options: cache parse results per sentence, set temperature 0 (check what `gemini_parser.py` sets), or both.
- **Clip boundary accuracy** (D49). A 50-80 ms offset fixed the one case tested by ear. Re-test on many sentences/voices once the UI exists; if the needed shift varies per boundary, add energy-based boundary snapping (new pure function, new decision entry).
- **Canonicalizer bias near nasal vowels** (D47 caveat): insertion scores next to nasal vowels should not be treated as fully trustworthy until a mitigation is designed.
- **Possible accent/microphone effects**: the first self-recording scored `e -> ɛ` on "acheté" and a deleted `p` in "pommes"; with no audio to inspect it is unknown whether these are the speaker, the microphone, or the model. Collect recordings (`score --record --save-recording`) before drawing conclusions.

---

## Core pipeline build order

1-5 above are complete (pure functions, G2P/POS, parser/TTS, diagnostic set and recognizer, alignment/scoring, `pipeline.py`). Next:

6. Triage the findings above, then run the native-corpus calibration.
7. Latency benchmark of the recognizer path, which decides D15 (async vs synchronous scoring).
8. Backend API and UI.

*(This ordering itself is a decision — see Decision Log if it changes.)*

---

## Open design questions (not yet resolved, need a decision before/during implementation)

- **Async vs. synchronous scoring API** (Decision Log D15, tentative). Depends on recognizer latency, which has not been benchmarked (the CLI makes it possible: time `score`).
- **UX flow beyond the two mocked screens.** Onboarding, how a user submits a sentence, what a post-practice review/summary looks like — only isolated chunk/unit-level practice screens have been sketched so far.
- **`PronunciationUnit.syllables` and `.note` have no owning stage** (also `Chunk.ipa_full`/`stress_syllable`, dropped from the model in D48 for the same reason).
- **Color-coded pronunciation visualization for Practice UI** (surfaced during AlignmentOp design, Decision Log D37) — green for match, red for substitution, yellow for insertion, gray for deletion. Needs TWO complementary views: (1) a CANONICAL text/IPA view (works for match/substitution/deletion; an insertion can only show as a marker between two phonemes) and (2) a DECODED AUDIO TIMELINE view using `start_ms`/`end_ms` (works for match/substitution/insertion; a deletion has no audio span). Depends on the Practice UI being built.
- **Packaging.** No `pyproject.toml`, so the `paulou[free-decode]`, `paulou[experiments]` and `paulou[record]` (sounddevice) extras groups mentioned in D43/D45 do not exist yet; dependencies are installed by name (see `docs/pipeline_cli.md`).
- **Registry-import convention for Codebase Conventions.** `pipeline.py::_STAGE_MODULES` (D48) is how implementations get imported now; `free_decode/__init__.py` still imports its two modules for the experiments runners. Decide whether to keep both or document one.

---

## Deferred to post-MVP (explicitly, not forgotten)

- **Free-input edge case handling** — proper nouns, technical/borrowed vocabulary not covered by Lexique400 or the liaison rule engine. Accepted limitation for MVP (Decision Log D1, D4).
- **Progress tracking / attempt history** — never designed. Needs its own data model extension beyond `Attempt`.
- **Backend API and frontend implementation** — structure is designed (Architecture Spec), no code written yet.
- **Supervised calibration** (replacing the unsupervised percentile/z-score approach, Decision Log D11) — deferred until there's real usage traction to justify the cost of expert-labeled French pronunciation data.
- **Alignment-free unified scoring (GOP-CTC-AF)** — explicitly deferred future upgrade path (Decision Log D9).
- **Paragraph-level practice** (multiple consecutive sentences, cross-sentence prosody/liaison).
- **Larger, multi-speaker diagnostic set** (D43's tradeoff; required for publication-grade evidence, Publication Plan).
- **Nhóm B recognizer candidates** — not tried; the D47 selection compared only two Nhóm A models.

---

## Documentation / repo hygiene todos

- `docs/kaldi_setup.md` — referenced as TODO in the README; likely obsolete after D36, decide whether to drop the reference.
- `LICENSE` file — needs full FSL text with Change Date and Change License (Apache 2.0) filled in.
- Keep Architecture Spec as the source of truth when it and the README diverge. Known stale spots in the Architecture Spec and README are listed in the docs update pass that accompanied D48-D50; re-check after each stage change.
- Link `docs/pipeline_cli.md` from the README's Getting started and from `experiments/README.md`; mention the new `tests/unit/` files.

---

## Collaboration

- Actively looking for a collaborator specifically for the **TTS and Speech Assessment** components. Relevant prep before they join: dependency extras separation (see Packaging), and keeping PRs/decision log entries for those two stages especially well self-contained (see Codebase Conventions). `docs/pipeline_cli.md` is the quickest way for them to see the whole pipeline run.