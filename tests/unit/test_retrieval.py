from app.ingestion import ingest
from app.retrieval import HybridRetriever, InMemoryIndex


def _retriever(*, threshold: float = 0.12) -> HybridRetriever:
    index = InMemoryIndex()
    index.add_many(
        [
            ingest(
                "# Fonds propres\n\n"
                "Article 3 - Le ratio de fonds propres minimal est de huit pour cent.",
                source="CRR",
            ),
            ingest(
                "# Liquidité\n\n"
                "Article 9 - Les banques maintiennent un coussin de liquidité quotidien.",
                source="LCR",
            ),
        ]
    )
    return HybridRetriever(index, evidence_threshold=threshold)


def test_hybrid_search_ranks_relevant_evidence_and_exposes_source() -> None:
    result = _retriever().search("ratio minimal de fonds propres", limit=1)[0]

    assert result.source == "CRR"
    assert result.citation == "CRR > Fonds propres > Article 3"
    assert "huit pour cent" in result.text
    assert 0.0 <= result.score <= 1.0
    assert result.lexical_score > 0
    assert result.similarity_score > 0


def test_evidence_threshold_returns_empty_for_unsupported_query() -> None:
    assert _retriever().search("astronomie exoplanète télescope") == []


def test_search_is_accent_insensitive_and_deterministic() -> None:
    retriever = _retriever()
    first = retriever.search("liquidite banque")
    second = retriever.search("liquidite banque")

    assert first == second
    assert first[0].source == "LCR"


def test_document_can_be_replaced_and_removed() -> None:
    index = InMemoryIndex()
    original = ingest("Texte initial.", source="stable")
    replacement = ingest("Texte révisé.", source="stable")
    index.add(original)
    index.add(replacement)

    assert len(index) == 2  # ids represent content versions, both are retained
    assert index.remove(original.id)
    assert len(index) == 1
    assert not index.remove("missing")


def test_invalid_search_parameters_are_rejected() -> None:
    retriever = _retriever()

    try:
        retriever.search("capital", limit=0)
    except ValueError as error:
        assert "positive" in str(error)
    else:
        raise AssertionError("limit=0 should be rejected")
