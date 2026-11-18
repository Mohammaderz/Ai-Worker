# Pinned multi-architecture manifest digest; update deliberately after verification.
FROM python:3.11-alpine3.24@sha256:769f2b47fc4722cc68ce31b9629672b2253919ce8286197c9d4fec7bf44c9ae5

USER root
RUN apk add --no-cache git 'krb5-libs=1.22.3-r0' 'zlib=1.4-r0'

RUN python -m pip install --no-cache-dir --upgrade pip==26.3 setuptools==84.2.1 pytest==9.2.0 build==1.6.1 \
    && python -m pip check \
    && python -m pip uninstall -y pip

WORKDIR /workspace
ENV HOME=/tmp
USER 65532:65532
ENTRYPOINT []
