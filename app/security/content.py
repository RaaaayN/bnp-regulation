import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SanitizationResult:
    text: str
    detected_categories: tuple[str, ...]
    injection_suspected: bool


_PERSONAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "IBAN",
        re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b", re.IGNORECASE),
    ),
    (
        "EMAIL",
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    ),
)

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"(?:system|developer)\s+(?:message|prompt)", re.IGNORECASE),
    re.compile(r"reveal\s+(?:the\s+)?(?:prompt|instructions|secrets?)", re.IGNORECASE),
)


def sanitize_untrusted_content(text: str) -> SanitizationResult:
    """Redact common identifiers and flag instruction-like document content.

    Regulatory text remains data even when it contains imperative language. The
    flag is therefore advisory and never causes the text to be executed or omitted.
    """

    sanitized = text
    categories: list[str] = []
    for category, pattern in _PERSONAL_PATTERNS:
        if pattern.search(sanitized):
            categories.append(category)
            sanitized = pattern.sub(f"[{category}_REDACTED]", sanitized)

    return SanitizationResult(
        text=sanitized,
        detected_categories=tuple(categories),
        injection_suspected=any(
            pattern.search(text) is not None for pattern in _INJECTION_PATTERNS
        ),
    )
