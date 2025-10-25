FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# copy code and shared contracts
COPY app.py ./app.py
# mount contracts at runtime via compose bind, but copy as fallback:
COPY ../common-contracts ./common-contracts

ENV BOOTSTRAP_SERVERS=redpanda:9092
ENV GROUP_ID=donna-orchestrator
ENV CASEEVENT_TOPIC=events.caseevent
ENV TASKS_TOPIC=tasks.suggested
ENV ROUTING_FILE=/app/common-contracts/yaml/routing.yaml

CMD ["python", "app.py"]
