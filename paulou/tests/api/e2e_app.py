"""ASGI app with the stub pipeline, for the browser smoke test
(frontend/e2e/smoke.mjs). NOT used by pytest. Run from the package directory:

    uvicorn tests.api.e2e_app:app --port 8000
"""

from backend.api.main import create_app
from backend.api.settings import Settings
from tests.api.conftest import LETTER_STATS, StubPipeline

app = create_app(StubPipeline(phone_stats=dict(LETTER_STATS)), Settings(), calibrated=False, warm_up=True)
