# Build-Kontext ist der Projektordner, nicht inference_service.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY inference_service/requirements.lock.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "from websocket import create_connection, WebSocketAddressException, WebSocketTimeoutException, WebSocketConnectionClosedException" \
    && useradd --create-home --uid 10001 worker
COPY autoencoder/model.py /app/autoencoder/model.py
COPY inference_service/__init__.py inference_service/processor.py inference_service/azure_store.py inference_service/worker.py inference_service/alarms.py /app/inference_service/
USER worker
CMD ["python", "-m", "inference_service.worker"]
