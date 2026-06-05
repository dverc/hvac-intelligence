from collections.abc import AsyncGenerator
import threading
import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.rag.retriever import RAGRetriever
from app.services.analytics_service import AnalyticsService
from app.services.churn_service import ChurnService
from app.services.customer_service import CustomerService
from app.services.dispatch_service import DispatchService
from app.services.tool_executor import ToolExecutor
from app.services.ticket_service import TicketService
from app.services.transcript_service import TranscriptService


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_customer_service(
    db: AsyncSession = Depends(get_db),
) -> CustomerService:
    return CustomerService(db)


async def get_churn_service(db: AsyncSession = Depends(get_db)) -> ChurnService:
    return ChurnService(db)


async def get_analytics_service(db: AsyncSession = Depends(get_db)) -> AnalyticsService:
    return AnalyticsService(db)


async def get_dispatch_service(db: AsyncSession = Depends(get_db)) -> DispatchService:
    return DispatchService(db)


async def get_transcript_service(db: AsyncSession = Depends(get_db)) -> TranscriptService:
    return TranscriptService(db)


_rag_retriever: RAGRetriever | None = None
_rag_retriever_lock = threading.Lock()


def get_rag_retriever() -> RAGRetriever:
    """Process-wide singleton — Pinecone client init is expensive."""
    global _rag_retriever
    if _rag_retriever is None:
        with _rag_retriever_lock:
            if _rag_retriever is None:
                _rag_retriever = RAGRetriever()
    return _rag_retriever


async def build_tool_executor(db: AsyncSession) -> ToolExecutor:
    return ToolExecutor(
        customer_service=CustomerService(db),
        dispatch_service=DispatchService(db),
        churn_service=ChurnService(db),
        ticket_service=TicketService(db),
        rag_retriever=get_rag_retriever(),
    )


async def get_ticket_service(db: AsyncSession = Depends(get_db)) -> TicketService:
    return TicketService(db)


async def get_knowledge_service(db: AsyncSession = Depends(get_db)) -> "KnowledgeService":
    from app.services.knowledge_service import KnowledgeService

    return KnowledgeService(db)


async def get_availability_service(
    db: AsyncSession = Depends(get_db),
) -> "AvailabilityService":
    from app.services.availability_service import AvailabilityService

    return AvailabilityService(db)


async def get_service_catalog_service(
    db: AsyncSession = Depends(get_db),
) -> "ServiceCatalogService":
    from app.services.service_catalog_service import ServiceCatalogService

    return ServiceCatalogService(db)


async def get_jobber_service(
    db: AsyncSession = Depends(get_db),
) -> "JobberService":
    from app.services.jobber_service import JobberService

    return JobberService(db)


async def get_google_calendar_service(
    db: AsyncSession = Depends(get_db),
) -> "GoogleCalendarService":
    from app.services.google_calendar_service import GoogleCalendarService

    return GoogleCalendarService(db)


async def get_csv_import_service(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> "CsvImportService":
    from app.services.csv_import_service import CsvImportService

    return CsvImportService(db, org_id)


async def get_google_drive_service(
    db: AsyncSession = Depends(get_db),
) -> "GoogleDriveService":
    from app.services.google_drive_service import GoogleDriveService

    return GoogleDriveService(db)


async def get_tool_executor(db: AsyncSession = Depends(get_db)) -> ToolExecutor:
    return await build_tool_executor(db)
