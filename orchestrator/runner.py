from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from . import db as dbm


def run_task(db_path: str, task_id: str) -> int:
    con = dbm.connect(dbm.DbConfig(path=db_path))
    dbm.migrate(con)

    row = con.execute(
        "SELECT id, routing, prompt, worktree_path, repo_path, plan_id FROM tasks WHERE id=?",
        (task_id,),
    ).fetchone()
    if not row:
        print(f"task not found: {task_id}", file=sys.stderr)
        return 66

    routing = (row["routing"] or "").strip().lower()
    prompt = row["prompt"] or ""

    if _is_codex_route(routing):
        return _run_codex(task_id=task_id, prompt=prompt, worktree_path=row["worktree_path"], repo_path=row["repo_path"])

    if _is_reviewer_route(routing):
        return _run_openclaw_agent(agent="reviewer", prompt=prompt)

    if _is_designer_route(routing):
        return _run_openclaw_agent(agent="designer", prompt=prompt)

    if _is_triage_route(routing):
        return _run_openclaw_agent(agent="triage", prompt=prompt)

    print(f"unsupported routing: {routing!r}", file=sys.stderr)
    return 64


def _is_codex_route(r: str) -> bool:
    return r.startswith("codex") or r in {"backend", "frontend", "coding", "implement"}


def _is_reviewer_route(r: str) -> bool:
    return r in {"reviewer", "review", "claude-review"} or "review" in r


def _is_designer_route(r: str) -> bool:
    return r in {"designer", "design", "gemini-design"} or "design" in r


def _is_triage_route(r: str) -> bool:
    return r in {"triage", "classify", "qwen-triage"} or "triage" in r


def _run_codex(*, task_id: str, prompt: str, worktree_path: Optional[str], repo_path: Optional[str]) -> int:
    workdir = (worktree_path or "").strip() or (repo_path or "").strip() or os.environ.get("ORCH_WORKDIR", "").strip()
    if not workdir:
        print("codex route requires worktree_path/repo_path or ORCH_WORKDIR", file=sys.stderr)
        return 65

    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    aux = wd / ".orchestrator"
    aux.mkdir(parents=True, exist_ok=True)
    prompt_file = aux / f"prompt.{task_id}.txt"
    prompt_file.write_text(prompt, encoding="utf-8")

    if not _has_bin("codex"):
        print("codex binary not found in PATH", file=sys.stderr)
        return 127

    cmd = ["codex", "exec", "--full-auto", prompt]
    p = subprocess.run(cmd, cwd=str(wd), text=True, capture_output=True)
    if p.stdout:
        print(p.stdout)
    if p.stderr:
        print(p.stderr, file=sys.stderr)
    return p.returncode


def _run_openclaw_agent(*, agent: str, prompt: str) -> int:
    if not _has_bin("openclaw"):
        print("openclaw binary not found in PATH", file=sys.stderr)
        return 127

    cmd = [
        "openclaw",
        "agent",
        "--agent",
        agent,
        "--thinking",
        "high",
        "--message",
        prompt,
        "--json",
    ]
    p = subprocess.run(cmd, text=True, capture_output=True)
    if p.stdout:
        print(p.stdout)
    if p.stderr:
        print(p.stderr, file=sys.stderr)
    return p.returncode


def _has_bin(name: str) -> bool:
    from shutil import which

    return which(name) is not None


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--task-id", required=True)
    args = ap.parse_args(argv)
    return run_task(db_path=args.db, task_id=args.task_id)


if __name__ == "__main__":
    raise SystemExit(main())
