# Timebutler clock server for n8n (see README "n8n mode").
# The Playwright base image already ships Chromium and its system libraries.
FROM mcr.microsoft.com/playwright/python:v1.57.0-noble

WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY tb_clock.py tb_schedule.py tb_selectors.py tb_server.py tb_session.py ./

ENV PYTHONUNBUFFERED=1 \
    TB_STATE_DIR=/data/state \
    TB_SKIP_DATES_FILE=/data/config/skip_dates.txt \
    TB_TIMEZONE=Europe/Berlin \
    TZ=Europe/Berlin

RUN useradd --create-home --uid 10001 clock \
    && mkdir -p /data/state /data/config \
    && chown -R clock:clock /data
USER clock

EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4)"

CMD ["python", "tb_server.py"]
