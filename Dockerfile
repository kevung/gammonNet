# gammonNet serve (#18) — a standalone HTTP evaluator process.
#
# Weights are baked into the image at BUILD time (fetched and SHA-256-verified
# by `tools/fetch_release.py`), so the running container needs no network
# access to serve a request. `tools/serve.py` re-verifies the SHA-256 on every
# start regardless — the check that the image's own bytes were not altered
# after the build, not merely a build-time convenience.
#
# Build stage needs a C compiler and git (to fetch the vendored rules/network
# reader at their pinned commit, per `tools/fetch_vendor.py`). None of that
# — nor PyTorch, which this image never installs — is needed at run time: the
# server loads a pre-exported, pre-quantised `.bin16`, never trains or
# exports one itself.

FROM debian:bookworm-slim AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libc6-dev make git ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Only what the native build and the two fetch scripts need — not the whole
# repository (training tools, docs/recherche/, the WebAssembly toolchain).
COPY Makefile ./
COPY src/ src/
COPY tools/fetch_vendor.py tools/fetch_release.py tools/
COPY models/release_pin.json models/README.md models/prune_32.bin models/

RUN python3 tools/fetch_vendor.py
RUN make build
RUN python3 tools/fetch_release.py

# ── Runtime ────────────────────────────────────────────────────────────────

FROM python:3.13-slim AS runtime

WORKDIR /app

COPY --from=build /src/build/libgammonnet.so build/libgammonnet.so
COPY --from=build /src/models/ models/
COPY python/ python/
COPY tools/serve.py tools/
COPY docs/mesures/t34-efficacite.json docs/mesures/t34-efficacite.json
COPY LICENSE THIRD-PARTY.md ./

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)" || exit 1

ENTRYPOINT ["python3", "tools/serve.py", "--host", "0.0.0.0", "--port", "8080"]
