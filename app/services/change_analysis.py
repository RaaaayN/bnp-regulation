"""Deterministic comparison of structured regulatory document versions."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

from app.domain import (
    ChangeType,
    Citation,
    Claim,
    ConfidenceLevel,
    MaterialityLevel,
    RegulatorySection,
    SectionChange,
)

_SPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)

# Increasing obligation strength.  Pairs are inspected in aligned word edits.
_MODAL_STRENGTH = {
    "may": 0,
    "can": 0,
    "could": 0,
    "should": 1,
    "shall": 2,
    "must": 3,
}
_REQUIREMENT_WORDS = frozenset({"must", "shall", "required", "prohibited", "ensure"})
_DEADLINE_WORDS = frozenset({"day", "days", "month", "months", "annual", "annually", "immediately"})


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return _SPACE_RE.sub(" ", value).strip()


def _words(value: str) -> list[str]:
    return _WORD_RE.findall(_normalise(value))


def _level(score: float, *, high: float, medium: float) -> MaterialityLevel:
    if score >= high:
        return MaterialityLevel.HIGH
    if score >= medium:
        return MaterialityLevel.MEDIUM
    return MaterialityLevel.LOW


def _confidence_level(score: float) -> ConfidenceLevel:
    if score >= 0.8:
        return ConfidenceLevel.HIGH
    if score >= 0.55:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


class ChangeAnalysisService:
    """Match sections and classify their changes without nondeterministic calls."""

    def __init__(self, *, section_match_threshold: float = 0.64) -> None:
        if not 0.0 <= section_match_threshold <= 1.0:
            raise ValueError("section_match_threshold must be between 0 and 1")
        self.section_match_threshold = section_match_threshold

    def compare_versions(
        self,
        previous: list[RegulatorySection] | tuple[RegulatorySection, ...],
        current: list[RegulatorySection] | tuple[RegulatorySection, ...],
    ) -> list[SectionChange]:
        """Return one stable result per matched, removed, or added section.

        Matching favours exact section identifiers, then exact normalised titles,
        then a conservative title/text similarity.  A greedy assignment is safe
        here because candidates are globally sorted with deterministic tie-breaks.
        """

        self._ensure_unique(previous, "previous")
        self._ensure_unique(current, "current")
        matches = self._match_sections(previous, current)
        matched_previous = {old_index for old_index, _ in matches}
        matched_current = {new_index for _, new_index in matches}

        results = [self.compare_sections(previous[i], current[j]) for i, j in sorted(matches)]
        results.extend(
            self.compare_sections(section, None)
            for i, section in enumerate(previous)
            if i not in matched_previous
        )
        results.extend(
            self.compare_sections(None, section)
            for i, section in enumerate(current)
            if i not in matched_current
        )
        return results

    def compare_sections(
        self,
        previous: RegulatorySection | None,
        current: RegulatorySection | None,
    ) -> SectionChange:
        if previous is None and current is None:
            raise ValueError("at least one section is required")

        if previous is None:
            assert current is not None
            return self._one_sided(current, ChangeType.ADDED)
        if current is None:
            return self._one_sided(previous, ChangeType.REMOVED)

        old_text, new_text = _normalise(previous.text), _normalise(current.text)
        similarity = round(SequenceMatcher(None, old_text, new_text, autojunk=False).ratio(), 4)
        change_type = ChangeType.UNCHANGED if old_text == new_text else ChangeType.MODIFIED
        signals, strengthened = self._signals(previous.text, current.text)
        materiality_score = self._materiality(
            change_type, similarity, previous.text, current.text, signals, strengthened
        )
        confidence_score = self._confidence(previous, current, similarity, change_type)
        claims = (
            ()
            if change_type is ChangeType.UNCHANGED
            else self._change_claims(previous, current, signals, strengthened)
        )
        return SectionChange(
            change_id=self._change_id(previous, current),
            change_type=change_type,
            previous_section=previous,
            current_section=current,
            similarity_score=similarity,
            materiality_score=materiality_score,
            materiality=_level(materiality_score, high=0.7, medium=0.35),
            confidence_score=confidence_score,
            confidence=_confidence_level(confidence_score),
            signals=tuple(signals),
            claims=claims,
        )

    @staticmethod
    def _ensure_unique(sections: object, label: str) -> None:
        values = list(sections)  # type: ignore[arg-type]
        keys = [(section.document_id, section.section_id) for section in values]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{label} sections contain duplicate identifiers")

    def _match_sections(
        self,
        previous: list[RegulatorySection] | tuple[RegulatorySection, ...],
        current: list[RegulatorySection] | tuple[RegulatorySection, ...],
    ) -> list[tuple[int, int]]:
        candidates: list[tuple[float, int, int]] = []
        for old_index, old in enumerate(previous):
            for new_index, new in enumerate(current):
                score = self._section_match_score(old, new)
                if score >= self.section_match_threshold:
                    candidates.append((score, old_index, new_index))
        matches: list[tuple[int, int]] = []
        used_old: set[int] = set()
        used_new: set[int] = set()
        for _, old_index, new_index in sorted(
            candidates, key=lambda row: (-row[0], row[1], row[2])
        ):
            if old_index not in used_old and new_index not in used_new:
                matches.append((old_index, new_index))
                used_old.add(old_index)
                used_new.add(new_index)
        return matches

    @staticmethod
    def _section_match_score(old: RegulatorySection, new: RegulatorySection) -> float:
        if old.section_id == new.section_id:
            return 1.0
        old_title, new_title = _normalise(old.title), _normalise(new.title)
        if old_title and old_title == new_title:
            return 0.98
        title_score = (
            SequenceMatcher(None, old_title, new_title, autojunk=False).ratio()
            if old_title and new_title
            else 0.0
        )
        text_score = SequenceMatcher(
            None, _normalise(old.text), _normalise(new.text), autojunk=False
        ).ratio()
        return round((0.7 * title_score) + (0.3 * text_score), 4)

    def _one_sided(self, section: RegulatorySection, change_type: ChangeType) -> SectionChange:
        is_added = change_type is ChangeType.ADDED
        citation = self._citation(section)
        claim = Claim(
            claim_id=self._claim_id(change_type.value, section.source_id),
            text=(
                f"Section {section.section_id} introduces new regulatory text."
                if is_added
                else f"Section {section.section_id} is absent from the current version."
            ),
            citations=(citation,),
        )
        score = 0.75 if any(word in _REQUIREMENT_WORDS for word in _words(section.text)) else 0.5
        return SectionChange(
            change_id=self._change_id(None if is_added else section, section if is_added else None),
            change_type=change_type,
            previous_section=None if is_added else section,
            current_section=section if is_added else None,
            similarity_score=0.0,
            materiality_score=score,
            materiality=_level(score, high=0.7, medium=0.35),
            confidence_score=0.98,
            confidence=ConfidenceLevel.HIGH,
            signals=("new_section" if is_added else "removed_section",),
            claims=(claim,),
        )

    @staticmethod
    def _signals(old: str, new: str) -> tuple[list[str], bool]:
        old_words, new_words = _words(old), _words(new)
        old_modals = Counter(word for word in old_words if word in _MODAL_STRENGTH)
        new_modals = Counter(word for word in new_words if word in _MODAL_STRENGTH)
        removed_strengths = [
            _MODAL_STRENGTH[word]
            for word, count in old_modals.items()
            if count > new_modals[word]
        ]
        added_strengths = [
            _MODAL_STRENGTH[word]
            for word, count in new_modals.items()
            if count > old_modals[word]
        ]
        strengthened = bool(
            removed_strengths
            and added_strengths
            and max(added_strengths) > min(removed_strengths)
        )
        weakened = bool(
            removed_strengths
            and added_strengths
            and min(added_strengths) < max(removed_strengths)
        )
        signals: list[str] = []
        if strengthened:
            signals.append("obligation_strengthened")
        if weakened:
            signals.append("obligation_weakened")
        if set(new_words) & _REQUIREMENT_WORDS and not set(old_words) & _REQUIREMENT_WORDS:
            signals.append("binding_language_added")
        if (set(old_words) ^ set(new_words)) & _DEADLINE_WORDS:
            signals.append("deadline_language_changed")
        old_numbers = {word for word in old_words if word.isdigit()}
        new_numbers = {word for word in new_words if word.isdigit()}
        if old_numbers != new_numbers:
            signals.append("numeric_threshold_changed")
        return signals, strengthened

    @staticmethod
    def _materiality(
        change_type: ChangeType,
        similarity: float,
        old: str,
        new: str,
        signals: list[str],
        strengthened: bool,
    ) -> float:
        if change_type is ChangeType.UNCHANGED:
            return 0.0
        textual_change = 1.0 - similarity
        score = 0.2 + min(0.35, textual_change * 0.6)
        if strengthened:
            score = max(score, 0.9)
        elif "binding_language_added" in signals:
            score = max(score, 0.78)
        if "numeric_threshold_changed" in signals:
            score += 0.18
        if "deadline_language_changed" in signals:
            score += 0.12
        # Avoid unused-parameter ambiguity: the texts influence similarity above
        # and make this helper's input contract explicit.
        assert old and new
        return round(min(score, 1.0), 4)

    @staticmethod
    def _confidence(
        old: RegulatorySection,
        new: RegulatorySection,
        similarity: float,
        change_type: ChangeType,
    ) -> float:
        if old.section_id == new.section_id:
            structural = 0.98
        elif _normalise(old.title) and _normalise(old.title) == _normalise(new.title):
            structural = 0.94
        else:
            structural = 0.72
        if change_type is ChangeType.UNCHANGED:
            return 1.0
        return round(min(0.99, (0.75 * structural) + (0.25 * max(similarity, 0.5))), 4)

    def _change_claims(
        self,
        previous: RegulatorySection,
        current: RegulatorySection,
        signals: list[str],
        strengthened: bool,
    ) -> tuple[Claim, ...]:
        citations = (self._citation(previous), self._citation(current))
        if strengthened:
            text = f"The obligation in section {current.section_id} has been strengthened."
        elif "obligation_weakened" in signals:
            text = f"The obligation in section {current.section_id} has been weakened."
        else:
            text = f"The regulatory text in section {current.section_id} has changed."
        return (
            Claim(
                claim_id=self._claim_id("modified", previous.source_id, current.source_id),
                text=text,
                citations=citations,
            ),
        )

    @staticmethod
    def _citation(section: RegulatorySection) -> Citation:
        return Citation(
            document_id=section.document_id,
            section_id=section.section_id,
            quote=section.text,
            page=section.page,
            version=section.version,
        )

    @staticmethod
    def _claim_id(*parts: str) -> str:
        value = "|".join(parts).encode()
        return f"claim-{hashlib.sha256(value).hexdigest()[:12]}"

    @staticmethod
    def _change_id(old: RegulatorySection | None, new: RegulatorySection | None) -> str:
        value = "|".join(
            (
                old.source_id if old else "-",
                old.version or "" if old else "",
                new.source_id if new else "-",
                new.version or "" if new else "",
            )
        ).encode()
        return f"change-{hashlib.sha256(value).hexdigest()[:12]}"
