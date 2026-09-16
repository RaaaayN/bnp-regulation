def test_ingest_search_compare_and_review_workflow(client) -> None:
    ingestion = client.post(
        "/v1/documents",
        json={
            "source": "EBA Guidelines 2026",
            "content": (
                "# Model monitoring\n\n"
                "Article 12.3\n\n"
                "Institutions must review the model monitoring framework annually."
            ),
        },
    )
    assert ingestion.status_code == 201
    assert ingestion.json()["chunks_indexed"] == 1

    search = client.post("/v1/search", json={"query": "annual model monitoring review"})
    assert search.status_code == 200
    assert search.json()["status"] == "evidence_found"
    assert "Article 12.3" in search.json()["results"][0]["citation"]

    comparison = client.post(
        "/v1/changes/compare",
        json={
            "previous": [
                {
                    "document_id": "eba-model-risk",
                    "section_id": "12.3",
                    "text": "Institutions should review controls annually.",
                    "version": "2025",
                }
            ],
            "current": [
                {
                    "document_id": "eba-model-risk",
                    "section_id": "12.3",
                    "text": "Institutions must review controls annually.",
                    "version": "2026",
                }
            ],
        },
    )
    assert comparison.status_code == 200
    change = comparison.json()[0]
    assert change["materiality"] == "high"
    assert "obligation_strengthened" in change["signals"]

    review = client.post("/v1/claims/review", json=change)
    assert review.status_code == 200
    assert review.json()["accepted_claims"]


def test_search_fails_closed_without_evidence(client) -> None:
    ingestion = client.post(
        "/v1/documents",
        json={
            "source": "Capital requirements",
            "content": "# Capital\n\nArticle 1\n\nFirms must maintain regulatory capital.",
        },
    )
    assert ingestion.status_code == 201

    for query in ("what is the capital of Mongolia", "the"):
        response = client.post("/v1/search", json={"query": query})

        assert response.status_code == 200
        assert response.json() == {"status": "insufficient_evidence", "results": []}
