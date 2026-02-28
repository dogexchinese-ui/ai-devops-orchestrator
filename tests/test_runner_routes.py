from orchestrator.runner import (
    _is_codex_route,
    _is_designer_route,
    _is_reviewer_route,
    _is_triage_route,
)


def test_route_detection():
    assert _is_codex_route("codex-backend")
    assert _is_codex_route("frontend")
    assert _is_reviewer_route("reviewer")
    assert _is_reviewer_route("pr-review")
    assert _is_designer_route("gemini-design")
    assert _is_triage_route("qwen-triage")
