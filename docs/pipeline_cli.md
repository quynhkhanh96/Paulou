# Testing the whole pipeline from the command line

`experiments/runners/pipeline_cli.py` runs `PaulouPipeline` end to end with **real components** (Gemini parser, Lexique400 + eSpeak G2P, edge-tts, wav2vec2 recognizer, your microphone). It is a manual check, not part of CI (Decision Log D16, D50): the automated tests in `tests/unit/` cover the same code with stubs and need no network, no API key and no model.

Use the CLI to answer "does it actually work on a real sentence?", and the unit tests to answer "did I break something?".

## 1. Installation

Run everything from the inner package directory (the folder that contains `core/`, `stages/`, `pipeline.py`, `experiments/` and `data/`).

**System tools**

| Tool | Why | Check |
|---|---|---|
| `ffmpeg` | pydub decodes/cuts the MP3 from TTS | `ffmpeg -version` |
| `espeak-ng` | G2P fallback for words not in Lexique400 | `espeak-ng --version` |

**Python packages** (there is no `pyproject.toml` yet, so no `paulou[...]` extras group; install by name):

```bash
conda activate paulou
pip install -r requirements-dev.txt                 # base set; check it lists spacy, pydub, google-genai, python-dotenv
pip install -U edge-tts                             # keep current: old versions get HTTP 403 from the service
pip install torch transformers soundfile            # free-phone recognizer (wav2vec2)
pip install sounddevice                             # only for `score --record`
python -m spacy download fr_core_news_sm
```

On Python 3.13, pydub also needs `pip install audioop-lts` (the stdlib `audioop` module was removed).

**Data and secrets**

- `data/Lexique400.tsv`: git-ignored, download separately (Decision Log D30, SETUP.md). Another location: `--lexique-path`.
- `.env` at the repo root with `GEMINI_API_KEY=...` (copy `.env.example`).
- The wav2vec2 model (`Cnam-LMSSC/wav2vec2-french-phonemizer`) downloads from Hugging Face on first use.
- edge-tts needs no key, but needs internet access to Microsoft's endpoint.

## 2. Commands

All commands: `python -m experiments.runners.pipeline_cli <command> "<sentence>" [options]`

| Command | What it does | Needs |
|---|---|---|
| `analyze` | parser, then Chunk Analyzer: prints chunks and units (words, type, phonemes) | Gemini key, spaCy, Lexique400 |
| `reference --out-dir DIR [--slow]` | one TTS pass; writes `reference.mp3`, `spans.json`, one clip per chunk and per unit. `--slow` adds a rate-0.7 pass under `DIR/slow/` | + internet (edge-tts), ffmpeg |
| `timings [--rate R] [--decode]` | diagnostic: raw TTS word timings; with `--decode`, which word window each decoded phone falls in (`GAP` = outside every window) | edge-tts; `--decode` also needs the recognizer |
| `selftest [--json-out FILE]` | no microphone: analyze, TTS, cut each chunk, decode and score the TTS clip against its own phonemes | everything except the microphone |
| `score --record [--chunk N\|all] [--save-recording FILE]` | shows the text, records from your microphone until Enter, scores it | + `sounddevice` |
| `score --audio FILE [--chunk N\|all]` | scores an existing recording (wav, flac, ogg, mp3) | |

Options shared by all commands:

| Option | Meaning |
|---|---|
| `--parser/--g2p/--tts/--free-decoder KEY` | override a `PipelineConfig` field (defaults: `gemini`, `lexique_espeak`, `edge_tts`, `wav2vec2_cnam`) |
| `--timing-offset-ms N` | edge_tts only: shift TTS word timings later by N ms (see "Clip boundaries" below) |
| `--tts-cache-dir DIR` | cache TTS output by text, voice and rate (D7) |
| `--phone-stats FILE` | JSON calibration table `{"a": {"mean": .., "std": .., "sample_size": ..}}`; without it, placeholder stats are used |
| `--hang-dump SECONDS` | if still running after N seconds, print every thread's stack to stderr |
| `--lexique-path FILE` | Lexique400 location (default `data/Lexique400.tsv`) |

## 3. Recommended first run

```bash
# 1. structure only (no TTS, no model)
python -m experiments.runners.pipeline_cli analyze "Les enfants ont acheté des pommes."

# 2. reference audio + clips, then LISTEN to chunk_*.mp3 and the unit clips
python -m experiments.runners.pipeline_cli reference "Les enfants ont acheté des pommes." \
    --out-dir experiments/results/pipeline_cli --slow --timing-offset-ms 50 --hang-dump 60

# 3. full loop without a microphone
python -m experiments.runners.pipeline_cli selftest "Les enfants ont acheté des pommes." \
    --timing-offset-ms 50 --json-out experiments/results/pipeline_cli/selftest.json

# 4. your own voice, whole sentence
python -m experiments.runners.pipeline_cli score "Les enfants ont acheté des pommes." \
    --record --chunk all --timing-offset-ms 50 \
    --save-recording experiments/results/pipeline_cli/me.wav
```

`experiments/results/**/*.mp3` and `*.wav` are git-ignored; `*.json` and `*.md` are committed (experiments/README.md, "What gets committed").

## 4. How to read the output

```
c1_unit_1     79  acheté
    match        a    -> a    score=99
    deletion     ə    -> -    score=0
    substitution e    -> ɛ    score=11
    feedback: Overall: good effort, ...
```

- First line: unit id, unit score (MEAN of its ops, D40), words.
- One line per alignment op (D38): `match`, `substitution` (canonical -> heard), `insertion` (`-` -> extra sound), `deletion` (canonical -> `-`).
- **The numbers are not meaningful yet.** No native-corpus `phone_stats` exist (Decision Log D11/D24), so every phone uses a placeholder (mean 0.5, std 0.2) and a warning is printed. Read the *structure* (which ops appear), not the scores.
- Unit ids are namespaced per chunk (`c1_unit_1` = chunk 1, unit 1), D48.

### Known causes of "errors" that are not the speaker's

Check these before concluding that a pronunciation was wrong (all tracked in `docs/roadmap.md`):

- **Liaison the rule engine does not predict.** TTS and natural speakers say "enfants‿ont" [z] and "ont‿acheté" [t]; the canonical sequence has neither, so the aligner reports an `insertion`. A liaison that crosses a chunk boundary is not modeled at all, because each chunk is analyzed on its own.
- **Optional schwa.** Lexique gives "acheté" as [aʃəte]; real speech usually drops the schwa, and it is reported as a `deletion` of `ə`.
- **Canonicalizer bias near nasal vowels** (D47): the recognizer can hallucinate a nasal consonant after a nasal vowel.
- **Recording problems:** a clipped start/end or a noisy microphone shows up as deletions or substitutions at the edges of the sentence.

## 5. Clip boundaries and `--timing-offset-ms`

edge-tts word timings do not line up with the audio they describe (word ends look derived from the next word's start; word-final vowels fall at or past the window end). With the raw timings, the end of a word such as "acheté" was cut and its /t e/ played at the start of the next chunk. Shifting all timings later fixed this by ear at 50 ms and 80 ms on one sentence (Decision Log D49). The provider default is 0 (unchanged service timings) until it is validated on more sentences. If clips sound cut or start late, compare `--timing-offset-ms 0 / 50 / 80`; `timings --decode` shows where the decoder places each phone against each word window.

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Hangs, no output, no files | Find where with `--hang-dump 30` (prints stacks). Before D49 any edge-tts error looked like a hang; errors now surface as exceptions |
| `403` / `Invalid response status` from edge-tts | `pip install -U edge-tts`; check the system clock; try another network |
| `GEMINI_API_KEY is not set` | create `.env` at the repo root (`.env.example`) |
| `Lexique400 not found at ...` | download it to `data/Lexique400.tsv` or pass `--lexique-path` |
| `No implementation registered for stage=..., key=...` | typo in an override, or an implementation not listed in `pipeline.py::_STAGE_MODULES` |
| `ValueError: ... do not spell the same text` | the TTS service spelled something differently from the units (e.g. a digit read as a word); `locate_spans` is strict by design (D48). Use words, not digits |
| Chunks differ between two runs of the same sentence | the Gemini parser is not deterministic. Use `score --record` (analysis and recording in one run) or `--chunk all` with `--audio` |
| `Recording needs sounddevice` | `pip install sounddevice`; on Linux also `libportaudio2` |
| `Loading weights` progress bar | normal on every `score`/`selftest`/`timings --decode` run: the recognizer is built lazily |

## 7. Automated tests that cover this code (no network, no models)

```bash
pytest tests/unit -v
```

Relevant files: `test_registry.py`, `test_timing_alignment.py`, `test_pipeline.py` (stub stages), `test_edge_tts_provider.py` (fake stream, including the hang regression), `test_pipeline_cli.py` (stub pipeline; real MP3 cutting). `test_pipeline_cli.py` needs ffmpeg and soundfile.