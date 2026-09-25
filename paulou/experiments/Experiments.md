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
                       # audio set (native/substitution/deletion/insertion) —
                       # 12 cases across Tranche 1 (liaison) + Tranche 2
                       # (broader error types), see Decision Log D43/D44
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

### Downloading a voice model

Not committed to the repo (large, third-party, reproducible from source —
same reasoning as `Lexique400.tsv`, D30). List available French voices,
then download one into this same directory:

```bash
python -m piper.download_voices | grep fr_FR
python -m piper.download_voices fr_FR-siwis-medium \
    --download-dir experiments/diagnostic_set/
```

This writes `<voice>.onnx` and `<voice>.onnx.json` — both git-ignored (see
"What gets committed" below).

### Generating the audio

```bash
python -m experiments.diagnostic_set.build_diagnostic_audio \
    --model experiments/diagnostic_set/fr_FR-siwis-medium.onnx \
    --config experiments/diagnostic_set/fr_FR-siwis-medium.onnx.json
```

This synthesizes native + perturbed audio for each of the 12 cases defined
in `cases.py` and writes them, plus `metadata.json`, under
`experiments/results/diagnostic_set/` by default. See [`CASES.md`](diagnostic_set/CASES.md) for a
human-readable catalog of what each case tests; see Decision Log D43 for
why Piper (not Azure/edge-tts/real recordings) and why this location; see
D44 for the synthesis parameters (`noise_scale`/`noise_w_scale`, zeroed by
default in the script) and the word-boundary pause technique.

Pass `--length-scale 1.0` for the model's normal speaking pace (the script
defaults to 1.3x slower, to make a single changed phoneme easier to verify
by ear — see D44).

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

- `experiments/diagnostic_set/*.onnx`, `*.onnx.json` — **git-ignored**.
  Downloaded voice models, reproducible via the download command above
  (same reasoning as `Lexique400.tsv`, D30).
- `experiments/results/**/*.wav`, `*.mp3` — **git-ignored**. Reproducible,
  one-off exploration output.
- `experiments/results/**/*.json`, `*.md` — **committed**. Per Codebase
  Conventions, experiment result summaries are expected to be linked in PR
  descriptions, so they need to exist in the repo.
- `tests/fixtures/diagnostic_audio/` — **committed in full** (`.wav` and
  `metadata.json`), once promoted. See Decision Log D43.