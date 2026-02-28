from orchestrator.failure import classify_failure


def test_classify_lint_failure():
    c = classify_failure("ruff check failed with 12 violations", rc=1)
    assert c.kind == "lint"


def test_classify_test_failure():
    c = classify_failure("pytest output: 2 failed, 10 passed", rc=1)
    assert c.kind == "test"


def test_classify_build_failure():
    c = classify_failure("compilation failed: syntax error", rc=1)
    assert c.kind == "build"


def test_classify_ci_failure():
    c = classify_failure("github actions status check failed", rc=1)
    assert c.kind == "ci"


def test_classify_agent_failure_from_rc():
    c = classify_failure("", rc=127)
    assert c.kind == "agent"


def test_classify_unknown():
    c = classify_failure("some random failure text", rc=3)
    assert c.kind == "unknown"
