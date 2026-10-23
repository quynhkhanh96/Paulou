# Running the web app (backend + frontend)

Local, single-user MVP (Decision Log D53). The backend only calls `PaulouPipeline` (D13); the frontend only talks to the backend's `/api`.

Run everything from the package directory (the one containing `core/`, `stages/`, `backend/`, `frontend/`, `pipeline.py`).

## Requirements

Same as `docs/pipeline_cli.md` (ffmpeg, espeak-ng, `data/Lexique400.tsv`, `GEMINI_API_KEY` in `.env` at the repo root, internet for edge-tts and the first model download), plus Node 20+ for the frontend (22 tested).

## Option A: Docker Compose

```bash
docker compose up --build        # then open http://localhost:8080
```

- Mounts `./data` (Lexique400 and the caches) and a named volume `hf-cache` (the wav2vec2 model, downloaded on first start).
- The UI says "Loading the speech model" until `/api/health` reports `ready` (~12 s after the container is up, D52).
- Open it as `http://localhost:8080`: browsers only allow the microphone on `localhost` or `https`.
- The Docker images were first written without a Docker daemon (validated with `docker compose config` only) and have since been built and run successfully by the author. Safari and Firefox recordings remain untested.

## Option B: two processes (development)

```bash
# backend
pip install -r backend/requirements-dev.txt
pip install torch                                  # CPU is enough
python -m spacy download fr_core_news_sm
uvicorn backend.api.main:create_default_app --factory --port 8000

# frontend (another terminal)
cd frontend
npm install
npm run dev                                         # http://localhost:5173, proxies /api to :8000
```

## Configuration (environment variables, all optional)

| Variable | Default | Meaning |
|---|---|---|
| `PAULOU_LEXIQUE_PATH` | `data/Lexique400.tsv` | Lexique400 file |
| `PAULOU_CACHE_DIR` | `data/cache` | parent of `tts/` (D7) and `parser/` (D55) caches |
| `PAULOU_PHONE_STATS_PATH` | unset | real calibration table (same JSON as `pipeline_cli --phone-stats`). Unset = placeholder stats: the API reports `calibrated=false` and no numeric scores |
| `PAULOU_TIMING_OFFSET_MS` | `50` | edge-tts word-timing shift (D49) |
| `PAULOU_CORS_ORIGINS` | `http://localhost:5173` | only needed if the UI is served from another origin |

When a real `phone_stats` file is supplied it must contain every phone the G2P can produce (or the pipeline needs a `fallback_phone_class`): a missing phone makes `calibrate_score` raise and `/api/attempts` answers `scoring_failed`.

## API

All under `/api`. Errors are `{"detail": {"code": "...", "message": "..."}}`.

| Endpoint | Purpose |
|---|---|
| `GET /health` | `{status: warming_up\|ready\|error, calibrated, detail}` |
| `POST /sentences` `{text}` | prepare a sentence (analyze + normal-speed TTS), synchronous, ~3.5-16 s. Returns `sentence_id`, `chunks[].units[]`. Same text (after whitespace normalization) = same id, prepared once |
| `GET /sentences/{id}/audio?speed=normal\|slow&chunk=N` or `&unit=ID` | MP3 of the whole sentence, a chunk or a unit. The slow pass (rate 0.7, D6) is made on first request |
| `POST /attempts` multipart: `sentence_id`, `chunk_index` or `unit_id`, `audio` | score one recording, synchronous (D52). Returns per-unit `ops` (canonical order), `feedback_text`, and `score` fields that are `null` until `calibrated` |

Error codes: `empty_text`, `text_too_long`, `no_content`, `text_not_supported`, `preparation_failed` (502), `sentence_not_found` (404, prepared sentences live in memory: prepare again), `chunk_not_found`, `unit_not_found`, `invalid_target`, `model_not_ready` (503), `bad_audio`, `audio_too_short`, `audio_too_long`, `audio_too_large` (413), `scoring_failed` (500).

## Tests

```bash
pytest tests/unit tests/api            # backend; no network, no models
cd frontend && npm test                # Vitest
```

Browser smoke test (real Chromium, fake microphone, the real FastAPI app with a stub pipeline):

```bash
uvicorn tests.api.e2e_app:app --port 8000 &
cd frontend && npm run build && npx vite preview --port 4173 &
PAULOU_CHROMIUM=/path/to/chromium node e2e/smoke.mjs
```

## What the UI shows, and what it does not

- Per unit: the expected sounds in order, marked match / substitution / extra sound / missing (canonical view, D37 view 1), plus `feedback_text`. No numeric score while `calibrated=false`.
- The overall wording in `feedback_text` ("good effort", "needs work") comes from placeholder scores; the UI says so next to it.
- Known limits are explained next to a result when the pattern appears: extra sounds that may be a cross-chunk liaison (D51), a dropped schwa (D50 finding), an extra consonant after a nasal vowel (D47).
- Not built: the audio-timeline view (D37 view 2), progress tracking, auth.