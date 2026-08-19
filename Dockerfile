# Base image: slim keeps the image small
# Should help with cold start times
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY workloads/ .
# -u for unbuffered, prevents buffering bug
CMD ["python", "-u", "model1.py"]