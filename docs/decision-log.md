# Paulou — Decision Log

Chronological record of major design/architecture decisions, why they were made, and what alternatives were considered. Update this note whenever a new significant decision is made — append, don't rewrite history. If a decision is later reversed, add a new entry noting the reversal and link back to the original; don't delete the original entry.

---

## Product

### D1 — Free-input sentences as the core product bet
**Decision:** Users type in any French sentence they want to practice, rather than choosing from app-provided content.
**Rationale:** Existing pronunciation apps (Duolingo, Babbel, ELSA Speak) only offer pre-scripted sentences. Free-input covers use cases those apps can't (e.g. practicing a presentation script, a specific sentence someone got wrong) and is the main product differentiator.
**Tradeoff accepted:** Every downstream pipeline stage must handle unconstrained input in real time (no manual curation/QA possible per-sentence), which is a meaningfully harder engineering problem than curated content. Edge cases (proper nouns, technical/borrowed vocabulary, out-of-dictionary words) are explicitly deferred post-MVP — see Roadmap note.
**Status:** Locked in for product direction; edge-case handling deferred.

### D2 — Chunking by rhythmic group (groupe rythmique), not punctuation
**Decision:** Sentences are split into chunks based on French rhythmic/prosodic groups, not commas/periods.
**Rationale:** Liaison and enchaînement happen *within* a rhythmic group, not at arbitrary punctuation boundaries — splitting any other way would separate sounds that are pronounced as one unit.
**Alternatives considered:** Punctuation-based splitting (rejected — doesn't match how liaison actually behaves).
**Status:** Locked in.

### D27 — Sentence parser uses the Gemini API, not Claude API
**Decision:** The LLM-based sentence parser (Architecture Spec stage 1) calls the Gemini API (`GeminiSentenceParser`, `stages/parsing/gemini_parser.py`) instead of the Claude API as the Architecture Spec originally named.
**Rationale:** Cost — the Gemini API is significantly cheaper than the Claude API for this stage's usage pattern. Quality has not been compared between the two at this point.
**Status:** Locked in for now; revisit if quality issues surface once real usage/chunking output can be evaluated (see the unverified round-trip note in `gemini_parser.py`).

### D31 — edge-tts added as a second TTS implementation, alongside Azure
**Decision:** `stages/tts/edge_tts_provider.py` (`EdgeTTSProvider`, `register("tts", "edge_tts")`) implements TTSProvider using the unofficial `edge-tts` library, registered alongside the existing `AzureTTSProvider` (`register("tts", "azure_neural")`) — both kept, swappable via registry (same spirit as Kaldi vs gop-ft for the GOP scorer).
**Rationale:** Setup friction with Azure API key/credential provisioning. Quality/reliability not yet compared between the two.
**Known risk:** edge-tts reverse-engineers Microsoft Edge browser's "Read Aloud" WebSocket protocol — not a published/supported API. No SLA; could break or be blocked at any time without notice. Uses the same underlying neural voices as Azure (Edge's Read Aloud runs on Azure Cognitive Services), so voice names are interchangeable between the two implementations.
**Status:** Locked in as an available alternative; no default chosen yet (no `PipelineConfig` exists to set one — `pipeline.py` not built).

---

## Liaison modeling

### D3 — Liaison as a first-class `PronunciationUnit` type, not word-level metadata
**Decision:** Introduced `PronunciationUnit` with `type: "single" | "liaison_group"`. A liaison group spans 2+ words and is scored/practiced as one block, not as separate words with a note attached.
**Rationale:** Liaison is a resyllabification phenomenon (the consonant migrates to become part of the next word's onset). Treating it as two words with a footnote loses the exact thing being taught. Practicing "deux" and "amis" separately would strip the liaison entirely.
**Status:** Locked in; this is the model's core structural idea.

### D4 — Rule-based liaison detection for MVP, not a learned model
**Decision:** Liaison (obligatoire/interdite/facultative) is determined via a rule engine (POS-pattern rules + closed lists for exceptions like h-aspiré), not a trained classifier.
**Rationale:** Sufficient because MVP sentences are either app-authored or short, structurally ordinary user sentences.
**Known limitation (accepted, not a gap to be "discovered" later):** Purely rule-based liaison detection is known to break down on unconstrained free-form input with rare vocabulary or unusual syntax. Prior research (Microsoft) needed a fine-tuned BERT model to handle liaison edge cases at scale. This is an accepted tradeoff for MVP scope, not an oversight.
**Status:** Locked in for MVP; revisit if/when free-input edge cases become a real usage pattern.

### D21 — Interdite checks run before obligatoire checks in the liaison rule engine
**Decision:** `apply_liaison_rules` evaluates structural-impossibility and grammar/closed-list interdite rules *before* checking obligatoire POS patterns, not after.
**Rationale:** A pair like ("les", "héros") matches the DET+NOUN obligatoire pattern, but "héros" is h-aspiré (interdite, closed list) and must override it. If obligatoire were checked first, this case would be misclassified.
**Status:** Locked in.

### D22 — "Subject noun + verb" interdite rule simplified to POS-adjacency only
**Decision:** The interdite rule "no liaison after a singular noun acting as subject, before its verb" is implemented as "NOUN directly followed by VERB/AUX", without checking number (singular vs. plural).
**Rationale:** POS tags alone (spaCy `fr_core_news`) don't carry number agreement in the tuple shape `apply_liaison_rules` currently accepts (`word, POS`). Getting this fully correct would require morphological features, not just POS.
**Tradeoff accepted:** Plural subject nouns before a vowel-initial verb (where liaison IS actually optional/facultative, not strictly forbidden) will be incorrectly marked interdite. Rare in practice for MVP scope; revisit if this rule engine's input signature gains morphological features.
**Status:** Locked in for MVP.

### D23 — Unit assembly resolves consecutive liaison decisions greedily, left-to-right
**Decision:** When two adjacent LiaisonDecisions both apply (e.g. "les anciens amis" — les|anciens and anciens|amis both obligatoire), `assemble_units` merges the first pair and consumes both its words; the second decision is then skipped because its left-hand word has already been consumed.
**Rationale:** `PronunciationUnit.liaison_consonant` is a single value, not a list, implying each liaison_group spans exactly one liaison boundary (2 words) as specced. A 3+ word chain has no defined schema to hold two consonants in one unit.
**Tradeoff accepted:** "anciens" is only drilled as part of "les anciens", never as part of "anciens amis" — the second liaison boundary is silently dropped rather than taught. Rare in practice for MVP-length sentences; revisit if chains turn out to matter (would require extending `PronunciationUnit.liaison_consonant` to a list).
**Status:** Locked in for MVP.

---

## TTS

### D5 — Sentence-level TTS synthesis, sliced by timestamp — not per-chunk or per-unit synthesis
**Decision:** Synthesize the full sentence once, retrieve word-boundary timestamps from the TTS engine, and slice the single audio file into chunk-level and unit-level clips.
**Rationale:**
- Synthesizing chunks independently causes the TTS engine to apply full-sentence intonation to what is actually a mid-sentence fragment (e.g. dropping pitch at the end of a non-final chunk, as if it were sentence-final).
- Independently synthesized chunks/words won't reliably produce liaison, since the engine has no lookahead to the next fragment.
**Alternatives considered:** Per-chunk synthesis (rejected — breaks prosody and liaison); per-unit synthesis (same problem, worse).
**Implementation note:** Add short silence padding + fade-in/out at slice boundaries, since natural continuous speech has no pause where a slice cut is made.
**Status:** Locked in.

### D6 — Slow-playback audio generated via TTS `prosody rate`, not time-stretching
**Decision:** Generate a separate slow-rate TTS pass (via SSML `<prosody rate="0.7">`) rather than time-stretching the normal-speed audio.
**Rationale:** Time-stretching degrades audio quality/naturalness; a dedicated slow synthesis pass sounds better.
**Cost implication:** Doubles the characters synthesized per sentence — mitigated by caching (see D7).
**Status:** Locked in.

### D7 — Cache TTS output by `hash(text + voice + rate)`
**Rationale:** Same sentence/chunk may be practiced repeatedly by the same or different users; avoids redundant API calls and cost.
**Status:** Locked in.

---

## Speech assessment

### D8 — Rejected Azure Pronunciation Assessment as the scoring engine
**Decision:** Build a custom phoneme-level scoring pipeline instead of using Azure's API.
**Rationale (from direct investigation, not assumption):**
- Azure's `ReferenceText` parameter only accepts plain text, not a custom phoneme sequence — no way to control what phoneme string is scored against, which is essential for liaison.
- SSML `<phoneme>` tags are a Text-to-Speech feature, not usable with Pronunciation Assessment — easy to confuse, confirmed not applicable.
- For `fr-FR` specifically: no `ProsodyScore`, no phoneme names returned, no `Syllables`, no `NBestPhonemes` — these exist only for `en-US` (partially `zh-CN`). Only per-phoneme `AccuracyScore` is usable.
- Microsoft's own support forum acknowledges French nasal vowels and liaison are challenging for their model — no guarantee of correct liaison handling even if usable.
**Status:** Locked in — custom pipeline is being built instead.

### D9 — Two parallel branches for speech assessment: GOP (substitution) + free phone recognition (insertion/deletion)
**Decision:** Run two separate scoring paths on the same audio:
- **Branch 1 (GOP, forced-align):** Detects substitution errors (e.g. said /s/ instead of /z/). Uses Kaldi GOP-DNN or `gop-ft` (PyTorch reimplementation) with a French acoustic model (`fr_kaldi-rhasspy` as candidate base).
- **Branch 2 (free phone recognition):** Detects insertion/deletion errors (e.g. dropped or added a liaison sound). Uses unconstrained CTC decoding (`Cnam-LMSSC/wav2vec2-french-phonemizer` as candidate model), aligned to canonical phonemes via Levenshtein to classify DEL/INS.
**Rationale:** Forced-align GOP is structurally bound to the expected number/order of reference phones — it's good at "wrong phone in the right place" but nearly blind to "phone missing/added entirely," which is precisely the failure mode liaison errors take (a liaison consonant dropped or wrongly added).
**Alternative considered and explicitly deferred:** Alignment-free unified scoring (GOP-CTC-AF, Cao et al. Interspeech 2024; improved by Parikh et al. 2025) would catch substitution+deletion+insertion in one formula. Not chosen for MVP because: (1) the original authors report the full SDI variant underperforms narrower variants, (2) compute scales quadratically with phone count — conflicts with CPU/mobile-friendly requirement, (3) no packaged implementation exists yet, meaning the formula would need to be implemented from the paper — high engineering risk for MVP. Flagged as a future upgrade path, not rejected outright.
**Status:** Architecture locked in for MVP; **Branch 2's core assumption is unverified — see D10.**

### D10 — [OPEN / UNVERIFIED] Canonicalizer bias risk in the free-decode branch
**Issue:** Branch 2's entire value rests on an unverified assumption: that the free-decode model honestly reports what the user actually pronounced, rather than "correcting" it toward the canonical form it learned during training. This is a documented failure mode in mispronunciation detection (MDD) literature — standard ASR training optimizes for *invariance* to pronunciation variation (recognize the word regardless of accent), which is the opposite of what pronunciation assessment needs (sensitivity to every deviation).
**Supporting evidence found:** A Mandarin MDD study showed models trained only on native speech (same setup as `Cnam-LMSSC`, trained on Common Voice) had increased False Acceptance Rate on learner speech — i.e., missed real errors, consistent with "canonicalizer" behavior.
**Concrete failure case of concern:** Audio that actually contains /leami/ (liaison dropped) could be "hallucinated" by the model into /lezami/ — a false negative on exactly the error type Paulou is designed to catch.
**Why published PER numbers don't answer this:** The model's published Phone Error Rate (4.75% on Common Voice French, 5.97% on French MLS v2) measures recognition accuracy on normal speech, not error-detection sensitivity on learner speech — a different question entirely.
**Mitigation direction (not yet implemented):** Instead of taking CTC argmax (top-1 phoneme), retain the full posterior distribution at each position and let the alignment step use it — a GOP-like approach applied to free decoding, giving both the model's "lean" and its confidence.
**Status:** **This is the #1 priority validation task before further investment in Branch 2.** Requires running a small diagnostic set (native / substitution / deletion / insertion recordings) through the model to determine whether it behaves as an honest recognizer or a canonicalizer. See Experiment Log and `experiments/runners/canonicalizer_bias_check.py`.

### D11 — Unsupervised percentile/z-score calibration, not a supervised regressor
**Decision:** Convert raw GOP scores to a 0–100 scale using per-phone mean/std (or percentile breakpoints) computed offline from a native French corpus (e.g. Common Voice fr), then `score = 100 × CDF_normal(z)` at runtime.
**Rationale for rejecting supervised approach:** A supervised regressor (like the one used for `speechocean762`) needs phone-level expert-labeled mispronunciation data, which doesn't exist for French (speechocean762 is English-only). Building one would require significant expert annotation effort.
**Tradeoff accepted:** Unsupervised calibration only measures "how different from native speech," not "how severe does this sound to a human listener" — the latter is what supervised labels would capture. Accepted for MVP; supervised approach deferred until there's traction and real usage data to justify the annotation cost.
**Status:** Locked in for MVP.

### D24 — Calibration stats passed as a parameter; sample-size threshold is an unvalidated placeholder
**Decision:** `calibrate_score` takes `phone_stats: dict[str, PhoneStats]` and `fallback_phone_class` as parameters rather than embedding a mean/std table in code. `min_sample_size` defaults to 30.
**Rationale:** The native French corpus run that D11 calls for (offline GOP pass over Common Voice fr to get per-phone mean/std) hasn't happened yet — there is no real data to embed. Passing it as a parameter keeps the formula itself testable now without pretending placeholder numbers are real calibration data.
**Tradeoff accepted:** `min_sample_size=30` is a guess (common statistical rule-of-thumb), not derived from anything specific to phone-level GOP distributions. Must be revisited once the actual corpus run produces real per-phone sample sizes.
**Status:** Locked in for MVP structure; the threshold value itself is not locked in and should be revisited.

### D30 — G2P dictionary wired to Lexique400, not Lexique383
**Decision:** `LexiqueEspeakG2P.from_lexique400()` loads the real Lexique400 database (lexique.org), not Lexique383 as the Architecture Spec originally named. Uses columns `1_Mot` (word) and `3_Phono_IPA` (IPA transcription).
**Rationale:** Lexique400 is more up-to-date (a "major upgrade" per its 2026 publication). It also provides real IPA directly, unlike Lexique383's ASCII phonetic code, simplifying integration.
**Implementation note:** IPA phoneme segmentation (grouping base character + Unicode combining marks, e.g. nasal tilde, into one phoneme) was empirically verified against Lexique400's own ASCII phonetic column across all 189,863 rows — 0 mismatches.
**Known limitation:** ~719 words (0.4%) have more than one distinct pronunciation in the file (minor phonetic variants, not true heteronyms in sampled cases); loader keeps whichever appears last, no disambiguation attempted.
**Not committed to the repo:** the 33MB file is git-ignored, expected at `paulou/data/Lexique400.tsv`, downloaded separately.
**Status:** Locked in.

### D19 — MVP scope excludes Branch 2 (free phone recognition / insertion-deletion detection)
**Decision:** MVP ships with only Branch 1 (GOP forced-align scoring). `liaison_group` units remain fully present in the UI (IPA, pedagogical notes, TTS sample, recording) but do not get a trustworthy automated score for "was the liaison sound present/absent" — either no auto-score is shown for that specific error type, or raw GOP is shown with an explicit low-confidence caveat.
**Rationale:** Forced-align GOP is structurally near-blind to insertion/deletion (see D9) — shipping it as the sole scorer for `liaison_group` units would mean confidently displaying feedback ("missing liaison /z/") that isn't actually reliable, for precisely the error type Paulou's liaison modeling (D3) exists to catch. Rather than fake reliability, MVP scopes the automated scoring down to what Branch 1 can honestly support (`single` units, `phoneme_accuracy`), while keeping the liaison teaching/UI content intact.
**Status:** Locked in.

### D25 — Feedback templating signature and weakest-phone selection
**Decision:** `generate_feedback` takes `(unit_type, calibrated_score, phone_scores)` directly instead of a full `UnitResult` as the Architecture Spec's stage table literally states. When a `single` unit has multiple phones, the phone named in the `[X]` placeholder is the one with the lowest `calibrated_score`.
**Rationale:** `UnitResult.feedback_text` is exactly what this function produces — accepting `UnitResult` as input would be circular (the caller would need `feedback_text` before it exists). The weakest-phone rule is the most natural reading of "watch the [X] sound" but isn't specified anywhere in the notes.
**Status:** Locked in for MVP; weakest-phone selection may need revisiting if a unit has multiple similarly-low phones and naming just one turns out to be poor pedagogy.

### D33 — MEAN aggregation for stage 5e, phoneme-to-unit score merging
**Decision:** `merge_to_unit_result` aggregates a unit's phone-level calibrated scores into the unit's `calibrated_score` via MEAN (rounded to nearest int), not MIN.
**Rationale:** MIN was the original instinct to keep score and feedback consistent when feedback could only name one weakest phone (see original D25). D32's feedback redesign (grouping all phones by score bracket, not just the weakest) removed that constraint — mean score + per-bracket feedback breakdown together surface both strengths and weaknesses, without one harsh phone dragging the displayed score down disproportionately.
**Status:** Locked in for MVP.

### D34 — GOPScorer returns uncalibrated RawPhoneScore, not PhoneScore
**Decision:** `GOPScorer.score(audio, canonical_phonemes)` returns `list[RawPhoneScore]` (phone, raw_gop, start_ms, end_ms — no calibrated_score), not `list[PhoneScore]` as the Architecture Spec originally specced. A new orchestration function, `score_chunk` (`stages/speech_assessment/speech_assessment.py`), calls `calibrate_score` on each entry to build real `PhoneScore`s, analogous to `analyze_chunk` for stage 2.
**Rationale:** Same reasoning D25 already applied to feedback templating (D12): a model-backed, swappable stage (GOPScorer) shouldn't call a separate pure-function stage's logic (calibration) itself — that couples two things meant to be independently swappable/testable. `KaldiGOPScorer` and `GopFtScorer` (Stage B, not built yet) will both return the same uncalibrated shape regardless of which is active.
**Status:** Locked in for MVP.

### D32 — Feedback templating redesigned: per-bracket phone grouping, applies to all unit types
**Decision:** `generate_feedback(calibrated_score, phone_scores)` now groups all phones by score bracket (85-100 / 60-84 / 0-59) and produces one sentence per non-empty bracket plus one overall sentence, instead of picking a single template and naming only the weakest phone. The `unit_type` parameter is removed — the function no longer special-cases or rejects `liaison_group`.
**Rationale:** Surfaces both strong and weak phones in the same unit, rather than only the weakest point (the original design's problem, which forced the stage 5e phone-to-unit aggregation toward MIN to keep score and feedback consistent — see the design discussion preceding D32). This also exercises D19's second explicitly-allowed option for `liaison_group` ("raw GOP shown with an explicit low-confidence caveat") instead of its first ("no auto-score shown"), since GOP can score individual phones in a liaison sequence for substitution accuracy even though it can't reliably confirm insertion/deletion. The caveat itself is not expressed by this function — attaching it in the UI, keyed on `PronunciationUnit.type`, is the caller's responsibility.
**Consequence for D25:** the weakest-phone-selection choice in D25 no longer applies (there's no single named phone anymore — phones are grouped, not ranked to one). D25's other point (function signature avoiding circularity with `UnitResult`) still stands.
**Status:** Locked in.

---

### D20 — `GOPScorer` accepts audio + canonical phonemes at any granularity, not just per-unit
**Decision:** The `GOPScorer` interface takes `audio: bytes, canonical_phonemes: list[str]` for whatever span is passed in (a single unit, a full chunk, or a full sentence) and returns per-phoneme scores with boundaries for that whole span. Grouping the returned per-phoneme scores into individual `PronunciationUnit` results happens as a separate merge step at the application layer, not by calling the scorer once per unit.
**Rationale:** GOP/forced-alignment doesn't care about linguistic unit boundaries — it only needs an audio signal and a reference phoneme sequence, and works the same whether that sequence is 3 phonemes or 30. Running one forced-align pass per chunk/sentence (rather than one per unit) preserves surrounding acoustic context for alignment (coarticulation — neighboring phones influence each other, including at liaison boundaries), which is the same reasoning already applied to sentence-level TTS synthesis (D5). Calling the scorer once per small unit would needlessly re-run forced-alignment with less context each time, and is unnecessary — the phoneme-boundary output already lets scores be grouped by unit afterward.
**Consequence:** A new pure merge step is needed — mapping the flat per-phoneme output of a chunk/sentence-level GOP call back onto each `PronunciationUnit`'s phonemes, using the phoneme sequence order (and boundaries, once fixed) to know which scores belong to which unit. This sits alongside the existing 5e merge (which combines Branch 1 + Branch 2 per unit) — not a replacement for it, but a step that happens before it.
**No change to calibration (5d):** calibration remains per-phoneme (z-score/percentile lookup keyed by phone identity), independent of what granularity the GOP call was made at.
**Status:** Locked in.

### D35 — Optional silence (SIL) inserted between units in canonical_phonemes
**Decision:** `score_chunk` inserts a `SIL_PHONE = "SIL"` marker between every pair of adjacent `PronunciationUnit`s when building `canonical_phonemes` for the GOP call — NOT within a `liaison_group`/`elision_group`'s own merged phoneme sequence. SIL entries are stripped from the result before calibration.
**Rationale:** Without a silence marker between units, a real forced aligner has no way to account for a pause/breath a learner (not a native speaker) might take between words — it would fold that silence into the timing/scoring of an adjacent real phone, corrupting both. Not inserted within liaison/elision groups, since those specifically represent phonemes meant to be pronounced with no gap.
**Known unresolved caveat:** inserting the literal string "SIL" only achieves true optional-silence behavior if the GOPScorer implementation's own alignment mechanism specifically treats it as skippable/zero-duration-allowed (normally a property of FST/lexicon construction, e.g. Kaldi's optional-silence handling) — not something a naive "align this reference, every phone mandatory" implementation gets for free. This is unverified with the current simulated stub (Stage A) and must be confirmed against the real GOPScorer implementation's behavior, and against `fr_kaldi-rhasspy`'s actual phone symbol table (to confirm "SIL" is the right token), once Stage B is built.
**Explicitly NOT addressed:** SIL within liaison/elision groups, which could help distinguish the Architecture Spec's "Smooth liaison, right rhythm" vs. "Liaison present but slightly separated" feedback cases — flagged as a possible future refinement, out of scope now.
**Status:** Locked in for the plumbing (insertion position, stripping); the alignment-semantics correctness is open pending Stage B.

### D36 — [REVERSAL of D9] Single free-decode + 3-way alignment pipeline,
replacing the two-branch GOP/free-decode architecture

**Decision:** Speech Assessment abandons the two-branch design (D9: Branch 1 GOP forced-align for substitution, Branch 2 free-decode for insertion/deletion). Instead: one free-phone-recognition pass per chunk/sentence, aligned to the canonical phoneme sequence via full three-operation Levenshtein alignment (substitution + insertion + deletion — not just DEL/INS as D9 originally scoped stage 5c). This single alignment result is now the sole source of both "was this phone right" and "was a phone missing/added" — no separate GOP/forced-align branch.

**Rationale:**
- Priority is the fastest path to a working MVP that stays legible and controllable end-to-end for a solo developer without prior GOP/Kaldi experience — not the most linguistically-established option.
- Direct verification of two currently-maintained open-source pronunciation-assessment tools with real French support (OpenPronounce, Echoic) shows both use exactly this pattern — free phone-decode + alignment, not GOP/Kaldi — a real community precedent, not just a theoretical preference.
- Eliminates the entire category of engineering risk carried by the GOP options investigated (Kaldi GOP-DNN, gop-ft): no Kaldi/PyKaldi toolchain, no acoustic-model-format conversion from fr_kaldi-rhasspy, no need to verify optional-silence semantics against an unfamiliar Kaldi FST/lexicon convention (D35's open caveat becomes moot under this design).
- A single 3-way Levenshtein alignment against one free-decode pass structurally catches everything D9's two branches were built to catch.

**Tradeoff accepted:**
- Score is inherently more binary (matched / substituted / missing / extra) than GOP's continuous log-likelihood-ratio. A graded 0-100 score needs a new design using the decoder's own per-position confidence — not GOP's ratio. Not yet designed.
- Canonicalizer bias (D10) risk is now concentrated on the ONE scoring mechanism for ALL error types, not just Branch 2 as D10 originally scoped it. The diagnostic validation D10 calls for is now MVP-blocking, not post-MVP — see Roadmap.

**Status:** Locked in for direction; implementation blocked on the follow-up redesign (AlignmentOp schema, confidence-based scoring — see Roadmap open design questions).

**Consequences (flagged, not resolved here):**
- D19 (MVP excludes Branch 2) — moot as written; see Roadmap.
- D20 (phoneme-to-unit grouping by flat order+count) — breaks under insertions/deletions; grouping must move to the alignment output itself.
- D33 (MEAN aggregation of calibrated phone scores) — concept may survive, but "a phone's score" needs redefining for deletion/insertion ops.
- D34 (`GOPScorer` returns uncalibrated `RawPhoneScore`) — `GOPScorer` Protocol and `RawPhoneScore` are obsolete for this pipeline; `FreePhoneRecognizer` becomes the sole model-backed interface for this stage.
- D35 (SIL_PHONE relying on Kaldi optional-silence FST semantics) — no longer applies; representing inter-word pauses in this pipeline is a new open question.
- Architecture Spec stage 5 and the Roadmap's MVP scope/build order need rewriting to match — see those notes.

---

## Engineering / codebase architecture

### D12 — Protocol interfaces + registry for swappable, model-backed stages; plain functions for deterministic logic
**Decision:** Every stage with an external/model dependency likely to be swapped or compared (sentence parser, G2P source, TTS provider, GOP scorer, free-phone recognizer) is defined as a `typing.Protocol` and resolved via a small registry + config, so implementations can be swapped by changing one config value. Pure, deterministic logic (liaison rules, unit assembly, alignment, merge, calibration, feedback templating) stays as plain functions — no interface/registry layer.
**Rationale:** The stages likely to need experimentation (e.g. Kaldi GOP vs. `gop-ft`) benefit from being swappable without touching pipeline code or other stages' tests. Applying the same abstraction to pure functions would be over-engineering — there's no real expectation of swapping the liaison rule algorithm itself.
**Status:** Locked in.

### D28 — Elision modeled as a third PronunciationUnit type, distinct from liaison
**Decision:** Introduced `PronunciationUnit.type = "elision_group"` and `scoring_focus = "elision_correctness"`, with detection in a new `stages/chunk_analyzer/elision/elision.py` (closed-list lookup, no rule engine needed). `assemble_units` checks elision before liaison at each position — no new parameter needed, since elision detection depends only on the word's own spelling.
**Rationale:** Elision (le/la/de/je/me/te/se/ne/que/ce → l'/d'/j'/m'/t'/s'/n'/qu'/c') is linguistically distinct from liaison — no consonant is added, it's a closed list rather than a POS pattern, and it's not a "decision" (seeing the elided orthographic form is itself proof it already happened). Confirmed empirically to never conflict with liaison at the same word (elided words have no liaison-capable final consonant).
**Explicitly NOT modeled:** enchaînement (already noted as deferred in the Glossary) — unlike elision, it requires knowing whether a word's final consonant is already pronounced, which needs G2P output rather than orthography/POS alone, and would require reordering the pipeline (G2P before the junction decision).
**Status:** Locked in.

### D29 — Chunk Analyzer sub-stages nested under stages/chunk_analyzer/, not flat under stages/
**Decision:** `g2p/`, `pos/`, `liaison/`, `elision/`, `assembly/` moved from flat siblings under `stages/` to nested children of a new `stages/chunk_analyzer/` folder.
**Rationale:** The Architecture Spec's own codebase structure was internally inconsistent — `speech_assessment/` (also a composite, multi-sub-module stage) already nests its sub-modules (`gop/`, `free_decode/`), but the Chunk Analyzer's sub-modules were flat, ranked alongside top-level stages like `parsing/` and `tts/`. Nesting makes the four top-level pipeline stages (Sentence Parser, Chunk Analyzer, TTS, Speech Assessment) visible directly in `stages/`'s folder listing, matching the Architecture Spec's own pipeline overview.
**Note:** `tests/` directory structure is unaffected — test files mirror module names, not directory nesting (Codebase Conventions), so only import statements inside test files changed, not test file locations.
**Status:** Locked in.

### D26 — POS tagging implemented as a plain class, not via Protocol/registry
**Decision:** POS tagging (spaCy `fr_core_news_sm`) is implemented as a plain class, not wrapped in a Protocol + registry like G2P/TTS/GOP scorer/free-phone recognizer, despite D12 not explicitly placing it in either category.
**Rationale:** D12's criterion is "likely to be swapped or compared" (e.g. GOP scorer's live Kaldi-vs-gop-ft question). Published UPOS accuracy for spaCy fr_core_news models (~96–97% on UD French Sequoia) is well above what's needed for the coarse POS categories the liaison rule engine consumes (DET/NOUN/ADJ/VERB/PRON/ADP/NUM/CCONJ/AUX); there's no live comparison question against Stanza the way there is for GOP scorers. Adding swap infrastructure with no anticipated swap would be over-engineering (same reasoning D12 already applies to pure functions).
**Status:** Locked in; revisit if French POS accuracy on liaison-relevant categories turns out to be a real problem in practice (AUX/VERB confusion is a known spaCy issue and directly touches two of our obligatoire/interdite patterns).

### D13 — Core pipeline fully decoupled from UI
**Decision:** `core/` and `stages/` have zero knowledge of `backend/` or `frontend/`. Dependency direction is one-way: UI layers import/call the pipeline, never the reverse.
**Rationale:** Keeps the pipeline callable directly from a notebook or pytest without any UI/DB/HTTP dependency, and means UI can be added later without refactoring core logic.
**Status:** Locked in.

### D14 — Separate DB models and API schemas from core data models
**Decision:** `core/models.py` stays plain dataclass/Pydantic with no ORM inheritance. `backend/db/models.py` (SQLAlchemy) and `backend/api/schemas.py` (Pydantic DTOs) are separate layers, mapped to/from core models explicitly.
**Rationale:**
- Core models must remain usable without a DB connection (for notebook/test use).
- API responses shouldn't leak internal debug detail (e.g. raw GOP posteriors) that core models may carry for internal use.
- Core models can evolve during algorithm experimentation without breaking the API contract with the frontend.
**Status:** Locked in.

### D15 — [TENTATIVE] Async job architecture for speech assessment
**Decision (tentative, pending benchmark):** Design the `/attempts` API to return an `attempt_id` + status immediately, process GOP/free-decode scoring as a background job, and have the frontend poll or receive a push update — rather than scoring synchronously within the request.
**Rationale:** GOP and free-decode inference latency is currently unknown/unbenchmarked; designing the API contract as async-ready from the start avoids a breaking API shape change later if synchronous scoring turns out to be too slow.
**Status:** Tentative — will be simplified to synchronous if latency benchmarking (see Experiment Log) shows response times are consistently low (~1–2s).

### D16 — Tests vs. experiments are separate concerns, separate directories
**Decision:** `tests/` contains only pass/fail assertions meant to run in CI (unit, contract/invariant, model, api, db). `experiments/` contains comparative, reproducible evaluations between candidate implementations (e.g. Kaldi vs. `gop-ft`), plus qualitative review notebooks — none of this runs in CI.
**Rationale:** Experiments are inherently non-binary (no fixed "correct" answer, just data to inform a decision) and often expensive/slow — mixing them into `tests/` would make CI slow and unstable. Notebooks are decision-support tools, not proof of pipeline correctness.
**Status:** Locked in. See Testing Conventions note and Experiment Log.

---

## Publishing / licensing

### D17 — Public repository from day one
**Decision:** Keep the repo public from the start rather than building privately first.
**Context:** An earlier discussion leaned toward "keep it private for now" reasoning that the real moat is pipeline robustness accumulated through testing, not the architecture itself, and that a not-yet-validated product doesn't need to decide open vs. closed yet. This was reconsidered in favor of public-from-day-one, likely for portfolio visibility given the industry research career goal.
**Status:** Locked in (supersedes the earlier private-first leaning).

### D18 — License: Functional Source License (FSL), not MIT
**Decision:** Use FSL instead of a fully permissive license.
**Rationale:** FSL keeps the source public and usable for non-competing purposes while restricting direct competitive use for a fixed period (2 years), after which it auto-converts to Apache 2.0. Chosen over MIT given the app is a real product idea, not just a reference implementation; chosen over BSL for simplicity (FSL has two fixed permission options rather than BSL's freeform "additional use grant" that has to be authored per-project).
**Status:** Locked in.
