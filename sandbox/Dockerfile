# Build this image ahead of time; task containers run with --pull=never and no network.
# Pin this base image to a verified digest before using the sandbox for production work.
FROM python:3.11-slim

RUN useradd --uid 65532 --create-home --shell /usr/sbin/nologin worker
WORKDIR /workspace
USER 65532:65532
ENTRYPOINT []
