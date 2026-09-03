from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.persistence.models import DocumentSection, RegulatoryDocument


@dataclass(frozen=True, slots=True)
class SectionRecord:
    reference: str
    content: str
    position: int
    heading: str | None = None
    page: int | None = None


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_document(
        self,
        *,
        external_id: str,
        title: str,
        regulator: str,
        version: str,
        sections: list[SectionRecord],
        document_type: str = "unknown",
        publication_date: date | None = None,
        source_url: str | None = None,
    ) -> RegulatoryDocument:
        document = RegulatoryDocument(
            external_id=external_id,
            title=title,
            regulator=regulator,
            version=version,
            document_type=document_type,
            publication_date=publication_date,
            source_url=source_url,
            sections=[
                DocumentSection(
                    reference=section.reference,
                    heading=section.heading,
                    page=section.page,
                    position=section.position,
                    content=section.content,
                )
                for section in sections
            ],
        )
        self._session.add(document)
        await self._session.commit()
        await self._session.refresh(document)
        return document

    async def get_document(self, external_id: str, version: str) -> RegulatoryDocument | None:
        statement = (
            select(RegulatoryDocument)
            .where(
                RegulatoryDocument.external_id == external_id,
                RegulatoryDocument.version == version,
            )
            .options(selectinload(RegulatoryDocument.sections))
        )
        return await self._session.scalar(statement)
