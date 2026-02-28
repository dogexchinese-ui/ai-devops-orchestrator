from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import db as dbm


@dataclass(frozen=True)
class WorktreeInfo:
    path: str
    branch: Optional[str]
    managed: bool


def ensure_task_worktree(
    con,
    *,
    task_id: str,
    repo_path: Optional[str],
    worktree_path: Optional[str],
) -> Optional[WorktreeInfo]:
    repo = (repo_path or "").strip()
    if not repo:
        return None

    repo_dir = Path(repo)
    if not _is_git_repo(repo_dir):
        return None

    configured_worktree = (worktree_path or "").strip()
    if configured_worktree:
        wt = Path(configured_worktree)
        managed = False
        if not _is_git_repo(wt):
            branch = f"orchestrator/{_sanitize_branch(task_id)}"
            _git(repo_dir, "worktree", "add", str(wt), "-B", branch)
        branch_name = _branch_name(wt)
        _persist_worktree(con, task_id, str(wt), managed, branch_name)
        return WorktreeInfo(path=str(wt), branch=branch_name, managed=managed)

    managed = True
    branch = f"orchestrator/{_sanitize_branch(task_id)}"
    wt = repo_dir / ".orchestrator" / "worktrees" / _sanitize_path(task_id)
    if not _is_git_repo(wt):
        wt.parent.mkdir(parents=True, exist_ok=True)
        _git(repo_dir, "worktree", "add", str(wt), "-B", branch)
    branch_name = _branch_name(wt)
    _persist_worktree(con, task_id, str(wt), managed, branch_name)
    return WorktreeInfo(path=str(wt), branch=branch_name, managed=managed)


def cleanup_task_worktree(con, *, task_id: str) -> None:
    row = con.execute(
        "SELECT worktree_path, worktree_managed, repo_path FROM tasks WHERE id=?",
        (task_id,),
    ).fetchone()
    if not row:
        return

    wt = (row["worktree_path"] or "").strip()
    repo = (row["repo_path"] or "").strip()
    managed = int(row["worktree_managed"] or 0) == 1

    if not managed or not wt or not repo:
        return

    wt_path = Path(wt)
    if not wt_path.exists():
        _clear_worktree_fields(con, task_id)
        return

    safe_root = Path(repo) / ".orchestrator" / "worktrees"
    if not _is_within(wt_path, safe_root):
        return

    try:
        _git(Path(repo), "worktree", "remove", "--force", str(wt_path))
    except Exception:
        # Fall back to local cleanup in case git worktree metadata is stale.
        shutil.rmtree(wt_path, ignore_errors=True)
    _clear_worktree_fields(con, task_id)


def _persist_worktree(con, task_id: str, path: str, managed: bool, branch: Optional[str]) -> None:
    now = dbm.now_ts()
    con.execute(
        "UPDATE tasks SET worktree_path=?, worktree_managed=?, worktree_branch=?, updated_at=? WHERE id=?",
        (path, 1 if managed else 0, branch, now, task_id),
    )


def _clear_worktree_fields(con, task_id: str) -> None:
    now = dbm.now_ts()
    con.execute(
        "UPDATE tasks SET worktree_path=NULL, worktree_managed=0, worktree_branch=NULL, updated_at=? WHERE id=?",
        (now, task_id),
    )


def _branch_name(path: Path) -> Optional[str]:
    try:
        return _git(path, "rev-parse", "--abbrev-ref", "HEAD").strip() or None
    except Exception:
        return None


def _is_git_repo(path: Path) -> bool:
    try:
        _git(path, "rev-parse", "--is-inside-work-tree")
        return True
    except Exception:
        return False


def _git(cwd: Path, *args: str) -> str:
    p = subprocess.run(["git", *args], cwd=str(cwd), text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or f"git {' '.join(args)} failed")
    return p.stdout


def _sanitize_branch(task_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._/-]+", "-", task_id).strip("-/") or "task"


def _sanitize_path(task_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", task_id).strip("-.") or "task"


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([str(path.resolve()), str(root.resolve())]) == str(root.resolve())
    except Exception:
        return False
