"""Builds the real PaulouPipeline for the backend (and nothing else).

Imports are inside the function so that `backend.api.main` can be imported
(and tested with a stub pipeline) without spaCy, torch or any API key.
"""

from backend.api.settings import Settings
from stages.speech_assessment.calibration import PhoneStats


def build_pipeline(settings: Settings, phone_stats: dict[str, PhoneStats]):
    from core.config import PipelineConfig
    from pipeline import PaulouPipeline

    config = PipelineConfig()
    stage_kwargs: dict[str, dict] = {}

    if config.g2p == "lexique_espeak":
        from stages.chunk_analyzer.g2p.lexique_espeak import load_lexique400

        if not settings.lexique_path.exists():
            raise RuntimeError(
                f"Lexique400 not found at {settings.lexique_path} (git-ignored, download it "
                "separately -- see SETUP.md; override with PAULOU_LEXIQUE_PATH)."
            )
        stage_kwargs["g2p"] = {"lexicon": load_lexique400(settings.lexique_path)}

    if config.tts == "edge_tts":
        stage_kwargs["tts"] = {"timing_offset_ms": settings.timing_offset_ms}  # D49

    return PaulouPipeline(
        config,
        phone_stats,
        tts_cache_dir=str(settings.tts_cache_dir),  # D7
        parser_cache_dir=str(settings.parser_cache_dir),  # D52/D55
        stage_kwargs=stage_kwargs,
    )
