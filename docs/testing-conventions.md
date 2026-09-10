# Paulou — Testing Conventions

How testing is organized across the codebase. Companion to the Architecture Spec (stage definitions) and Decision Log (D16 covers the tests/ vs. experiments/ split at a high level — this note is the detailed version).

---

## Core principle: match the test strategy to the module's nature

Every module in the pipeline is either:
- **Pure / deterministic** — same input always gives the same output. Testable with ordinary assertions.
- **Stochastic / model-based** — output can vary (LLM calls) or depends on a trained model's behavior (GOP scorer, free-phone recognizer). Cannot be tested with exact-output assertions; needs a different approach per category below.

Trying to force exact-match assertions onto a stochastic module produces flaky tests that fail for the wrong reasons. Trying to skip testing a stochastic module entirely leaves real regressions undetected. The categories below exist to avoid both failure modes.

---

## The four categories

### 1. Unit tests — pure functions
**What goes here:** liaison rule engine, unit assembly, Levenshtein alignment, merge, calibration, feedback templating.
**How to test:** ordinary `pytest` assertions against fixed input/output pairs.
**Speed:** fast, no external dependencies (no model loading, no network) — runs on every commit.

```python
# tests/unit/test_liaison_rules.py
def test_obligatoire_determiner_noun():
    result = apply_liaison_rules([("les", "DET"), ("amis", "NOUN")])
    assert result[0].applies is True
    assert result[0].consonant == "z"

def test_interdite_before_h_aspire():
    result = apply_liaison_rules([("les", "DET"), ("héros", "NOUN")])
    assert result[0].applies is False
```

### 2. Contract tests — stochastic modules, checked via invariants
**What goes here:** sentence chunking (LLM-based), pronunciation unit assembly (checked against liaison decisions).
**How to test:** not "is the output correct" (unanswerable with a fixed assertion for an LLM call) but "does the output satisfy properties that must always hold, regardless of what the LLM returned."

```python
# tests/contract/test_chunking_invariants.py
def test_chunking_preserves_all_text(sentence):
    chunks = parser.parse(sentence)
    assert normalize("".join(chunks)) == normalize(sentence)  # no text lost or added
    assert len(chunks) >= 1
    assert all(chunk.strip() for chunk in chunks)              # no empty chunks
```

**What this catches:** malformed LLM output, silently dropped/added text, empty chunks. **What this does NOT catch:** whether the chunking is *linguistically good* (that's category 4, qualitative review).

**Also applies to swappable model-backed stages via a shared contract:** if two implementations both satisfy `GOPScorer`, they should both pass the same contract test (e.g. "native pronunciation scores higher than a substitution error") regardless of which one is active. This is what lets `KaldiGOPScorer` and `GopFtScorer` be swapped via config without silently breaking a basic correctness expectation.

```python
# tests/contract/test_gop_scorer_contract.py
@pytest.mark.parametrize("scorer_key", ["kaldi", "gopft"])
def test_native_scores_higher_than_substitution(scorer_key, diagnostic_set):
    scorer = build("gop_scorer", scorer_key)
    native_score = scorer.score(diagnostic_set["native"], canonical_phonemes)
    subst_score = scorer.score(diagnostic_set["substitution"], canonical_phonemes)
    assert avg(native_score) > avg(subst_score)
```

### 3. Model tests — require loading real models/audio
**What goes here:** GOP scorer ranking behavior, free-phone recognizer diagnostic checks (including the canonicalizer bias check — see Decision Log D10).
**How to test:** run against the diagnostic audio set (native / substitution / deletion / insertion recordings), assert expected *directional* behavior (e.g. ranking, not exact scores).
**Speed:** slow — requires loading acoustic models. Marked separately so they don't block fast iteration.

```python
# tests/model/test_free_decode_canonicalizer_bias.py
@pytest.mark.model
def test_deletion_is_detected_not_corrected(diagnostic_set):
    decoded, _ = recognizer.decode(diagnostic_set["deletion"]["deux_amis_no_liaison"])
    assert "z" not in decoded  # model should NOT hallucinate the missing liaison
```

Use `pytest.mark.slow` or `pytest.mark.model` to separate these from the fast suite:
```bash
pytest tests/unit tests/contract          # fast — every commit
pytest tests/model                        # slow — run separately, needs models loaded
```

### 4. Qualitative review — notebooks, human judgment
**What goes here:** chunking quality (is this split linguistically sensible?), G2P fallback quality (does the eSpeak-predicted IPA sound right?), TTS slicing (does the cut audio sound natural?), GOP alignment visualization (does the forced-align timing look right against the waveform?).
**How to review:** Jupyter notebooks under `experiments/notebooks/`, using `IPython.display.Audio` for playback, waveform/TextGrid overlays for alignment, and side-by-side tables for comparing candidate outputs.
**Not part of CI.** These are decision-support tools for a human, not automated checks.

**On LLM-as-judge as a supplement:** for chunking quality specifically, a second LLM call can score chunking output against a rubric, to monitor drift over time between human reviews. This is a heuristic proxy only — the judge model can itself be wrong — and does not replace periodic human review.

---

## Directory layout

```
tests/
  fixtures/
    g2p_golden.tsv                # word → hand-verified IPA
    liaison_rules_cases.json      # test cases per rule (obligatoire/interdite/facultative)
    chunking_eval_sentences.json  # curated sentences for chunking review
    diagnostic_audio/             # shared by model tests AND experiments — see below
      native/*.wav
      substitution/*.wav
      deletion/*.wav
      insertion/*.wav
      metadata.json               # maps file → expected phoneme, perturbation type
  unit/
    test_liaison_rules.py
    test_alignment.py
    test_merge.py
    test_calibration.py
    test_feedback_templates.py
  contract/
    test_chunking_invariants.py
    test_pronunciation_unit_assembly.py
    test_gop_scorer_contract.py
    test_tts_provider_contract.py
  model/
    test_gop_ranking.py
    test_free_decode_canonicalizer_bias.py
  api/                             # once backend exists
    test_sentences_endpoint.py     # uses TestClient, mocks PaulouPipeline
    test_attempts_endpoint.py
  db/                              # once backend exists
    test_repository.py             # SQLite in-memory or test container
```

**API/DB test principle:** mock `PaulouPipeline` rather than running it for real. The interface-based design (Decision Log D12) makes this straightforward. This keeps API tests fast and keeps "is the pipeline correct" (owned by unit/contract/model tests) separate from "does the API wire things together correctly."

---

## The diagnostic audio set — shared fixture, used by both tests/ and experiments/

The native/substitution/deletion/insertion recordings (Decision Log D10, "highest priority validation task") serve two purposes:
- **In `tests/model/`:** ongoing regression checks (e.g. "does the currently-configured GOP scorer still rank native > substitution?")
- **In `experiments/`:** one-time or periodic comparative evaluation (e.g. "which GOP implementation ranks better, Kaldi or gop-ft?")

**Must be version-pinned** (hash or tag) so that a comparison run today and one run in three months are evaluated against the same data — otherwise "did the model get better" and "did the test data change" become indistinguishable.

---

## What NOT to do

- Don't write exact-match unit tests for LLM output (chunking text, feedback wording) — write contract/invariant tests instead.
- Don't put notebooks in `tests/` — they're not CI-checkable and belong in `experiments/notebooks/` (see Decision Log D16).
- Don't skip testing a stochastic module just because it can't be exact-match tested — use the contract test category instead of skipping entirely.
- Don't let `tests/model/` run in the default fast test command — it needs explicit invocation since it loads real models.
