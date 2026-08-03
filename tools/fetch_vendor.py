#!/usr/bin/env python3
"""Fetch the third-party sources gammonNet builds on, pinned to an exact commit.

Nothing fetched here is committed to this repository: `vendor/` is gitignored.
What IS committed is the pin below — so that any measurement can be traced back
to the exact upstream tree that produced it.

Licences are recorded in THIRD-PARTY.md. Read it before adding a source here.

Usage:
    python tools/fetch_vendor.py             # fetch, pin, and build
    python tools/fetch_vendor.py --no-build  # fetch and pin only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor"


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    commit: str
    licence: str


SOURCES = (
    Source(
        name="backgammon-ai-engine",
        url="https://github.com/alexstrehl/backgammon-ai-engine.git",
        commit="b2750df",
        licence="MIT",
    ),
)


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"    $ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def fetch(source: Source) -> None:
    dest = VENDOR / source.name

    if not (dest / ".git").is_dir():
        print(f"==> cloning {source.name} ({source.licence})")
        run(["git", "clone", source.url, str(dest)])
    else:
        print(f"==> updating {source.name} ({source.licence})")
        run(["git", "fetch", "--all", "--tags"], cwd=dest)

    run(["git", "checkout", "--quiet", source.commit], cwd=dest)
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    print(f"    {source.name} @ {head}")


def build_reference_engine() -> None:
    """Build the reference C rules engine — ~20x faster than its pure-Python path."""
    c_engine = VENDOR / "backgammon-ai-engine" / "c_engine"
    print("==> building the reference C rules engine")
    run(
        ["gcc", "-O2", "-shared", "-fPIC", "-o", "libbg_engine.so", "bg_engine.c", "-Wall"],
        cwd=c_engine,
    )
    print(f"    {c_engine / 'libbg_engine.so'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-build", action="store_true", help="fetch and pin only, do not compile"
    )
    args = parser.parse_args()

    VENDOR.mkdir(exist_ok=True)
    for source in SOURCES:
        fetch(source)

    if not args.no_build:
        build_reference_engine()

    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
