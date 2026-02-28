from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from typing import Iterable, Optional

from . import db as dbm


@dataclass(frozen=True)
class PullRequestInfo:
    number: int
    url: str


@dataclass(frozen=True)
class CiInfo:
    state: str
    detail: str
    url: Optional[str]


def monitor_once(db_path: str, *, task_id: Optional[str] = None) -> int:
    con = dbm.connect(dbm.DbConfig(path=db_path))
    dbm.migrate(con)

    rows = _load_tasks(con, task_id=task_id)
    updated = 0
    for row in rows:
        wt = (row["worktree_path"] or "").strip()
        if not wt:
            continue
        try:
            branch = _git(wt, "rev-parse", "--abbrev-ref", "HEAD").strip()
        except Exception:
            continue
        if not branch:
            continue

        _update_worktree_branch(con, row["id"], branch)

        repo_slug = _repo_slug_from_worktree(wt)
        if not repo_slug:
            continue

        pr = discover_pr(repo_slug, branch)
        if not pr:
            continue

        ci = discover_ci(repo_slug, pr.number)
        _write_pr_ci(con, task_id=row["id"], pr=pr, ci=ci)
        updated += 1

    return updated


def discover_pr(repo_slug: str, branch: str) -> Optional[PullRequestInfo]:
    payload = _gh_json(
        "pr",
        "list",
        "--repo",
        repo_slug,
        "--state",
        "all",
        "--head",
        branch,
        "--limit",
        "20",
        "--json",
        "number,url,headRefName",
    )
    for item in payload:
        if item.get("headRefName") == branch:
            return PullRequestInfo(number=int(item["number"]), url=str(item["url"]))
    if payload:
        item = payload[0]
        return PullRequestInfo(number=int(item["number"]), url=str(item["url"]))
    return None


def discover_ci(repo_slug: str, pr_number: int) -> CiInfo:
    payload = _gh_json("pr", "checks", str(pr_number), "--repo", repo_slug, "--json", "state,link,name")
    if not payload:
        return CiInfo(state="unknown", detail="no checks", url=None)

    states = [str(i.get("state") or "").upper() for i in payload]
    failed_states = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}
    success_states = {"SUCCESS", "SKIPPED", "NEUTRAL"}
    pending_states = {"PENDING", "IN_PROGRESS", "QUEUED", "WAITING"}

    if any(s in failed_states for s in states):
        state = "failed"
    elif all((s in success_states) for s in states if s):
        state = "passed"
    elif any(s in pending_states for s in states):
        state = "pending"
    else:
        state = "unknown"

    detail = ",".join(sorted(set(states))) or "unknown"
    ci_url = None
    for item in payload:
        link = item.get("link")
        if link:
            ci_url = str(link)
            break
    return CiInfo(state=state, detail=detail, url=ci_url)


def parse_github_repo(remote_url: str) -> Optional[str]:
    url = (remote_url or "").strip()
    if not url:
        return None

    if url.startswith("git@github.com:"):
        slug = url.split("git@github.com:", 1)[1]
    elif url.startswith("ssh://git@github.com/"):
        slug = url.split("ssh://git@github.com/", 1)[1]
    elif url.startswith("https://github.com/"):
        slug = url.split("https://github.com/", 1)[1]
    else:
        return None

    if slug.endswith(".git"):
        slug = slug[:-4]
    parts = [p for p in slug.split("/") if p]
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def _repo_slug_from_worktree(worktree_path: str) -> Optional[str]:
    try:
        remote = _git(worktree_path, "remote", "get-url", "origin").strip()
    except Exception:
        return None
    return parse_github_repo(remote)


def _load_tasks(con, *, task_id: Optional[str]) -> Iterable:
    if task_id:
        return con.execute(
            "SELECT id, worktree_path, worktree_branch FROM tasks WHERE id=?",
            (task_id,),
        ).fetchall()
    return con.execute(
        "SELECT id, worktree_path, worktree_branch FROM tasks WHERE kind='subtask' AND worktree_path IS NOT NULL",
    ).fetchall()


def _update_worktree_branch(con, task_id: str, branch: str) -> None:
    now = dbm.now_ts()
    con.execute(
        "UPDATE tasks SET worktree_branch=?, updated_at=? WHERE id=?",
        (branch, now, task_id),
    )


def _write_pr_ci(con, *, task_id: str, pr: PullRequestInfo, ci: CiInfo) -> None:
    now = dbm.now_ts()
    con.execute(
        """
        UPDATE tasks
        SET pr_number=?, pr_url=?, ci_state=?, ci_detail=?, ci_url=?, updated_at=?
        WHERE id=?
        """,
        (pr.number, pr.url, ci.state, ci.detail, ci.url, now, task_id),
    )


def _git(cwd: str, *args: str) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "git command failed")
    return p.stdout


def _gh_json(*args: str):
    try:
        p = subprocess.run(["gh", *args], text=True, capture_output=True)
    except FileNotFoundError as e:
        raise RuntimeError("gh CLI not found in PATH") from e
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "gh command failed")
    text = (p.stdout or "").strip()
    if not text:
        return []
    return json.loads(text)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--task-id", default=None)
    args = ap.parse_args(argv)
    try:
        updated = monitor_once(args.db, task_id=args.task_id)
    except RuntimeError as e:
        print(str(e))
        return 2
    print(updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
