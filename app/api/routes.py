from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_retriever
from app.api.schemas import (
    IngestRequest,
    IngestResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from app.config import get_settings
from app.domain import (
    ImpactAssessment,
    ImpactCandidate,
    RegulatorySection,
    ReviewResult,
    SectionChange,
)
from app.ingestion import ingest
from app.retrieval import LexicalRetriever
from app.security.content import sanitize_untrusted_content
from app.services import ChangeAnalysisService, ClaimReviewer, ImpactAnalysisService

router = APIRouter(prefix="/v1")


@router.post("/documents", response_model=IngestResponse, status_code=201, tags=["ingestion"])
async def ingest_document(
    payload: IngestRequest,
    retriever: Annotated[LexicalRetriever, Depends(get_retriever)],
) -> IngestResponse:
    sanitized = sanitize_untrusted_content(payload.content)
    document = ingest(
        sanitized.text,
        source=payload.source,
        content_type=payload.content_type,
        title=payload.title,
        document_type=payload.document_type,
        jurisdiction=payload.jurisdiction,
        published_at=payload.published_at,
        attributes=payload.attributes,
    )
    retriever.index.add(document)
    return IngestResponse(
        document_id=document.id,
        chunks_indexed=len(document.chunks),
        injection_suspected=sanitized.injection_suspected,
        redacted_categories=sanitized.detected_categories,
    )


@router.post("/search", response_model=SearchResponse, tags=["retrieval"])
async def search_documents(
    payload: SearchRequest,
    retriever: Annotated[LexicalRetriever, Depends(get_retriever)],
) -> SearchResponse:
    settings = get_settings()
    results = retriever.search(payload.query, limit=payload.limit or settings.max_results)
    return SearchResponse(
        status="evidence_found" if results else "insufficient_evidence",
        results=tuple(
            SearchHit(
                chunk_id=result.chunk.id,
                document_id=result.chunk.document_id,
                text=result.text,
                citation=result.citation,
                score=round(result.score, 4),
                query_coverage=round(result.query_coverage, 4),
            )
            for result in results
        ),
    )


@router.post("/changes/compare", response_model=list[SectionChange], tags=["analysis"])
async def compare_versions(
    previous: list[RegulatorySection], current: list[RegulatorySection]
) -> list[SectionChange]:
    return ChangeAnalysisService().compare_versions(previous, current)


@router.post("/claims/review", response_model=ReviewResult, tags=["verification"])
async def review_change(change: SectionChange) -> ReviewResult:
    sources = tuple(
        section
        for section in (change.previous_section, change.current_section)
        if section is not None
    )
    return ClaimReviewer().review_claims(change.claims, sources)


@router.post("/impacts/analyze", response_model=list[ImpactAssessment], tags=["analysis"])
async def analyze_impacts(
    change: SectionChange, candidates: list[ImpactCandidate]
) -> list[ImpactAssessment]:
    return ImpactAnalysisService().analyze(change, candidates)
