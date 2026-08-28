#!/usr/bin/env python3
"""#20 -- HTTP throughput of `tools/serve.py` under concurrent `/v1/eval`
load, AFTER the `_ENGINE_LOCK` fix that serializes access to the shared
native engine state.

Serializing every request behind one lock trades concurrency for
correctness (#20: without it, concurrent requests corrupted each other's
response 85% of the time -- see `tests/test_serve_concurrency.py`). This
bench answers the question that trade leaves open: does the serialized
server still serve gammonGo's expected concurrent load without becoming a
perceptible bottleneck? `CLAUDE.md` rule 3: a throughput or latency number
is measured here, never deduced from the 86 us/eval figure alone.

Usage:
    python bench/bench_serve_concurrency.py                 # 1,2,8,16 clients
    python bench/bench_serve_concurrency.py --clients 8 16 32
"""

from __future__ import annotations

import argparse
import json
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVE = ROOT / "tools" / "serve.py"

XGID = "XGID=-b----E-C---eE---c-e----B-:0:0:1:31:0:0:0:0:10"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_healthy(base_url: str, proc: subprocess.Popen, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("le serveur s'est arrêté avant d'être prêt")
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=1) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.2)
    raise TimeoutError("le serveur n'a jamais répondu à /healthz")


def _client(base_url: str, duration_s: float, latencies: list[float], counts: list[int]) -> None:
    payload = json.dumps({"xgid": XGID, "ply": 0}).encode()
    deadline = time.monotonic() + duration_s
    n = 0
    while time.monotonic() < deadline:
        req = urllib.request.Request(
            f"{base_url}/v1/eval", data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        latencies.append(time.monotonic() - t0)
        n += 1
    counts.append(n)


def measure(base_url: str, num_clients: int, duration_s: float) -> dict:
    latencies: list[float] = []
    counts: list[int] = []
    lock = threading.Lock()

    def worker():
        local_lat: list[float] = []
        local_cnt: list[int] = []
        _client(base_url, duration_s, local_lat, local_cnt)
        with lock:
            latencies.extend(local_lat)
            counts.extend(local_cnt)

    threads = [threading.Thread(target=worker) for _ in range(num_clients)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start

    total = sum(counts)
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else float("nan")
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else float("nan")
    return {
        "clients": num_clients,
        "requests": total,
        "elapsed_s": elapsed,
        "req_per_s": total / elapsed,
        "mean_latency_ms": statistics.mean(latencies) * 1000 if latencies else float("nan"),
        "p50_latency_ms": p50 * 1000,
        "p95_latency_ms": p95 * 1000,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", type=int, nargs="+", default=[1, 2, 8, 16])
    parser.add_argument("--duration", type=float, default=3.0, help="secondes par palier")
    args = parser.parse_args(argv)

    port = _free_port()
    proc = subprocess.Popen(
        # stdout/stderr go to DEVNULL, not PIPE: `Handler.log_message` writes
        # one line per request, and at hundreds of req/s an unread PIPE fills
        # its OS buffer (~64 KiB) within seconds -- the child then blocks on
        # write(), stalling the handler thread that logged, and eventually
        # every worker thread queued behind the same full pipe. That is a
        # bench-harness bug, not a `serve.py` one (measured while chasing a
        # spurious hang here); nothing about it depends on the #20 fix.
        [sys.executable, str(SERVE), "--host", "127.0.0.1", "--port", str(port), "--max-ply", "0"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_healthy(base_url, proc)
        print(f"==> gammonNet serve prêt sur {base_url} (0-ply, verrou #20 en place)")
        print(f"{'clients':>8} {'req/s':>10} {'moy (ms)':>10} {'p50 (ms)':>10} {'p95 (ms)':>10} {'requêtes':>10}")
        results = []
        for n in args.clients:
            r = measure(base_url, n, args.duration)
            results.append(r)
            print(
                f"{r['clients']:>8} {r['req_per_s']:>10.1f} {r['mean_latency_ms']:>10.2f} "
                f"{r['p50_latency_ms']:>10.2f} {r['p95_latency_ms']:>10.2f} {r['requests']:>10}"
            )
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
