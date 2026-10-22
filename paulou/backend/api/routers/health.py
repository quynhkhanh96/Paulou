from fastapi import APIRouter, Depends

from backend.api.dependencies import AppState, get_state
from backend.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(state: AppState = Depends(get_state)) -> HealthResponse:
    if state.warmup_error is not None:
        return HealthResponse(status="error", calibrated=state.calibrated, detail=state.warmup_error)
    status = "ready" if state.ready.is_set() else "warming_up"
    return HealthResponse(status=status, calibrated=state.calibrated)
