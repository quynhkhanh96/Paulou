# Canonicalizer-bias check — results summary

Human-readable summary of the D10 diagnostic check (D45-D47), run against
the D43/D44 12-case Tranche 1+2 diagnostic set. The raw per-case JSON these
runs produced is not committed here (regenerate with the commands below);
this file captures the interpretation and conclusion, which is what's
worth keeping.

**Commands used:**
```bash
python -m experiments.runners.compare_free_decoder \
    --recognizers wav2vec2_cnam wav2vec2_bofenghuang
```

## Headline result

| | Cnam-LMSSC | bofenghuang |
|---|---|---|
| Bias rate (12 perturbed cases) | **25.0%** (3 biased / 7 honest / 2 ambiguous) | 33.3% (4 biased / 6 honest / 2 ambiguous) |
| `liaison_deletion_les_anciens_amis_chain` (D23's chain example — the single most important case) | **HONEST** | BIASED |
| Native-audio anomalies | 4 files | 3 files |

**Conclusion (D47):** Cnam-LMSSC selected as the default `free_decoder`
candidate — lower bias rate, and correctly honest on the structurally most
important liaison-chain case. This is a "go, with a caveat," not a clean
"go" — see below.

## The caveat: a real, cross-model bias signal on genuinely clean audio

`liaison_insertion_un_heros`'s NATIVE recording (no liaison present at
all — "un héros" with h-aspiré correctly blocking it) was hallucinated by
**both** models into having a liaison-like nasal consonant:

| Model | Native audio decoded as |
|---|---|
| Cnam-LMSSC | `œ̃ m e ʁ o` (hallucinated /m/) |
| bofenghuang | `œ̃ n e ʁ o` (hallucinated /n/) |

This is the exact scenario D10 was written to guard against ("audio that
actually contains /leami/... could be hallucinated into /lezami/"), now
confirmed in practice, on two independently-trained models. Because both
models fail the same way, this reads as a genuine shared bias pattern
(both trained on similarly-transcribed Common Voice data) rather than an
implementation bug in one recognizer.

**Practical implication:** don't yet fully trust `accuracy_score` (D39)
for insertion/substitution errors immediately after a nasal vowel, without
further mitigation or at least a caveat surfaced to the user — same spirit
as D19's liaison_group caveat for the old design.

## Other findings, and what NOT to read into them

- **`substitution_bonjour`**: both models "corrected" the injected `/ɑ̃/`
  back to canonical `/ɔ̃/` — BIASED for both. A second real, consistent
  bias pattern (not just the nasal-insertion one above).
- **`final_consonant_deletion_table`**: both models decoded garbage
  unrelated to the actual word on BOTH native and perturbed audio (e.g.
  `k a ʁ ɑ̃`). Almost certainly a Piper synthesis artifact at a word-final
  cut, not a recognizer signal — don't count this case's AMBIGUOUS verdict
  as evidence either way until the underlying audio is checked.
- **`final_consonant_deletion_porte`** and **`substitution_lune`**
  (native): both models also erred here, differently but on the same
  underlying words — more likely generic recognition difficulty
  (word-final consonants, the /y/ vowel) than liaison-specific bias.

## What this does NOT settle

- Only a 12-case, MVP-scope diagnostic set (D43) — not the rigorous
  multi-speaker set the Publication Plan calls for.
- Group B candidates (`facebook/wav2vec2-lv-60-espeak-cv-ft`,
  `kgnlp/allophant`) were not run — see D45 for why they were deferred
  (vocabulary/framework mismatch, not simple drop-ins).
- Whether the nasal-hallucination pattern is specific to `œ̃` or to nasal
  vowels generally is unknown — would need more nasal-vowel insertion
  cases (a candidate Tranche 3 item) to isolate.