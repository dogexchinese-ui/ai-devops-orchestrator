from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FailureClassification:
    kind: str
    detail: str


_PATTERNS = (
    (
        "lint",
        [
            r"\blint(?:ing)?\b",
            r"\bflake8\b",
            r"\beslint\b",
            r"\bruff\b",
            r"\bpylint\b",
            r"\bblack\b",
            r"\bstyle check\b",
            r"\bformat(?:ting)? check\b",
        ],
    ),
    (
        "test",
        [
            r"\btest(?:s)?\b.*\bfailed\b",
            r"\bpytest\b",
            r"\bjunit\b",
            r"\bnosetests\b",
            r"\bfailing test\b",
            r"\bassert(?:ion)?error\b",
        ],
    ),
    (
        "build",
        [
            r"\bbuild\b.*\bfailed\b",
            r"\bcompile(?:r|d)?\b",
            r"\bcompilation\b",
            r"\bsyntax error\b",
            r"\blink(?:er)? error\b",
            r"\bmodule not found\b",
            r"\bfailed to build\b",
        ],
    ),
    (
        "ci",
        [
            r"\bgithub actions\b",
            r"\bworkflow run\b",
            r"\bci\b",
            r"\bcheck run\b",
            r"\bstatus check\b",
            r"\bpipeline\b",
        ],
    ),
    (
        "agent",
        [
            r"\bcodex\b",
            r"\bopenclaw\b",
            r"\bagent\b",
            r"\bunsupported routing\b",
            r"\bbinary not found\b",
            r"\btimeout\b",
            r"\bpermission denied\b",
        ],
    ),
)


def classify_failure(text: str, *, rc: int | None = None) -> FailureClassification:
    hay = (text or "").lower()
    if rc is not None and rc in (126, 127):
        return FailureClassification(kind="agent", detail=f"runner rc={rc}")

    for kind, patterns in _PATTERNS:
        for pat in patterns:
            if re.search(pat, hay):
                return FailureClassification(kind=kind, detail=f"matched:{pat}")

    if rc is not None:
        return FailureClassification(kind="unknown", detail=f"runner rc={rc}")
    return FailureClassification(kind="unknown", detail="no failure signal matched")
