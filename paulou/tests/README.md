# Tests

Companion to the project's Testing Conventions note — this README is a
per-test index (purpose + expected outcome), not a restatement of the
testing philosophy.

## How to run

```bash
cd paulou
pytest tests/unit -v                  # fast suite — pure functions + G2P dict lookup
pytest tests/model -v -m model        # slow suite — loads the real spaCy model (~seconds)
pytest tests/contract -v --ignore=tests/contract/test_edge_tts_provider_contract.py
pytest tests/ -v --ignore=tests/contract/test_edge_tts_provider_contract.py  # everything else
```
`tests/unit/` holds Category 1 (pure functions, ordinary `pytest`
assertions) per the Testing Conventions note, plus `test_g2p.py`'s
dictionary-lookup tests, `test_tts_caching.py` (fully deterministic, no
real network), and `test_audio_slicing.py`. A few tests call real system
binaries — `espeak-ng` (`test_g2p.py`) and `ffmpeg`/`avconv`
(`test_audio_slicing.py`) — neither a pip package, and are skipped
automatically if missing.

`tests/model/` holds Category 3 (requires loading a real trained model —
here, spaCy's `fr_core_news_sm`) per the Testing Conventions note. Marked
with `pytest.mark.model` (registered in `pytest.ini`) so it can be excluded
from the fast suite (`pytest tests/unit -m "not model"` or simply running
`tests/unit` alone, as above). Skipped automatically if spaCy or the model
isn't installed.

`tests/contract/` holds Category 2 (stochastic modules, checked via
invariants, not exact output) per the Testing Conventions note. Calls the
real Gemini and Azure APIs — needs `GEMINI_API_KEY` and/or
`AZURE_SPEECH_KEY`/`AZURE_SPEECH_REGION` set (repo-root `.env`, see
`.env.example`) and costs quota; skipped automatically if the relevant
credential isn't set. `test_edge_tts_provider_contract.py` is the
exception — no credential needed, so run it separately (see its own
section below for why it isn't included in the routine commands above).

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
REDESIGNED (Decision Log D32) to group phones by score bracket and
produce multiple sentences instead of one, and to apply uniformly to
every unit type — no more `unit_type` parameter or `liaison_group`
special-casing (see that module's docstring for the D19 implications).

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_all_good_phones_singular` | Verify singular phrasing when exactly one phone lands in a bracket. | `"Overall: great job! Good pronunciation on the a sound!"` |
| `test_all_good_phones_plural` | Verify plural phrasing when 2+ phones land in the same bracket. | `"...Good pronunciation on these sounds: a, m!"` |
| `test_mixed_brackets_produce_multiple_sentences` | Verify a unit with phones spread across all three brackets produces one sentence per bracket, in order (overall, good, close, needs-work). | Full 4-sentence string, exact match. |
| `test_close_bracket_plural` | Verify plural phrasing for the 60–84 bracket specifically. | Contains `"Close, watch these sounds: ʁ, ø."` |
| `test_needs_work_bracket_plural` | Verify plural phrasing for the 0–59 bracket specifically. | Contains `"These sounds need work, try the slow sample: t, d."` |
| `test_empty_brackets_are_skipped` | Verify a unit with phones in only one bracket doesn't emit empty/templated text for the other two. | No `"Close"` or `"needs work"` substring present. |
| `test_overall_sentence_boundaries` | Verify the overall-score bracket boundaries (85, 84, 60, 59, 0) each map to the correct sentence. | Each score's result starts with the expected overall sentence. |
| `test_empty_phone_scores_raises` | Verify the function can't run with nothing to group. | Raises `ValueError`. |
| `test_out_of_range_calibrated_score_raises` | Defensive validation for `calibrated_score` outside 0–100. | Raises `ValueError` for both `101` and `-1`. |
| `test_works_uniformly_regardless_of_unit_type` | Verify the function works identically for what would be a `liaison_group`'s phone_scores — no special-casing or rejection. | Correct mixed-bracket sentences, same as any other unit. |

---

## `test_phoneme_grouping.py`

Tests `group_phone_scores_by_unit` in
`stages/speech_assessment/phoneme_grouping.py` (Architecture Spec stage
5a-2, Decision Log D20) — using directly-constructed `PronunciationUnit`s
and simulated `PhoneScore`s (Stage A of the GOP scorer work: no real
GOP/Kaldi/gop-ft yet, see the design discussion).

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_groups_single_units_correctly` | Verify a flat score list splits correctly across two `single` units by phoneme count. | Each unit's group contains exactly its own phones, in order. |
| `test_groups_liaison_unit_including_consonant` | Verify the liaison consonant (included as its own element in `phonemes`, per core/models.py) is correctly counted and included in the group. | 6-phone liaison unit gets all 6 scores. |
| `test_multiple_units_various_types_preserve_order` | Verify grouping works across mixed unit types (elision_group + single) in one chunk, preserving order. | Correct per-unit slices in the right order. |
| `test_raises_on_count_mismatch` | Guard against a real integration bug: total phoneme count across units must match the flat score list length. | Raises `ValueError`. |
| `test_empty_units_and_scores` | Degenerate case: nothing to group. | Returns `{}`, no crash. |

---

## `test_merge.py`

Tests `merge_to_unit_result` in `stages/speech_assessment/merge.py`
(Architecture Spec stage 5e, Decision Log D33) — MEAN aggregation of a
unit's phone scores into its `UnitResult`, using simulated `PhoneScore`
data (Stage A, same reasoning as `test_phoneme_grouping.py`).

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_mean_aggregation_not_min` | Verify the D33 choice (MEAN, not MIN) is actually what's implemented, not just documented. | `(90+70+40)/3 = 66.67` rounds to `67`, not `40`. |
| `test_mean_rounds_to_nearest_int` | Flags a real gotcha: Python's `round()` uses round-half-to-even ("banker's rounding"), not always-round-up. | `80.5` rounds to `80`, not `81`. |
| `test_single_phone_unit_score_equals_that_phone` | Sanity check for the trivial one-phone case. | `calibrated_score` equals that phone's own score exactly. |
| `test_feedback_text_matches_generate_feedback_output` | Verify `merge_to_unit_result` calls `generate_feedback` with the right arguments, not a divergent inline copy of the same logic. | `result.feedback_text` equals calling `generate_feedback` directly with the same score/phones. |
| `test_unit_id_and_phone_scores_pass_through_unchanged` | Verify `UnitResult.unit_id` and `.phone_scores` are passed through faithfully. | Exact match to what was passed in. |
| `test_raises_on_empty_phone_scores` | Guard against merging a unit with nothing to aggregate. | Raises `ValueError`. |
| `test_works_for_liaison_group_phone_scores_too` | Verify no unit-type special-casing exists here either (Decision Log D19/D32) — a liaison_group's phone_scores merge exactly the same way as any other unit's. | Correct MEAN score; feedback names the weak phone. |

---

## `test_speech_assessment.py`

Tests `score_chunk` in `stages/speech_assessment/speech_assessment.py` —
the full stage-5 orchestration (GOP → calibration → grouping → merge),
using a deterministic `_StubGOPScorer` (Stage A: no real GOP model yet —
Kaldi/gop-ft is Stage B). `raw_gop_by_phone` lets each test fully control
what raw score each phoneme gets, so results through calibration are
predictable; `STATS` gives every test phone a mean=0/std=1 native
distribution, matching `test_calibration.py`'s own baseline case
(raw_gop=0.0 → calibrated_score=50).

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_single_unit_scored_correctly` | Verify the full pipeline produces a correct `UnitResult` for a basic one-unit chunk. | `calibrated_score == 50`; `phone_scores` in the right order. |
| `test_multiple_units_each_get_their_own_result` | Verify a chunk with 2 units (single + liaison_group) produces 2 separate `UnitResult`s with correctly-grouped phone_scores. | Each result's `unit_id` and `phone_scores` match its own unit. |
| `test_liaison_group_scored_same_way_as_single` | Verify no unit_type special-casing anywhere in this flow (D19/D32/D33) — a liaison_group with one bad and one great phone gets the same kind of mixed feedback a single unit would. | Feedback names both the weak and the strong phone. |
| `test_raw_gop_flows_through_calibration_correctly` | End-to-end check that a raw GOP value genuinely flows through `calibrate_score` (not bypassed or hardcoded). | A raw_gop far above the native mean calibrates to a high score (>95). |
| `test_empty_units_returns_empty_list` | Degenerate case: nothing to score. | Returns `[]`, no crash. |
| `test_raises_on_gop_scorer_count_mismatch` | Guard against a real integration bug: the GOPScorer must return exactly one score per requested canonical phoneme. | Raises `ValueError`. |

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

---

## `test_tts_caching.py`

Tests `CachingTTSProvider` in `stages/tts/caching.py`, using a
`_CountingStubProvider` fixture (fake `TTSProvider` that counts calls) —
fully deterministic, no real network or credentials needed.

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_cache_miss_calls_underlying_provider` | Verify a first call reaches the wrapped provider and returns its result. | `call_count == 1`; audio/timings match the stub's output. |
| `test_cache_hit_does_not_call_underlying_provider_again` | Verify a second identical call is served from the filesystem cache, never touching the wrapped provider again. | `call_count` stays `1` after the second call. |
| `test_different_text_is_a_cache_miss` | Verify the cache key includes the text. | Two different texts -> `call_count == 2`. |
| `test_different_rate_is_a_cache_miss` | Verify the cache key includes the rate. | Same text, different `rate` -> `call_count == 2`. |
| `test_different_voice_is_a_cache_miss` | Verify the cache key includes the voice — critical, since ignoring voice would silently return audio in the wrong voice. | Two providers with different `voice`, same text/rate, same cache dir -> each called once, no collision. |
| `test_voice_property_delegates_to_wrapped_provider` | Verify `CachingTTSProvider.voice` reads through to the wrapped provider (needed for it to satisfy the `TTSProvider` Protocol itself). | `cache.voice == stub.voice`. |
| `test_cached_word_timings_round_trip_correctly` | Verify `WordTiming` objects survive JSON serialization/deserialization on a cache hit, not just raw audio bytes. | Timings read back from cache equal the originals exactly. |
| `test_cache_persists_across_provider_instances` | Verify the cache is filesystem-backed (persists across separate `CachingTTSProvider` instances pointed at the same directory), not just an in-memory dict scoped to one instance. | A fresh instance served from disk never calls its own wrapped stub. |

---

## `test_audio_slicing.py`

Tests `slice_audio` in `stages/tts/audio_slicing.py`. Requires `ffmpeg` (or
`avconv`) — skipped automatically otherwise. Uses a synthetically
generated 440Hz test tone (pydub's own sine-wave generator) as a stand-in
for real TTS audio, since no real audio was available to test against in
the environment this was built in (no network access to Azure/edge-tts's
endpoints there).

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_slice_duration_matches_expected` | Verify the output duration equals the requested clip length plus padding on both sides. | `len(result) ≈ (end_ms - start_ms) + 2 * padding_ms` (600ms for the test's values), within a small encoder-framing tolerance. |
| `test_slice_start_is_silent` | Verify the padding region is genuine silence, not just a fade toward zero. | Max amplitude in the first 5ms is exactly `0`. |
| `test_slice_middle_has_signal` | Verify the actual audio content survives the slice+pad+fade pipeline intact. | Max amplitude well past the padding/fade region is high (>10,000). |
| `test_slice_with_default_padding_and_fade` | Verify the function works with its documented defaults, not just explicit test values. | Output is longer than the raw requested clip. |
| `test_slice_produces_valid_decodable_audio` | Sanity check that the output is well-formed audio, not corrupted data. | Decoding the sliced bytes doesn't raise. |
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

---

## `test_tts_provider_contract.py` (`tests/contract/`)

Tests `AzureTTSProvider` in `stages/tts/azure_tts.py`. Calls the real Azure
Speech API — requires `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION`
(repo-root `.env`), skipped automatically otherwise. Per Testing
Conventions, TTS output can't be exact-match tested (real audio bytes,
timing jitter), so these check invariants.

**Not run/verified by the assistant that wrote this code** — no network
access to Azure's endpoints from that environment, and no real
credentials. The SSML/event-wiring shape was verified structurally against
the real installed SDK (1.51.2); only the live round-trip is unverified.
Run this yourself once credentials are set.

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_synthesize_returns_nonempty_audio` | Verify a basic call returns real audio data. | `audio` is non-empty `bytes`. |
| `test_synthesize_returns_one_timing_per_word_roughly` | Verify the number of word-boundary timings is in the same ballpark as the word count of the input (not necessarily exact — SSML/tokenization quirks). | `abs(len(timings) - word_count) <= 2`. |
| `test_word_timings_are_in_order_and_non_negative` | Verify timings are well-formed: non-negative, `end_ms >= start_ms`, and in chronological order. | All timings satisfy this; `start_ms` values are sorted. |
| `test_slower_rate_produces_longer_or_equal_audio` | Verify `rate=0.7` (the D6 slow-playback pass) actually produces slower/longer audio for the same text, as a rough correctness check on the SSML `<prosody rate>` wiring. | `len(slow_audio) >= len(normal_audio)`. |

---

## `test_edge_tts_provider_contract.py` (`tests/contract/`)

Tests `EdgeTTSProvider` in `stages/tts/edge_tts_provider.py` — a second
TTS implementation alongside Azure (Decision Log D31), using the
unofficial `edge-tts` library (no API key needed). Same invariants as the
Azure contract test, since both implement the same `TTSProvider` Protocol.

**Skip mechanism differs from other contract tests**: since no credential
exists to check for, the whole module is skipped via a fast (3s) raw-socket
reachability check against `speech.platform.bing.com:443` (edge-tts's
actual host, read from its own `constants.py`) — deliberately not relying
on catching an exception from the full synthesis call, which was confirmed
to hang for 20+ seconds rather than fail cleanly in the sandboxed
environment this was built in.

**Not run/verified by the assistant that wrote this** — worse, in that
same sandboxed environment, even the reachability pre-check gave a false
positive (raw TCP connect succeeded; the actual WebSocket protocol data
still hung) — likely specific to how that sandbox's network proxy
intercepts traffic, not necessarily representative of a normal firewall.
Run this yourself and report back, especially if anything hangs instead of
completing or skipping quickly.

| Test | Purpose | Expected outcome |
|---|---|---|
| `test_synthesize_returns_nonempty_audio` | Verify a basic call returns real audio data. | `audio` is non-empty `bytes`. |
| `test_synthesize_returns_one_timing_per_word_roughly` | Verify word-boundary timing count is in the same ballpark as the word count — also implicitly verifies `boundary="WordBoundary"` was passed correctly (the library's default, `"SentenceBoundary"`, would give far fewer entries). | `abs(len(timings) - word_count) <= 2`. |
| `test_word_timings_are_in_order_and_non_negative` | Verify timings are well-formed and chronological. | All timings satisfy `start_ms >= 0`, `end_ms >= start_ms`; `start_ms` values sorted. |
| `test_slower_rate_produces_longer_or_equal_audio` | Verify the `float` rate → percentage-string conversion (`rate=0.7` → `"-30%"`) actually produces slower/longer audio. | `len(slow_audio) >= len(normal_audio)`. |