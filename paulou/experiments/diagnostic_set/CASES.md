# Diagnostic set — case catalog

Human-readable reference for the 12 cases in `cases.py`, generated from
their actual data (not hand-typed) after Tranche 1+2 were finalized and
verified locally — see Decision Log D43 (methodology) and D44 (final case
list, synthesis parameters, word-boundary technique) for the full
rationale. This file describes WHAT each case tests; it does not repeat
WHY the methodology was chosen — see the Decision Log for that.

**Reading the phoneme rows:** `|` marks a word-boundary pause inserted for
that specific rendering (see D44) — present only where the two words are
NOT connected by an intact liaison in that rendering. Its absence does not
mean "wrong"; most cases (all of Tranche 2, plus `chat`) have no word-pair
boundary concept at all (single word, or substitution/insertion that
doesn't change word connectedness).

If `cases.py` changes, regenerate this file rather than hand-editing it out
of sync — see the one-liner at the bottom.

---

## Tranche 1 — liaison-focused (D3/D9's core concern)

| case_id | sentence | rule | native | perturbed |
|---|---|---|---|---|
| `liaison_deletion_les_amis` | les amis | obligatoire (determiner+noun) | `l e z a m i` | `l e \| a m i` |
| `liaison_deletion_petit_ami` | petit ami | obligatoire (adjective+noun) | `p ə t i t a m i` | `p ə t i \| a m i` |
| `liaison_deletion_les_anciens_amis_chain` | les anciens amis | obligatoire chain (D23) | `l e z ɑ̃ s j ɛ̃ z a m i` | `l e \| ɑ̃ s j ɛ̃ z a m i` |
| `liaison_insertion_un_heros` | un héros | interdite (h-aspiré) | `œ̃ e ʁ o` | `œ̃ n e ʁ o` |
| `liaison_insertion_et_amis` | et amis | interdite (after "et") | `e \| a m i` | `e z a m i` |
| `substitution_chat` | chat | not liaison — general phoneme_accuracy | `ʃ a` | `s a` |

**Notes:**
- `liaison_deletion_les_amis` — deletes the /z/. Chosen as the primary case: SLA-literature review (D43) found omission is the dominant real liaison error type, not substitution.
- `liaison_deletion_petit_ami` — deletes the /t/. Diversifies liaison-consonant coverage beyond /z/.
- `liaison_deletion_les_anciens_amis_chain` — a genuine two-boundary liaison chain, reusing D23's own worked example. Deletes only the FIRST /z/ (les|anciens); the second /z/ (anciens|amis) stays intact in both renderings, testing whether a correct liaison right next to a deleted one still reads correctly. `unit_id` assignment for this case is a flagged simplification in `cases.py` — it does not resolve D23's own open ambiguity about which unit "owns" a word sitting between two liaison boundaries.
- `liaison_insertion_un_heros` — wrongly inserts /n/ where h-aspiré blocks liaison. **No word-boundary pause on either rendering** — confirmed by listening (D44) that a pause after the nasal vowel `œ̃` creates a nasal-release artifact easily mistaken for /n/, which would defeat the point of this case.
- `liaison_insertion_et_amis` — wrongly inserts /z/ where "et" always blocks liaison. A *different* interdite rule than `un_héros`, and its boundary works cleanly (oral vowel, no nasal-release issue).
- `substitution_chat` — not liaison-related; included in Tranche 1 as the original single-consonant substitution case, informed by L2-ARCTIC's substitution-dominant error distribution for ordinary phoneme errors.

## Tranche 2 — broader, non-liaison error types (D36's expanded scope)

| case_id | sentence | subtype | native | perturbed |
|---|---|---|---|---|
| `final_consonant_deletion_table` | table | final-consonant deletion | `t a b l` | `t a b` |
| `final_consonant_deletion_porte` | porte | final-consonant deletion | `p ɔ ʁ t` | `p ɔ ʁ` |
| `weak_cluster_deletion_spectacle` | spectacle | internal-cluster deletion | `s p ɛ k t a k l` | `s p ɛ t a k l` |
| `substitution_bonjour` | bonjour | nasal-vowel substitution | `b ɔ̃ ʒ u ʁ` | `b ɑ̃ ʒ u ʁ` |
| `substitution_lune` | lune | oral-vowel substitution | `l y n` | `l u n` |
| `substitution_deux` | deux | oral-vowel substitution | `d ø` | `d e` |

**Notes:**
- All six are single words — no word-pair, so no boundary-pause concept applies to any of them.
- `final_consonant_deletion_table` / `_porte` — word-final consonant dropped (/l/, /t/), unrelated to liaison; tests general deletion sensitivity per D36's "one model responsible for all error types" framing.
- `weak_cluster_deletion_spectacle` — deletes the first /k/ inside the k-t-a-k-l cluster (not word-final).
- `substitution_bonjour` — nasal vowel /ɔ̃/->/ɑ̃/, a classic learner confusion (Glossary: nasal vowels).
- `substitution_lune` — oral vowel /y/->/u/, a well-known confusable pair for many L2 learners.
- `substitution_deux` — oral vowel /ø/->/e/, a vowel-height merger.

---

## Deliberately deferred (not forgotten — see D44 Tradeoffs)

From the external proposal reviewed while designing Tranche
2, these categories were NOT built into this 12-case set, kept as a
candidate Tranche 3 if 12 cases don't produce a clear enough
canonicalizer-bias signal:
- Extra trailing schwa insertion (e.g. "bonjour" -> "bonjourə")
- Isolated word-initial consonant insertion with no liaison context
- Additional substitution pairs (more nasal vowels, voicing pairs, schwa-to-vowel)

## Regenerating this file

```bash
python -m experiments.diagnostic_set.cases  # or write a small script using
                                             # build_cases() + apply_perturbation()
                                             # to regenerate this table if cases.py changes
```