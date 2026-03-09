FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install fastapi uvicorn google-genai websockets
COPY backend.py .
CMD ["uvicorn", "backend:app", "--host", "0.0.0.0", "--port", "8080"]