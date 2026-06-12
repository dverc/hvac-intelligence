from __future__ import annotations

import os
import re
import secrets
import uuid
from datetime import date

from passlib.context import CryptContext
from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.org_settings import OrgSettings
from app.models.organization import Organization
from app.models.technician import Technician
from app.models.user import User
from app.schemas.admin import (
    AdminOrganizationCreate,
    AdminOrganizationCreateResponse,
    AdminOrganizationDetail,
    AdminOrganizationListItem,
    AdminOrganizationUpdate,
    AdminTechnicianCreate,
    AdminTechnicianOut,
    AdminUserCreate,
    AdminUserCreateResponse,
    AdminUserOut,
    OnboardingProgressOut,
    OnboardingProgressUpdate,
    OrgSettingsOut,
    ProvisionResponse,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return (slug.strip("-") or "org")[:100]


def _org_status(org: Organization, settings: OrgSettings | None) -> str:
    if not org.is_active:
        return "INACTIVE"
    if settings is None or not settings.onboarding_completed:
        return "TRIAL"
    return "ACTIVE"


def _settings_out(settings: OrgSettings) -> OrgSettingsOut:
    return OrgSettingsOut.model_validate(settings)


def _sync_settings_to_org_jsonb(org: Organization, settings: OrgSettings) -> None:
    """Mirror org_settings fields into organizations.settings JSONB for legacy readers."""
    merged = dict(org.settings or {})
    if settings.display_name:
        merged["outbound_display_name"] = settings.display_name
    merged["outbound_enabled"] = settings.outbound_enabled
    merged["outbound_disclosure_style"] = settings.outbound_disclosure_style
    merged["timezone"] = settings.timezone
    org.settings = merged


class AdminOnboardingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _unique_slug(self, base_slug: str) -> str:
        slug = base_slug
        suffix = 2
        while True:
            existing = (
                await self.db.execute(
                    select(Organization).where(Organization.slug == slug)
                )
            ).scalar_one_or_none()
            if existing is None:
                return slug
            slug = f"{base_slug}-{suffix}"[:100]
            suffix += 1

    async def _fetch_organization(self, org_id: uuid.UUID) -> Organization | None:
        return (
            await self.db.execute(
                select(Organization)
                .where(Organization.org_id == org_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    async def _get_settings(self, org_id: uuid.UUID) -> OrgSettings | None:
        return (
            await self.db.execute(
                select(OrgSettings)
                .where(OrgSettings.org_id == org_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    async def _ensure_settings(self, org: Organization) -> OrgSettings:
        settings = await self._get_settings(org.org_id)
        if settings is None:
            settings = OrgSettings(
                org_id=org.org_id,
                display_name=org.org_name,
                phone_display=org.business_phone,
            )
            self.db.add(settings)
            await self.db.flush()
        return settings

    async def _user_count(self, org_id: uuid.UUID) -> int:
        return int(
            (
                await self.db.execute(
                    select(func.count(User.id)).where(User.org_id == str(org_id))
                )
            ).scalar_one()
            or 0
        )

    async def _technician_count(self, org_id: uuid.UUID) -> int:
        return int(
            (
                await self.db.execute(
                    select(func.count(Technician.technician_id)).where(
                        Technician.org_id == org_id
                    )
                )
            ).scalar_one()
            or 0
        )

    async def list_organizations(self) -> list[AdminOrganizationListItem]:
        user_counts = (
            select(
                User.org_id.label("org_id_str"),
                func.count(User.id).label("user_count"),
            )
            .group_by(User.org_id)
            .subquery()
        )
        technician_counts = (
            select(
                Technician.org_id.label("org_id"),
                func.count(Technician.technician_id).label("technician_count"),
            )
            .group_by(Technician.org_id)
            .subquery()
        )
        rows = (
            await self.db.execute(
                select(
                    Organization,
                    OrgSettings,
                    func.coalesce(user_counts.c.user_count, 0),
                    func.coalesce(technician_counts.c.technician_count, 0),
                )
                .outerjoin(OrgSettings, OrgSettings.org_id == Organization.org_id)
                .outerjoin(
                    user_counts,
                    user_counts.c.org_id_str == cast(Organization.org_id, String),
                )
                .outerjoin(
                    technician_counts,
                    technician_counts.c.org_id == Organization.org_id,
                )
                .order_by(Organization.org_name)
            )
        ).all()

        items: list[AdminOrganizationListItem] = []
        for org, settings, user_count, technician_count in rows:
            items.append(
                AdminOrganizationListItem(
                    org_id=org.org_id,
                    org_name=org.org_name,
                    slug=org.slug,
                    industry=org.industry,
                    plan_tier=org.plan_tier,
                    is_active=org.is_active,
                    status=_org_status(org, settings),
                    user_count=int(user_count),
                    technician_count=int(technician_count),
                    onboarding_completed=settings.onboarding_completed
                    if settings
                    else False,
                    onboarding_step=settings.onboarding_step if settings else 0,
                    display_name=settings.display_name if settings else org.org_name,
                    created_at=org.created_at,
                )
            )
        return items

    async def create_organization(
        self, body: AdminOrganizationCreate
    ) -> AdminOrganizationCreateResponse:
        slug = await self._unique_slug(_slugify(body.company_name))
        org_json_settings: dict[str, str] = {"timezone": "America/Los_Angeles"}
        if body.admin_first_name.strip():
            org_json_settings["admin_first_name"] = body.admin_first_name.strip()
        if body.admin_last_name.strip():
            org_json_settings["admin_last_name"] = body.admin_last_name.strip()
        org = Organization(
            org_name=body.company_name.strip(),
            slug=slug,
            industry=body.industry,
            plan_tier=body.plan_tier,
            is_active=True,
            settings=org_json_settings,
        )
        self.db.add(org)
        await self.db.flush()

        settings = OrgSettings(
            org_id=org.org_id,
            display_name=body.company_name.strip(),
            onboarding_step=0,
            onboarding_completed=False,
        )
        self.db.add(settings)
        await self.db.flush()

        temp_password: str | None = None
        admin_user_id: str | None = None
        email = body.admin_email.strip().lower()
        if email:
            temp_password = secrets.token_urlsafe(12)
            user = User(
                org_id=str(org.org_id),
                email=email,
                hashed_password=pwd_context.hash(temp_password),
                role="admin",
            )
            self.db.add(user)
            await self.db.flush()
            admin_user_id = str(user.id)

        await self.db.refresh(org)
        await self.db.refresh(settings)
        return AdminOrganizationCreateResponse(
            org_id=org.org_id,
            org_name=org.org_name,
            slug=org.slug,
            settings=_settings_out(settings),
            admin_user_id=admin_user_id,
            temporary_password=temp_password,
        )

    async def get_organization(self, org_id: uuid.UUID) -> AdminOrganizationDetail:
        org = await self._fetch_organization(org_id)
        if org is None:
            raise ValueError("Organization not found")
        await self.db.refresh(org)
        settings = await self._get_settings(org_id)
        if settings is not None:
            await self.db.refresh(settings)
        return AdminOrganizationDetail(
            org_id=org.org_id,
            org_name=org.org_name,
            slug=org.slug,
            industry=org.industry,
            business_phone=org.business_phone,
            plan_tier=org.plan_tier,
            is_active=org.is_active,
            status=_org_status(org, settings),
            user_count=await self._user_count(org_id),
            technician_count=await self._technician_count(org_id),
            settings=_settings_out(settings) if settings else None,
            created_at=org.created_at,
            updated_at=org.updated_at,
        )

    async def update_organization(
        self, org_id: uuid.UUID, body: AdminOrganizationUpdate
    ) -> AdminOrganizationDetail:
        org = await self.db.get(Organization, org_id)
        if org is None:
            raise ValueError("Organization not found")
        settings = await self._ensure_settings(org)

        if body.org_name is not None:
            org.org_name = body.org_name
        if body.industry is not None:
            org.industry = body.industry
        if body.plan_tier is not None:
            org.plan_tier = body.plan_tier
        if body.is_active is not None:
            org.is_active = body.is_active
        if body.business_phone is not None:
            org.business_phone = body.business_phone

        for field in (
            "display_name",
            "phone_display",
            "address_line1",
            "city",
            "state",
            "zip",
            "agent_greeting",
            "agent_name",
            "business_hours_start",
            "business_hours_end",
            "timezone",
            "vapi_assistant_id",
            "vapi_phone_number_id",
            "vapi_phone_number",
            "outbound_enabled",
            "outbound_disclosure_style",
            "max_outbound_attempts",
            "onboarding_step",
        ):
            value = getattr(body, field)
            if value is not None:
                setattr(settings, field, value)

        if body.display_name is not None:
            org.org_name = body.display_name
            org.agent_name = body.display_name
        if body.agent_name is not None:
            org.agent_name = body.agent_name

        if body.vapi_assistant_id is not None:
            org.vapi_assistant_id = body.vapi_assistant_id
        if body.vapi_phone_number_id is not None:
            org.vapi_phone_number_id = body.vapi_phone_number_id
        if body.vapi_phone_number is not None:
            org.vapi_phone_number = body.vapi_phone_number

        _sync_settings_to_org_jsonb(org, settings)

        await self.db.flush()
        await self.db.refresh(org)
        await self.db.refresh(settings)
        return await self.get_organization(org_id)

    async def create_user(
        self, org_id: uuid.UUID, body: AdminUserCreate
    ) -> AdminUserCreateResponse:
        org = await self.db.get(Organization, org_id)
        if org is None:
            raise ValueError("Organization not found")

        email = body.email.strip().lower()
        existing = (
            await self.db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError("Email already registered")

        temp_password = secrets.token_urlsafe(12)
        user = User(
            org_id=str(org_id),
            email=email,
            hashed_password=pwd_context.hash(temp_password),
            role=body.role,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return AdminUserCreateResponse(
            user_id=str(user.id),
            email=user.email,
            role=user.role,
            org_id=user.org_id,
            temporary_password=temp_password,
        )

    async def list_users(self, org_id: uuid.UUID) -> list[AdminUserOut]:
        users = (
            await self.db.execute(
                select(User)
                .where(User.org_id == str(org_id))
                .order_by(User.created_at.desc())
            )
        ).scalars().all()
        return [
            AdminUserOut(
                user_id=str(user.id),
                email=user.email,
                role=user.role,
                org_id=user.org_id,
                is_active=user.is_active,
                created_at=user.created_at,
                last_login_at=user.last_login_at,
            )
            for user in users
        ]

    async def create_technician(
        self, org_id: uuid.UUID, body: AdminTechnicianCreate
    ) -> AdminTechnicianOut:
        org = await self.db.get(Organization, org_id)
        if org is None:
            raise ValueError("Organization not found")

        count = await self._technician_count(org_id)
        employee_number = f"TECH-{count + 1:03d}"
        tech = Technician(
            org_id=org_id,
            employee_number=employee_number,
            full_name=body.full_name.strip(),
            phone=body.phone,
            email=body.email,
            hire_date=date.today(),
            employment_status="ACTIVE",
            skills=[body.specialty],
        )
        self.db.add(tech)
        await self.db.flush()
        await self.db.refresh(tech)
        return AdminTechnicianOut(
            technician_id=tech.technician_id,
            full_name=tech.full_name,
            phone=tech.phone,
            email=tech.email,
            specialty=body.specialty,
            employment_status=tech.employment_status,
        )

    async def list_technicians(self, org_id: uuid.UUID) -> list[AdminTechnicianOut]:
        techs = (
            await self.db.execute(
                select(Technician)
                .where(Technician.org_id == org_id)
                .order_by(Technician.full_name)
            )
        ).scalars().all()
        return [
            AdminTechnicianOut(
                technician_id=tech.technician_id,
                full_name=tech.full_name,
                phone=tech.phone,
                email=tech.email,
                specialty=(tech.skills or ["General"])[0],
                employment_status=tech.employment_status,
            )
            for tech in techs
        ]

    async def get_onboarding(self, org_id: uuid.UUID) -> OnboardingProgressOut:
        org = await self.db.get(Organization, org_id)
        if org is None:
            raise ValueError("Organization not found")
        settings = await self._ensure_settings(org)
        await self.db.refresh(settings)
        return OnboardingProgressOut(
            org_id=org_id,
            onboarding_completed=settings.onboarding_completed,
            onboarding_step=settings.onboarding_step,
            display_name=settings.display_name,
        )

    async def update_onboarding(
        self, org_id: uuid.UUID, body: OnboardingProgressUpdate
    ) -> OnboardingProgressOut:
        org = await self.db.get(Organization, org_id)
        if org is None:
            raise ValueError("Organization not found")
        settings = await self._ensure_settings(org)
        if body.onboarding_step is not None:
            settings.onboarding_step = body.onboarding_step
        if body.onboarding_completed is not None:
            settings.onboarding_completed = body.onboarding_completed
            if body.onboarding_completed:
                settings.onboarding_step = max(settings.onboarding_step, 5)
        await self.db.flush()
        await self.db.refresh(settings)
        return await self.get_onboarding(org_id)

    async def provision(self, org_id: uuid.UUID) -> ProvisionResponse:
        org = await self.db.get(Organization, org_id)
        if org is None:
            raise ValueError("Organization not found")
        settings = await self._ensure_settings(org)
        settings.onboarding_step = max(settings.onboarding_step, 1)
        if not settings.display_name:
            settings.display_name = org.org_name
        if not settings.agent_greeting:
            name = settings.display_name or org.org_name
            settings.agent_greeting = (
                f"Hi, thanks for calling {name}! "
                "This is an AI virtual assistant. How can I help you today?"
            )

        customer_count = int(
            (
                await self.db.execute(
                    select(func.count(Customer.customer_id)).where(
                        Customer.org_id == org_id
                    )
                )
            ).scalar_one()
            or 0
        )
        example_created = False
        env = os.getenv("ENVIRONMENT", "production")
        if customer_count == 0 and env in ("development", "test", "dev"):
            self.db.add(
                Customer(
                    org_id=org_id,
                    full_name="Example Customer",
                    phone_primary="+15550100001",
                    email="example@customer.local",
                    address_line1="123 Main St",
                    city="Demo City",
                    state="CA",
                    zip="92612",
                    customer_since=date.today(),
                    account_status="ACTIVE",
                    contract_type="RESIDENTIAL_OTC",
                )
            )
            example_created = True

        await self.db.flush()
        await self.db.refresh(org)
        await self.db.refresh(settings)
        return ProvisionResponse(
            org_id=org_id,
            settings=_settings_out(settings),
            example_customer_created=example_created,
        )
