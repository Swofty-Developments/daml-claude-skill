#!/usr/bin/env python3
"""Ensure the Daml reference corpus is available locally.

Prints the absolute path to the directory containing `canton/`, `splice/`,
and `splice-wallet-kernel/`. Works on macOS, Linux, and Windows.

Resolution order:
  1. $DAML_REFS env var (if set and contains all three repos)
  2. ~/Developer/daml/ (if it contains all three repos)
  3. <user cache dir>/daml-claude-skill/refs/ (clones there on first use)

The cache location is:
  - macOS/Linux: ~/.cache/daml-claude-skill/refs
  - Windows:     %LOCALAPPDATA%\\daml-claude-skill\\refs

Idempotent: ~50 ms when repos exist, 30-120 s on first clone.
Requires: python3, git (both standard on dev machines).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPOS = [
    ("canton",               "https://github.com/digital-asset/canton.git"),
    ("splice",               "https://github.com/hyperledger-labs/splice.git"),
    ("splice-wallet-kernel", "https://github.com/hyperledger-labs/splice-wallet-kernel.git"),
]


def has_all_repos(base: Path) -> bool:
    return all((base / name).is_dir() for name, _ in REPOS)


def cache_dir() -> Path:
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / "daml-claude-skill" / "refs"
    return Path.home() / ".cache" / "daml-claude-skill" / "refs"


def clone_if_missing(base: Path, name: str, url: str) -> None:
    target = base / name
    if target.is_dir():
        return
    print(f"cloning {name} into {base} ...", file=sys.stderr)
    if shutil.which("git") is None:
        sys.exit("error: git is not installed or not on PATH")
    subprocess.run(
        ["git", "clone", "--depth=1", "--quiet", url, str(target)],
        check=True,
    )


def main() -> int:
    env = os.environ.get("DAML_REFS")
    if env and has_all_repos(Path(env).expanduser()):
        print(Path(env).expanduser().resolve())
        return 0

    dev = Path.home() / "Developer" / "daml"
    if has_all_repos(dev):
        print(dev.resolve())
        return 0

    base = cache_dir()
    base.mkdir(parents=True, exist_ok=True)
    for name, url in REPOS:
        clone_if_missing(base, name, url)
    print(base.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
