import pytest

from tests.api.conftest import make_client


def test_returns_mp3_for_a_word_and_passes_normal_rate():
    client, pipeline = make_client()
    response = client.get("/api/guide/audio", params={"text": "ici"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert len(response.content) > 0
    assert pipeline.synthesize_text_calls == [("ici", 1.0)]


def test_slow_uses_the_configured_slow_rate():
    client, pipeline = make_client()
    client.get("/api/guide/audio", params={"text": "ici", "speed": "slow"})
    assert pipeline.synthesize_text_calls == [("ici", 0.7)]


@pytest.mark.parametrize("text", ["l'ami", "les amis", "grand homme", "c'est", "peut-être", "école", "œuf"])
def test_accepts_french_words_and_short_phrases(text):
    client, pipeline = make_client()
    assert client.get("/api/guide/audio", params={"text": text}).status_code == 200
    assert pipeline.synthesize_text_calls[0][0] == text


def test_whitespace_is_normalized():
    client, pipeline = make_client()
    client.get("/api/guide/audio", params={"text": "  les   amis "})
    assert pipeline.synthesize_text_calls[0][0] == "les amis"


@pytest.mark.parametrize(
    "text",
    ["", "   ", "42", "a" * 41, "hello, world", "<ssml>", "/si/", "-ici", "ici-", "a  -  b"],
)
def test_rejects_anything_that_is_not_a_short_word_or_phrase(text):
    client, pipeline = make_client()
    response = client.get("/api/guide/audio", params={"text": text})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_guide_text"
    assert pipeline.synthesize_text_calls == []


def test_text_is_required():
    client, _ = make_client()
    assert client.get("/api/guide/audio").status_code == 422


def test_a_tts_failure_is_502_without_detail():
    client, pipeline = make_client()
    pipeline.fail_synthesize_text = RuntimeError("secret internals")
    response = client.get("/api/guide/audio", params={"text": "ici"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "audio_unavailable"
    assert "secret" not in response.text
