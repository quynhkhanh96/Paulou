"""Importing this package registers every FreePhoneRecognizer implementation
under the "free_decoder" stage key (core/registry.py), as a side effect of
each submodule's @register(...) decorator actually running.

Decorators only execute when their module is imported -- and nothing else
in the pipeline imports these submodules directly yet (no pipeline.py /
PipelineConfig exists to do that centrally, per the Roadmap). Anything
calling build("free_decoder", ...) -- e.g. experiments/runners/
canonicalizer_bias_check.py, compare_free_decoder.py -- must import this
package (or a specific submodule) first, or the registry will be empty.
"""

from stages.speech_assessment.free_decode import wav2vec2_bofenghuang, wav2vec2_cnam

__all__ = ["wav2vec2_bofenghuang", "wav2vec2_cnam"]