FROM python:3.11-slim

LABEL org.opencontainers.image.title="PriceWatch" \
      org.opencontainers.image.description="Self-hosted price & website change monitor" \
      org.opencontainers.image.source="https://github.com/jameshoffman7667/pricewatch" \
      org.opencontainers.image.licenses="MIT"
# org.opencontainers.image.version is set by the release workflow (metadata step).

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5400 \
    PRICEWATCH_DATA_DIR=/data \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers

WORKDIR /app

# tini forwards SIGTERM for a clean stop; the rest are Playwright/Chromium runtime libs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini wget ca-certificates fonts-liberation libnss3 libatk-bridge2.0-0 \
    libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 \
    libpangocairo-1.0-0 libgtk-3-0 libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# No --with-deps: the libraries are installed above (a second apt pass failed in CI).
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium

COPY VERSION ./VERSION
COPY app ./app

# Run as non-root 1000:100; data folders must be writable by this user.
RUN mkdir -p /data && chown -R 1000:100 /data /app
USER 1000:100
VOLUME ["/data"]

EXPOSE 5400

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD wget -qO- http://127.0.0.1:${PORT}/healthz >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
