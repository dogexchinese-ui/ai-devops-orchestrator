from orchestrator import db as dbm


def test_migrate_adds_pr_ci_and_worktree_columns(tmp_path):
    db_path = tmp_path / "orch.db"
    con = dbm.connect(dbm.DbConfig(path=str(db_path)))
    dbm.migrate(con)

    cols = {r["name"] for r in con.execute("PRAGMA table_info(tasks)").fetchall()}
    assert "worktree_managed" in cols
    assert "worktree_branch" in cols
    assert "pr_number" in cols
    assert "pr_url" in cols
    assert "ci_state" in cols
    assert "ci_detail" in cols
    assert "ci_url" in cols
