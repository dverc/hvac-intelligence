import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.core.constants import SEED_ORG_ID, SEED_ORG_ID_STR


@pytest.mark.asyncio
async def test_scheduling_availability_returns_slots(auth_client, db_session):
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
    response = await auth_client.get(
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
async def test_put_working_hours(auth_client, db_session):
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

    response = await auth_client.put(
        f"/api/v1/scheduling/technicians/{tech.technician_id}/working-hours",
        json=[{"day_of_week": 0, "start_time": "09:00", "end_time": "16:00"}],
    )
    assert response.status_code == 200
    assert response.json()["working_hours"][0]["start_time"] == "09:00"


@pytest.mark.asyncio
async def test_post_override(auth_client, db_session):
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
    response = await auth_client.post(
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
async def test_get_scheduled_jobs(auth_client, seeded_customer):
    today = date.today().isoformat()
    response = await auth_client.get(
        "/api/v1/scheduling/jobs",
        params={"date_from": today, "date_to": today},
    )
    assert response.status_code == 200
    body = response.json()
    assert "items" in body


@pytest.mark.asyncio
async def test_completed_dispatch_jobs_sorted_by_completion_date(
    auth_client, db_session, seeded_customer
):
    from zoneinfo import ZoneInfo

    from app.models.dispatch_job import DispatchJob

    # API filters by completion date in org timezone (default America/Los_Angeles).
    org_tz = ZoneInfo("America/Los_Angeles")
    org_today = datetime.now(org_tz).date()
    completion_newer = datetime.combine(org_today, time(17, 30), tzinfo=org_tz)
    completion_older = datetime.combine(org_today, time(9, 0), tzinfo=org_tz)
    job_newer = "DX-COMP-SORT-NEWER"
    job_older = "DX-COMP-SORT-OLDER"

    customer = seeded_customer["customer"]
    tech_id = uuid.UUID(seeded_customer["technician_id"])

    newer_job = DispatchJob(
        org_id=SEED_ORG_ID,
        job_number=job_newer,
        customer_id=customer.customer_id,
        technician_id=tech_id,
        issue_type="AC_FAILURE",
        job_status="COMPLETED",
        scheduled_window_start=completion_newer - timedelta(hours=2),
        scheduled_window_end=completion_newer,
        actual_completion=completion_newer,
        created_by="TEST",
    )
    older_job = DispatchJob(
        org_id=SEED_ORG_ID,
        job_number=job_older,
        customer_id=customer.customer_id,
        technician_id=tech_id,
        issue_type="MAINTENANCE",
        job_status="COMPLETED",
        scheduled_window_start=completion_older - timedelta(hours=2),
        scheduled_window_end=completion_older,
        actual_completion=completion_older,
        created_by="TEST",
    )
    db_session.add_all([newer_job, older_job])
    await db_session.flush()

    response = await auth_client.get(
        "/api/v1/scheduling/jobs/completed",
        params={"date_from": org_today.isoformat(), "date_to": org_today.isoformat()},
    )
    assert response.status_code == 200
    job_numbers = [item["job_number"] for item in response.json()["items"]]
    assert job_newer in job_numbers, job_numbers
    assert job_older in job_numbers, job_numbers
    assert job_numbers.index(job_newer) < job_numbers.index(job_older)
