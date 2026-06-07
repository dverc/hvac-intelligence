from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs")
async def list_audit_logs(
    org_id: str = Query(...),
    resource_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(AuditLog).where(AuditLog.org_id == org_id)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    rows = (
        await db.execute(
            stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()

    return {
        "org_id": org_id,
        "total": int(total),
        "items": [
            {
                "id": str(row.id),
                "org_id": row.org_id,
                "actor": row.actor,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "ip_address": row.ip_address,
                "call_id": row.call_id,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }
