from tests.api.conftest import StubPipeline, make_client


def test_health_reports_warming_up_until_the_decoder_is_loaded():
    pipeline = StubPipeline()
    pipeline.free_decoder.block_warm_up.clear()
    client, _ = make_client(pipeline)
    with client:
        assert pipeline.free_decoder.warm_up_started.wait(timeout=5)
        assert client.get("/api/health").json() == {
            "status": "warming_up", "calibrated": False, "detail": None,
        }

        pipeline.free_decoder.block_warm_up.set()
        client.app.state.paulou.ready.wait(timeout=5)
        assert client.get("/api/health").json()["status"] == "ready"


def test_warm_up_runs_exactly_one_decode_at_startup():
    pipeline = StubPipeline()
    client, _ = make_client(pipeline)
    with client:
        client.app.state.paulou.ready.wait(timeout=5)
    assert pipeline.free_decoder.warm_up_calls == 1


def test_health_reports_calibrated_flag():
    client, _ = make_client(calibrated=True)
    with client:
        client.app.state.paulou.ready.wait(timeout=5)
        assert client.get("/api/health").json()["calibrated"] is True


def test_a_decoder_that_cannot_be_built_is_reported_as_error():
    class Broken(StubPipeline):
        @property
        def free_decoder(self):
            raise RuntimeError("no weights")

        @free_decoder.setter
        def free_decoder(self, value):
            pass

    client, _ = make_client(Broken())
    with client:
        deadline_state = client.app.state.paulou
        for _ in range(50):
            if deadline_state.warmup_error:
                break
            import time

            time.sleep(0.05)
        body = client.get("/api/health").json()
    assert body["status"] == "error"
    assert "no weights" in body["detail"]


def test_a_failing_warm_up_decode_still_becomes_ready():
    pipeline = StubPipeline()

    def failing_decode(audio):
        raise RuntimeError("empty input")

    pipeline.free_decoder.decode = failing_decode
    client, _ = make_client(pipeline)
    with client:
        assert client.app.state.paulou.ready.wait(timeout=5)
        assert client.get("/api/health").json()["status"] == "ready"
