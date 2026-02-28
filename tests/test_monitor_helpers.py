from orchestrator.monitor import CiInfo, discover_ci, parse_github_repo


def test_parse_github_repo_variants():
    assert parse_github_repo("git@github.com:org/repo.git") == "org/repo"
    assert parse_github_repo("ssh://git@github.com/org/repo.git") == "org/repo"
    assert parse_github_repo("https://github.com/org/repo") == "org/repo"
    assert parse_github_repo("https://gitlab.com/org/repo") is None


def test_discover_ci_state_failed(monkeypatch):
    def fake_gh_json(*args):
        assert args[0:2] == ("pr", "checks")
        return [
            {"state": "SUCCESS", "link": "https://ci.example/1", "name": "lint"},
            {"state": "FAILURE", "link": "https://ci.example/2", "name": "tests"},
        ]

    monkeypatch.setattr("orchestrator.monitor._gh_json", fake_gh_json)
    ci = discover_ci("org/repo", 42)
    assert isinstance(ci, CiInfo)
    assert ci.state == "failed"
    assert ci.url == "https://ci.example/1"
