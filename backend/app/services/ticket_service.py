from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support_ticket import SupportTicket


class TicketService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_open_tickets(self, customer_id: uuid.UUID) -> list[dict[str, Any]]:
        stmt = (
            select(SupportTicket)
            .where(
                SupportTicket.customer_id == customer_id,
                SupportTicket.status.in_(("OPEN", "IN_PROGRESS")),
            )
            .order_by(SupportTicket.created_at.desc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_serialize_ticket(t) for t in rows]

    async def create_ticket(
        self,
        customer_id: uuid.UUID,
        ticket_type: str,
        subject: str,
        description: str,
        priority: str,
        preferred_callback_time: Optional[str] = None,
        call_transcript_id: Optional[uuid.UUID] = None,
        created_by: str = "VOICE_AGENT",
    ) -> dict[str, Any]:
        ticket = SupportTicket(
            customer_id=customer_id,
            call_transcript_id=call_transcript_id,
            ticket_type=ticket_type,
            subject=subject,
            description=description,
            priority=priority,
            status="OPEN",
            preferred_callback_time=preferred_callback_time,
            created_by=created_by,
        )
        self.db.add(ticket)
        await self.db.flush()
        return _serialize_ticket(ticket)


def _serialize_ticket(ticket: SupportTicket) -> dict[str, Any]:
    return {
        "ticket_id": str(ticket.ticket_id),
        "customer_id": str(ticket.customer_id),
        "call_transcript_id": str(ticket.call_transcript_id)
        if ticket.call_transcript_id
        else None,
        "ticket_type": ticket.ticket_type,
        "subject": ticket.subject,
        "description": ticket.description,
        "priority": ticket.priority,
        "status": ticket.status,
        "preferred_callback_time": ticket.preferred_callback_time,
        "created_by": ticket.created_by,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
    }
