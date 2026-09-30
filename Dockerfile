FROM python:3.11-slim
 
LABEL org.opencontainers.image.title="PriceWatch" \
      org.opencontainers.image.description="Self-hosted price & website change monitor" \
      org.opencontainers.image.source="https://github.com/jameshoffman7667/pricewatch" \
      org.opencontainers.image.licenses="MIT"
 
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PRICEWATCH_DATA_DIR=/data \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
 
WORKDIR /app
 
# System deps needed by Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget ca-certificates fonts-liberation libnss3 libatk-bridge2.0-0 \
    libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 \
    libpangocairo-1.0-0 libgtk-3-0 libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*
 
COPY requirements.txt .
# Note: --with-deps is intentionally omitted. It triggers a second apt-get
# pass for Chromium's runtime libs on top of the ones already installed
# above, and that second pass is fragile under QEMU emulation during the
# multi-arch (linux/arm64) build - it's a common cause of "exit code 1"
# with no useful detail in buildx output. The libs it would install are
# already covered by the apt-get step above, so plain `chromium` (just
# downloads the browser binary, no apt-get) is enough and more reliable.
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium
 
COPY app ./app
 
RUN mkdir -p /data
VOLUME ["/data"]
 
EXPOSE 8000
 
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1
 
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
 
