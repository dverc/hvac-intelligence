from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.models.support_ticket import SupportTicket
from app.schemas.customer import CustomerUpdate
from app.services.churn_service import ChurnService

_ADDRESS_FIELD_MAP = {
    "line1": "address_line1",
    "line2": "address_line2",
    "city": "city",
    "state": "state",
    "zip": "zip",
}


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if len(digits) == 10:
        return f"+1{digits}"
    return phone.strip()


class CustomerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._churn = ChurnService(db)

    async def lookup_by_phone(self, phone: str) -> Optional[Customer]:
        normalized = normalize_phone(phone)
        digits = re.sub(r"\D", "", normalized)
        stmt = select(Customer).where(
            or_(
                Customer.phone_primary == phone,
                Customer.phone_primary == normalized,
                Customer.phone_secondary == phone,
                Customer.phone_secondary == normalized,
                func.regexp_replace(Customer.phone_primary, r"\D", "", "g") == digits,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, customer_id: uuid.UUID) -> Optional[Customer]:
        stmt = (
            select(Customer)
            .where(Customer.customer_id == customer_id)
            .options(
                selectinload(Customer.equipment),
                selectinload(Customer.dispatch_jobs),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_customer(
        self, customer_id: uuid.UUID, payload: CustomerUpdate
    ) -> Optional[Customer]:
        customer = await self.get_by_id(customer_id)
        if customer is None:
            return None

        data = payload.model_dump(exclude_unset=True)
        address_patch = data.pop("address", None)

        if address_patch is not None:
            for key, value in address_patch.items():
                column = _ADDRESS_FIELD_MAP[key]
                setattr(customer, column, value)

        for field, value in data.items():
            if field == "phone_primary" and value is not None:
                value = normalize_phone(value)
            if field == "phone_secondary" and value is not None:
                value = normalize_phone(value)
            if field == "contract_value_usd" and value is not None:
                value = Decimal(str(value))
            setattr(customer, field, value)

        await self.db.commit()
        await self.db.refresh(customer)
        return await self.get_by_id(customer_id)

    async def get_by_email(self, email: str) -> Optional[Customer]:
        stmt = select(Customer).where(func.lower(Customer.email) == email.lower())
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def lookup(
        self, lookup_method: str, lookup_value: str
    ) -> Optional[Customer]:
        if lookup_method == "phone":
            return await self.lookup_by_phone(lookup_value)
        if lookup_method == "customer_id":
            return await self.get_by_id(uuid.UUID(lookup_value))
        if lookup_method == "email":
            return await self.get_by_email(lookup_value)
        return None

    async def _equipment_with_computed_age(
        self, customer_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        rows = await self.db.execute(
            text(
                """
                SELECT equipment_id, make, model, equipment_type, install_date,
                       last_service_date, warranty_expiry, service_count,
                       known_issues, efficiency_rating, age_years_computed
                FROM v_equipment_computed
                WHERE customer_id = :customer_id
                ORDER BY last_service_date DESC NULLS LAST
                """
            ),
            {"customer_id": customer_id},
        )
        return [dict(row._mapping) for row in rows]

    async def _open_tickets(self, customer_id: uuid.UUID) -> list[dict[str, Any]]:
        stmt = (
            select(SupportTicket)
            .where(
                SupportTicket.customer_id == customer_id,
                SupportTicket.status.in_(("OPEN", "IN_PROGRESS")),
            )
            .order_by(SupportTicket.created_at.desc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            {
                "ticket_id": str(t.ticket_id),
                "ticket_type": t.ticket_type,
                "subject": t.subject,
                "priority": t.priority,
                "status": t.status,
                "created_at": t.created_at.isoformat(),
            }
            for t in rows
        ]

    async def _recent_jobs(self, customer_id: uuid.UUID, limit: int = 5) -> list[DispatchJob]:
        stmt: Select[tuple[DispatchJob]] = (
            select(DispatchJob)
            .where(DispatchJob.customer_id == customer_id)
            .order_by(DispatchJob.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def build_customer_profile(self, customer: Customer) -> dict[str, Any]:
        equipment_rows = await self._equipment_with_computed_age(customer.customer_id)
        churn = await self._churn.get_latest_score(str(customer.customer_id))
        jobs = await self._recent_jobs(customer.customer_id)
        open_tickets = await self._open_tickets(customer.customer_id)

        return {
            "customer_id": str(customer.customer_id),
            "external_id": customer.external_id,
            "full_name": customer.full_name,
            "phone_primary": customer.phone_primary,
            "email": customer.email,
            "account_status": customer.account_status,
            "customer_since": customer.customer_since.isoformat(),
            "contract_type": customer.contract_type,
            "contract_value_usd": float(customer.contract_value_usd)
            if customer.contract_value_usd is not None
            else None,
            "address": {
                "line1": customer.address_line1,
                "line2": customer.address_line2,
                "city": customer.city,
                "state": customer.state,
                "zip": customer.zip,
            },
            "equipment": [
                {
                    "equipment_id": str(row["equipment_id"]),
                    "make": row["make"],
                    "model": row["model"],
                    "equipment_type": row["equipment_type"],
                    "age_years": float(row["age_years_computed"])
                    if row["age_years_computed"] is not None
                    else None,
                    "last_service_date": row["last_service_date"].isoformat()
                    if row["last_service_date"]
                    else None,
                    "warranty_expiry": row["warranty_expiry"].isoformat()
                    if row["warranty_expiry"]
                    else None,
                    "known_issues": row["known_issues"] or [],
                }
                for row in equipment_rows
            ],
            "open_tickets": open_tickets,
            "service_history_summary": {
                "total_jobs": len(jobs),
                "recent_jobs": [
                    {
                        "job_number": job.job_number,
                        "issue_type": job.issue_type,
                        "job_status": job.job_status,
                        "priority": job.priority,
                        "scheduled_window_start": job.scheduled_window_start.isoformat()
                        if job.scheduled_window_start
                        else None,
                    }
                    for job in jobs
                ],
            },
            "churn": churn,
        }

    async def get_customer_info(
        self, lookup_method: str, lookup_value: str
    ) -> dict[str, Any]:
        customer = await self.lookup(lookup_method, lookup_value)
        if customer is None:
            return {"found": False, "message": "Customer not found"}
        profile = await self.build_customer_profile(customer)
        profile["found"] = True
        return profile

    async def get_call_context(self, phone: str, call_id: str) -> dict[str, str]:
        customer = await self.lookup_by_phone(phone)
        if customer is None:
            return {
                "greeting": (
                    "Thank you for calling HVAC Intelligence. "
                    "I don't have an account linked to this number yet — how can I help you today?"
                ),
                "system_prompt_injection": (
                    "CALLER STATUS: Unknown phone number (no CRM match).\n"
                    f"call_id: {call_id}\n"
                    "Collect name, address, and issue details. Offer to create a service request."
                ),
            }

        profile = await self.build_customer_profile(customer)
        first_name = customer.full_name.split()[0]
        equipment = profile["equipment"]
        primary_unit = equipment[0] if equipment else None
        churn = profile["churn"]
        risk_tier = churn.get("risk_tier", "LOW")
        churn_prob = churn.get("churn_probability", 0.0)

        equipment_line = ""
        if primary_unit:
            age = primary_unit.get("age_years")
            age_str = f"{age:.0f} years old" if age is not None else "age unknown"
            equipment_line = (
                f"{primary_unit['make']} {primary_unit['model']} ({age_str}), "
                f"last service: {primary_unit.get('last_service_date') or 'no record on file'}"
            )

        retention_block = ""
        if risk_tier in {"HIGH", "CRITICAL"}:
            retention_block = (
                f"\n⚠️ {risk_tier} CHURN RISK (probability {churn_prob:.0%}): "
                "Apply retention protocol. Offer priority dispatch, empathy, and proactive resolution. "
                "Avoid transfers unless safety-critical."
            )

        greeting = f"Hi {first_name}, thank you for calling HVAC Intelligence."
        if equipment_line:
            greeting += f" I see your {equipment_line.split(',')[0]} on file."
        greeting += " How can I help you today?"

        system_prompt = (
            f"CUSTOMER CONTEXT (call_id={call_id}):\n"
            f"- Name: {customer.full_name}\n"
            f"- customer_id: {customer.customer_id}\n"
            f"- Account: {customer.account_status} | Contract: {customer.contract_type or 'N/A'}\n"
        )
        if equipment_line:
            system_prompt += f"- Primary equipment: {equipment_line}\n"
        system_prompt += (
            f"- Open tickets: {len(profile['open_tickets'])}\n"
            f"- Churn risk: {risk_tier} ({churn_prob:.1%})\n"
            f"{retention_block}\n"
            "Use tools to schedule dispatch, query churn, and pull equipment details as needed."
        )

        return {
            "greeting": greeting,
            "system_prompt_injection": system_prompt.strip(),
            "customer_id": str(customer.customer_id),
        }

