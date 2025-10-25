import json, os, time, uuid, yaml
from datetime import datetime, timedelta
from kafka import KafkaConsumer, KafkaProducer

BOOTSTRAP = os.getenv("BOOTSTRAP_SERVERS", "localhost: 9092")
GROUP_ID = os.getenv("GROUP_ID", "Donna")
CASEEVENT_TOPIC = os.getenv("CASEEVENT_TOPIC", "events.caseevent")
TASKS_TOPIC = os.getenv("TASKS_TOPIC","tasks.suggested")
ROUTING_FILE = os.getenv("ROUTING_FILE", "common-contracts/yaml/routing.yaml")

def detect_tasks(text:str):
  text_low = (text or "").lower()
  detected = []

  if any(k in text_low for k in ["schedule", "call", "talk", "meet", "depo", "mediation", "deposition"]):
    detected.append("SCHEDULE_CALL")
  
  if any(k in text_low for k in ["mri", "records","bill","hospital","orthoped","medical"]):
    detected.append("REQUEST_RECORDS")
  
  if any(k in text_low for k in ["offer", "verdict","citation","demand", "case law"]):
    detected.append("LEGAL_RESEARCH")