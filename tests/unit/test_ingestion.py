from app.ingestion import DocumentMetadata, ingest, parse_html, parse_text


def test_plain_text_is_split_by_heading_article_and_paragraph() -> None:
    document = parse_text(
        """# Gouvernance

Article 4 - Les établissements conservent les preuves.

La durée minimale est de cinq ans.

## Contrôles

Un contrôle annuel est requis.""",
        DocumentMetadata(source="reglement-42", jurisdiction="FR"),
    )

    assert len(document.chunks) == 3
    assert document.chunks[0].text == "Les établissements conservent les preuves."
    assert document.chunks[0].heading_path == ("Gouvernance",)
    assert document.chunks[0].article == "Article 4"
    assert document.chunks[2].heading_path == ("Gouvernance", "Contrôles")
    assert document.chunks[2].article is None
    assert document.chunks[0].citation == "reglement-42 > Gouvernance > Article 4"


def test_html_ignores_scripts_and_uses_title_as_metadata() -> None:
    document = parse_html(
        """<html><head><title>Règlement prudentiel</title><style>ignored</style></head>
        <body><h1>Capital</h1><p>Article 7 : Le ratio minimal est fixé.</p>
        <script>danger()</script><p>Une revue est menée chaque année.</p></body></html>""",
        DocumentMetadata(source="https://example.test/rule"),
    )

    assert document.metadata.title == "Règlement prudentiel"
    assert [chunk.text for chunk in document.chunks] == [
        "Le ratio minimal est fixé.",
        "Une revue est menée chaque année.",
    ]
    assert all("danger" not in chunk.text for chunk in document.chunks)


def test_ingestion_ids_are_stable_and_change_with_source() -> None:
    first = ingest("Un paragraphe réglementaire.", source="source-a")
    repeated = ingest("Un paragraphe réglementaire.", source="source-a")
    other_source = ingest("Un paragraphe réglementaire.", source="source-b")

    assert first.id == repeated.id
    assert first.chunks[0].id == repeated.chunks[0].id
    assert first.id != other_source.id


def test_metadata_attributes_are_immutable_and_sorted() -> None:
    original = {"z": "last", "a": "first"}
    metadata = DocumentMetadata(source=" source ", attributes=original)
    original["new"] = "not copied"

    assert metadata.source == "source"
    assert list(metadata.attributes) == ["a", "z"]
    assert "new" not in metadata.attributes
