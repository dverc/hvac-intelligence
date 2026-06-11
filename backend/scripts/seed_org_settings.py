#!/usr/bin/env python3
"""Seed org_settings for the demo organization (idempotent)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from sqlalchemy import select  # noqa: E402

from app.core.constants import SEED_ORG_ID  # noqa: E402
from app.core.database import get_session_factory  # noqa: E402
from app.models.org_settings import OrgSettings  # noqa: E402


async def main() -> None:
    async with get_session_factory()() as session:
        existing = (
            await session.execute(
                select(OrgSettings).where(OrgSettings.org_id == SEED_ORG_ID)
            )
        ).scalar_one_or_none()
        if existing:
            print("Already exists")
            return

        session.add(
            OrgSettings(
                org_id=SEED_ORG_ID,
                display_name="HVAC Intelligence Demo",
                agent_greeting=(
                    "Hi, thanks for calling! This is an AI virtual assistant. "
                    "How can I help you today?"
                ),
                business_hours_start=8,
                business_hours_end=18,
                timezone="America/Los_Angeles",
                outbound_enabled=False,
                onboarding_completed=True,
                onboarding_step=5,
            )
        )
        await session.commit()
    print("Org settings seeded")


if __name__ == "__main__":
    asyncio.run(main())
