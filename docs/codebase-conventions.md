# Paulou — Codebase Conventions

Practical, day-to-day conventions for writing code in this repo. Complements the Architecture Spec (what the modules are and how they fit together) and Testing Conventions (how each module is tested). This note is about *how to write and add code* — naming, structure rules, and the step-by-step for extending the pipeline. Worth keeping current given a collaborator may join for the TTS/Speech Assessment components.

---

## Module boundary rules (recap + enforcement)

These rules come from the Architecture Spec / Decision Log — this section states them as things to actually check before merging code, not just design intent.

1. **`core/` and `stages/` never import from `backend/` or `frontend/`.** Dependency direction is one-way (Decision Log D13). If a stage module needs something like a DB session or an HTTP request object, that's a sign the logic belongs in `backend/`, not in `stages/`.
2. **A stage goes through the registry only if it's genuinely swappable** (has an external/model dependency, or is a real candidate for comparison — see Decision Log D12). Don't wrap a pure function in `Protocol`/`register()` just for consistency — that's the over-engineering case explicitly rejected for liaison rules, alignment, merge, calibration, and feedback templating.
3. **`core/models.py` has no ORM or web-framework inheritance.** It must be importable and usable with zero DB connection, zero API framework — this is what keeps notebooks and `tests/unit` fast and dependency-free (Decision Log D14).
4. **Anything in `stages/` that touches an external API/model must implement its stage's `Protocol` exactly** — no extra required constructor args beyond what config provides, since the registry instantiates via `build(stage, key, **kwargs)`.

---

## Adding a new implementation for an existing stage

This is the most common type of change expected (e.g. trying `gop-ft` alongside `kaldi`, or a different TTS vendor). Steps:

1. **Implement the Protocol.** Create `stages/<stage_name>/<new_impl>.py`, write a class matching the stage's `Protocol` signature exactly (see Architecture Spec for each interface). No need to import or subclass anything from `core/interfaces.py` — `Protocol` is structural, matching by signature is enough.
2. **Register it.**
   ```python
   @register("gop_scorer", "gopft")
   class GopFtScorer:
       def score(self, audio, canonical_phonemes): ...
   ```
3. **Make sure it passes the stage's shared contract test** (`tests/contract/test_<stage>_contract.py`) — this is what proves the new implementation is a valid drop-in, not just "it runs."
4. **If the decision to adopt it isn't obvious, write an experiment**, not just a contract test pass. Add a runner under `experiments/runners/compare_<stage>.py` using the shared diagnostic set, and record the result under `experiments/results/`. See Experiment Log conventions.
5. **Do not change `PipelineConfig`'s default until the experiment/decision is resolved.** Adding an implementation and switching the default are separate steps — keep the currently-trusted implementation as default until there's a documented reason (an experiment result or a decision log entry) to change it.
6. **If adopted, add a Decision Log entry** referencing the experiment result that justified the switch.

---

## Naming conventions

- **Files:** `snake_case.py`, named after what they contain, not the vendor (`kaldi_gop.py` is fine since it names the specific implementation; a file with multiple candidate implementations should be split, not combined, so the registry decorator per file stays easy to find).
- **Classes implementing a Protocol:** suffix with the role, not "Impl" — `KaldiGOPScorer`, `AzureTTSProvider`, `ClaudeSentenceParser` — the class name should make sense read standalone in a stack trace or log line.
- **Pure functions:** name as verbs describing the transformation — `apply_liaison_rules`, `assemble_units`, `align_phonemes`, `calibrate_score` — avoid vague names like `process` or `handle`.
- **Test files:** mirror the module path (`stages/liaison/rule_engine.py` → `tests/unit/test_liaison_rules.py`); contract tests named `test_<stage>_contract.py` regardless of which implementation is under test, since the point is the shared contract, not one implementation.

---

## Type hints and data validation

- All public function signatures (anything called from another module, i.e. everything in `stages/*/`, `core/*`, `pipeline.py`) require type hints — this is what makes the `Protocol`-based structural typing actually catch mismatches.
- `core/models.py`: use `@dataclass(frozen=True)` for data models that represent a completed analysis result (`Sentence`, `Chunk`, `PronunciationUnit`, `UnitResult`) — these shouldn't be mutated after construction, since they're passed across module boundaries and mutation-after-the-fact is a common source of hard-to-trace bugs. Use plain (non-frozen) dataclasses only for things actively being built up during a single function (e.g. an internal accumulator in the unit assembler).
- Prefer `Literal[...]` over bare `str` for fields with a fixed set of values (`type: Literal["single", "liaison_group"]`, `scoring_focus: Literal[...]`) — catches typos at type-check time rather than at runtime.

---

## Error handling

- **G2P fallback chain:** if Lexique383 lookup fails, fall back to eSpeak-ng — this fallback is a designed behavior, not an exception path. `G2PProvider.phonemize()` should never raise for "word not found"; it should return the eSpeak-ng result with `source="espeak"` so the caller can decide how much to trust it, rather than the caller needing to catch an exception to detect a fallback occurred.
- **External API failures (LLM parser, TTS, Azure-adjacent calls):** these should raise a specific exception type per stage (e.g. `ParserUnavailableError`), not propagate the raw HTTP/SDK exception — keeps `backend/api/` error handling decoupled from which vendor SDK is behind a given stage.
- **Contract test failures vs. runtime exceptions:** a stage implementation failing its contract test (e.g. GOP scorer doesn't rank native > substitution) is a development-time signal, not something to handle with a try/except at runtime — don't write defensive runtime code to paper over a contract violation; fix the implementation or don't register it as production-ready.

---

## Configuration and secrets

- `PipelineConfig` (in `core/config.py`) holds *which implementation* is active per stage — not secrets, not environment-specific paths.
- API keys (Claude API, Azure TTS/Speech) are read from environment variables inside each stage implementation's `__init__`, never hardcoded, and never passed through `PipelineConfig`. `PipelineConfig` should be safe to log or commit as a default file.
- When trying an experiment that requires a new external service, the corresponding env var should be documented in `.env.example`, not just used silently.

---

## Dependency management

- New dependencies (especially heavy ones — Kaldi, PyTorch, spaCy models) go in a stage-specific extras group where practical (e.g. `pip install paulou[gop-kaldi]`), so someone working only on the parser/liaison side doesn't need to install acoustic modeling dependencies. Worth setting this up before a collaborator joins for the TTS/Speech Assessment side, so their setup isn't blocked on unrelated dependencies (G2P, chunking) and vice versa.
- Pin versions for anything model-related (acoustic models, HuggingFace model revisions) — an unpinned model update changing GOP score distributions silently would invalidate calibration (Decision Log D11) without any code change to point to.

---

## Git / PR conventions

- **Commit messages:** reference the stage/module touched, e.g. `liaison: add closed-list exception for "onze"` rather than generic messages.
- **When a PR represents a real design decision** (new implementation adopted as default, a tradeoff accepted, an architecture change) — the PR description should link to (or add) the corresponding Decision Log entry. The Decision Log should stay the single source of truth for *why*, not scattered across PR descriptions and commit messages.
- **When a PR adds or changes an experiment** — link the `experiments/results/*.json` or `.md` output in the PR description, not just the runner code, so reviewers see the actual numbers.
- Given the collaborator situation (someone joining specifically for TTS/Speech Assessment): PRs touching those stages are the ones most worth keeping self-contained and well-described, since review context can't be assumed to be shared the way it is for solo work.

---

## Keeping docs in sync

- **Architecture Spec** is the working source of truth for data models/interfaces — update it first when a design changes, then update the README's summary version, not the other way around (Decision Log D-references should point to the Architecture Spec / Decision Log, not to README, since the README is expected to lag).
- **Decision Log** is append-only in spirit — see its own header note. Don't rewrite past entries to "clean them up"; add a new entry noting a reversal or refinement instead, so the history of *why* stays intact.
