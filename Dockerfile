FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY scripts ./scripts
RUN mkdir /app/.local
HEALTHCHECK --interval=1m --timeout=10s --start-period=2m --retries=2 \
    CMD python -m src.health --max-age-seconds 120 || exit 1
CMD ["python", "-m", "src.telegram.listener"]
