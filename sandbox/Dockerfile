# Pinned multi-architecture manifest digest; update deliberately after verification.
FROM python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir pytest==8.4.2

WORKDIR /workspace
ENV HOME=/tmp
USER 65532:65532
ENTRYPOINT []
