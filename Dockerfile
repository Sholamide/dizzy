FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py notifier.py config.py risk_scorer.py health_scorer.py join_store.py server_store.py .
RUN mkdir -p /app/data
ENV DATA_DIR=/app/data

CMD ["python", "main.py"]
