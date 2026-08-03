# Base image: slim keeps the image small
# Should help with cold start times
FROM python:3.12-slim
WORKDIR /app
COPY workloads/model1.py .
# -u for unbuffered, prevents buffering bug
CMD ["python", "-u", "model1.py"]