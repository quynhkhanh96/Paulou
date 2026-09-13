# Tests

Companion to the project's Testing Conventions note — this README is a
per-test index (purpose + expected outcome), not a restatement of the
testing philosophy.

## How to run

```bash
cd paulou
pytest tests/unit -v                  # fast suite — pure functions + G2P dict lookup
pytest tests/model -v -m model        # slow suite — loads the real spaCy model (~seconds)
pytest tests/contract -v              # calls the real Gemini API — needs GEMINI_API_KEY
pytest tests/ -v                      # everything
```
`tests/unit/` holds Category 1 (pure functions, ordinary `pytest`
assertions) per the Testing Conventions note, plus `test_g2p.py`'s
dictionary-lookup tests (deterministic, no model loading). A few tests in
`test_g2p.py` call the real `espeak-ng` binary — a system dependency (`apt
install espeak-ng`), not a pip package — and are skipped automatically if
it isn't installed.

`tests/model/` holds Category 3 (requires loading a real trained model —
here, spaCy's `fr_core_news_sm`) per the Testing Conventions note. Marked
with `pytest.mark.model` (registered in `pytest.ini`) so it can be excluded
from the fast suite (`pytest tests/unit -m "not model"` or simply running
`tests/unit` alone, as above). Skipped automatically if spaCy or the model
isn't installed.

`tests/contract/` holds Category 2 (stochastic modules, checked via
invariants, not exact output) per the Testing Conventions note. Calls the
real Gemini API — needs `GEMINI_API_KEY` set (repo-root `.env`, see
`.env.example`) and costs quota; skipped automatically if the key isn't
set.

No `tests/api` or `tests/db` directories exist yet — no backend has been
built (build order step 3+ still in progress).

---

## `test_liaison_rules.py`

Tests `apply_liaison_rules` and `get_liaison_consonant` in
`stages/chunk_analyzer/liaison/rule_engine.py`.

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_obligatoire_determiner_noun` | Verify the textbook DET+NOUN obligatoire pattern ("les amis"). | `applies=True`, `consonant="z"`, `rule_type="obligatoire"`. |
| `test_interdite_before_h_aspire` | Verify a closed-list h-aspiré word ("héros") overrides an otherwise-matching DET+NOUN obligatoire pattern (Decision Log D21). | `applies=False`, `consonant=None`, `rule_type="interdite"`. |
| `test_interdite_after_et` | Verify the fixed grammar rule "liaison never occurs after et". | `applies=False`, `rule_type="interdite"`. |
| `test_interdite_subject_noun_before_verb` | Verify the (simplified, D22) subject-noun-before-verb interdite rule fires on POS adjacency alone. | `applies=False`, `rule_type="interdite"`. |
| `test_facultative_not_predicted` | Verify a pair matching no obligatoire/interdite rule ("pas encore") falls through to the facultative category, not silently defaulted to one of the other two. | `rule_type="facultative"` (`applies` is a placeholder `False`, not a real prediction). |
| `test_no_liaison_before_consonant_initial_word` | Verify liaison never triggers when the next word starts with an ordinary consonant, regardless of POS pattern. | `applies=False`, `consonant=None`, `rule_type="interdite"`. |
| `test_no_liaison_when_word_has_no_liaison_consonant` | Verify a word with no liaison-capable final consonant ("amie") never produces liaison, even before a vowel-initial word. | `applies=False`, `consonant=None`, `rule_type="interdite"`. |
| `test_pronoun_clitic_before_verb` | Verify the PRON+VERB obligatoire pattern ("nous avons"). | `applies=True`, `consonant="z"`, `rule_type="obligatoire"`. |
| `test_adjective_before_noun` | Verify the prenominal ADJ+NOUN obligatoire pattern ("petit ami"). | `applies=True`, `consonant="t"`. |
| `test_monosyllabic_preposition` | Verify the monosyllabic-preposition obligatoire pattern ("dans un"). | `applies=True`, `consonant="z"`. |
| `test_multiple_pairs_in_a_chunk` | Verify `apply_liaison_rules` returns exactly one decision per adjacent word pair for a longer, 3-word chunk ("les anciens amis"). | `len(result) == 2`; both decisions `rule_type="obligatoire"`. |
| `test_get_liaison_consonant_mapping` | Verify the raw final-letter → consonant table directly, independent of full rule logic. | `"les"→"z"`, `"grand"→"t"`, `"un"→"n"`, `"amie"→None`. |

---

## `test_unit_assembler.py`

Tests `assemble_units` in `stages/chunk_analyzer/assembly/unit_assembler.py`, using
synthetic `LiaisonDecision`s (per Testing Conventions — the assembler is
tested without needing the real rule engine).

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_all_single_words_when_no_liaison_applies` | Baseline: no liaison anywhere in the chunk. | 2 `single` units; `scoring_focus="phoneme_accuracy"`; `liaison_consonant=None`; IPA is each word's own phonemes joined. |
| `test_single_liaison_group_formed` | Basic pair-merge: one applying decision groups exactly 2 words. | 1 `liaison_group` unit; `words=["les","amis"]`; `ipa="lezami"`; `liaison_consonant="z"`; `scoring_focus="liaison_presence_and_continuity"`. |
| `test_mixed_single_and_liaison_group_in_one_chunk` | Verify the assembler correctly interleaves `single` and `liaison_group` units within one 4-word chunk. | `[u.type for u in units] == ["single", "liaison_group", "single"]`. |
| `test_consecutive_applicable_decisions_only_merge_first_pair` | Locks in the greedy left-to-right resolution for the unresolved consecutive-liaison edge case (Decision Log D23). | First pair merges into one `liaison_group`; the third word stands alone as `single` (second decision is not applied). |
| `test_single_word_input_with_no_decisions` | Degenerate case: one word, no decisions to process. | 1 `single` unit, no exception. |
| `test_unit_ids_are_sequential` | Verify the deterministic id scheme. | `ids == ["unit_0", "unit_1", "unit_2"]`. |
| `test_raises_on_mismatched_decision_count` | Guard against a real integration bug: decision count must match `len(words) - 1`. | Raises `ValueError`. |
| `test_elision_group_formed` | Verify basic elision fusion (added after the original design — see `elision.py`): an elided clitic ("l'") merges with the next word into its own unit type. | 1 `elision_group` unit; `words=["l'","ami"]`; `ipa="lami"`; `liaison_consonant=None`; `scoring_focus="elision_correctness"`. |
| `test_elision_overrides_possibly_wrong_g2p_phonemes` | Verify a real practical benefit: even if G2P produced the wrong phonemes for "l'" (per the confirmed eSpeak-ng bug — isolated "l'" mispronounced as the letter name "elle"), `assemble_units` ignores that and substitutes the correct closed-list phoneme. | `ipa == "lami"`, NOT `"ɛlami"`, even when the input phonemes for "l'" are the wrong `["ɛ","l"]`. |
| `test_elision_takes_priority_over_liaison_decision_at_same_position` | Defensively lock in the documented priority order: elision is checked before liaison at each position, using a synthetic (unrealistic) `LiaisonDecision` to prove it's ignored. | Result is still `elision_group`, `liaison_consonant=None` — the synthetic liaison decision has no effect. |
| `test_mixed_elision_single_and_liaison_group` | Verify elision and liaison grouping compose correctly in one 4-word sequence ("j'ai un ami"). | 2 units: `elision_group` (`["j'","ai"]`), then `liaison_group` (`["un","ami"]`, consonant `"n"`). |
| `test_elision_as_last_word_raises` | Guard against malformed input: an elided clitic with no following word to fuse with. | Raises `ValueError`. |

---

## `test_elision.py`

Tests `detect_elision` in `stages/chunk_analyzer/elision/elision.py` — a small closed-list
lookup, distinct from liaison and enchaînement (see that module's
docstring and the Glossary's "Elision" entry).

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_recognized_clitics` | Verify all 9 closed-list elided forms map to their correct phoneme. | `"l'"→["l"]`, `"d'"→["d"]`, `"j'"→["ʒ"]`, `"m'"→["m"]`, `"n'"→["n"]`, `"qu'"→["k"]`, `"s'"→["s"]`, `"t'"→["t"]`, `"c'"→["s"]`. |
| `test_case_insensitive` | Verify lookup normalizes case. | `"L'"→["l"]`, `"Qu'"→["k"]`. |
| `test_ordinary_word_returns_none` | Verify non-elided words (including the un-elided base form "le") don't match. | `None` for `"amis"` and `"le"`. |
| `test_word_kept_whole_by_tokenizer_returns_none` | Verify a word that happens to contain an apostrophe but isn't an elided clitic ("aujourd'hui", confirmed NOT split by spaCy's tokenizer) doesn't false-positive. | `None`. |
| `test_typographic_apostrophe_does_not_match` | Verify only the straight ASCII apostrophe (U+0027) is recognized, matching what spaCy's tokenizer actually produces — not the typographic U+2019. | `None` for `"l’"` (U+2019). |

---

## `test_calibration.py`

Tests `calibrate_score` and `PhoneStats` in
`stages/speech_assessment/calibration.py`, using synthetic stats tables
(no real French corpus data exists yet — see Decision Log D24).

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_raw_gop_equal_to_mean_gives_score_50` | Verify the z-score/CDF formula at its center point (`z=0`). | `score == 50`. |
| `test_raw_gop_far_below_mean_gives_low_score` | Verify a native-atypical (poor) pronunciation yields a low score. | `score < 5`. |
| `test_raw_gop_far_above_mean_gives_high_score` | Verify a very native-like pronunciation yields a high score. | `score > 95`. |
| `test_score_is_clamped_to_0_100_range` | Verify the final score is always clamped to `[0, 100]`, even for extreme raw GOP values. | `high == 100`, `low == 0`. |
| `test_missing_phone_with_no_fallback_raises` | Verify the function fails loudly rather than guessing when a phone has no stats and no fallback. | Raises `ValueError`. |
| `test_undersampled_phone_falls_back_to_broader_class` | Verify the D11 fallback-to-broader-phone-class mechanism actually uses the fallback's stats, not the undersampled phone's own. | Score computed from the fallback class's mean (`0.0`), i.e. `50` — not from the undersampled phone's own mean (`-5.0`). |
| `test_undersampled_phone_without_fallback_uses_its_own_stats_anyway` | Verify the soft-degradation policy: use what data exists rather than hard-failing when there's no better option. | Score computed from the phone's own (undersampled) stats. |
| `test_zero_std_does_not_crash` | Guard against division-by-zero on a degenerate (`std=0`) distribution. | `z` forced to `0.0`; `score == 50`; no exception. |

---

## `test_feedback_templates.py`

Tests `generate_feedback` in `stages/speech_assessment/feedback.py`.
MVP-scoped to `single` units only (Decision Log D19).

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_high_score_gives_good_pronunciation_template` | Verify top-tier (85–100) template selection. | `"Good pronunciation!"` |
| `test_mid_score_names_the_weakest_phone` | Verify mid-tier (60–84) template + `[X]` placeholder substitution. | `"Close, watch the ʁ sound"` |
| `test_low_score_names_the_weakest_phone` | Verify low-tier (<60) template + `[X]` placeholder substitution. | `"The ʁ sound needs work, try the slow sample"` |
| `test_boundary_score_85_is_good_pronunciation` | Verify the 85 boundary is inclusive on the high tier, matching the spec's "85–100" range. | `"Good pronunciation!"` |
| `test_boundary_score_59_is_low_tier` | Verify 59 is correctly assigned to the <60 tier, not the 60–84 tier. | Result contains `"needs work"`. |
| `test_liaison_group_raises_not_implemented` | Verify the MVP scoping (D19) is enforced in code, not just documentation — liaison feedback can't silently return a bogus string. | Raises `NotImplementedError`. |
| `test_single_unit_without_phone_scores_raises` | Verify the function can't produce an `[X]` template with no phone to name. | Raises `ValueError`. |
| `test_unknown_unit_type_raises` | Defensive input validation for an invalid `unit_type`. | Raises `ValueError`. |

---

## `test_g2p.py`

Tests `LexiqueEspeakG2P`, `_load_lexicon`, and `_parse_espeak_ipa` in
`stages/chunk_analyzer/g2p/lexique_espeak.py`. Uses the fixture lexicon
`tests/fixtures/g2p_golden.tsv` (a small hand-picked dictionary, NOT the
real Lexique383 database — see that module's docstring). Tests calling the
real `espeak-ng` binary are marked and skipped if it isn't installed.

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_dict_lookup_returns_source_dict` | Verify a word present in the fixture lexicon is returned from the dictionary, not eSpeak. | `phonemes == ["b","ɔ̃","ʒ","u","ʁ"]`, `source == "dict"`. |
| `test_dict_lookup_is_case_insensitive` | Verify lookup normalizes case ("Bonjour" matches "bonjour"). | Same result as the lowercase lookup, `source == "dict"`. |
| `test_load_lexicon_raises_on_malformed_line` | Verify a lexicon file line missing the expected tab-separated format fails loudly instead of silently mis-parsing. | Raises `ValueError`. |
| `test_missing_lexicon_file_raises` | Verify a nonexistent lexicon path fails clearly at construction time. | Raises `FileNotFoundError`. |
| `test_parse_espeak_ipa_simple_word` | Verify the parser splits a clean underscore-separated eSpeak string correctly (canned string, no binary needed). | `"b_ɔ̃_ʒ_ˈu_ʁ" -> ["b","ɔ̃","ʒ","u","ʁ"]`. |
| `test_parse_espeak_ipa_strips_leading_empty_token` | Verify a leading `_` (producing an empty first token, observed on words like "onze") doesn't leak an empty string into the output. | `"_ˈɔ̃_z" -> ["ɔ̃","z"]`. |
| `test_parse_espeak_ipa_strips_trailing_hyphen` | Verify a stray trailing `-` (a liaison hint, observed on words like "les") is stripped, not treated as part of a phoneme. | `"l_ˈe-" -> ["l","e"]`. |
| `test_parse_espeak_ipa_single_phoneme_word` | Verify a word with no underscores at all (single phoneme) still parses correctly. | `"ˈœ̃" -> ["œ̃"]`. |
| `test_fallback_to_espeak_for_unknown_word` *(requires espeak-ng)* | Verify a word absent from the fixture lexicon falls back to eSpeak-ng rather than failing. | `source == "espeak"`, non-empty phoneme list. |
| `test_espeak_fallback_output_has_no_stress_marks` *(requires espeak-ng)* | Verify stress marks (ˈ, ˌ) from eSpeak's isolated-word synthesis are stripped — they'd be linguistically wrong at the chunk level (French stress is rhythmic-group-level, not lexical). | No phoneme contains `ˈ` or `ˌ`. |
| `test_espeak_fallback_never_raises_for_unknown_word` *(requires espeak-ng)* | Verify the Codebase Conventions contract: `phonemize()` must never raise for "word not found" — falling back is the designed behavior, not an error path. | `source == "espeak"`, non-empty phoneme list, no exception. |
| `test_espeak_not_found_gives_actionable_error` | Regression test for a real crash found via user testing: on a machine without `espeak-ng` on PATH (confirmed on Windows), the raw `FileNotFoundError` surfaced as a cryptic `[WinError 2]` with no indication of what was missing. Uses `monkeypatch` to simulate this without needing an actual missing binary. | Raises `RuntimeError` with a message containing "espeak-ng executable not found". |
| `test_from_lexique400_loads_known_words` *(requires `paulou/data/Lexique400.tsv`, git-ignored)* | Verify the real Lexique400 loader (Decision Log D30) returns correct phonemes for a known word. | `"bonjour" → ["b","ɔ̃","ʒ","u","ʁ"]`, `source == "dict"`. |
| `test_from_lexique400_nasal_vowel_is_one_phoneme` *(requires Lexique400.tsv)* | Verify the combining-mark segmentation (base char + combining tilde = one phoneme), empirically validated against Lexique400's own ASCII phonetic column across all 189,863 rows. | `"avons" → ["a","v","ɔ̃"]`; last phoneme is 2 codepoints, 1 phoneme. |
| `test_from_lexique400_has_substantial_coverage` *(requires Lexique400.tsv)* | Sanity check that the real database loaded, not an empty/truncated file. | Lexicon has over 100,000 entries. |
| `test_from_lexique400_elided_clitics_are_real_dictionary_entries` *(requires Lexique400.tsv)* | Verify Lexique400 has its own entries for elided clitics ("l'", "d'", etc.) — confirmed to match `ELIDED_CLITICS` in `elision.py` exactly — so the eSpeak fallback (which mishandles these, see elision.py) is never reached for them via this path. | `"l'" → source="dict"`, `phonemes == ["l"]`. |

---

## `test_pos_tagger.py` (`tests/model/`)

Tests `tag_sentence` in `stages/chunk_analyzer/pos/spacy_tagger.py`. Requires the real
`fr_core_news_sm` spaCy model to be installed — skipped automatically
otherwise. Marked `pytest.mark.model` (Category 3 — loads a real trained
model).

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_determiner_noun` | Verify correct tagging of the DET+NOUN liaison example used throughout the liaison rule engine tests. | `[("les","DET"), ("amis","NOUN")]`. |
| `test_pronoun_verb` | Verify correct tagging of the PRON+VERB liaison example. | `[("nous","PRON"), ("avons","VERB")]`. |
| `test_adjective_noun` | Verify correct tagging of the ADJ+NOUN liaison example. | `[("petit","ADJ"), ("ami","NOUN")]`. |
| `test_liaison_chain_sentence` | Verify correct tagging of the 3-word consecutive-liaison example ("les anciens amis"). | `[("les","DET"), ("anciens","ADJ"), ("amis","NOUN")]`. |
| `test_facultative_example_sentence` | Verify correct tagging of the facultative liaison example ("pas encore"). | `[("pas","ADV"), ("encore","ADV")]`. |
| `test_subject_noun_verb_requires_full_sentence_context` | Documents an empirically verified gotcha: the same words tagged as an isolated 2-word fragment vs. embedded in a real sentence give different results — tagging must always be done on the full sentence, never on fragments assembled elsewhere. | Fragment `"enfant arrive"` mistags "arrive" as `ADJ`; full sentence `"Mon enfant arrive demain."` correctly tags it `VERB`. |
| `test_known_limitation_content_mistagged_as_adverb` | Regression-locking test for a known model limitation: "content" (adjective) is reproducibly mistagged as `ADV` even in a full, correct sentence, which would cause the rule engine's "très/trop + ADJ" obligatoire pattern to miss real liaison on this word. If this test ever fails, that means the model improved — update the docstring/decision log note when it does. | `"Il est trop content de venir."` tags "content" as `ADV`. |

---

## `test_chunk_analyzer.py` (`tests/model/`)

Tests `analyze_chunk` in `stages/chunk_analyzer/chunk_analyzer.py` — the
orchestration function composing POS tagging, liaison rules, G2P, and unit
assembly (Architecture Spec, stage 2). Requires the real `fr_core_news_sm`
model (via `tag_sentence`) — skipped automatically otherwise. Uses a
deterministic `_StubG2P` (defined in the test file) instead of the real
`LexiqueEspeakG2P`, to isolate this orchestration logic from real G2P
behavior — G2P's own quirks (including the confirmed eSpeak-ng elision bug)
are already covered separately in `test_g2p.py` and `test_unit_assembler.py`.

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_les_amis_arrivent_demain` | The worked example from the original chunk-analyzer design discussion — verifies the full pipeline end-to-end matches the manually-derived expected grouping. | 3 units: `liaison_group` (`["les","amis"]`, consonant `"z"`), `single` (`["arrivent"]`), `single` (`["demain"]`). |
| `test_elision_end_to_end` | Verify elision fusion works through the full orchestration, including that `assemble_units` still overrides the stub's deliberately-wrong phonemes for "l'" (mirroring the real eSpeak-ng bug). | 2 units: `elision_group` (`["l'","ami"]`, `ipa="lami"` — not `"ɛlami"`), `single` (`["arrive"]`). |
| `test_punctuation_is_filtered_out` | Verify PUNCT tokens (e.g. a comma) never produce a bogus unit or appear in any unit's `words`. | No unit contains `","`. |
| `test_empty_chunk_returns_empty_list` | Verify the empty-input edge case doesn't crash. | `analyze_chunk("", g2p) == []`. |
| `test_single_word_chunk` | Verify the degenerate one-word-chunk case (no adjacent pairs to evaluate). | 1 `single` unit. |

---

## `test_chunking_invariants.py` (`tests/contract/`)

Tests `GeminiSentenceParser` in `stages/parsing/gemini_parser.py`. Calls
the real Gemini API — requires `GEMINI_API_KEY` (repo-root `.env`),
skipped automatically otherwise. Per Testing Conventions, chunking is
stochastic (LLM-based), so these check invariants that must always hold —
NOT exact expected chunk boundaries.

**Not run/verified by the assistant that wrote this code** — no network
access to the Gemini API from that environment. Run this yourself once
`GEMINI_API_KEY` is set; if it fails on `interaction.output_text`, see the
alternative noted in `gemini_parser.py`'s docstring.

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_chunking_preserves_all_text` (parametrized, 4 sentences) | Verify no text is lost or added when a sentence is split into chunks, and no chunk is empty — the core invariant any chunking implementation must satisfy regardless of *where* it draws the boundaries. | Chunks are non-empty; whitespace/case-normalized, concatenated chunks equal the original sentence. |
| `test_chunking_returns_a_list_of_strings` | Verify the structured-output JSON parses into the expected Python shape (`list[str]`), catching a malformed schema response early. | `isinstance(chunks, list)` and every element is a `str`. |