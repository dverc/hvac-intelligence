"""Audit trail for create, update, and delete actions on tenant resources."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

AUDIT_CREATE = "CREATE"
AUDIT_UPDATE = "UPDATE"
AUDIT_DELETE = "DELETE"
AUDIT_TOOL_CALL = "TOOL_CALL"

ACTOR_SYSTEM = "system"
ACTOR_VAPI = "vapi_agent"
ACTOR_API = "api_key"


async def log_action(
    db: AsyncSession,
    org_id: str,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
    call_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Persist an audit log entry. Never raises — failures are logged only."""
    try:
        entry = AuditLog(
            org_id=org_id,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            old_value=old_value,
            new_value=new_value,
            call_id=call_id,
            ip_address=ip_address,
        )
        db.add(entry)
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.exception(
            "Failed to write audit log | org_id=%s action=%s resource_type=%s resource_id=%s",
            org_id,
            action,
            resource_type,
            resource_id,
        )
