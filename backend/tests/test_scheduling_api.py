import uuid
from datetime import date, time, timedelta

import pytest

from app.core.constants import SEED_ORG_ID, SEED_ORG_ID_STR


@pytest.mark.asyncio
async def test_scheduling_availability_returns_slots(api_client, db_session):
    from app.models.technician import Technician
    from app.models.technician_schedule import TechnicianSchedule

    tech = Technician(
        org_id=SEED_ORG_ID,
        employee_number=f"T-API-{uuid.uuid4().hex[:6]}",
        full_name="API Tech",
        hire_date=date(2020, 1, 1),
        employment_status="ACTIVE",
    )
    db_session.add(tech)
    await db_session.flush()
    for dow in range(5):
        db_session.add(
            TechnicianSchedule(
                org_id=SEED_ORG_ID,
                technician_id=tech.technician_id,
                day_of_week=dow,
                start_time=time(8, 0),
                end_time=time(17, 0),
                is_active=True,
                effective_from=date.today(),
            )
        )
    await db_session.commit()

    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=2)
    response = await api_client.get(
        "/api/v1/scheduling/availability",
        params={
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1


@pytest.mark.asyncio
async def test_put_working_hours(api_client, db_session):
    from app.models.technician import Technician

    tech = Technician(
        org_id=SEED_ORG_ID,
        employee_number=f"T-WH-{uuid.uuid4().hex[:6]}",
        full_name="Hours Tech",
        hire_date=date(2020, 1, 1),
        employment_status="ACTIVE",
    )
    db_session.add(tech)
    await db_session.commit()

    response = await api_client.put(
        f"/api/v1/scheduling/technicians/{tech.technician_id}/working-hours",
        json=[{"day_of_week": 0, "start_time": "09:00", "end_time": "16:00"}],
    )
    assert response.status_code == 200
    assert response.json()["working_hours"][0]["start_time"] == "09:00"


@pytest.mark.asyncio
async def test_post_override(api_client, db_session):
    from app.models.technician import Technician

    tech = Technician(
        org_id=SEED_ORG_ID,
        employee_number=f"T-OV-{uuid.uuid4().hex[:6]}",
        full_name="Override Tech",
        hire_date=date(2020, 1, 1),
        employment_status="ACTIVE",
    )
    db_session.add(tech)
    await db_session.commit()

    override_date = (date.today() + timedelta(days=5)).isoformat()
    response = await api_client.post(
        f"/api/v1/scheduling/technicians/{tech.technician_id}/overrides",
        json={
            "override_date": override_date,
            "override_type": "day_off",
            "reason": "Vacation",
        },
    )
    assert response.status_code == 200
    assert response.json()["override_type"] == "day_off"


@pytest.mark.asyncio
async def test_get_scheduled_jobs(api_client, seeded_customer):
    today = date.today().isoformat()
    response = await api_client.get(
        "/api/v1/scheduling/jobs",
        params={"date_from": today, "date_to": today},
    )
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
