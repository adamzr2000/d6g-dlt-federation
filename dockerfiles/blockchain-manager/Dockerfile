FROM python:3.6-slim

LABEL maintainer="azahir@pa.uc3m.es"

# Set environment variables to avoid user interaction during the installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    python3 \
    python3-pip \
    sudo \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY app/ .

# Set the entrypoint to execute main.py
ENTRYPOINT ["python3", "-m", "uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]