import io
import threading

from pydub import AudioSegment

from tests.api.conftest import StubPipeline, make_client


def _mp3_duration_ms(data: bytes) -> int:
    return len(AudioSegment.from_file(io.BytesIO(data), format="mp3"))


def test_create_sentence_returns_chunks_and_units(client, pipeline):
    response = client.post("/api/sentences", json={"text": "Bonjour les petits amis"})

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Bonjour les petits amis"
    assert [c["text"] for c in body["chunks"]] == ["Bonjour les", "petits amis"]
    assert [c["index"] for c in body["chunks"]] == [0, 1]
    unit = body["chunks"][0]["units"][0]
    assert unit == {
        "id": "c0_unit_0", "type": "single", "words": ["Bonjour"],
        "phonemes": list("bonjour"), "ipa": "bonjour",
        "liaison_consonant": None, "scoring_focus": "phoneme_accuracy",
    }
    assert pipeline.tts_calls == [("Bonjour les petits amis", 1.0)]


def test_response_does_not_leak_core_only_fields(prepared):
    unit = prepared["chunks"][0]["units"][0]
    assert "syllables" not in unit and "note" not in unit


def test_same_sentence_is_prepared_once_whatever_the_spacing(client, pipeline):
    a = client.post("/api/sentences", json={"text": "Bonjour les amis"}).json()
    b = client.post("/api/sentences", json={"text": "  Bonjour   les amis "}).json()

    assert a["sentence_id"] == b["sentence_id"]
    assert pipeline.analyze_calls == ["Bonjour les amis"]
    assert len(pipeline.tts_calls) == 1


def test_double_submit_in_parallel_shares_one_preparation():
    pipeline = StubPipeline()
    pipeline.analyze_delay_s = 0.3
    client, _ = make_client(pipeline)
    with client:
        client.app.state.paulou.ready.wait(timeout=5)
        results = []
        threads = [
            threading.Thread(
                target=lambda: results.append(client.post("/api/sentences", json={"text": "Bonjour les amis"}))
            )
            for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert [r.status_code for r in results] == [200] * 4
    assert len(pipeline.analyze_calls) == 1


def test_empty_and_blank_text_are_rejected(client):
    assert client.post("/api/sentences", json={"text": ""}).status_code == 422
    blank = client.post("/api/sentences", json={"text": "   \n "})
    assert blank.status_code == 422
    assert blank.json()["detail"]["code"] == "empty_text"


def test_too_long_text_is_rejected(client, pipeline):
    response = client.post("/api/sentences", json={"text": "a " * 400})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "text_too_long"
    assert pipeline.analyze_calls == []


def test_text_without_practicable_content_is_rejected(client):
    response = client.post("/api/sentences", json={"text": "... ?!"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "no_content"


def test_text_the_voice_spells_differently_gets_an_actionable_error(client):
    response = client.post("/api/sentences", json={"text": "J'ai 3 pommes"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "text_not_supported"
    assert "words" in detail["message"]


def test_failures_are_502_without_internal_detail_and_are_not_cached(client, pipeline):
    pipeline.fail_analyze = RuntimeError("GEMINI_API_KEY is not set")
    response = client.post("/api/sentences", json={"text": "Bonjour les amis"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "preparation_failed"
    assert "GEMINI" not in response.text

    pipeline.fail_analyze = None
    assert client.post("/api/sentences", json={"text": "Bonjour les amis"}).status_code == 200


def test_tts_failure_is_502(client, pipeline):
    pipeline.fail_tts = ConnectionError("403")
    response = client.post("/api/sentences", json={"text": "Bonjour les amis"})
    assert response.status_code == 502
    assert "403" not in response.text


# --- audio ------------------------------------------------------------------


def test_whole_sentence_audio_is_mp3(client, prepared):
    response = client.get(f"/api/sentences/{prepared['sentence_id']}/audio")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert abs(_mp3_duration_ms(response.content) - 1600) < 150  # 4 words x 400 ms


def test_chunk_clip_is_shorter_than_the_sentence(client, prepared):
    sid = prepared["sentence_id"]
    whole = client.get(f"/api/sentences/{sid}/audio").content
    clip = client.get(f"/api/sentences/{sid}/audio", params={"chunk": 1})

    assert clip.status_code == 200
    assert _mp3_duration_ms(clip.content) < _mp3_duration_ms(whole)
    assert abs(_mp3_duration_ms(clip.content) - (800 + 100)) < 150  # 2 words + 2x50 ms padding


def test_unit_clip(client, prepared):
    response = client.get(
        f"/api/sentences/{prepared['sentence_id']}/audio", params={"unit": "c1_unit_0"}
    )
    assert response.status_code == 200
    assert abs(_mp3_duration_ms(response.content) - (380 + 100)) < 150


def test_slow_pass_is_made_lazily_once_at_rate_0_7(client, prepared, pipeline):
    sid = prepared["sentence_id"]
    assert len(pipeline.tts_calls) == 1

    slow = client.get(f"/api/sentences/{sid}/audio", params={"speed": "slow"})
    client.get(f"/api/sentences/{sid}/audio", params={"speed": "slow", "chunk": 0})
    client.get(f"/api/sentences/{sid}/audio", params={"speed": "slow", "unit": "c0_unit_0"})

    assert pipeline.tts_calls[1:] == [("Bonjour les petits amis", 0.7)]
    normal = client.get(f"/api/sentences/{sid}/audio").content
    assert _mp3_duration_ms(slow.content) > _mp3_duration_ms(normal)


def test_repeat_clip_request_does_not_cut_again(client, prepared, monkeypatch):
    sid = prepared["sentence_id"]
    cuts = []
    original = client.app.state.paulou.pipeline.slice_reference
    monkeypatch.setattr(
        client.app.state.paulou.pipeline, "slice_reference",
        lambda ref, span: cuts.append(span) or original(ref, span),
    )
    client.get(f"/api/sentences/{sid}/audio", params={"chunk": 0})
    client.get(f"/api/sentences/{sid}/audio", params={"chunk": 0})
    assert len(cuts) == 1


def test_audio_errors(client, prepared):
    sid = prepared["sentence_id"]
    missing = client.get("/api/sentences/deadbeef/audio")
    assert (missing.status_code, missing.json()["detail"]["code"]) == (404, "sentence_not_found")

    assert client.get(f"/api/sentences/{sid}/audio", params={"chunk": 9}).status_code == 404
    assert client.get(f"/api/sentences/{sid}/audio", params={"unit": "nope"}).status_code == 404
    both = client.get(f"/api/sentences/{sid}/audio", params={"chunk": 0, "unit": "c0_unit_0"})
    assert both.status_code == 422
    assert client.get(f"/api/sentences/{sid}/audio", params={"speed": "warp"}).status_code == 422
    assert client.get(f"/api/sentences/{sid}/audio", params={"chunk": -1}).status_code == 422
