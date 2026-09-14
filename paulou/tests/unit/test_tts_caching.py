from core.models import WordTiming
from stages.tts.caching import CachingTTSProvider


class _CountingStubProvider:
    """Fake TTSProvider that counts calls — lets tests verify cache hits
    skip the underlying provider entirely, without any real network call.
    """

    def __init__(self, voice: str = "test-voice"):
        self.voice = voice
        self.call_count = 0

    def synthesize(self, text: str, rate: float = 1.0) -> tuple[bytes, list[WordTiming]]:
        self.call_count += 1
        audio = f"AUDIO:{text}:{rate}".encode()
        timings = [
            WordTiming(word=w, start_ms=i * 100, end_ms=i * 100 + 50)
            for i, w in enumerate(text.split())
        ]
        return audio, timings


def test_cache_miss_calls_underlying_provider(tmp_path):
    stub = _CountingStubProvider()
    cache = CachingTTSProvider(stub, cache_dir=tmp_path)

    audio, timings = cache.synthesize("Bonjour les amis")

    assert stub.call_count == 1
    assert audio == b"AUDIO:Bonjour les amis:1.0"
    assert len(timings) == 3


def test_cache_hit_does_not_call_underlying_provider_again(tmp_path):
    stub = _CountingStubProvider()
    cache = CachingTTSProvider(stub, cache_dir=tmp_path)

    cache.synthesize("Bonjour les amis")
    audio, timings = cache.synthesize("Bonjour les amis")

    assert stub.call_count == 1  # NOT called a second time
    assert audio == b"AUDIO:Bonjour les amis:1.0"
    assert len(timings) == 3


def test_different_text_is_a_cache_miss(tmp_path):
    stub = _CountingStubProvider()
    cache = CachingTTSProvider(stub, cache_dir=tmp_path)

    cache.synthesize("Bonjour")
    cache.synthesize("Au revoir")

    assert stub.call_count == 2


def test_different_rate_is_a_cache_miss(tmp_path):
    stub = _CountingStubProvider()
    cache = CachingTTSProvider(stub, cache_dir=tmp_path)

    cache.synthesize("Bonjour", rate=1.0)
    cache.synthesize("Bonjour", rate=0.7)

    assert stub.call_count == 2


def test_different_voice_is_a_cache_miss(tmp_path):
    # Two providers, same text/rate, different voice -> must not collide.
    stub_a = _CountingStubProvider(voice="voice-a")
    stub_b = _CountingStubProvider(voice="voice-b")
    cache_a = CachingTTSProvider(stub_a, cache_dir=tmp_path)
    cache_b = CachingTTSProvider(stub_b, cache_dir=tmp_path)

    cache_a.synthesize("Bonjour")
    cache_b.synthesize("Bonjour")

    assert stub_a.call_count == 1
    assert stub_b.call_count == 1


def test_voice_property_delegates_to_wrapped_provider(tmp_path):
    stub = _CountingStubProvider(voice="fr-FR-DeniseNeural")
    cache = CachingTTSProvider(stub, cache_dir=tmp_path)

    assert cache.voice == "fr-FR-DeniseNeural"


def test_cached_word_timings_round_trip_correctly(tmp_path):
    stub = _CountingStubProvider()
    cache = CachingTTSProvider(stub, cache_dir=tmp_path)

    cache.synthesize("Bonjour les amis")
    _, timings = cache.synthesize("Bonjour les amis")  # from cache this time

    assert timings == [
        WordTiming(word="Bonjour", start_ms=0, end_ms=50),
        WordTiming(word="les", start_ms=100, end_ms=150),
        WordTiming(word="amis", start_ms=200, end_ms=250),
    ]


def test_cache_persists_across_provider_instances(tmp_path):
    # A fresh CachingTTSProvider pointed at the same cache_dir should see
    # entries written by an earlier instance (filesystem-backed, not
    # in-memory only).
    stub1 = _CountingStubProvider()
    CachingTTSProvider(stub1, cache_dir=tmp_path).synthesize("Bonjour")

    stub2 = _CountingStubProvider()
    audio, _ = CachingTTSProvider(stub2, cache_dir=tmp_path).synthesize("Bonjour")

    assert stub2.call_count == 0  # served from disk, never touched stub2
    assert audio == b"AUDIO:Bonjour:1.0"