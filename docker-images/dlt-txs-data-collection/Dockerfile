# Use the specific version of the Ubuntu 20.04 base image from Docker Hub
FROM ubuntu:20.04

LABEL maintainer="azahir@pa.uc3m.es"

# Set environment variables to avoid user interaction during the installation
ENV DEBIAN_FRONTEND=noninteractive

# Install necessary dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    python3 \
    python3-pip \
&& apt-get clean \
&& rm -rf /var/lib/apt/lists/*

# Install Python dependencies from requirements.txt using pip3
COPY requirements.txt .
RUN pip3 install -r requirements.txt

# Set the working directory inside the container
WORKDIR /app

RUN mkdir data && mkdir smart-contracts

COPY ./scripts/dlt_txs_monitoring.py ./dlt_txs_monitoring.py
COPY ./scripts/start_data_collection.sh ./start_data_collection.sh

RUN chmod +755 *.sh

# Indicate completion of Dockerfile setup
RUN echo "ALL Done"

CMD "./start_data_collection.sh"