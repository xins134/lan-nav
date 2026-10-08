FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 1000 --home /app --shell /usr/sbin/nologin app

COPY requirements.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY app ./app
COPY run.py ./
COPY data/navigation.yml.example /app/navigation.yml.example
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod 755 /entrypoint.sh \
    && chown -R app:app /app

ENV HOST=0.0.0.0 \
    PORT=8090 \
    DEBUG=false \
    TZ=Asia/Shanghai \
    DATA_FILE=/app/data/navigation.yml \
    EXAMPLE_FILE=/app/navigation.yml.example \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8090
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/api/health')"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "run.py"]
