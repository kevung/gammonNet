"""La mémoire de travail d'un fil est rendue quand ce fil meurt (issue #35).

Chaque fil qui évalue reçoit ses tampons (`gn_parallel_scratch`) — près d'un
mégaoctet pour le noyau par lot. Les fils du pool vivent autant que le
processus ; mais un appelant peut évaluer depuis des fils éphémères, un par
requête par exemple. Tant que ces tampons n'étaient jamais libérés, chaque fil
mort en abandonnait un jeu : +1 Mo par requête 0-ply, jusqu'à l'OOM.

Ce test fait chercher 200 fils neufs, pool à un fil puis à quatre, et exige
que la mémoire résidente reste plate. Le 0-ply suffit : c'est le fil appelant
qui alloue ses tampons et meurt. Le seuil (32 Mo) est loin des deux côtés —
mesuré le 2026-10-28 : +206 Mo avant la correction, moins d'un mégaoctet
après.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import Position  # noqa: E402
from gammonnet.search import SearchConfig, search_plays, set_threads  # noqa: E402

PIN = ROOT / "models" / "release_pin.json"
MODEL = PIN.parent / json.loads(PIN.read_text())["network_fp16"]["filename"]
needs_model = pytest.mark.skipif(not MODEL.exists(), reason="modèle absent")
needs_proc = pytest.mark.skipif(
    not Path("/proc/self/status").exists(), reason="/proc absent"
)

THREADS_SPAWNED = 200
WARMUP = 20
MAX_GROWTH_KB = 32 * 1024


def rss_kb() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    raise RuntimeError("VmRSS absent de /proc/self/status")


def search_on_new_thread(net, config) -> None:
    errors: list[BaseException] = []

    def body():
        try:
            assert search_plays(net, Position.initial(), 3, 1, config)
        except BaseException as exc:  # noqa: BLE001 -- re-raised below
            errors.append(exc)

    t = threading.Thread(target=body)
    t.start()
    t.join()
    if errors:
        raise errors[0]


@pytest.fixture(scope="module")
def net():
    with Network.load(MODEL) as n:
        yield n


@pytest.fixture(autouse=True)
def serial_after():
    yield
    set_threads(1)


@needs_model
@needs_proc
@pytest.mark.parametrize("threads", [1, 4])
def test_short_lived_threads_do_not_leak(net, threads):
    set_threads(threads)
    config = SearchConfig(ply=0)
    for _ in range(WARMUP):
        search_on_new_thread(net, config)
    before = rss_kb()
    for _ in range(THREADS_SPAWNED):
        search_on_new_thread(net, config)
    growth = rss_kb() - before
    assert growth < MAX_GROWTH_KB, (
        f"+{growth / 1024:.0f} Mo pour {THREADS_SPAWNED} fils éphémères : "
        "la mémoire de travail d'un fil mort n'est pas rendue"
    )
