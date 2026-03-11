FROM python:3.11-slim

LABEL org.opencontainers.image.title="accessibility-autopilot" \
      org.opencontainers.image.description="Accessibility Autopilot backend service" \
      org.opencontainers.image.source="https://github.com/engineering-hbu/accessibility-autopilot" \
      team="prod_eng" \
      app="accessibility-autopilot"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend.py .
CMD uvicorn backend:app --host 0.0.0.0 --port ${PORT:-8080}