from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_db
from app.services.system_health_service import SystemHealthService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def system_health(db: AsyncSession = Depends(get_db)) -> dict:
    service = SystemHealthService(db)
    return await service.get_health()
