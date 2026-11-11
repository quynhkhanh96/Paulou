"""Rate limits (Decision Log D71): the limiter itself, the client key, and the
wiring on the three limited endpoints."""

import pytest

from backend.api.rate_limit import SlidingWindowLimiter, client_key, retry_after_header
from backend.api.settings import Settings
from tests.api.conftest import make_client, wav_bytes


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


# -- SlidingWindowLimiter -----------------------------------------------------


def test_allows_up_to_the_limit_then_reports_the_wait():
    clock = FakeClock()
    limiter = SlidingWindowLimiter([(3, 60.0)], clock=clock)
    assert [limiter.hit("a") for _ in range(3)] == [None, None, None]
    clock.now += 10
    assert limiter.hit("a") == pytest.approx(50.0)  # first hit leaves the window at +60


def test_window_slides():
    clock = FakeClock()
    limiter = SlidingWindowLimiter([(2, 60.0)], clock=clock)
    limiter.hit("a")
    clock.now += 30
    limiter.hit("a")
    clock.now += 31  # the first hit is now 61 s old
    assert limiter.hit("a") is None
    assert limiter.hit("a") == pytest.approx(29.0)  # the second hit leaves at +90


def test_rejected_hits_are_not_counted():
    clock = FakeClock()
    limiter = SlidingWindowLimiter([(1, 60.0)], clock=clock)
    limiter.hit("a")
    for _ in range(5):
        clock.now += 1
        assert limiter.hit("a") is not None
    clock.now = 1000.0 + 60.5
    assert limiter.hit("a") is None


def test_clients_are_counted_separately():
    limiter = SlidingWindowLimiter([(1, 60.0)], clock=FakeClock())
    assert limiter.hit("a") is None
    assert limiter.hit("b") is None
    assert limiter.hit("a") is not None


def test_the_longest_wait_of_all_windows_is_returned():
    clock = FakeClock()
    limiter = SlidingWindowLimiter([(10, 60.0), (2, 3600.0)], clock=clock)
    limiter.hit("a")
    clock.now += 100
    limiter.hit("a")
    clock.now += 100
    # Minute window is fine (0 hits in it); the hour window is full.
    assert limiter.hit("a") == pytest.approx(3400.0)


def test_zero_limit_turns_a_window_off():
    limiter = SlidingWindowLimiter([(0, 60.0), (0, 3600.0)], clock=FakeClock())
    assert not limiter.enabled
    assert all(limiter.hit("a") is None for _ in range(1000))


def test_idle_clients_are_swept(monkeypatch):
    import backend.api.rate_limit as rate_limit

    monkeypatch.setattr(rate_limit, "_SWEEP_THRESHOLD", 3)
    clock = FakeClock()
    limiter = SlidingWindowLimiter([(5, 60.0)], clock=clock)
    for key in "abcd":
        limiter.hit(key)
    clock.now += 61
    limiter.hit("e")
    assert set(limiter._hits) == {"e"}


# -- client_key, Retry-After --------------------------------------------------


def test_client_key_uses_the_peer_by_default():
    assert client_key("10.0.0.1", "1.2.3.4", trust_forwarded_for=False) == "10.0.0.1"


def test_client_key_uses_the_rightmost_forwarded_address_when_trusted():
    # The leftmost entry is written by the client and can be forged.
    assert client_key("10.0.0.1", "6.6.6.6, 1.2.3.4", trust_forwarded_for=True) == "1.2.3.4"
    assert client_key("10.0.0.1", None, trust_forwarded_for=True) == "10.0.0.1"
    assert client_key(None, None, trust_forwarded_for=False) == "unknown"


@pytest.mark.parametrize("wait, header", [(0.2, "1"), (1.0, "1"), (29.01, "30")])
def test_retry_after_is_whole_seconds_at_least_one(wait, header):
    assert retry_after_header(wait) == header


# -- Settings -----------------------------------------------------------------


def test_settings_defaults_and_env():
    assert (Settings().tts_limit_per_minute, Settings().attempt_limit_per_hour) == (20, 300)
    s = Settings.from_env(
        {
            "PAULOU_TTS_LIMIT_PER_MINUTE": "0",
            "PAULOU_ATTEMPT_LIMIT_PER_HOUR": "50",
            "PAULOU_TRUST_FORWARDED_FOR": "1",
        }
    )
    assert s.tts_limit_per_minute == 0
    assert s.tts_limit_per_hour == 200
    assert s.attempt_limit_per_hour == 50
    assert s.trust_forwarded_for is True
    assert Settings.from_env({}).trust_forwarded_for is False


# -- Endpoints ----------------------------------------------------------------


def _client(**settings_kw):
    # warm_up=False: the model counts as ready as soon as the app starts.
    client, _ = make_client(warm_up=False, **settings_kw)
    return client


def test_sentence_preparation_is_limited_with_a_retry_after():
    client = _client(tts_limit_per_minute=2)
    with client:
        for text in ("Bonjour", "Salut"):
            assert client.post("/api/sentences", json={"text": text}).status_code == 200
        response = client.post("/api/sentences", json={"text": "Bonjour encore"})
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "rate_limited"
    assert int(response.headers["retry-after"]) >= 1


def test_guide_audio_shares_the_tts_bucket():
    client = _client(tts_limit_per_minute=2)
    with client:
        assert client.post("/api/sentences", json={"text": "Bonjour"}).status_code == 200
        assert client.get("/api/guide/audio", params={"text": "rue"}).status_code == 200
        assert client.get("/api/guide/audio", params={"text": "roue"}).status_code == 429


def test_reference_clips_are_not_limited():
    client = _client(tts_limit_per_minute=1)
    with client:
        sentence_id = client.post("/api/sentences", json={"text": "Bonjour les petits amis"}).json()[
            "sentence_id"
        ]
        for _ in range(5):
            response = client.get(f"/api/sentences/{sentence_id}/audio", params={"chunk": 0})
            assert response.status_code == 200


def test_attempts_have_their_own_bucket():
    client = _client(tts_limit_per_minute=1, attempt_limit_per_minute=2)
    with client:
        sentence_id = client.post("/api/sentences", json={"text": "Bonjour les petits amis"}).json()[
            "sentence_id"
        ]

        def attempt():
            return client.post(
                "/api/attempts",
                data={"sentence_id": sentence_id, "chunk_index": "0"},
                files={"audio": ("a.wav", wav_bytes(1000), "audio/wav")},
            )

        assert [attempt().status_code for _ in range(3)] == [200, 200, 429]


def test_limits_off_when_zero():
    client = _client(tts_limit_per_minute=0, tts_limit_per_hour=0)
    with client:
        codes = {client.post("/api/sentences", json={"text": "Salut"}).status_code for _ in range(25)}
    assert codes == {200}


def test_forwarded_for_is_ignored_unless_trusted():
    # Untrusted: a client cannot dodge the limit by changing the header.
    client = _client(tts_limit_per_minute=1)
    with client:
        assert client.post("/api/sentences", json={"text": "Un"}, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
        assert client.post("/api/sentences", json={"text": "Deux"}, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 429

    # Trusted (behind our proxy): each forwarded client has its own count.
    client = _client(tts_limit_per_minute=1, trust_forwarded_for=True)
    with client:
        assert client.post("/api/sentences", json={"text": "Un"}, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
        assert client.post("/api/sentences", json={"text": "Deux"}, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
