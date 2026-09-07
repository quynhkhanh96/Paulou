# Setup

Instructions to get the repo running locally, as it stands right now
(Roadmap build order steps 1-2: pure functions, G2P, POS tagging). This
will grow once the remaining model-backed stages (sentence parser, TTS,
GOP scorer, free-phone recognizer) exist — see the note at the bottom.

## Prerequisites

- **Python 3.10 or later.** Required because the codebase uses the `X | Y`
  union-type syntax (PEP 604) directly in dataclass fields (e.g.
  `LiaisonConsonant | None`), which needs Python 3.10+. Developed and
  tested against Python 3.12.3 — anything 3.10+ should work, but 3.10/3.11
  haven't been explicitly verified yet.
- **`espeak-ng`** — a system package, NOT a pip dependency. Used as the G2P
  fallback in `paulou/stages/g2p/lexique_espeak.py`. Install via your OS
  package manager:
  ```bash
  apt install espeak-ng        # Debian/Ubuntu
  brew install espeak-ng       # macOS
  ```
  Not required just to get the repo running — tests that need it are
  skipped automatically if it's missing (see `paulou/tests/README.md`).

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

5. **Run the tests** to confirm everything works. Tests live inside the
   `paulou/` package directory (no packaging / `pip install -e .` set up
   yet, so imports resolve relative to running from inside `paulou/`):
   ```bash
   cd paulou
   pytest tests/unit -v              # fast suite
   pytest tests/model -v -m model    # slow suite — loads the real spaCy model
   ```
   All 53 tests should pass (46 fast + 7 model) if both `espeak-ng` and the
   spaCy model are installed. If either is missing, the tests that need it
   are skipped, not failed. See `paulou/tests/README.md` for what each
   individual test checks.

6. **Run the code directly**, if you want to explore interactively (still
   from inside `paulou/`):
   ```bash
   python3
   >>> from stages.liaison.rule_engine import apply_liaison_rules
   >>> apply_liaison_rules([("les", "DET"), ("amis", "NOUN")])
   ```

## What's NOT needed yet (but will be)

Per the Codebase Conventions note ("Dependency management"), heavier,
stage-specific dependencies are meant to be added as separate extras groups
once those stages are actually built — not bundled in up front:

- **Sentence parser + TTS** (build order step 3): Anthropic API client,
  Azure TTS SDK.
- **GOP scorer** (build order step 4): Kaldi (with its own non-Python
  setup — see `docs/kaldi_setup.md`, not written yet) and/or PyTorch for
  `gop-ft`.
- **Free-phone recognizer** (post-MVP, Decision Log D19): PyTorch +
  HuggingFace `transformers` for `Cnam-LMSSC/wav2vec2-french-phonemizer`.

None of this is installed or pinned yet — `requirements-dev.txt` will grow
(or split into extras) as each of those stages gets built, in build order.
