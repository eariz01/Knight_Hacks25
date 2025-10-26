FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./app.py

# No COPY of common-contracts here; we’ll mount it via volumes

ENV BOOTSTRAP_SERVERS=redpanda:9092
ENV GROUP_ID=donna-orchestrator
ENV CASEEVENT_TOPIC=events.caseevent
ENV TASKS_TOPIC=tasks.suggested
# ROUTING_FILE is fine to point to the mounted path if you use it
# ENV ROUTING_FILE=/app/common-contracts/yaml/routing.yaml

CMD ["python", "app.py"]
