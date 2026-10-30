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
| `POST /attempts` multipart: `sentence_id`, exactly one of `chunk_index` / `unit_id` / `whole_sentence=true` (D59), `audio` | score one recording, synchronous (D52). Returns per-unit `ops` (canonical order, each with `kind` M / S_near / S / D / I and `near_reasons` codes, D64), `feedback_text`, and `score` fields that are `null` until `calibrated` |
| `GET /guide/audio?text=…` | a short word or phrase read aloud (mp3) for the guide's example buttons (D62). Letters, spaces, apostrophes and hyphens only, at most 40 characters (`max_guide_text_chars`); anything else is `422 invalid_guide_text`. Uses the TTS cache (D7), needs the same network access as sentence preparation |

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

- **Score line**: "x/y words correct · a/b sounds correct · n close". Counts only, no numeric score while `calibrated=false` (D57).
- **Needs fixing** (first) and **You did well**: at most 2 items each, far errors before near ones, an empty box is hidden. Praise is concrete (a hard sound done right, an all-correct word, a list of correct sounds); there is no comparison with earlier attempts.
- **Word chips** (one per pronunciation unit; ok / close / error). Clicking one opens a card with the sound-by-sound track changes (expected sound is the spine: correct, close, replaced, missing, extra), its own boxes, **Hear the model** and **Hear yourself**. The first non-ok unit opens by itself.
- Wording is generated in the frontend from the ops (`learnerText.tsx`, English). `feedback_text` stays in the API but this view does not show it (partly supersedes D57).
- Near vs far is decided in the backend by `stages/speech_assessment/phone_similarity.py` (hand-written feature tables, no model); the API sends `kind` and reason codes, the frontend only maps them to sentences. `confidence` is not exposed.
- **Hear yourself** decodes the recording in the browser (Web Audio) and plays the slice between the unit's first and last timestamp (+80 ms padding). It depends on the recognizer timestamps (D37) lining up with the upload; this has only been checked with the stub pipeline, and not in Safari or Firefox.
- Known limits are explained next to a result when the pattern appears: extra sounds that may be a cross-chunk liaison (D51), a dropped schwa (D50 finding), an extra consonant after a nasal vowel (D47).
- Not built: the audio-timeline view (D37 view 2), the expert/debug drawer, progress tracking, auth.

## UI

- **Practice** tab: one tab per chunk plus a **Whole sentence** tab (D59). In a chunk tab you can drill the whole chunk or a single unit; in the sentence tab you record the whole sentence and the results are grouped by chunk.
- **Pronunciation guide** tab (D60): static reference of French sounds (IPA, how to make each, spellings, examples) and of linking, elision and rhythm. Content lives in `frontend/src/guideData.ts`; it needs no pipeline. Each example has a play button that reads the word with the reference voice (D62); the sounds themselves have no audio, because TTS cannot pronounce a bare IPA symbol. Switching tabs keeps the current practice state.
- Whole-sentence scoring has only been exercised with the stub pipeline and unit tests, not with a real recording on the real model. A link across a chunk boundary is still shown as an extra sound (D51).
