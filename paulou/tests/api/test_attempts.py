import threading

import pytest

from tests.api.conftest import FIXTURES, StubPipeline, make_client, wav_bytes


def _post(client, sentence_id, wav=None, **fields):
    data = {"sentence_id": sentence_id, **{k: str(v) for k, v in fields.items()}}
    files = {"audio": ("attempt.wav", wav if wav is not None else wav_bytes(1000), "audio/wav")}
    return client.post("/api/attempts", data=data, files=files)


def test_chunk_attempt_scores_every_unit_of_the_chunk(client, prepared):
    response = _post(client, prepared["sentence_id"], chunk_index=0)

    assert response.status_code == 200
    body = response.json()
    assert (body["chunk_index"], body["unit_id"]) == (0, None)
    assert [r["unit_id"] for r in body["results"]] == ["c0_unit_0", "c0_unit_1"]
    ops = body["results"][0]["ops"]
    assert [o["op_type"] for o in ops] == ["match", "deletion", "match", "match", "match", "match", "match"]
    deleted = ops[1]
    assert deleted["canonical_phoneme"] == "o" and deleted["decoded_phoneme"] is None
    assert deleted["start_ms"] is None


def test_unit_attempt_scores_only_that_unit(client, prepared):
    response = _post(client, prepared["sentence_id"], unit_id="c1_unit_1")

    body = response.json()
    assert response.status_code == 200
    assert (body["chunk_index"], body["unit_id"]) == (None, "c1_unit_1")
    assert [r["unit_id"] for r in body["results"]] == ["c1_unit_1"]


def test_no_scores_are_exposed_while_stats_are_placeholders(client, prepared):
    body = _post(client, prepared["sentence_id"], chunk_index=0).json()

    assert body["calibrated"] is False
    for result in body["results"]:
        assert result["score"] is None
        assert all(op["score"] is None for op in result["ops"])
        assert result["feedback_text"]  # text feedback is still returned


def test_placeholder_stats_are_filled_for_the_phones_in_play(client, prepared, pipeline):
    assert pipeline.phone_stats == {}
    _post(client, prepared["sentence_id"], chunk_index=0)
    assert {"b", "o", "n", "j", "u", "r", "l", "e", "s"} <= pipeline.phone_stats.keys()


def test_real_stats_expose_scores_and_are_not_overwritten():
    client, pipeline = make_client(calibrated=True)
    with client:
        client.app.state.paulou.ready.wait(timeout=5)
        sid = client.post("/api/sentences", json={"text": "Bonjour les amis"}).json()["sentence_id"]
        before = dict(pipeline.phone_stats)

        body = _post(client, sid, chunk_index=0).json()

    assert body["calibrated"] is True
    assert isinstance(body["results"][0]["score"], int)
    assert any(isinstance(op["score"], int) for op in body["results"][0]["ops"])
    assert pipeline.phone_stats == before


def test_recorded_webm_reaches_the_recognizer_as_readable_wav(client, prepared, pipeline):
    webm = (FIXTURES / "browser_recording.webm").read_bytes()
    files = {"audio": ("attempt.webm", webm, "audio/webm")}
    response = client.post(
        "/api/attempts", data={"sentence_id": prepared["sentence_id"], "chunk_index": "0"}, files=files
    )

    assert response.status_code == 200
    sent = pipeline.free_decoder.audios[-1]  # the stub decoder already sf.read() it
    assert sent[:4] == b"RIFF"


def test_exactly_one_target_is_required(client, prepared):
    sid = prepared["sentence_id"]
    for fields in ({}, {"chunk_index": 0, "unit_id": "c0_unit_0"}):
        response = _post(client, sid, **fields)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_target"


def test_unknown_targets_are_404(client, prepared):
    sid = prepared["sentence_id"]
    assert _post(client, "deadbeef", chunk_index=0).json()["detail"]["code"] == "sentence_not_found"
    assert _post(client, sid, chunk_index=7).json()["detail"]["code"] == "chunk_not_found"
    assert _post(client, sid, unit_id="zzz").json()["detail"]["code"] == "unit_not_found"


# Parametrized by a short id, not by the bytes: pytest puts the parameter repr
# in PYTEST_CURRENT_TEST, and a 1 MB value makes every subprocess (ffmpeg)
# fail with "Argument list too long".
BAD_RECORDINGS = {
    "not_audio": (lambda: b"definitely not audio" * 50, "bad_audio"),
    "too_short": (lambda: wav_bytes(100), "audio_too_short"),
    "too_long": (lambda: wav_bytes(46_000, rate=8_000), "audio_too_long"),
}


@pytest.mark.parametrize("name", list(BAD_RECORDINGS))
def test_bad_recordings(client, prepared, name):
    make_wav, code = BAD_RECORDINGS[name]
    response = _post(client, prepared["sentence_id"], wav=make_wav(), chunk_index=0)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code


def test_oversized_upload_is_413(prepared):
    client, _ = make_client(max_audio_bytes=1000)
    with client:
        client.app.state.paulou.ready.wait(timeout=5)
        sid = client.post("/api/sentences", json={"text": "Bonjour les amis"}).json()["sentence_id"]
        response = _post(client, sid, wav=wav_bytes(1000), chunk_index=0)
    assert response.status_code == 413


def test_attempts_before_the_model_is_ready_get_503_not_a_hang():
    pipeline = StubPipeline()
    pipeline.free_decoder.block_warm_up.clear()
    client, _ = make_client(pipeline)
    with client:
        assert pipeline.free_decoder.warm_up_started.wait(timeout=5)
        sid = client.post("/api/sentences", json={"text": "Bonjour les amis"}).json()["sentence_id"]
        response = _post(client, sid, chunk_index=0)
        pipeline.free_decoder.block_warm_up.set()

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "model_not_ready"


def test_scoring_error_is_500_without_detail(client, prepared, pipeline, monkeypatch):
    monkeypatch.setattr(pipeline, "score_attempt", lambda units, audio: (_ for _ in ()).throw(KeyError("ɛ")))
    response = _post(client, prepared["sentence_id"], chunk_index=0)
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "scoring_failed"
    assert "ɛ" not in response.text


def test_concurrent_attempts_are_decoded_one_at_a_time(client, prepared, pipeline):
    pipeline.free_decoder.delay_s = 0.15
    statuses = []
    threads = [
        threading.Thread(
            target=lambda: statuses.append(_post(client, prepared["sentence_id"], chunk_index=0).status_code)
        )
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert statuses == [200] * 4
    assert pipeline.free_decoder.max_active == 1
