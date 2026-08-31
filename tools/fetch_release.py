#!/usr/bin/env python3
"""Fetch the pinned float16 release artifact that `tools/serve.py` loads.

`models/release_pin.json` is committed and names an exact published release
archive (`archive.url`, `archive.sha256`) plus the two members inside it this
project actually needs — the big network and the pruning network, both
float16. GitHub release ASSETS on this repository are the archive and its
own checksum file, not the individual weight files (`gh release view` shows
exactly two assets); the weights only exist as members of that tarball. This
script downloads the archive, verifies IT, extracts exactly the two named
members into `models/`, and refuses to leave either in place if its own
SHA-256 does not match the pin.

This is deliberately NOT `make model` + `tools/pack_fp16.py`: the whole point
of pinning a *published* artifact is that it is the same bytes the WebAssembly
target ships (#18's constraint, already verified in the T50 release audit) —
byte-identical, not merely "regenerated the same way". Regenerating here would
reintroduce exactly the drift the pin exists to rule out.

Usage:
    python tools/fetch_release.py                    # fetch, extract, verify
    python tools/fetch_release.py --pin models/release_pin.json --dest models
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PIN = ROOT / "models" / "release_pin.json"
DEFAULT_DEST = ROOT / "models"

CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path) -> None:
    print(f"    $ GET {url}")
    with urllib.request.urlopen(url) as response, dest.open("wb") as out:
        while True:
            chunk = response.read(CHUNK)
            if not chunk:
                break
            out.write(chunk)


def already_satisfied(pin: dict, dest_dir: Path) -> bool:
    for key in ("network_fp16", "prune_fp16"):
        target = dest_dir / pin[key]["filename"]
        if not target.is_file() or sha256_of(target) != pin[key]["sha256"].lower():
            return False
    return True


def fetch(pin_path: Path, dest_dir: Path, force: bool) -> None:
    pin = json.loads(pin_path.read_text())
    dest_dir.mkdir(parents=True, exist_ok=True)

    print(f"==> release épinglée : {pin['version']}")
    if not force and already_satisfied(pin, dest_dir):
        print("    déjà présents et conformes — rien à faire (--force pour retélécharger)")
        return

    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / "archive.tar.gz"
        download(pin["archive"]["url"], archive_path)

        actual = sha256_of(archive_path)
        expected = pin["archive"]["sha256"].lower()
        if actual != expected:
            raise SystemExit(
                f"REFUSÉ : l'archive téléchargée ne correspond pas au SHA-256 épinglé\n"
                f"  attendu : {expected}\n"
                f"  obtenu  : {actual}\n"
                f"Rien n'est extrait — une archive qui ne correspond pas à son épingle "
                f"n'est jamais gardée, jamais approximée."
            )
        print(f"    archive : sha256 conforme ({pin['archive']['url'].rsplit('/', 1)[-1]})")

        with tarfile.open(archive_path) as tar:
            for key in ("network_fp16", "prune_fp16"):
                entry = pin[key]
                member = tar.getmember(entry["member"])
                extracted = Path(tmp) / "extracted"
                # `filter=` needs Python >= 3.12 (or a backport not guaranteed
                # present everywhere this script runs) — fall back silently
                # where it is not accepted. Either way this is safe: the
                # archive is OUR OWN pinned, hash-verified release, not
                # attacker-controlled input.
                try:
                    tar.extract(member, path=extracted, filter="data")
                except TypeError:
                    tar.extract(member, path=extracted)
                source = extracted / entry["member"]

                actual = sha256_of(source)
                expected = entry["sha256"].lower()
                if actual != expected:
                    raise SystemExit(
                        f"REFUSÉ : {entry['member']} (dans l'archive) ne correspond pas "
                        f"au SHA-256 épinglé pour {key}\n"
                        f"  attendu : {expected}\n"
                        f"  obtenu  : {actual}"
                    )

                target = dest_dir / entry["filename"]
                shutil.move(str(source), str(target))
                print(f"    {key} : sha256 conforme -> {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pin", type=Path, default=DEFAULT_PIN)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--force", action="store_true", help="retélécharger même si déjà conforme")
    args = parser.parse_args()

    fetch(args.pin, args.dest, args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
