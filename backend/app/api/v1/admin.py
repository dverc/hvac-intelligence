from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.auth_jwt import require_admin
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
    ProvisionResponse,
)
from app.services.admin_onboarding_service import AdminOnboardingService

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


def _service(db: AsyncSession) -> AdminOnboardingService:
    return AdminOnboardingService(db)


@router.get("/organizations", response_model=list[AdminOrganizationListItem])
async def list_admin_organizations(
    db: AsyncSession = Depends(get_db),
) -> list[AdminOrganizationListItem]:
    return await _service(db).list_organizations()


@router.post(
    "/organizations",
    response_model=AdminOrganizationCreateResponse,
    status_code=201,
)
async def create_admin_organization(
    body: AdminOrganizationCreate,
    db: AsyncSession = Depends(get_db),
) -> AdminOrganizationCreateResponse:
    return await _service(db).create_organization(body)


@router.get("/organizations/{org_id}", response_model=AdminOrganizationDetail)
async def get_admin_organization(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AdminOrganizationDetail:
    try:
        return await _service(db).get_organization(org_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/organizations/{org_id}", response_model=AdminOrganizationDetail)
async def update_admin_organization(
    org_id: uuid.UUID,
    body: AdminOrganizationUpdate,
    db: AsyncSession = Depends(get_db),
) -> AdminOrganizationDetail:
    try:
        return await _service(db).update_organization(org_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/organizations/{org_id}/users", response_model=list[AdminUserOut])
async def list_admin_organization_users(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[AdminUserOut]:
    return await _service(db).list_users(org_id)


@router.post(
    "/organizations/{org_id}/users",
    response_model=AdminUserCreateResponse,
    status_code=201,
)
async def create_admin_organization_user(
    org_id: uuid.UUID,
    body: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
) -> AdminUserCreateResponse:
    try:
        return await _service(db).create_user(org_id, body)
    except ValueError as exc:
        detail = str(exc)
        status = 409 if "already registered" in detail.lower() else 404
        raise HTTPException(status_code=status, detail=detail) from exc


@router.get(
    "/organizations/{org_id}/technicians",
    response_model=list[AdminTechnicianOut],
)
async def list_admin_organization_technicians(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[AdminTechnicianOut]:
    return await _service(db).list_technicians(org_id)


@router.post(
    "/organizations/{org_id}/technicians",
    response_model=AdminTechnicianOut,
    status_code=201,
)
async def create_admin_organization_technician(
    org_id: uuid.UUID,
    body: AdminTechnicianCreate,
    db: AsyncSession = Depends(get_db),
) -> AdminTechnicianOut:
    try:
        return await _service(db).create_technician(org_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/organizations/{org_id}/onboarding", response_model=OnboardingProgressOut)
async def get_admin_onboarding(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> OnboardingProgressOut:
    try:
        return await _service(db).get_onboarding(org_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/organizations/{org_id}/onboarding", response_model=OnboardingProgressOut)
async def update_admin_onboarding(
    org_id: uuid.UUID,
    body: OnboardingProgressUpdate,
    db: AsyncSession = Depends(get_db),
) -> OnboardingProgressOut:
    try:
        return await _service(db).update_onboarding(org_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/organizations/{org_id}/provision", response_model=ProvisionResponse)
async def provision_admin_organization(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ProvisionResponse:
    try:
        return await _service(db).provision(org_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
