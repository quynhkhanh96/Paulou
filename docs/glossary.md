# Paulou — Glossary

Reference for terms used throughout the other notes (Decision Log, Architecture Spec, Testing Conventions, Roadmap). Grouped by domain. Add new terms here as they come up rather than re-explaining them inline in other notes.

---

## French linguistics

- **Groupe rythmique (rhythmic group)** — the natural prosodic unit French is spoken in; roughly, a phrase pronounced as one breath/rhythm group. Paulou's chunking (Sentence Parser stage) splits sentences along these boundaries, not punctuation.
- **Accent tonique (rhythmic/tonic stress)** — in French, stress falls on the *last syllable of the rhythmic group*, not on a fixed syllable within each individual word (unlike English lexical stress). This is why `Chunk.stress_syllable` is a property of the chunk, not of each word.
- **Liaison** — the pronunciation of an otherwise-silent word-final consonant when the next word begins with a vowel sound, e.g. *les amis* → /le.z‿a.mi/ (the /z/ is not part of "les" on its own). Categorized as:
  - **Obligatoire** — liaison must occur (e.g. determiner + noun).
  - **Interdite** — liaison must never occur (e.g. after "et", before h-aspiré words).
  - **Facultative** — liaison is optional/style-dependent; Paulou doesn't predict a single "correct" answer here (see Decision Log D4) and accepts either variant.
- **Elision** — the dropping of a word's final vowel before a following vowel-initial word, marked orthographically with an apostrophe. Limited to a small closed set of French function words: *le/la, de, je, me, te, se, ne, que, ce* → *l', d', j', m', t', s', n', qu', c'* (e.g. *l'ami* /l‿a.mi/). Distinct from liaison: no consonant is added, only a vowel is removed; and it's not a "decision" the way liaison is — seeing the elided form in text is itself proof the fusion already happened. Mutually exclusive with liaison on the same word (elidable words end in a vowel, so there's no final consonant for liaison to act on). See Decision Log D28.
- **Enchaînement** — related but distinct from liaison: the resyllabification of an *already-pronounced* final consonant onto the next word's vowel-initial syllable (e.g. *elle arrive* → /ɛ.la.ʁiv/), rather than a normally-silent letter becoming pronounced. Paulou's current liaison modeling focuses on liaison specifically; enchaînement is linguistically adjacent but not separately modeled as of now.
- **H-aspiré (aspirated h)** — a class of French words starting with "h" that behave as if they start with a consonant for liaison purposes (blocking liaison) even though the "h" itself is silent, e.g. "les héros" has no liaison. Handled in the rule engine as a closed list, not a general rule.
- **Schwa** — the neutral/mute "e" sound (/ə/), often dropped in casual speech (e.g. "je" → /ʒ/ alone). Noted in pronunciation guidance as a common area of learner confusion.
- **Resyllabification** — the underlying phonological mechanism behind liaison: a consonant "moves" to become the onset of the following syllable rather than staying attached to its original word. This is the linguistic justification for modeling liaison as one unit (`liaison_group`) instead of two separate words (Decision Log D3).

---

## Speech technology / ML

- **GOP (Goodness of Pronunciation)** — a scoring method that compares how likely the audio is to match the *expected* (canonical) phoneme versus the *most likely* phoneme at each position, via forced alignment. `GOP = log P(canonical) − log P(best_match)`. Good at detecting substitution errors; structurally blind to insertion/deletion (see Architecture Spec, stage 5a).
- **Forced alignment** — aligning audio to a known, fixed phoneme sequence (the reference/canonical pronunciation), determining where each expected phone occurs in time. Unlike free decoding, it assumes the reference sequence is correct and just finds timing — it cannot detect that a phone is missing or extra.
- **Free phone recognition** — phone-level speech recognition *without* being constrained to a reference sequence; the decoder proposes whatever phones it thinks it hears, in whatever quantity. Used in Paulou's Branch 2 specifically because it can reveal insertion/deletion (unlike forced-align GOP).
- **CTC (Connectionist Temporal Classification)** — a training/decoding method for sequence models (like the wav2vec2-based free-phone recognizer) that doesn't require pre-aligned input/output pairs; naturally suited to free (unconstrained) decoding.
- **PER (Phone Error Rate)** — a standard ASR metric measuring how often decoded phones differ from ground truth on normal speech. Important caveat noted in the Decision Log (D10): a low PER measures recognition accuracy, not error-*detection* sensitivity on learner/mispronounced speech — these are different questions.
- **MDD (Mispronunciation Detection and Diagnosis)** — the research field concerned with detecting and diagnosing learner pronunciation errors (as opposed to general ASR, which aims to recognize the intended word regardless of accent). The canonicalizer bias risk (D10) is a known failure mode specifically discussed in this literature.
- **Canonicalizer bias** — the risk that a speech recognition model, trained to be invariant to pronunciation variation (standard ASR goal), "corrects" a learner's actual (possibly incorrect) pronunciation back toward the canonical form during decoding — the opposite of what's needed for pronunciation assessment, which needs sensitivity to deviation. See Decision Log D10 for Paulou's specific unverified risk here.
- **Levenshtein alignment** — classic edit-distance-based sequence alignment, used here to compare the free-decoder's output phone sequence against the canonical phoneme sequence and classify differences as deletions (DEL) or insertions (INS).
- **Percentile / z-score calibration** — converting a raw score (here, raw GOP value) to a normalized 0–100 scale by comparing it to the distribution of that score observed in a reference corpus (native speakers), via `z = (raw − mean) / std` then mapping through the normal CDF. Chosen over supervised regression due to lack of labeled French mispronunciation data (Decision Log D11).
- **Alignment-free GOP (GOP-CTC-AF)** — a more recent scoring approach (Cao et al., Interspeech 2024) that marginalizes over all possible CTC alignments to catch substitution, deletion, and insertion errors in one unified formula, instead of needing two separate branches. Considered but deferred for Paulou's MVP (Decision Log D9) due to compute cost and lack of a packaged implementation.

---

## Paulou-specific terms

- **PronunciationUnit** — the atomic unit of practice and scoring in Paulou; a `single` word, a `liaison_group` (2 words joined by liaison), or an `elision_group` (2 words joined by elision). See Architecture Spec for full schema.
- **Chunk** — a rhythmic-group-sized piece of a sentence, containing one or more `PronunciationUnit`s. The intermediate level between a full sentence and individual pronunciation units.
- **scoring_focus** — a field on `PronunciationUnit` indicating which kind of error the unit is scored for: `phoneme_accuracy` (substitution-style scoring, for `single` units), `liaison_presence_and_continuity` (does the liaison sound exist and is it not awkwardly paused, for `liaison_group` units), or `elision_correctness` (for `elision_group` units).
- **Branch 1 / Branch 2** — shorthand used throughout the notes for the two parallel Speech Assessment paths: Branch 1 = GOP/forced-align (substitution detection), Branch 2 = free phone recognition (insertion/deletion detection). See Architecture Spec, stage 5. Superseded by Decision Log D36 — kept here only to help read older Decision Log entries (D9, D10, D19, D20, D33–D35) that predate the single-pipeline design.

---

## Tools / models referenced

- **Lexique383** — open French lexical/phonetic database, primary source for word-level phoneme lookup (G2P).
- **eSpeak NG** — open-source text-to-speech/G2P engine, used as the fallback when a word isn't in Lexique383 (rare words, proper nouns).
- **Kaldi** — a widely used open-source speech recognition toolkit; here specifically its GOP-DNN recipe for pronunciation scoring.
- **fr_kaldi-rhasspy** — an open, community-maintained French acoustic model for Kaldi (trained on Common Voice + M-AILabs + Voxforge, WER 3.23%), a candidate base for the GOP scorer.
- **gop-ft** — a PyTorch reimplementation (by JazminVidal) of the Kaldi GOP-DNN formula, easier to deploy than raw Kaldi but requires converting a Kaldi acoustic model to use it, and needs separate score-scale calibration (Decision Log D9).
- **Cnam-LMSSC/wav2vec2-french-phonemizer** — a HuggingFace model (MIT license), wav2vec2-based, fine-tuned for direct French IPA output via CTC; the candidate model for Branch 2 (free phone recognition).
- **Azure Pronunciation Assessment** — Microsoft's commercial pronunciation-scoring API; evaluated and rejected as Paulou's core scoring engine due to lack of custom phoneme control and limited `fr-FR` feature support (Decision Log D8).
- **speechocean762** — a publicly available English pronunciation dataset with expert phone-level labels, used to train supervised GOP calibration models. No French equivalent exists, which is part of why Paulou uses unsupervised calibration for now (Decision Log D11).