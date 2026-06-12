from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import get_knowledge_service
from app.schemas.service_catalog import (
    ServiceCatalogCreate,
    ServiceCatalogItem,
    ServiceCatalogListResponse,
    ServiceCatalogUpdate,
)
from app.services.knowledge_service import KnowledgeService, RagInjectionError

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/{org_id}/namespaces")
async def list_namespaces(
    org_id: uuid.UUID,
    knowledge: KnowledgeService = Depends(get_knowledge_service),
) -> list[dict]:
    org = await knowledge._get_org(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return await knowledge.list_namespaces(org_id)


@router.get("/{org_id}/documents")
async def list_documents(
    org_id: uuid.UUID,
    knowledge: KnowledgeService = Depends(get_knowledge_service),
) -> dict:
    org = await knowledge._get_org(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    items = await knowledge.list_documents(org_id)
    return {"org_id": str(org_id), "total": len(items), "items": items}


@router.post("/{org_id}/documents")
async def upload_document(
    org_id: uuid.UUID,
    file: UploadFile = File(...),
    namespace: str = Form(default="faq_general"),
    document_id: str | None = Form(default=None),
    chunking_strategy: str = Form(default="paragraph"),
    knowledge: KnowledgeService = Depends(get_knowledge_service),
) -> dict:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file upload")
    try:
        return await knowledge.upload_document(
            org_id=org_id,
            filename=file.filename or "upload.txt",
            content=content,
            namespace=namespace,
            document_id=document_id,
            mime_type=file.content_type,
            chunking_strategy=chunking_strategy,
        )
    except RagInjectionError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "RAG_INJECTION_DETECTED", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{org_id}/documents/{document_id}")
async def delete_document(
    org_id: uuid.UUID,
    document_id: str,
    knowledge: KnowledgeService = Depends(get_knowledge_service),
) -> dict:
    result = await knowledge.delete_document(org_id, document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.get("/{org_id}/service-catalog", response_model=ServiceCatalogListResponse)
async def list_service_catalog(
    org_id: uuid.UUID,
    knowledge: KnowledgeService = Depends(get_knowledge_service),
) -> ServiceCatalogListResponse:
    org = await knowledge._get_org(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    items = await knowledge.list_service_catalog(org_id)
    return ServiceCatalogListResponse(
        org_id=str(org_id),
        total=len(items),
        items=items,
    )


@router.post("/{org_id}/service-catalog", response_model=ServiceCatalogItem)
async def create_service_catalog_entry(
    org_id: uuid.UUID,
    payload: ServiceCatalogCreate,
    knowledge: KnowledgeService = Depends(get_knowledge_service),
) -> ServiceCatalogItem:
    org = await knowledge._get_org(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    try:
        return await knowledge.create_service_catalog_entry(org_id, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/{org_id}/service-catalog/{service_id}",
    response_model=ServiceCatalogItem,
)
async def update_service_catalog_entry(
    org_id: uuid.UUID,
    service_id: uuid.UUID,
    payload: ServiceCatalogUpdate,
    knowledge: KnowledgeService = Depends(get_knowledge_service),
) -> ServiceCatalogItem:
    item = await knowledge.update_service_catalog_entry(org_id, service_id, payload)
    if item is None:
        raise HTTPException(status_code=404, detail="Service not found")
    return item
