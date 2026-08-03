from fastapi import APIRouter
from app.api.auth import router as auth_router
from app.api.rv import router as rv_router
from app.schemas.health import HealthResponse

router = APIRouter()
router.include_router(auth_router)
router.include_router(rv_router)

@router.get('/health', response_model=HealthResponse)
def health():
  return HealthResponse(status="ok", service="Trading Platform API")

@router.get('/version')
def version():
  return {"version": "1.0.0"}
