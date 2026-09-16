from app.ingestion import ingest
from app.retrieval import InMemoryIndex, LexicalRetriever


def _retriever(*, minimum_query_coverage: float = 0.6) -> LexicalRetriever:
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
    return LexicalRetriever(
        index, minimum_query_coverage=minimum_query_coverage
    )


def test_lexical_search_ranks_relevant_evidence_and_exposes_source() -> None:
    result = _retriever().search("ratio minimal de fonds propres", limit=1)[0]

    assert result.source == "CRR"
    assert result.citation == "CRR > Fonds propres > Article 3"
    assert "huit pour cent" in result.text
    assert 0.0 <= result.score <= 1.0
    assert result.lexical_score > 0
    assert result.similarity_score > 0
    assert result.query_coverage >= 0.6


def test_query_coverage_gate_returns_empty_for_unsupported_query() -> None:
    assert _retriever().search("astronomie exoplanète télescope") == []


def test_query_coverage_gate_rejects_unrelated_question_with_shared_stop_words() -> None:
    retriever = _retriever()

    assert retriever.search("what is the capital of Mongolia") == []
    assert retriever.search("the") == []


def test_query_coverage_threshold_changes_admission_independently_of_bm25_rank() -> None:
    query = "ratio astronomy telescope"
    permissive_result = _retriever(minimum_query_coverage=0.0).search(query)[0]

    assert permissive_result.query_coverage == 1 / 3
    assert permissive_result.score < 0.5
    assert _retriever(minimum_query_coverage=0.6).search(query) == []


def test_search_is_accent_insensitive_and_deterministic() -> None:
    retriever = _retriever()
    first = retriever.search("liquidite quotidien")
    second = retriever.search("liquidite quotidien")

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
