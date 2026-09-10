# Paulou — Roadmap / Backlog

Forward-looking list of what's not done yet — deferred decisions, open design questions, and build order. Complements the Decision Log (which explains decisions already made) and Architecture Spec (which describes the target design). Update by moving items between sections as they progress, not by deleting — a completed item can move to a "Done" section or just get linked to its Decision Log entry.

---

## MVP scope note

MVP excludes Branch 2 (free phone recognition, insertion/deletion detection) — see Decision Log D19. `liaison_group` units are fully present in the UI and TTS/practice flow; only automated scoring for "was the liaison present/absent" is out of scope for MVP. This means the item below (previously "Priority #0, blocks MVP") **no longer blocks MVP** — it's now a post-MVP task, and also the basis for the Publication Plan.

---

## Post-MVP, highest priority — feeds both the app and the Publication Plan

**Canonicalizer bias diagnostic check** (Decision Log D10, D19)
- Build a small diagnostic audio set: native / substitution / deletion / insertion recordings for a handful of target words/liaison pairs.
- Run through `Cnam-LMSSC/wav2vec2-french-phonemizer`, compare actual audio vs. model output vs. expected.
- Determine: does the model honestly report what was said, or does it "correct" toward canonical French?
- **This result decides whether Branch 2 is worth building as designed, or needs a fallback approach — and, per the Publication Plan, is being designed rigorously enough (multiple speakers, controlled error types, quantitative reporting) to also serve as the paper's core finding, rather than being redone later at higher rigor.**
- Owner/status: not started.

---

## Core pipeline build order (bottom-up, per dependency and testability)

1. **Pure functions first** — liaison rule engine, unit assembly, Levenshtein alignment, merge, calibration, feedback templating. No external dependencies, fastest to implement and test, and the design for these is the most settled already.
2. **G2P + POS tagging** — Lexique383 + eSpeak-ng fallback, spaCy/Stanza POS tagging. Offline, testable via golden set.
3. **Sentence parser (LLM chunking) + TTS** — lower technical risk, well-understood approach (LLM call + vendor API wrapper).
4. **GOP scorer (Branch 1 only)** — sufficient for MVP scope (Decision Log D19); no diagnostic set dependency needed for this alone.
5. **MVP complete at this point** — steps 1-4 are sufficient to ship (per D19), without Branch 2.
6. *(Post-MVP)* **Diagnostic audio set + Branch 2 (free phone recognition)** — see "Post-MVP, highest priority" above. Depends on MVP being functional enough to have real practice content/usage to validate against, and doubles as Publication Plan groundwork.

*(This ordering itself is a decision — see Decision Log if it changes.)*

---

## Open design questions (not yet resolved, need a decision before/during implementation)

- **Merge logic (Architecture Spec, stage 5e).** How GOP branch output (per-phone scores) and free-decode branch output (DEL/INS ops) combine into one `UnitResult` has not been designed in detail yet. This affects what `feedback.py` can actually say to the user when both branches disagree or only one applies.
- **Async vs. synchronous scoring API** (Decision Log D15, tentative). Depends on GOP/free-decode latency benchmarking, which hasn't been run yet. Resolve after step 4 above produces working code to benchmark.
- **UX flow beyond the two mocked screens.** Onboarding, how a user submits a sentence, what a post-practice review/summary looks like — only isolated chunk/unit-level practice screens have been sketched so far, not the surrounding flow.
- **`gop-ft` vs. Kaldi GOP as the production choice** — currently both are candidate implementations behind the same interface (Decision Log D9); no experiment has been run yet to decide (see `experiments/runners/compare_gop_scorers.py`, not yet executed).
- **`PronunciationUnit.syllables` and `.note` have no owning stage.** No syllabifier and no pedagogical-note generator are designed anywhere in the Architecture Spec. `assemble_units` currently leaves both as empty placeholders (`[]`, `""`).

---

## Deferred to post-MVP (explicitly, not forgotten)

- **Branch 2 (free phone recognition, insertion/deletion detection)** — MVP scoped down to Branch 1 only (Decision Log D19). Depends on the canonicalizer bias diagnostic (see "Post-MVP, highest priority" above) before further investment.
- **Free-input edge case handling** — proper nouns, technical/borrowed vocabulary not covered by Lexique383 or the liaison rule engine. Accepted limitation for MVP (Decision Log D1, D4).
- **Progress tracking / attempt history** — mentioned in the original 5-stage sketch, never designed. Needs its own data model extension beyond `Attempt` (e.g. aggregating weak phonemes/units over time).
- **Backend API and frontend implementation** — structure is designed (Architecture Spec), no code written yet.
- **Supervised calibration** (replacing the unsupervised percentile/z-score approach, Decision Log D11) — deferred until there's real usage traction to justify the cost of expert-labeled French pronunciation data.
- **Alignment-free unified scoring (GOP-CTC-AF)** — explicitly deferred future upgrade path (Decision Log D9), not chosen for MVP due to compute scaling and lack of packaged implementation.
- **Paragraph-level practice** (multiple consecutive sentences, cross-sentence prosody/liaison) — came up when discussing the presentation-practice use case; free-input already supports practicing sentence-by-sentence, so this is a "nice to have" extension, not a blocker for that use case.

---

## Documentation / repo hygiene todos

- `docs/kaldi_setup.md` — referenced as TODO in the README, not written yet.
- `LICENSE` file — needs full FSL text with Change Date and Change License (Apache 2.0) filled in; README currently only links to it.
- Keep Architecture Spec as the source of truth when it and the README diverge (README updates lag by design — see Codebase Conventions).
- Dependency extras groups (`paulou[gop-kaldi]`, etc.) — not yet set up; worth doing before the TTS/Speech Assessment collaborator's setup depends on it.

---

## Collaboration

- Actively looking for a collaborator specifically for the **TTS and Speech Assessment** components. Relevant prep before they join: dependency extras separation (see above), and keeping PRs/decision log entries for those two stages especially well self-contained (see Codebase Conventions).
