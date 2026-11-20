# ---- build stage: install dependencies and build the vector index -------------------------
FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
# Compilers only exist in this stage (needed if a dependency has no wheel for your CPU, e.g. some arm64 hosts).
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install -r /tmp/requirements.txt
WORKDIR /srv
COPY app ./app
COPY data/processed ./data/processed
# Embed every document now, so the container starts without any model download.
RUN /opt/venv/bin/python -m app.build_index

# ---- runtime stage: no compilers, non-root, read-only friendly ----------------------------
FROM python:3.13-slim
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 HF_HUB_OFFLINE=1
RUN useradd --create-home --uid 10001 appuser
WORKDIR /srv
COPY --from=build /opt/venv /opt/venv
COPY --from=build /srv/app ./app
COPY --from=build /srv/data ./data
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health', timeout=4)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-server-header --timeout-keep-alive 5 --limit-concurrency 64"]
