# Tests

Companion to the project's Testing Conventions note — this README is a
per-test index (purpose + expected outcome), not a restatement of the
testing philosophy.

## How to run

```bash
cd paulou
pytest tests/unit -v      # verbose, one line per test
pytest tests/unit         # quiet, summary only
```

No `tests/contract`, `tests/model`, `tests/api`, or `tests/db` directories
exist yet — only the pure-function stages (build order step 1) have been
implemented so far. All tests below are Category 1 (pure functions,
ordinary `pytest` assertions) per the Testing Conventions note; none load
models or call external services, so the full suite runs in well under a
second.

---

## `test_liaison_rules.py`

Tests `apply_liaison_rules` and `get_liaison_consonant` in
`stages/liaison/rule_engine.py`.

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

Tests `assemble_units` in `stages/assembly/unit_assembler.py`, using
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
