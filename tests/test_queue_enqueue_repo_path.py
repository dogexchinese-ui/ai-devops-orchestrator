from orchestrator import db as dbm
from orchestrator.queue import enqueue_plan


def test_enqueue_stores_repo_and_paths(tmp_path):
    db_path = tmp_path / "orch.db"
    con = dbm.connect(dbm.DbConfig(path=str(db_path)))
    dbm.migrate(con)

    plan = {
        "planId": "p-repo-1",
        "title": "repo path test",
        "repo": "demo/repo",
        "repoPath": "/tmp/demo-repo",
        "subtasks": [
            {
                "id": "t-a",
                "prompt": "do A",
                "routing": "codex-backend",
            },
            {
                "id": "t-b",
                "prompt": "do B",
                "routing": "codex-backend",
                "repoPath": "/tmp/override-repo",
            },
        ],
    }

    enqueue_plan(con, plan)

    a = con.execute("SELECT repo, repo_path FROM tasks WHERE id='t-a'").fetchone()
    b = con.execute("SELECT repo, repo_path FROM tasks WHERE id='t-b'").fetchone()

    assert a["repo"] == "demo/repo"
    assert a["repo_path"] == "/tmp/demo-repo"
    assert b["repo"] == "demo/repo"
    assert b["repo_path"] == "/tmp/override-repo"
