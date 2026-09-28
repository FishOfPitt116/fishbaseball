"""Downstream canary: checks a real `pip install`ed `fishbaseball` against the live published
data. Not part of the package — run directly (`python scripts/canary.py`), never imported by
`fishbaseball` itself, so it never ships in the wheel.

Checks:
1. The release pointer (`latest.json`) resolves without error.
2. Its schema_version is one this installed version supports (`SchemaChangedError` would fail this).
3. Every table in the catalog downloads, verifies its checksum, and matches the manifest's
   declared columns — since the CI runner's cache starts empty, `load()` exercises the full
   fetch-and-verify path for real, for every table.

One open issue (label `canary`) covers a failing run, commented on if it recurs; the next
success closes it. Not yet checked: whether an older installed minor version still reads
current data cleanly (meaningful once there's more than one minor version to test).

CLI: python scripts/canary.py [--repo OWNER/REPO] [--alert]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run_checks() -> list[str]:
    """Returns a list of failure messages; empty means everything passed."""
    import fishbaseball as fb
    from fishbaseball.exceptions import FishbaseballError

    failures: list[str] = []

    try:
        tag = fb.lahman.version(refresh=True)
        print(f"ok    resolved release: {tag}")
    except FishbaseballError as e:
        failures.append(f"version(): {type(e).__name__}: {e}")
        print(f"FAIL  version(): {e}")
        return failures  # nothing downstream can be checked without a resolved release

    try:
        names = fb.lahman.tables()
        print(f"ok    tables(): {len(names)} tables")
    except FishbaseballError as e:
        failures.append(f"tables(): {type(e).__name__}: {e}")
        print(f"FAIL  tables(): {e}")
        return failures

    for name in names:
        try:
            df = fb.lahman.load(name, refresh=True)
            print(f"ok    load({name!r}): {df.height} rows")
        except FishbaseballError as e:
            failures.append(f"load({name!r}): {type(e).__name__}: {e}")
            print(f"FAIL  load({name!r}): {e}")

    return failures


def _gh(*args: str, repo: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args, "--repo", repo], capture_output=True, text=True, check=True)


def alert(failures: list[str], repo: str, run_url: str) -> None:
    open_issues = json.loads(
        _gh(
            "issue", "list", "--state", "open", "--label", "canary", "--json", "number", repo=repo
        ).stdout
    )
    if failures:
        body = f"Run: {run_url}\n\n```\n" + "\n".join(failures) + "\n```\n"
        if open_issues:
            _gh("issue", "comment", str(open_issues[0]["number"]), "--body", body, repo=repo)
        else:
            _gh(
                "issue", "create", "--title", "fishbaseball downstream canary failed",
                "--body", body, "--label", "canary", repo=repo,
            )  # fmt: skip
    else:
        for issue in open_issues:
            _gh(
                "issue", "close", str(issue["number"]),
                "--comment", f"Resolved by a successful run: {run_url}", repo=repo,
            )  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--repo", default=os.environ.get("GITHUB_REPOSITORY", "FishOfPitt116/fishbaseball")
    )
    ap.add_argument("--run-url", default="")
    ap.add_argument("--alert", action="store_true")
    args = ap.parse_args(argv)

    failures = run_checks()
    Path("canary.json").write_text(json.dumps(failures, indent=2) + "\n")
    if args.alert:
        alert(failures, args.repo, args.run_url)
    if failures:
        print(f"\n{len(failures)} check(s) failed", file=sys.stderr)
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
