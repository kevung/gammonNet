#!/usr/bin/env python3
"""Record the exact machine and toolchain a measurement was produced on.

Every strength or throughput figure this repository publishes must cite the
configuration it came from. This script produces that citation, in a form that
can be pasted into a report or committed next to one.

Usage:
    python tools/env_report.py            # human-readable
    python tools/env_report.py --json     # machine-readable
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone


def _run(cmd: list[str]) -> str | None:
    """Run a command, returning its first line of output, or None if unavailable."""
    if shutil.which(cmd[0]) is None:
        return None
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (subprocess.SubprocessError, OSError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip().splitlines()[0] if out.stdout.strip() else None


def _cpu_model() -> str | None:
    try:
        with open("/proc/cpuinfo") as fh:
            for line in fh:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def _memory_gib() -> float | None:
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / (1024 * 1024), 1)
    except (OSError, ValueError):
        pass
    return None


def _gpus() -> list[str]:
    """List CUDA devices as seen by torch, falling back to nvidia-smi.

    torch is the authority here: a GPU nvidia-smi reports but torch cannot open
    is a GPU this project cannot use.
    """
    try:
        import torch
    except ImportError:
        raw = _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
        return [f"{raw} (seen by nvidia-smi; torch not installed)"] if raw else []

    if not torch.cuda.is_available():
        return []
    return [
        f"{torch.cuda.get_device_name(i)} "
        f"({torch.cuda.get_device_properties(i).total_memory // (1024**2)} MiB)"
        for i in range(torch.cuda.device_count())
    ]


def collect() -> dict:
    try:
        import torch

        torch_version = torch.__version__
        cuda_version = torch.version.cuda
    except ImportError:
        torch_version = cuda_version = None

    try:
        import numpy

        numpy_version = numpy.__version__
    except ImportError:
        numpy_version = None

    import os

    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        # Le nom de la machine n'est PAS consigné. Les rapports de mesure sont
        # publiés, et un nom d'hôte n'apporte rien à la reproductibilité : ce
        # qui compte est la configuration, pas l'étiquette. `--host` le remet
        # pour un usage local.
        "os": f"{platform.system()} {platform.release()}",
        "cpu": _cpu_model(),
        "cpu_threads": os.cpu_count(),
        "memory_gib": _memory_gib(),
        "gpus": _gpus(),
        "python": sys.version.split()[0],
        "torch": torch_version,
        "torch_cuda": cuda_version,
        "numpy": numpy_version,
        "gcc": _run(["gcc", "--version"]),
        "emcc": _emcc_version(),
        "gnubg_nn": _gnubg_nn_version(),
    }


# Emscripten n'est pas toujours dans le PATH : le paquet Arch l'installe sous
# /usr/lib/emscripten sans lien dans /usr/bin. Le signaler « absent » alors
# qu'il est présent ferait consigner à une mesure une configuration fausse.
EMCC_CANDIDATES = (
    "emcc",
    "/usr/lib/emscripten/emcc",
    "/usr/share/emscripten/emcc",
)


def _emcc_version() -> str | None:
    for candidate in EMCC_CANDIDATES:
        found = _run([candidate, "--version"])
        if found:
            return found
    return None


def _gnubg_nn_version() -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("gnubg-nn")
    except PackageNotFoundError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--host", action="store_true",
                        help="inclure le nom de la machine — usage local, "
                             "à ne pas coller dans un rapport publié")
    args = parser.parse_args()

    info = collect()
    if args.json:
        print(json.dumps(info, indent=2))
        return 0

    width = max(len(k) for k in info)
    for key, value in info.items():
        if isinstance(value, list):
            value = ", ".join(value) if value else "none"
        print(f"{key.rjust(width)} : {value if value is not None else 'absent'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
