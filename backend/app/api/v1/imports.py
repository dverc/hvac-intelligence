from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.api.deps import get_csv_import_service, get_google_drive_service
from app.schemas.imports import CsvImportResultResponse
from app.models.organization import Organization
from app.services.csv_import_service import CsvImportService
from app.services.google_drive_service import GoogleDriveService, _FOLDER_NAME

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/{org_id}/customers", response_model=CsvImportResultResponse)
async def import_customers(
    org_id: uuid.UUID,
    file: UploadFile = File(...),
    dry_run: bool = Form(default=False),
    importer: CsvImportService = Depends(get_csv_import_service),
) -> CsvImportResultResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty CSV upload")
    result = await importer.import_customers(
        content, file.filename or "customers.csv", dry_run=dry_run
    )
    return CsvImportResultResponse.from_result(result)


@router.post("/{org_id}/equipment", response_model=CsvImportResultResponse)
async def import_equipment(
    org_id: uuid.UUID,
    file: UploadFile = File(...),
    dry_run: bool = Form(default=False),
    importer: CsvImportService = Depends(get_csv_import_service),
) -> CsvImportResultResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty CSV upload")
    result = await importer.import_equipment(
        content, file.filename or "equipment.csv", dry_run=dry_run
    )
    return CsvImportResultResponse.from_result(result)


@router.get("/{org_id}/templates/customers")
async def download_customer_template(
    org_id: uuid.UUID,
    importer: CsvImportService = Depends(get_csv_import_service),
) -> Response:
    del org_id
    data = importer.generate_customer_template()
    return Response(
        content=data,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="customers_template.csv"'
        },
    )


@router.get("/{org_id}/templates/equipment")
async def download_equipment_template(
    org_id: uuid.UUID,
    importer: CsvImportService = Depends(get_csv_import_service),
) -> Response:
    del org_id
    data = importer.generate_equipment_template()
    return Response(
        content=data,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="equipment_template.csv"'
        },
    )


@router.post("/{org_id}/drive/setup")
async def setup_drive_folder(
    org_id: uuid.UUID,
    drive: GoogleDriveService = Depends(get_google_drive_service),
) -> dict:
    try:
        folder_id = await drive.get_or_create_watch_folder(org_id)
        org = await drive.db.get(Organization, org_id)
        folder_url = drive.get_folder_url(org) if org else None
        return {
            "folder_id": folder_id,
            "folder_url": folder_url,
            "message": (
                "Drive folder ready. Drop PDF, Word, or text files into "
                f"'{_FOLDER_NAME}' — they sync every 30 minutes."
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{org_id}/drive/sync")
async def sync_drive_folder(
    org_id: uuid.UUID,
    drive: GoogleDriveService = Depends(get_google_drive_service),
) -> dict:
    try:
        return await drive.sync_folder_to_knowledge_base(org_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{org_id}/drive/status")
async def drive_status(
    org_id: uuid.UUID,
    drive: GoogleDriveService = Depends(get_google_drive_service),
) -> dict:
    try:
        return await drive.get_drive_status(org_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
