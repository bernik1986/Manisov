"""Fail-closed admission for both Actions and timer deployments of one commit."""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.request import Request, urlopen


def github_get(path):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    with urlopen(Request("https://api.github.com" + path, headers=headers), timeout=30) as response:
        return json.load(response)


def verified(sha, repository, get=github_get):
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        raise ValueError("Exact SHA and owner/repository are required")
    prefix = f"/repos/{repository}/actions"
    runs = get(f"{prefix}/workflows/deploy.yml/runs?head_sha={sha}&per_page=100")["workflow_runs"]
    # Only the newest trusted-branch run counts. A failed rerun revokes admission.
    runs = [r for r in runs if r["head_sha"] == sha and r["head_branch"] == "main"
            and r["event"] in {"push", "workflow_dispatch"}
            and r["path"].split("@")[0] == ".github/workflows/deploy.yml"
            and r["repository"]["full_name"].lower() == repository.lower()]
    if not runs:
        return False
    run = max(runs, key=lambda r: (r["run_number"], r.get("run_attempt", 1)))
    jobs = get(f"{prefix}/runs/{run['id']}/attempts/{run.get('run_attempt', 1)}/jobs?per_page=100")["jobs"]
    checks = [j for j in jobs if j["name"] == "verify"]
    return len(checks) == 1 and checks[0]["status"] == "completed" and checks[0]["conclusion"] == "success"


if __name__ == "__main__":
    try:
        allowed = verified(sys.argv[1], os.environ["GITHUB_REPOSITORY"])
    except Exception as exc:
        raise SystemExit(f"CI admission unavailable; deployment denied ({type(exc).__name__})") from None
    if not allowed:
        raise SystemExit("Exact commit lacks a successful verify job in deploy.yml; deployment denied")
