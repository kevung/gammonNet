#!/usr/bin/env python3
"""Export the reference network to the flat `.bin` our C code reads.

A thin wrapper around `export_weights.py` of the vendored reference repository
(Alexander Strehl, MIT). It is a wrapper and not a re-implementation on
purpose: the file format is theirs, and a second writer of it would be a second
thing to keep in step with the reader.

What this adds is the part that belongs to us -- putting the artefact where the
project expects it, and recording *which* weights produced it. `BRIEF.md` §8 is
explicit that a network is identified by its weights: an artefact whose
provenance is not traceable cannot carry a measurement.

    python tools/export_model.py
    python tools/export_model.py --model <name.pt> --out <path.bin>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "vendor" / "backgammon-ai-engine"

# The only model this project retains. `BRIEF.md` §3.1: the cubeful variants
# emit an aggregated money equity, which match play cannot use.
DEFAULT_MODEL = "cubeless_prob5_512_512_256_128.pt"
DEFAULT_OUT = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pinned_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REFERENCE), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    source = REFERENCE / "best_models" / args.model
    if not source.is_file():
        print(f"modèle introuvable : {source}", file=sys.stderr)
        print("lancer d'abord `make vendor`", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)

    # Run in the reference tree: export_weights.py imports `model` and
    # `encoding` as siblings.
    result = subprocess.run(
        [sys.executable, "export_weights.py", str(source), str(args.out.resolve())],
        cwd=REFERENCE, capture_output=True, text=True,
    )
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode

    provenance = {
        "network": args.model,
        "source": "alexstrehl/backgammon-ai-engine",
        "license": "MIT",
        "pinned_commit": pinned_commit(),
        "artifact": args.out.name,
        "sha256": sha256(args.out),
        "bytes": args.out.stat().st_size,
    }
    sidecar = args.out.with_suffix(".provenance.json")
    sidecar.write_text(json.dumps(provenance, indent=2) + "\n")

    print(f"  Provenance: {sidecar}")
    print(f"  SHA-256: {provenance['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
