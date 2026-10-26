"""Backend settings, read once from environment variables.

Holds paths and limits only -- never secrets. API keys (GEMINI_API_KEY) are
read by the stage implementations themselves (Codebase Conventions,
"Configuration and secrets"). Which implementation runs per stage is
`core.config.PipelineConfig`, not this class.

Environment variables (all optional):
- PAULOU_LEXIQUE_PATH     Lexique400 file (default data/Lexique400.tsv)
- PAULOU_CACHE_DIR        parent of the TTS and parser caches (default data/cache)
- PAULOU_PHONE_STATS_PATH calibration table JSON; unset = placeholder stats (D50/D53)
- PAULOU_TIMING_OFFSET_MS edge-tts word-timing shift (default 50, D49)
- PAULOU_CORS_ORIGINS     comma-separated allowed origins (default: Vite dev server)
"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    lexique_path: Path = Path("data/Lexique400.tsv")
    cache_dir: Path = Path("data/cache")
    phone_stats_path: Path | None = None
    timing_offset_ms: int = 50
    slow_rate: float = 0.7  # D6
    max_text_chars: int = 300
    max_guide_text_chars: int = 40  # D62: a word or a short phrase, not free text
    max_audio_bytes: int = 15 * 1024 * 1024
    min_audio_ms: int = 300
    max_audio_ms: int = 45_000
    store_capacity: int = 32
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)

    @property
    def tts_cache_dir(self) -> Path:
        return self.cache_dir / "tts"

    @property
    def parser_cache_dir(self) -> Path:
        return self.cache_dir / "parser"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        defaults = cls()
        stats = env.get("PAULOU_PHONE_STATS_PATH")
        origins = env.get("PAULOU_CORS_ORIGINS")
        return cls(
            lexique_path=Path(env.get("PAULOU_LEXIQUE_PATH", defaults.lexique_path)),
            cache_dir=Path(env.get("PAULOU_CACHE_DIR", defaults.cache_dir)),
            phone_stats_path=Path(stats) if stats else None,
            timing_offset_ms=int(env.get("PAULOU_TIMING_OFFSET_MS", defaults.timing_offset_ms)),
            cors_origins=(
                tuple(o.strip() for o in origins.split(",") if o.strip())
                if origins
                else defaults.cors_origins
            ),
        )
