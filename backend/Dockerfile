FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg fonts-dejavu-core fonts-liberation fontconfig curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# Bold display fonts for overlays (best-effort: the renderer falls back to
# DejaVu/Liberation if a download is unavailable, so the build never breaks).
RUN mkdir -p /usr/share/fonts/truetype/app && cd /usr/share/fonts/truetype/app \
    && for url in \
        "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf" \
        "https://github.com/google/fonts/raw/main/ofl/archivoblack/ArchivoBlack-Regular.ttf" \
        "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf" \
        "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald%5Bwght%5D.ttf" ; do \
         curl -fsSL -O "$url" || echo "skip $url" ; \
       done \
    && fc-cache -f || true
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project
COPY src ./src
COPY workers ./workers
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN uv sync --no-dev
ENV PATH="/app/.venv/bin:$PATH"
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "doppel_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
