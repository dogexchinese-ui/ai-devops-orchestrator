from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    reason: str


def decide_retry(
    *,
    failure_kind: str | None,
    failure_detail: str | None,
    attempt: int,
    max_attempts: int,
) -> RetryDecision:
    """Hard gate for automatic retries.

    Philosophy:
    - Prefer rerunning *the same CI/test step* once for flakiness.
    - Only allow LLM-driven 'fix-and-retry' for fixable categories.
    - Never exceed max_attempts.

    This is a placeholder policy; tune with your own signals.
    """

    if attempt >= max_attempts:
        return RetryDecision(False, f"attempt {attempt} >= max_attempts {max_attempts}")

    fk = (failure_kind or "unknown").lower()
    detail = (failure_detail or "").lower()

    # Safe flake rerun bucket
    if "timeout" in detail or "flaky" in detail or "temporar" in detail:
        return RetryDecision(True, "flaky/timeout signal")

    # Known fixable buckets
    if fk in {"lint", "format", "type", "build"}:
        return RetryDecision(True, f"fixable failure_kind={fk}")

    if fk in {"test", "ci"}:
        # Only retry automatically if we have a strong signal
        if any(k in detail for k in ["connection reset", "rate limit", "502", "503"]):
            return RetryDecision(True, "infra signal in CI/test")
        return RetryDecision(False, "CI/test failures require classification / human gate")

    return RetryDecision(False, f"unknown/untrusted failure_kind={fk}")
