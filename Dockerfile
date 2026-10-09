FROM python:3.10-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt numpy joblib scikit-learn pandas tensorflow

COPY backend/ /app/

EXPOSE 50051

CMD ["python", "heart_server.py"]