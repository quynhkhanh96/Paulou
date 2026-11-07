# Paulou — Roadmap / Backlog

Forward-looking list of what's not done yet — deferred decisions, open design questions, and build order. Complements the Decision Log (which explains decisions already made) and Architecture Spec (which describes the target design). Update by moving items between sections as they progress, not by deleting — a completed item can move to a "Done" section or just get linked to its Decision Log entry.

---

## MVP scope note

Decision Log D36 replaced the old Branch 1/Branch 2 split: MVP uses a single free-decode + 3-way alignment pipeline for Speech Assessment, covering substitution AND insertion/deletion in one pass. The pipeline runs end to end with real components, from the command line (D48, D50) and through the local web app (D53-D66).

D70 sets the MVP priorities: technical readiness first (response time, easy local setup, a public link), and the lightest workable rule for answer quality (chunking, liaison, schwa, text normalization), checked by hand on a few examples. Native-corpus calibration is no longer MVP-blocking: scores are hidden (D57) and the result view uses op kinds and counts only (D63). MVP ships as (1) a public link that needs no install and (2) `git clone` + `docker compose up` for collaborators, with no API key.

---

## Done

- **Pure functions** — liaison rule engine, elision, unit assembly, alignment (D38), scoring (D39), merge (D40), feedback (D41), calibration math (D11/D24).
- **G2P + POS tagging** (D26, D30), **sentence parser** (D27), **TTS providers + cache + slicing** (D5-D7, D31).
- **Diagnostic audio set and canonicalizer-bias check** (D10 -> D43-D47): resolved with a documented caveat; `wav2vec2_cnam` is the default free decoder.
- **Real `FreePhoneRecognizer` implementations** (D45): Cnam-LMSSC and bofenghuang.
- **Merge logic** (was an open design question; resolved by D40) and **feedback** (D41).
- **`PipelineConfig`, `PaulouPipeline`, span location** (D48); **edge-tts hang fix** (D49); **manual end-to-end CLI** (D50, `docs/pipeline_cli.md`).
- **Latency benchmark** (`experiments/runners/benchmark_latency.py`, `experiments/results/latency/RESULTS.md`) — resolves D15: synchronous `/attempts` (D52).
- **Backend API and frontend** (build-order step 6; D52-D58): FastAPI backend, Vite + React + TS frontend, run instructions in `docs/web_app.md`. Docker images built and run by the author on one machine (D53).
- **Parser cache by sentence text** (D52 item, D55): `CachingSentenceParser`.
- **Whole-sentence practice tab, real tabs, pronunciation guide with example audio** (D59-D62).
- **Learner result view** (D63): counts-only score line, "Needs fixing" / "You did well" boxes, one chip per unit opening sound-by-sound track changes, "Hear the model" / "Hear yourself" (D65). Resolves the canonical half of the colour-coded visualization question (the audio-timeline half stays open, see below).
- **Close vs far substitutions** (D64): `phone_similarity.py`, a short confusion table with reason codes; API op fields `kind` and `near_reasons`.
- **Learner-facing wording generated in the frontend** (D66): `learnerText.tsx`. Resolves the step-6 follow-up about `feedback_text` wording under placeholder stats: that text is no longer displayed.

---

## MVP — next work (D67-D70)

In this order:

1. **Rule-based chunker replaces Gemini as the default parser** (D67). Liaison and elision computed over the whole sentence first; a chunk boundary never falls inside a liaison or elision. Removes the API key, run-to-run differences and most of the preparation latency; should also remove most of D51. Hand-test on "Les enfants ont acheté des pommes.", "les anciens amis" and a few others.
2. **Text normalization** (D68): apostrophe variants -> `'` (fixes elision detection), numbers via `num2words`, a few rules for times and abbreviations. Replaces today's rejection of sentences with digits. Open: confirm that the learner sees and practises the normalized text.
3. **Local TTS** (D69, tentative): `KokoroTTSProvider` with word timings computed from predicted phoneme durations; needs a local check that the timings line up with the words (espeak may merge words across a liaison). If it fails, keep edge-tts. Either way, add a rate limit on sentence preparation.
4. **Docker downloads Lexique400 (and models) automatically** on first start into a volume; no `.env` key once D67 is in.
5. **Re-measure latency on the target hardware** (e.g. the container limited to 2 vCPU), including concurrent attempts, then choose a host. The public link needs HTTPS (microphone).
6. **Quality items, lightest fix + hand test** (findings below): optional schwa (needs its own decision entry) and the in-chunk liaison miss.

Follow-ups from step 6 still open: real-browser check of Safari and Firefox recordings (D56); "Hear yourself" timing checked only with the stub pipeline (D65).

*(This ordering itself is a decision — D70.)*

---

## Findings from the first real end-to-end runs (D50)

Each needs a diagnosis, some need a design decision. Reproduce with `docs/pipeline_cli.md`.
- **Liaison inside a chunk that the rule engine does not predict.** "ont‿acheté" [t] is inside one chunk but missing from the canonical sequence, so it is scored as an `insertion`. To diagnose: the rule engine (AUX + participle), the POS tags, and D23's greedy resolution of liaison chains.
- **Optional schwa.** Lexique gives "acheté" as [aʃəte]; natural speech (and TTS) usually drops the schwa, which is scored as a `deletion` of `ə`. Needs a decision, e.g. treat schwa as an optional phoneme in `align_phonemes` (D38's equal-weight Levenshtein has no notion of optional phones).
- **Parser non-determinism.** The parse cache (D55) makes a repeated sentence stable; a new sentence can still be chunked differently. Goes away with D67.
- **Clip boundary accuracy** (D49). A 50-80 ms offset fixed the one case tested by ear. Re-test on many sentences/voices; if the needed shift varies per boundary, add energy-based boundary snapping (new pure function, new decision entry). Revisit if D69 replaces edge-tts.
- **Canonicalizer bias near nasal vowels** (D47 caveat): insertion scores next to nasal vowels should not be treated as fully trustworthy until a mitigation is designed.
- **Possible accent/microphone effects**: the first self-recording scored `e -> ɛ` on "acheté" and a deleted `p` in "pommes"; with no audio to inspect it is unknown whether these are the speaker, the microphone, or the model. Collect recordings (`score --record --save-recording`) before drawing conclusions.

Note: the UI surfaces D51 (cross-chunk liaison), optional schwa and D47 (nasal-vowel bias) as hints to the learner. This mitigates the user-facing symptom; the items above stay open.

---

## Open design questions (not yet resolved, need a decision before/during implementation)

- **Sentence preparation latency** (D52). `analyze_sentence` took 2.6-13.4 s median (p90 up to 14.8 s) with Gemini. Re-measure after D67; if still too slow, move sentence preparation to a background job (`/sentences` returns an id, client polls).
- **Concurrent load.** Decode is CPU-bound; concurrent attempts will queue. Not measured (D52); measure before the public deployment (MVP step 5).
- **Hosting for the public link** (D70). Needs HTTPS and enough CPU/RAM for wav2vec2. Hugging Face Spaces now needs a paid plan to create a Docker Space; free CPU hardware sleeps after about 48 h idle. Decide after MVP step 5.
- **Audio-timeline view** (D37 view 2). The decoded-audio timeline using `start_ms`/`end_ms` is not built; only the canonical view (D63).
- **Browser recording to WAV: client-side vs server-side.** The MVP converts the browser recording to WAV on the server (`audio_convert.py`, D56). Decide whether to capture WAV client-side instead.
- **UX flow beyond the practice screens.** Onboarding and a post-practice review/summary are not designed.
- **`PronunciationUnit.syllables` and `.note` have no owning stage** (also `Chunk.ipa_full`/`stress_syllable`, dropped from the model in D48 for the same reason).
- **Packaging.** No `pyproject.toml`, so the `paulou[free-decode]`, `paulou[experiments]` and `paulou[record]` (sounddevice) extras groups mentioned in D43/D45 do not exist yet; dependencies are installed by name (see `docs/pipeline_cli.md`).
- **Registry-import convention for Codebase Conventions.** `pipeline.py::_STAGE_MODULES` (D48) is how implementations get imported now; `free_decode/__init__.py` still imports its two modules for the experiments runners. Decide whether to keep both or document one.

---

## Deferred to post-MVP (explicitly, not forgotten)

- **Native-corpus calibration (`phone_stats`)** (D11, D24; moved here by D70). Run the free-phone recognizer over a native French corpus (e.g. Common Voice fr) to get per-phone mean/std of the match-op confidence; settles `min_sample_size` and `fallback_phone_class`. Until then the backend fills placeholder statistics internally (D50) and the API returns `score: null`. Remove the placeholders and the always-null `score` fields together with this work. Showing scores afterwards would also need a decision reversing D57.
- **Golden regression set** (D70). Sentences with expected chunks, units, liaisons and canonical phonemes, plus `(canonical, decoded) -> ops` cases for alignment, run as one pytest test. Needed before quality rules (chunking, liaison, schwa, normalization) can be changed with confidence.
- **Confusion table** (D64). Extend from real attempts or a learner corpus (e.g. IFCASL): ʁ->ɣ, i/e, u/o, b/v… Decide whether "near" means almost-right or common confusion, and add a third feedback level for common-but-distant confusions (ʁ->l, ʁ->ɡ), which today show as far without an explanation.
- **Liaison across chunk boundaries** (D51). Should mostly disappear with D67's hard rule; only if it does not, consider units that cross chunks.
- **Free-input edge case handling** — proper nouns, technical/borrowed vocabulary not covered by Lexique400 or the liaison rule engine. Accepted limitation for MVP (Decision Log D1, D4).
- **Progress tracking / attempt history** — never designed. Needs its own data model extension beyond `Attempt`.
- **Supervised calibration** (replacing the unsupervised percentile/z-score approach, Decision Log D11) — deferred until there's real usage traction to justify the cost of expert-labeled French pronunciation data.
- **Alignment-free unified scoring (GOP-CTC-AF)** — explicitly deferred future upgrade path (Decision Log D9).
- **Paragraph-level practice** (multiple consecutive sentences, cross-sentence prosody/liaison).
- **Larger, multi-speaker diagnostic set** (D43's tradeoff; required for publication-grade evidence, Publication Plan).
- **Group B recognizer candidates** — not tried; the D47 selection compared only two Group A models.
- **Dark mode** for the learner result view (D63).

---

## Documentation / repo hygiene todos

- `docs/kaldi_setup.md` — referenced as TODO in the README; likely obsolete after D36, decide whether to drop the reference.
- `LICENSE` file — needs full FSL text with Change Date and Change License (Apache 2.0) filled in.
- Keep Architecture Spec as the source of truth when it and the README diverge. Known stale spots in the Architecture Spec and README are listed in the docs update pass that accompanied D48-D50; re-check after each stage change. The Architecture Spec does not yet describe the web app (D53-D66) or the D67-D69 changes.
- Link `docs/pipeline_cli.md` from the README's Getting started and from `experiments/README.md`; mention the new `tests/unit/` files.
- Update README and `docs/web_app.md` setup steps once D67 (no Gemini key) and the automatic Lexique400 download land.
- Add `.pytest_cache/` to `.gitignore` if missing.

---

## Collaboration

- Actively looking for a collaborator specifically for the **TTS and Speech Assessment** components. Relevant prep before they join: dependency extras separation (see Packaging), and keeping PRs/decision log entries for those two stages especially well self-contained (see Codebase Conventions). `docs/pipeline_cli.md` is the quickest way for them to see the whole pipeline run; after MVP step 4, `docker compose up` with no key will be the quickest way to see the app.