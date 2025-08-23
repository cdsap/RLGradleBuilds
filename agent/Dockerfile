FROM python:3.10-slim

# Install required system dependencies for gRPC and Firestore
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    libssl-dev \
    libnss3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Cloud Run will inject PORT
ENV PORT=8080

CMD exec uvicorn main:app --host 0.0.0.0 --port $PORT
