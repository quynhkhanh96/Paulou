# experiments/

Comparative evaluations between candidate implementations, diagnostic-set
generation, and qualitative review notebooks. **Nothing under this
directory runs in CI** — see Decision Log D16 for why `tests/` and
`experiments/` are kept separate. If you're looking for the pass/fail test
suite, see `tests/` and `tests/README.md` instead.

## Structure

```
experiments/
  diagnostic_set/     # generates the D10 canonicalizer-bias diagnostic
                       # audio set (native/substitution/deletion/insertion)
  runners/            # not yet built — comparative runs between candidate
                       # stage implementations (e.g. FreePhoneRecognizer
                       # candidates), see Codebase Conventions
  notebooks/          # not yet built — qualitative review (chunking
                       # quality, audio playback, alignment visualization)
  results/            # output of runs above — see "What gets committed"
```

## Setup

Dependencies here are NOT tied to any registered pipeline stage (unlike,
e.g., `paulou[gop-kaldi]`), so they live in their own extras group instead
of a stage-specific one — see Decision Log D43:

```bash
conda activate paulou
pip install -r experiments/requirements-experiments.txt
```

`piper-tts` bundles its own `espeak-ng-data` and binding — it does NOT use
the system `espeak-ng` CLI. That CLI is a SEPARATE, already-required system
dependency for the pipeline's own G2P fallback (`LexiqueEspeakG2P`, D30);
installing the extras above does not remove that requirement.

## `diagnostic_set/` — generating the D10 diagnostic audio

```bash
python -m experiments.diagnostic_set.build_diagnostic_audio \
    --model <path>/fr_FR-siwis-medium.onnx \
    --config <path>/fr_FR-siwis-medium.onnx.json
```

This synthesizes native + perturbed audio for each case defined in
`cases.py` and writes them, plus `metadata.json`, under
`experiments/results/diagnostic_set/` by default. See Decision Log D43 for
why Piper (not Azure/edge-tts/real recordings) and why this location.

Two smaller modules can be run standalone, with no voice model needed, to
sanity-check the case definitions and phoneme-format conversion:

```bash
python -m experiments.diagnostic_set.cases          # prints each case's phonemes
python -m experiments.diagnostic_set.perturbation   # prints native vs. perturbed
python -m experiments.diagnostic_set.piper_phonemes # checks phoneme coverage
                                                     # against Piper's DEFAULT map
```

## Promoting a diagnostic-set version to `tests/fixtures/`

Once a generated version is judged good enough (voice quality checked,
`metadata.json` reviewed), copy the chosen files into
`tests/fixtures/diagnostic_audio/` and commit them there directly (do NOT
git-ignore that copy — see Decision Log D43 for why the pinned fixture is
committed rather than regenerated from a script). Anything left behind
under `experiments/results/diagnostic_set/` remains iteration history, not
the fixture used by `tests/model/`.

## What gets committed

- `experiments/results/**/*.wav`, `*.mp3` — **git-ignored**. Reproducible,
  one-off exploration output.
- `experiments/results/**/*.json`, `*.md` — **committed**. Per Codebase
  Conventions, experiment result summaries are expected to be linked in PR
  descriptions, so they need to exist in the repo.
- `tests/fixtures/diagnostic_audio/` — **committed in full** (`.wav` and
  `metadata.json`), once promoted. See Decision Log D43.
