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

### D37 — AlignmentOp schema, and FreePhoneRecognizer Protocol simplified to drop the full posterior vector
**Decision:** Introduced `AlignmentOp` (`core/models.py`) — one op per position in the optimal edit path between a chunk's canonical phonemes and a free-phone-recognizer's decoded output: `op_type` (match/substitution/insertion/deletion), `unit_id`, `canonical_phoneme` (None only for insertion), `decoded_phoneme` (None only for deletion), `confidence` (None only for deletion), `start_ms`/`end_ms` (None only for deletion). Also simplified the Architecture Spec's stage 5b `FreePhoneRecognizer` Protocol from `decode() -> tuple[list[str], list[list[float]]]` (phones + full posterior distribution per position) to `tuple[list[str], list[float], list[tuple[int, int]]]` (phones, per-position top-1 confidence, per-position time boundaries).
**Rationale:** `AlignmentOp` replaces `RawPhoneScore`/`PhoneScore` (D34) as the atomic unit of Speech Assessment output under D36. `start_ms`/`end_ms` were added even though nothing currently consumes them, on the expectation that Practice UI (stage 4, not yet built) will want to highlight the matching audio span during playback — confirmed useful when discussing color-coded pronunciation visualization (green/red/yellow/gray by op_type) during this design pass, though that visualization needs the CANONICAL view (fixed text/IPA) for deletion (no audio span exists) and the DECODED view (timeline) for match/substitution/insertion — see Roadmap. The Protocol simplification follows directly from deciding (see D39) that insertion scoring reuses plain confidence rather than posterior entropy — nothing downstream needs more than one float per position, so carrying the full vector was unused weight. `FreePhoneRecognizer` has no implementation yet, so this was a free edit, not a breaking change.
**Tradeoff accepted:** insertion attribution (no canonical counterpart) is a product convention, not a technical necessity — attaches to the PRECEDING unit's `unit_id` (last one consumed), or the first unit if nothing precedes it. Chosen for simplicity over computing time-distance to the nearest neighboring unit, since the goal is surfacing "an extra sound was added" rather than precisely which word it belongs to.
**Status:** Locked in. `RawPhoneScore`/`PhoneScore`/`GOPScorer` Protocol remain dormant in code (not deleted — `GOPScorer` Protocol still imports `RawPhoneScore`, and both need a coordinated removal not yet done).

### D38 — align_phonemes: equal-weight 3-way Levenshtein, with a deterministic tie-break order
**Decision:** `stages/speech_assessment/align.py::align_phonemes` uses classic Levenshtein DP with equal edit weights (sub_cost = del_cost = ins_cost = 1), replacing the old DEL/INS-only alignment (Architecture Spec stage 5c, originally scoped for Branch 2 alone under D9). Backtrace tie-breaking (needed because equal weights create ties often) follows a fixed priority: diagonal (match/substitution) > deletion > insertion. `unit_id` is assigned to each op DURING alignment, from a `unit_ids` array kept parallel to `canonical_phonemes` — not as a separate post-hoc grouping step.
**Rationale:** Equal weights were chosen for MVP simplicity (explicitly considered and rejected weighting deletion more heavily, e.g. for liaison-drop, to keep the algorithm's behavior easy to reason about for a solo developer new to this — same MVP-speed priority behind D36 overall). A genuinely useful emergent property of equal weights, not something special-cased: a single real mispronunciation always resolves as ONE substitution (cost 1) rather than a deletion+insertion pair for the same event (cost 2) — the more pedagogically useful reading. The tie-break order was chosen because reading a frame as "a phone was actually produced there" (match/substitution) is the more natural interpretation of the same acoustic evidence than "the expected phone vanished and an unrelated one appeared from nowhere" — and because backtrace ties are otherwise nondeterministic, which would break exact-match unit tests.
**Consequence:** Fully replaces D20 (count-based phoneme-to-unit grouping) — D20's approach breaks once insertions/deletions can make the canonical and decoded sequences different lengths; `phoneme_grouping.py` has no successor file, since `align_phonemes` absorbs its job outright.
**Status:** Locked in for MVP; edit weights are the most likely thing to revisit if real usage shows equal weighting produces poor pedagogical results for some error type.

### D39 — score_alignment_op: per-op-type scoring, and calibration.py's raw_gop renamed to raw_value
**Decision:** `stages/speech_assessment/scoring.py::score_alignment_op` converts one `AlignmentOp` into a 0-100 `accuracy_score`, kept as a separate pure function from alignment itself (same D34-style separation: alignment is structural, scoring is policy). Per op_type:
- `match`: `calibrate_score` (D11), reused as-is — only the parameter/field renamed from `raw_gop` to `raw_value` in `calibration.py` (and its tests), since this module has nothing to do with GOP anymore.
- `substitution` / `insertion`: `100 * (1 - confidence)` — deliberately NOT calibrated against a native reference distribution, since native speech has no substitutions/insertions by definition; there's nothing to build that distribution from.
- `deletion`: always `0`.
**Rationale:** For `match`, D11's z-score/CDF math still applies: a phone's `confidence` needs comparing against ITS OWN native distribution (some phones are naturally less "confident" to the decoder even when perfectly pronounced), not used as a raw score. For `substitution`, a confident wrong guess is unambiguous evidence of an error (score low); a hesitant one may be an honest near-miss (score higher) — the inverse relationship a first heuristic ("confidence cao → phạt cố định") failed to capture, corrected during design discussion. `insertion` reuses the same formula rather than a separate entropy-based "how sharp was the extra sound" measure (considered, rejected for MVP simplicity — see D37's Protocol simplification, which removed the full posterior vector this would have needed).
**Related framing (see Glossary's "Anomaly detection framing" entry):** D11's z-score calibration is itself a simple one-class/anomaly-detection model (fit only on native data, score deviation) — noted for the Publication Plan's contribution framing, not a reason to change this design.
**Status:** Locked in for MVP.

### D40 — merge_to_unit_result: MEAN aggregation carried over via ScoredAlignmentOp
**Decision:** Introduced `ScoredAlignmentOp` (`core/models.py`) — an `AlignmentOp` paired with its `accuracy_score` — kept separate from `AlignmentOp` for the same reason scoring is kept separate from alignment (D39). `UnitResult.phone_scores: list[PhoneScore] | None` is replaced by `UnitResult.scored_ops: list[ScoredAlignmentOp]`. The new `stages/speech_assessment/merge.py::merge_to_unit_result` scores every op via `score_alignment_op`, then aggregates via MEAN — D33's choice, carried over unchanged (a deletion's 0 pulls a unit's average down without one harsh op dominating the way MIN would). Adds one new guard not in the pre-D36 version: raises if any op's `unit_id` doesn't match the function's `unit_id` argument.
**Rationale:** D33's flagged D36 consequence ("a phone's score needs redefining for deletion/insertion") is resolved by D39 giving every op_type a real 0-100 `accuracy_score` — MEAN needed no change in kind, only in what it aggregates over. The new mismatched-`unit_id` guard was added because this function is now the point where a real integration bug (ops from the wrong unit reaching a merge call) would otherwise silently produce a wrong average instead of failing loudly.
**Status:** Locked in for MVP.

### D41 — generate_feedback redesigned: structural ops get explicit sentences, match ops keep D32's bracket grouping
**Decision:** `stages/speech_assessment/feedback.py::generate_feedback` produces, in this order: an overview sentence (from `calibrated_score`, same 85/60/0 boundaries as D32), then one sentence each for deletion, insertion, and substitution ops (if any — omitted if none of that type is present), then D32's bracket-grouped sentences for `match` ops only (good/close/needs-work). The overview sentence always appears, even for a unit with a single op that is itself a structural error (e.g. a one-phone unit that was dropped entirely) — confirmed as a product decision, not assumed.
**Rationale:** `match` still carries a continuous 0-100 score suited to D32's bracket idea (surface both strengths and weaknesses, not just the weakest phone — D25's original problem). `substitution`/`insertion`/`deletion` are different in kind: alignment already says exactly what happened (which sound was missing, extra, or wrong) — bucketing them into score brackets would throw away the most specific, useful information alignment provides. Structural-error sentences are ordered before match brackets because they're the more actionable, specific feedback.
**Consequence:** Resolves D32's flagged D36 consequence — bracket boundaries now apply ONLY to `match` ops, not to every phone regardless of op_type as D32 originally specified.
**Status:** Locked in for MVP. Exact sentence wording (e.g. "You substituted a sound: s→ʃ") is a first draft, not user-tested — revisit if real usage suggests clearer phrasing.

### D42 — Chunk-level orchestration (score_chunk) written as Stage A, not deferred to Stage B
**Decision:** Added `stages/speech_assessment/speech_assessment.py::score_chunk` (wires a `FreePhoneRecognizer` through `align_phonemes` and `merge_chunk_results` to score a whole chunk in one call) and `core/interfaces.py::FreePhoneRecognizer` (the real Protocol, per D37's simplified signature — previously only specced in the Architecture Spec, not in code). `GOPScorer` in `core/interfaces.py` is now explicitly commented as dormant/obsolete alongside it.
**Rationale:** `score_chunk` calls `FreePhoneRecognizer.decode()` — a model-backed dependency — but is fully testable via a stub implementing the Protocol (`_StubFreePhoneRecognizer`, same pattern as the pre-D36 `_StubGOPScorer`), with zero dependency on a real model existing. This was initially miscategorized as Stage B work in the turn that closed out D37-D41; the mistake was caught when checking whether `merge_to_unit_result` (unit-level only) and `align_phonemes` (chunk-level) actually connected end to end. Writing it now means Stage B is reduced to exactly what D36 always intended it to be: a real `FreePhoneRecognizer` implementation, and the diagnostic audio set to validate it (D10) — no orchestration glue left to write once a real model exists.
**Status:** Locked in. Stage A (pure functions + stub-testable orchestration) is complete for the redesigned Speech Assessment pipeline.

### D43 — Diagnostic audio set (D10) generated via open-source local TTS phoneme injection (Piper), not Azure/edge-tts/real recordings; storage split between experiments/ and tests/fixtures/

**Decision:** For the D10 canonicalizer-bias diagnostic set (native/substitution/deletion/insertion), audio is generated for MVP by feeding hand-edited phoneme sequences directly into an open-source, locally-run neural TTS model (Piper, MIT license), bypassing its text/G2P frontend, rather than using Azure Speech's SSML `<phoneme>` override, `edge-tts`, or real human recordings. Real human-recorded samples are explicitly deferred past MVP, to be collected once the app's own UI/recording flow is testable end-to-end. The generator code and all exploratory iterations live under `experiments/`, not `stages/` — Piper here is diagnostic tooling for stage 5, not a fourth candidate for the stage-3 `TTSProvider` registry (D31), and must not be confused with one. Once a version is judged good enough, the chosen audio files and their `metadata.json` are promoted (copied) into `tests/fixtures/diagnostic_audio/`, which remains the single pinned fixture shared by `tests/model/` regression checks and future `experiments/` comparisons across `FreePhoneRecognizer` candidates, per the existing Testing Conventions note. A new dependency extras group, `paulou[experiments]`, is introduced for dependencies (Piper, onnxruntime) that belong to `experiments/` tooling rather than to any registered stage — extending the existing per-stage extras pattern (Codebase Conventions) to cover this case.

**Rationale:**
- Azure Speech SSML natively supports `<phoneme alphabet="ipa" ph="...">` override, which would be the most direct approach, but no Azure Speech API key is currently provisioned.
- `edge-tts` (the existing no-API-key TTS provider, D31) was investigated as a substitute and confirmed, via its official repository README, to have removed all custom SSML support (including `<phoneme>`) since v5.0.0 — only `<prosody>` rate/volume/pitch remains. Ruled out.
- The raw `espeak-ng` CLI was tested directly (installed and probed in this session) and confirmed to support phoneme-sequence synthesis via its `[[...]]` bracket input, empirically verified by producing a measurably shorter WAV file for a liaison-deletion case (0.667s) versus the native case (0.741s) for the same words. However, `[[...]]` only accepts espeak-ng's own internal mnemonic/Kirshenbaum-style ASCII phoneme codes (confirmed: feeding real IPA characters directly produced broken/truncated output), which would require building and maintaining a full mapping table against Lexique400's IPA notation (D30), and espeak-ng's formant synthesis is audibly robotic.
- Piper was investigated instead by installing the package and reading its source directly (not from documentation alone): its phonemizer (`phonemize_espeak.py`) produces real IPA characters via espeak-ng, decomposed by Unicode NFD (base character and combining diacritics as separate codepoints) — the same IPA character family Lexique400 already uses (`LexiqueEspeakG2P._segment_ipa`), differing only in that Lexique400 groups a base character with its combining marks into one phoneme unit while Piper's phoneme-id map (`phoneme_ids.py`) keys each codepoint separately. Converting between the two is a mechanical NFD decomposition, not a hand-built symbol mapping table.
- Piper additionally exposes two ways to inject a custom phoneme sequence directly, bypassing its own text frontend entirely: the `[[...]]` raw-phoneme syntax inside `voice.phonemize()`, and the lower-level `phonemes_to_ids()` plus `phoneme_ids_to_audio()` pair, which accepts a hand-built phoneme list with no text/G2P step at all. Piper is MIT-licensed and runs fully locally, with no API key and no network call at synthesis time.
- Real human recordings, while closer to the production domain (learner audio), are deferred: MVP only needs a go/no-go signal on canonicalizer bias, and a much more convenient, realistic opportunity to validate with real speech will exist once the app's own UI/recording pipeline can be tested end-to-end post-MVP.
- Storing generated audio only under `experiments/results/` (as initially proposed) would conflict with the existing Testing Conventions requirement that the diagnostic set be a stable, version-pinned fixture shared between `tests/model/` regression checks and future `experiments/` comparisons — a folder meant for one-off, iterating comparison output does not give `tests/model/` the stable reference it needs. Splitting into an iteration phase (`experiments/`) and a promoted, pinned fixture (`tests/fixtures/diagnostic_audio/`) preserves both the freedom to iterate and the stability the fixture concept requires.
- Committing the promoted `.wav`/`metadata.json` files directly to git, rather than git-ignoring them and relying on regenerating from a script as D30 does for the large third-party Lexique400 file, is necessary because neural TTS synthesis (Piper's VITS/ONNX inference) is not guaranteed bit-identical across `onnxruntime` versions or hardware — committing the actual generated files is the only reliable way to pin them, matching the existing precedent of committing the small, self-authored `tests/fixtures/g2p_golden.tsv`. Generated audio under `experiments/results/` stays git-ignored (reproducible, one-off exploration artifacts), while `experiments/results/` JSON/markdown result summaries stay committed, per the existing Codebase Conventions expectation that such summaries are linked in PR descriptions.
- Case selection for the diagnostic set is informed by real literature rather than assumption: general MDD corpora (L2-ARCTIC, English) show substitution as the dominant phoneme-level error type (roughly 76% substitution / 19% deletion / 6% insertion across annotated subsets in multiple papers), but SLA/phonology literature specific to French liaison acquisition shows the opposite emphasis for liaison itself — omission (deletion) is repeatedly reported as the dominant liaison error type, with insertion notably rarer (one child-corpus study reports roughly 5.3% substitution, 4.8% omission, but only 0.8% insertion of total liaison productions), and liaison insertion errors, when they do occur, often take specific forms (glottal-stop or /l/-insertion) rather than substituting one liaison consonant for another. No ready-made annotated corpus exists specifically for French liaison MDD, unlike L2-ARCTIC for general English, so this is production-study literature, not a reusable labeled dataset.

**Tradeoff accepted:**
- Piper's suitability is confirmed only at the code level in this session, by reading the installed package's source directly, not yet with a real French voice model — the sandbox used could not reach huggingface.co to download an actual voice and run a real synthesis-plus-listening check. This remains open until verified locally: checking a French voice's `config.json` for `phoneme_type`/`phoneme_id_map`, and reproducing the native-vs-deletion duration/listening check already done with espeak-ng.
- The diagnostic set built this way is synthetic TTS-generated audio, not real learner speech; this is accepted for the MVP go/no-go question but is a known deviation from the production domain, to be revisited once real recordings are collected post-MVP.
- This diagnostic set is explicitly not the rigorous, multi-speaker, publication-grade set the Publication Plan calls for — that remains a separate, later task.
- Weighting diagnostic cases toward deletion for liaison specifically, per the SLA literature above, is a deliberate departure from what a naive reading of general MDD literature (substitution-dominant) would suggest; if this weighting turns out to be wrong for this specific `FreePhoneRecognizer` model's failure modes, the case set may need rebalancing once real results come in.

**Status:** Proposed — pending Khanh's local verification of a real Piper French voice before being fully locked in; the storage split, commit policy, extras group, and case-weighting rationale are agreed and locked in for MVP regardless of that outcome.

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
