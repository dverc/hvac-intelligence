from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_registry import DocumentRegistry
from app.models.google_calendar_token import GoogleCalendarToken
from app.models.organization import Organization
from app.services.google_calendar_service import GoogleCalendarService
from app.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)

_FOLDER_NAME = "hvac_intelligence_kb"
_INDEXABLE_MIME = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_GOOGLE_DOC_MIME = "application/vnd.google-apps.document"


class GoogleDriveService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.gcal = GoogleCalendarService(db)
        self.knowledge = KnowledgeService(db)

    async def _get_active_token(self, org_id: uuid.UUID) -> GoogleCalendarToken:
        row = await self.gcal._get_token_row(org_id)
        if row is None:
            raise ValueError(
                "Google is not connected. Connect Google Calendar first, "
                "then re-authorize to grant Drive access."
            )
        return row

    async def _drive_service(self, org_id: uuid.UUID):
        row = await self._get_active_token(org_id)
        credentials = self.gcal._build_credentials(row)
        from google.auth.transport.requests import Request

        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            from app.core.encryption import encrypt_token

            row.access_token = encrypt_token(credentials.token) or ""
            row.token_expiry = self.gcal._expiry_for_db(credentials.expiry)
            await self.db.flush()
        return build("drive", "v3", credentials=credentials, cache_discovery=False)

    def _settings(self, org: Organization) -> dict[str, Any]:
        return dict(org.settings or {})

    async def _save_settings(self, org: Organization, settings: dict[str, Any]) -> None:
        org.settings = settings
        await self.db.flush()

    async def get_or_create_watch_folder(self, org_id: uuid.UUID) -> str:
        org = await self.db.get(Organization, org_id)
        if org is None:
            raise ValueError(f"Organization {org_id} not found")

        settings = self._settings(org)
        existing_id = settings.get("drive_folder_id")
        if existing_id:
            return str(existing_id)

        drive = await self._drive_service(org_id)
        query = (
            f"name='{_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' "
            "and trashed=false"
        )
        listed = (
            drive.files()
            .list(q=query, spaces="drive", fields="files(id,name)", pageSize=1)
            .execute()
        )
        files = listed.get("files") or []
        if files:
            folder_id = files[0]["id"]
        else:
            created = (
                drive.files()
                .create(
                    body={
                        "name": _FOLDER_NAME,
                        "mimeType": "application/vnd.google-apps.folder",
                    },
                    fields="id",
                )
                .execute()
            )
            folder_id = created["id"]

        settings["drive_folder_id"] = folder_id
        await self._save_settings(org, settings)
        return str(folder_id)

    async def list_folder_files(self, org_id: uuid.UUID) -> list[dict[str, Any]]:
        org = await self.db.get(Organization, org_id)
        if org is None:
            raise ValueError(f"Organization {org_id} not found")
        settings = self._settings(org)
        folder_id = settings.get("drive_folder_id")
        if not folder_id:
            return []

        drive = await self._drive_service(org_id)
        query = f"'{folder_id}' in parents and trashed=false"
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            response = (
                drive.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id,name,mimeType,modifiedTime,size)",
                    pageToken=page_token,
                )
                .execute()
            )
            for item in response.get("files", []):
                if item.get("mimeType") == "application/vnd.google-apps.folder":
                    continue
                items.append(item)
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return items

    async def download_file(self, org_id: uuid.UUID, file_id: str) -> tuple[bytes, str]:
        drive = await self._drive_service(org_id)
        meta = (
            drive.files()
            .get(fileId=file_id, fields="mimeType,name")
            .execute()
        )
        mime_type = meta.get("mimeType") or "application/octet-stream"

        if mime_type == _GOOGLE_DOC_MIME:
            data = (
                drive.files()
                .export(fileId=file_id, mimeType="text/plain")
                .execute()
            )
            if isinstance(data, bytes):
                return data, "text/plain"
            return str(data).encode("utf-8"), "text/plain"

        request = drive.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue(), mime_type

    def get_folder_url(self, org: Organization) -> str | None:
        folder_id = self._settings(org).get("drive_folder_id")
        if not folder_id:
            return None
        return f"https://drive.google.com/drive/folders/{folder_id}"

    async def sync_folder_to_knowledge_base(self, org_id: uuid.UUID) -> dict[str, int]:
        org = await self.db.get(Organization, org_id)
        if org is None:
            raise ValueError(f"Organization {org_id} not found")

        settings = self._settings(org)
        folder_id = settings.get("drive_folder_id")
        if not folder_id:
            raise ValueError("Drive folder not set up. Call drive/setup first.")

        synced = 0
        skipped = 0
        errors = 0

        for item in await self.list_folder_files(org_id):
            file_id = item.get("id")
            if not file_id:
                continue
            mime_type = item.get("mimeType") or ""
            if mime_type not in _INDEXABLE_MIME and mime_type != _GOOGLE_DOC_MIME:
                skipped += 1
                continue

            document_id = f"gdrive:{file_id}"
            modified_raw = item.get("modifiedTime")
            modified_at: datetime | None = None
            if modified_raw:
                modified_at = datetime.fromisoformat(
                    modified_raw.replace("Z", "+00:00")
                )

            existing = (
                await self.db.execute(
                    select(DocumentRegistry).where(
                        DocumentRegistry.org_id == org_id,
                        DocumentRegistry.document_id == document_id,
                    )
                )
            ).scalar_one_or_none()

            if (
                existing is not None
                and modified_at is not None
                and existing.last_indexed_at >= modified_at
            ):
                skipped += 1
                continue

            try:
                content, downloaded_mime = await self.download_file(org_id, file_id)
                name = item.get("name") or document_id
                if mime_type == _GOOGLE_DOC_MIME and not name.endswith(".txt"):
                    name = f"{name}.txt"
                elif mime_type == "application/pdf" and not name.lower().endswith(
                    ".pdf"
                ):
                    name = f"{name}.pdf"
                elif (
                    mime_type
                    == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    and not name.lower().endswith(".docx")
                ):
                    name = f"{name}.docx"

                strategy = "page" if name.lower().endswith(".pdf") else "paragraph"
                await self.knowledge.upload_document(
                    org_id=org_id,
                    filename=name,
                    content=content,
                    namespace="faq_general",
                    document_id=document_id,
                    mime_type=downloaded_mime,
                    chunking_strategy=strategy,
                )
                synced += 1
            except Exception as exc:
                errors += 1
                logger.warning(
                    "Drive sync failed for org=%s file=%s: %s",
                    org_id,
                    file_id,
                    exc,
                )

        settings["drive_last_sync_at"] = datetime.now(timezone.utc).isoformat()
        await self._save_settings(org, settings)
        return {"synced": synced, "skipped": skipped, "errors": errors}

    async def get_drive_status(self, org_id: uuid.UUID) -> dict[str, Any]:
        org = await self.db.get(Organization, org_id)
        if org is None:
            raise ValueError(f"Organization {org_id} not found")

        connected = await self.gcal.has_active_connection(org_id)
        settings = self._settings(org)
        folder_id = settings.get("drive_folder_id")
        file_count = 0
        if folder_id and connected:
            try:
                file_count = len(await self.list_folder_files(org_id))
            except Exception as exc:
                logger.warning("Drive list failed for org %s: %s", org_id, exc)

        return {
            "connected": connected,
            "folder_id": folder_id,
            "folder_url": self.get_folder_url(org) if folder_id else None,
            "file_count": file_count,
            "last_sync": settings.get("drive_last_sync_at"),
        }
