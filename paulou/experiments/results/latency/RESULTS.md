# Latency benchmark — results (2026-10-22)

Run:
```bash
python -m experiments.runners.benchmark_latency --repeats 5 --timing-offset-ms 50
```
Raw data: `latency_20261022_150648.json` (same folder).
Machine: Windows 10 (build 26300), AMD64 Family 25 Model 80, 16 logical CPUs, torch 2.14.0+cpu, 8 torch threads, no CUDA. Python 3.11.16. One process, one request at a time (no concurrency measured).
Components: Gemini parser, Lexique400 + eSpeak G2P, edge-tts, `wav2vec2_cnam` on CPU. Audio scored = TTS reference audio (decode time depends on audio length, not on the speaker).

## Per attempt (what D15 is about)

| Audio scored | Audio length | `score_attempt` median | p90 | RTF (decode / audio) |
|---|---|---|---|---|
| one chunk (15 clips) | 0.52-1.16 s | 0.075-0.114 s | ≤ 0.115 s | 0.09-0.16 |
| whole sentence, short to long | 1.87-7.03 s | 0.175-0.595 s | ≤ 0.631 s | 0.08-0.10 |

Align + merge + feedback add nothing measurable: `score_attempt` ≈ `decode` (differences are within run-to-run noise).

## Per sentence submitted

| Step | Median | p90 |
|---|---|---|
| `analyze_sentence` (Gemini + spaCy + G2P) | 2.60 s ("Bonjour.") to 13.43 s (20-word sentence) | up to 14.82 s |
| `synthesize_reference`, one pass | 0.85-0.97 s | ≤ 1.02 s |

`analyze_sentence` is the slowest step by an order of magnitude and grows with sentence length. The parser call and `analyze_chunk` were not timed separately; the length scaling suggests the Gemini call dominates, but that is not measured.

## Once per process (cold)

| Step | Time |
|---|---|
| `free_decoder` construction (wav2vec2 load) | 12.24 s |
| parser client | 1.12 s |
| TTS provider, G2P (Lexique400 already loaded by `build_pipeline`) | ≤ 0.04 s |
| first decode (torch warm-up) | 0.38 s |

The 12 s model load may include a Hugging Face Hub network check (the run printed the unauthenticated-requests warning); not separated.

## Conclusions

- Scoring is fast enough to be synchronous: ≤ 0.12 s per chunk and ≤ 0.63 s for a 7 s sentence, far under D15's ~1-2 s threshold (Decision Log D52).
- The model must be loaded and warmed at server start, not on the first request (otherwise the first user waits ~12.6 s): `PaulouPipeline` builds stages lazily (D48), so the backend has to touch `free_decoder` and run one decode at startup.
- Sentence preparation (analysis + reference audio) takes ~3.5-16 s (median to p90), dominated by `analyze_sentence`. This is the step that needs a loading state, caching by sentence text, or a faster parser configuration; see D52.

## Not measured

Concurrent requests (CPU decode will queue), server hardware, the slow TTS pass (a second `synthesize_reference` call at rate 0.7), real learner recordings, the parser vs. `analyze_chunk` split.