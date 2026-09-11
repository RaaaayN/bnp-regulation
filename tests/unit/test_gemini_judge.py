from pathlib import Path
from types import SimpleNamespace

import pytest

from app.evaluation.gemini_judge import (
    GeminiJudge,
    GeminiJudgeError,
    GeminiJudgeRequest,
    GeminiJudgeResult,
    GeminiJudgeUnavailable,
)


class FakeModels:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _request(answer: str = "Institutions must report incidents.") -> GeminiJudgeRequest:
    return GeminiJudgeRequest(
        question="What is required?",
        answer=answer,
        evidence=("Institutions must report major incidents within four hours.",),
    )


def _result() -> GeminiJudgeResult:
    return GeminiJudgeResult(
        groundedness=1,
        correctness=0.9,
        completeness=0.8,
        passed=True,
        rationale="The answer is supported, though less specific than the evidence.",
    )


def test_refuses_to_start_without_api_key() -> None:
    with pytest.raises(GeminiJudgeUnavailable, match="disabled"):
        GeminiJudge(api_key=None)


def test_requests_structured_json_and_caches_by_content(tmp_path: Path) -> None:
    models = FakeModels([SimpleNamespace(parsed=_result())])
    judge = GeminiJudge(client=SimpleNamespace(models=models), cache_dir=tmp_path)

    first = judge.judge(_request())
    second = judge.judge(_request())

    assert first == second == _result()
    assert len(models.calls) == 1
    config = models.calls[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is GeminiJudgeResult
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_cache_hash_changes_with_evaluation_input(tmp_path: Path) -> None:
    models = FakeModels(
        [SimpleNamespace(parsed=_result()), SimpleNamespace(parsed=_result())]
    )
    judge = GeminiJudge(client=SimpleNamespace(models=models), cache_dir=tmp_path)

    judge.judge(_request("First answer"))
    judge.judge(_request("Different answer"))

    assert len(models.calls) == 2
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_retries_with_exponential_backoff(tmp_path: Path) -> None:
    models = FakeModels(
        [TimeoutError("transient"), RuntimeError("busy"), SimpleNamespace(parsed=_result())]
    )
    delays: list[float] = []
    judge = GeminiJudge(
        client=SimpleNamespace(models=models),
        cache_dir=tmp_path,
        max_attempts=3,
        backoff_seconds=0.25,
        sleep=delays.append,
    )

    assert judge.judge(_request()).passed is True
    assert delays == [0.25, 0.5]


def test_raises_sanitized_error_after_retry_budget(tmp_path: Path) -> None:
    models = FakeModels([RuntimeError("provider detail"), RuntimeError("provider detail")])
    judge = GeminiJudge(
        client=SimpleNamespace(models=models),
        cache_dir=tmp_path,
        max_attempts=2,
        backoff_seconds=0,
    )

    with pytest.raises(GeminiJudgeError, match="failed after 2 attempt") as captured:
        judge.judge(_request())

    assert "provider detail" not in str(captured.value)


def test_accepts_json_text_when_sdk_does_not_populate_parsed(tmp_path: Path) -> None:
    models = FakeModels([SimpleNamespace(parsed=None, text=_result().model_dump_json())])
    judge = GeminiJudge(client=SimpleNamespace(models=models), cache_dir=tmp_path)

    assert judge.judge(_request()) == _result()
