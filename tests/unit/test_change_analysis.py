from app.domain import ChangeType, ImpactCandidate, MaterialityLevel, RegulatorySection
from app.services import ChangeAnalysisService, ImpactAnalysisService


def section(section_id: str, text: str, *, version: str, title: str = "") -> RegulatorySection:
    return RegulatorySection(
        document_id="eba-guidelines",
        section_id=section_id,
        title=title,
        text=text,
        page=12,
        version=version,
    )


def test_compare_versions_classifies_all_change_types_deterministically() -> None:
    previous = [
        section("1", "Institutions should review controls annually.", version="2025"),
        section("2", "The report is retained for five years.", version="2025"),
        section("3", "Legacy appendix.", version="2025"),
    ]
    current = [
        section("1", "Institutions must review controls annually.", version="2026"),
        section("2", "  The report is retained for five years. ", version="2026"),
        section("4", "Institutions must document incidents.", version="2026"),
    ]

    changes = ChangeAnalysisService().compare_versions(previous, current)

    assert [change.change_type for change in changes] == [
        ChangeType.MODIFIED,
        ChangeType.UNCHANGED,
        ChangeType.REMOVED,
        ChangeType.ADDED,
    ]
    strengthened = changes[0]
    assert "obligation_strengthened" in strengthened.signals
    assert strengthened.materiality is MaterialityLevel.HIGH
    assert strengthened.materiality_score >= 0.9
    assert len(strengthened.claims[0].citations) == 2
    assert changes == ChangeAnalysisService().compare_versions(previous, current)


def test_sections_can_match_by_title_when_identifiers_change() -> None:
    old = section("A-12", "Reports must be retained.", version="1", title="Record keeping")
    new = section(
        "B-7", "Reports must be retained for seven years.", version="2", title="Record Keeping"
    )

    changes = ChangeAnalysisService().compare_versions([old], [new])

    assert len(changes) == 1
    assert changes[0].change_type is ChangeType.MODIFIED


def test_impact_analysis_only_returns_explainable_potential_matches() -> None:
    change = ChangeAnalysisService().compare_sections(
        section("1", "Institutions should review model controls.", version="1"),
        section("1", "Institutions must review model controls annually.", version="2"),
    )
    candidates = [
        ImpactCandidate(
            item_id="POL-1",
            name="Model governance policy",
            item_type="policy",
            keywords=("model", "controls"),
        ),
        ImpactCandidate(
            item_id="POL-2",
            name="Travel policy",
            item_type="policy",
            keywords=("travel", "expenses"),
        ),
    ]

    results = ImpactAnalysisService().analyse(change, candidates)

    assert [item.candidate.item_id for item in results] == ["POL-1"]
    assert "Potential impact" in results[0].rationale
    assert results[0].claims[0].citations[0].section_id == "1"
