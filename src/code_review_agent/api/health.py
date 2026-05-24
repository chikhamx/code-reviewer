from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "code-review-agent", "version": "0.1.0"}


@router.get("/health/ready")
async def readiness_check():
    return {"status": "ready"}
