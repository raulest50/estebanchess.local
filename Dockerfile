# syntax=docker/dockerfile:1

FROM debian:bookworm-slim AS stockfish-builder

ARG STOCKFISH_TAG=sf_18
ARG STOCKFISH_ARCH=
ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        build-essential \
        curl \
        git \
        make \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --branch "${STOCKFISH_TAG}" --depth 1 https://github.com/official-stockfish/Stockfish.git /tmp/stockfish

WORKDIR /tmp/stockfish/src
RUN set -eux; \
    if [ -z "${STOCKFISH_ARCH}" ]; then \
        case "${TARGETARCH}" in \
            amd64) STOCKFISH_ARCH="x86-64-avx2" ;; \
            arm64) STOCKFISH_ARCH="armv8" ;; \
            *) STOCKFISH_ARCH="general-64" ;; \
        esac; \
    fi; \
    make -j"$(nproc)" build ARCH="${STOCKFISH_ARCH}"; \
    install -D -m 0755 stockfish /out/stockfish


FROM python:3.12-slim AS python-builder

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

WORKDIR /app
RUN python -m venv "${VIRTUAL_ENV}"

COPY pyproject.toml README.md ./
COPY chess_move_analyzer ./chess_move_analyzer

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .


FROM python:3.12-slim AS runtime

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV STOCKFISH_PATH=/usr/local/bin/stockfish
ENV CHESS_ANALYZER_HOST=0.0.0.0
ENV CHESS_ANALYZER_PORT=8080
ENV CHESS_ANALYZER_SHOW=false

WORKDIR /app

COPY --from=python-builder /opt/venv /opt/venv
COPY --from=stockfish-builder /out/stockfish /usr/local/bin/stockfish

RUN chmod +x /usr/local/bin/stockfish \
    && mkdir -p /app/data

EXPOSE 8080
VOLUME ["/app/data"]

CMD ["python", "-m", "chess_move_analyzer"]
