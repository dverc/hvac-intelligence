from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.call_transcript import CallTranscript
from app.schemas.transcript import TranscriptDetail, transcript_to_detail

router = APIRouter(prefix="/calls", tags=["calls"])


@router.get("/{call_id}", response_model=TranscriptDetail)
async def get_call_detail(
    call_id: str,
    db: AsyncSession = Depends(get_db),
) -> TranscriptDetail:
    row = (
        await db.execute(
            select(CallTranscript).where(CallTranscript.call_id == call_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Call transcript not found for call_id={call_id}",
        )
    return transcript_to_detail(row)
