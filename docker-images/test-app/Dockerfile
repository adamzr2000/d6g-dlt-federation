# Use the official Python image from the Docker Hub based on Alpine Linux
FROM python:3.9-alpine

# Set the working directory in the container
WORKDIR /app

# Install dependencies
RUN apk add --no-cache --update \
    build-base \
    python3-dev \
    py-pip \
    curl \
    && pip install --upgrade pip

# Copy the requirements file into the container
COPY requirements.txt requirements.txt

# Install any dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Run app.py when the container launches
CMD ["python", "app.py"]
