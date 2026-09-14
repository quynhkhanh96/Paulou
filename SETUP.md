# Setup

Instructions to get the repo running locally, as it stands right now
(Roadmap build order steps 1–2, plus the sentence-parser and core-TTS
halves of step 3 — TTS caching and audio slicing are still pending). This
will grow further once the GOP scorer and free-phone recognizer exist —
see the note at the bottom.

## Prerequisites

- **Python 3.10 or later.** Required because the codebase uses the `X | Y`
  union-type syntax (PEP 604) directly in dataclass fields (e.g.
  `LiaisonConsonant | None`), which needs Python 3.10+. Developed and
  tested against Python 3.12.3 — anything 3.10+ should work, but 3.10/3.11
  haven't been explicitly verified yet.
- **`espeak-ng`** — a system package, NOT a pip dependency. Used as the G2P
  fallback in `paulou/stages/chunk_analyzer/g2p/lexique_espeak.py`. Install via your OS
  package manager:
  ```bash
  apt install espeak-ng        # Debian/Ubuntu
  brew install espeak-ng       # macOS
  ```
  **Windows:** download an installer from
  [github.com/espeak-ng/espeak-ng/releases](https://github.com/espeak-ng/espeak-ng/releases)
  and make sure the folder containing `espeak-ng.exe` is added to your PATH
  — confirmed via real testing that a missing/misconfigured PATH here
  originally surfaced as a cryptic `[WinError 2] The system cannot find the
  file specified`; this now raises a clear `RuntimeError` instead.
  Not required just to get the repo running — tests that need it are
  skipped automatically if it's missing (see `paulou/tests/README.md`).
- **`ffmpeg`** (or `avconv`) — a system package, NOT a pip dependency.
  Used by `pydub` for audio slicing
  (`paulou/stages/tts/audio_slicing.py`, Decision Log D5). Install via:
  ```bash
  apt install ffmpeg        # Debian/Ubuntu
  brew install ffmpeg       # macOS
  ```
  **Known future risk:** `pydub` depends on the stdlib `audioop` module,
  which is REMOVED (not just deprecated) in Python 3.13+. Fine on the
  Python 3.12.3 this was developed against; revisit before upgrading past
  3.12. Not required just to get the repo running — tests that need it are
  skipped automatically if it's missing. Used by the sentence parser
  (`paulou/stages/parsing/gemini_parser.py`). Get one at
  [aistudio.google.com/apikey](https://aistudio.google.com/apikey). Also
  not required just to get the repo running — tests that need it are
  skipped automatically if it's missing (see step 5 below for where it
  goes).
- **An Azure Speech resource key + region.** Used by TTS
  (`paulou/stages/tts/azure_tts.py`). Create a Speech resource at
  [portal.azure.com](https://portal.azure.com) to get these. Also not
  required just to get the repo running — skipped automatically if
  missing.

## Steps

1. **Clone/unzip the repo** and `cd` into the root (the directory this
   file is in — the one containing `paulou/`, `docs/`, `README.md`):
   ```bash
   cd Paulou
   ```

2. **Create a virtual environment** (keeps this project's dependencies
   isolated from anything else on your machine):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # macOS/Linux
   # .venv\Scripts\activate         # Windows
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements-dev.txt
   ```

4. **Download the French spaCy model** (a separate step — spaCy model
   packages aren't pulled in by `pip install spacy` alone):
   ```bash
   python -m spacy download fr_core_news_sm
   ```
   If that command fails in your environment (e.g. restricted network
   access — this is how it had to be done in the environment these stages
   were originally built and tested in), install the model wheel directly
   instead:
   ```bash
   pip install https://github.com/explosion/spacy-models/releases/download/fr_core_news_sm-3.8.0/fr_core_news_sm-3.8.0-py3-none-any.whl
   ```

5. **Set up your `.env` file** (needed for the sentence parser's and TTS's
   contract tests, and for actually calling `GeminiSentenceParser` /
   `AzureTTSProvider`). Copy the example and fill in your real values:
   ```bash
   cp .env.example .env
   ```
   Then edit `.env` (repo root — same directory as this file, NOT inside
   `paulou/`) so it contains:
   ```
   GEMINI_API_KEY=your-real-key-here
   AZURE_SPEECH_KEY=your-real-key-here
   AZURE_SPEECH_REGION=your-region-here
   ```
   Both `gemini_parser.py` and `azure_tts.py` find this automatically via
   `python-dotenv`, regardless of which directory you run commands from.

6. **Run the tests** to confirm everything works. Tests live inside the
   `paulou/` package directory (no packaging / `pip install -e .` set up
   yet, so imports resolve relative to running from inside `paulou/`):
   ```bash
   cd paulou
   pytest tests/unit -v              # fast suite
   pytest tests/model -v -m model    # slow suite — loads the real spaCy model
   pytest tests/contract -v --ignore=tests/contract/test_edge_tts_provider_contract.py
   ```
   All 95 tests should pass (74 fast + 12 model + 9 contract) if
   `espeak-ng`, `ffmpeg`, the spaCy model, `GEMINI_API_KEY`, and
   `AZURE_SPEECH_KEY`/`REGION` are all set up. If any is missing, the
   tests that need it are skipped, not failed — except a contract test
   will genuinely fail (not skip) if its credential is set but
   invalid/out of quota, since at that point a real API call is
   attempted. See `paulou/tests/README.md` for what each individual test
   checks.

   **Run separately, not as part of the above:**
   `tests/contract/test_edge_tts_provider_contract.py` (4 tests) — no
   credential needed for edge-tts, so it isn't skipped the same way; it
   does a fast reachability pre-check instead. On a restrictive
   network/proxy this can still hang rather than skip cleanly (confirmed
   in the sandboxed environment this was built in) — run it on its own
   and kill it if it hangs, rather than folding it into a routine
   full-suite run.

7. **Run the code directly**, if you want to explore interactively (still
   from inside `paulou/`):
   ```bash
   python3
   >>> from stages.chunk_analyzer.liaison.rule_engine import apply_liaison_rules
   >>> apply_liaison_rules([("les", "DET"), ("amis", "NOUN")])
   ```

## What's NOT needed yet (but will be)

Per the Codebase Conventions note ("Dependency management"), heavier,
stage-specific dependencies are meant to be added as separate extras groups
once those stages are actually built — not bundled in up front:

- **TTS caching + audio slicing** (rest of build order step 3, Decision Log
  D5/D7): the core `synthesize()` call is implemented; hash-based caching
  and chunk/unit-level audio slicing with fade-in/out are not — see
  `azure_tts.py`'s docstring. Slicing will need an audio-manipulation
  dependency (e.g. `pydub`) not yet added.
- **GOP scorer** (build order step 4): Kaldi (with its own non-Python
  setup — see `docs/kaldi_setup.md`, not written yet) and/or PyTorch for
  `gop-ft`.
- **Free-phone recognizer** (post-MVP, Decision Log D19): PyTorch +
  HuggingFace `transformers` for `Cnam-LMSSC/wav2vec2-french-phonemizer`.

None of this is installed or pinned yet — `requirements-dev.txt` will grow
(or split into extras) as each of those stages gets built, in build order.