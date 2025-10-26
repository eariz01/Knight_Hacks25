import os, json, uuid, time
from datetime import datetime
from threading import Thread
from kafka import KafkaConsumer, KafkaProducer
import sys 

# -----------------------------
# Env / Config (with defaults)
# -----------------------------
BOOTSTRAP = os.getenv("BOOTSTRAP_SERVERS", "redpanda:9092")
GROUP_ID  = os.getenv("GROUP_ID", "donna-orchestrator")

CASEEVENT_TOPIC   = os.getenv("CASEEVENT_TOPIC", "events.caseevent")
TO_CM_TOPIC       = os.getenv("TO_CM_TOPIC", "tasks.case_manager")
FROM_CM_TOPIC     = os.getenv("FROM_CM_TOPIC", "results.case_manager")
TO_PL_TOPIC       = os.getenv("TO_PL_TOPIC", "tasks.paralegal")
FROM_PL_TOPIC     = os.getenv("FROM_PL_TOPIC", "results.paralegal")

PRECEDENTS_DIR    = os.getenv("PRECEDENTS_DIR", "/precedence")  # bind-mounted via docker-compose

# -----------------------------
# Kafka helpers
# -----------------------------
def make_producer():
    return KafkaProducer(
        bootstrap_servers=BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        linger_ms=10,
        acks="all",
        api_version=(0, 10, 2)
    )

def make_consumer(topic, group_suffix=""):
    client_id = f"client-{GROUP_ID}{group_suffix}"
    return KafkaConsumer(
        topic,
        bootstrap_servers=BOOTSTRAP,
        group_id=f"{GROUP_ID}{group_suffix}",
        client_id=client_id, 
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        # REMOVED consumer_timeout_ms - this was causing threads to exit!
        api_version=(0, 10, 2)
    )

# -----------------------------
# Handlers
# -----------------------------
def handle_caseevent(ce: dict, producer: KafkaProducer):
    """
    Input: CaseEvent JSON with attachments[].name (filename contains case number).
    Output: For each filename, emit a work item to Case Manager.
    """
    case_id = (ce.get("case_id") or "UNKNOWN").strip()
    ev_id   = ce.get("event_id", "")
    atts    = ce.get("attachments") or []

    if not atts:
        print(f"[Donna] CaseEvent {ev_id} has no attachments; skipping.")
        return

    for a in atts:
        fname = (a.get("name") or "").strip()
        if not fname:
            continue
        work = {
            "task_id": f"T_{uuid.uuid4().hex[:8]}",
            "case_id": case_id,
            "filename": fname,
            "received_at": datetime.utcnow().isoformat() + "Z"
        }
        print(f"[Donna] → To CaseManager: {fname} (task {work['task_id']})")
        producer.send(TO_CM_TOPIC, work)
    producer.flush()


def handle_cm_result(res: dict, producer: KafkaProducer):
    """
    Input: Case Manager result JSON (free-form, but should include task_id, case_id, items[]).
    Output: Forward a paralegal request to TO_PL_TOPIC (wrap CM result).
    """
    task_id  = res.get("task_id")
    case_id  = (res.get("case_id") or "UNKNOWN").strip()

    pl_req = {
        "request_id": f"PLR_{uuid.uuid4().hex[:6]}",
        "case_id": case_id,
        "source_task_id": task_id,
        "evidence": {
            "summary": res.get("summary", ""),
            "items":    res.get("items", [])
        }
    }
    print(f"[Donna] → To Paralegal: {pl_req['request_id']} (from task {task_id})")
    producer.send(TO_PL_TOPIC, pl_req)
    producer.flush()


def handle_pl_result(res: dict):
    """
    Input: Paralegal precedents JSON (includes case_id, request_id, precedents[]).
    Action: Save JSON to /precedence/<CASE_ID>/<timestamp>_<request_id>.json
    """
    case_id    = (res.get("case_id") or "UNKNOWN").strip()
    request_id = (res.get("request_id") or f"PLR_{uuid.uuid4().hex[:6]}").strip()

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    case_dir = os.path.join(PRECEDENTS_DIR, case_id)
    os.makedirs(case_dir, exist_ok=True)

    out_path = os.path.join(case_dir, f"{ts}_{request_id}.json")
    tmp_path = out_path + ".tmp"

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, out_path)

    print(f"[Donna] 💾 Saved precedents JSON → {out_path}")


# -----------------------------
# Main loops
# -----------------------------
def loop_caseevents(producer: KafkaProducer):
    try:
        consumer = make_consumer(CASEEVENT_TOPIC, group_suffix="")
        print(f"[Donna] [THREAD START] Listening for CaseEvents on: {CASEEVENT_TOPIC}")
        sys.stdout.flush()
        
        # Explicit polling loop instead of iterator
        while True:
            msg_batch = consumer.poll(timeout_ms=1000, max_records=10)
            for topic_partition, messages in msg_batch.items():
                for msg in messages:
                    print(f"[Donna][DEBUG] Received CaseEvent: {msg.value}")
                    handle_caseevent(msg.value, producer)
                    sys.stdout.flush()
    except Exception as e:
        print(f"[Donna][FATAL ERR] CaseEvent Consumer loop failed: {e}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()


def loop_cm_results(producer: KafkaProducer):
    try:
        consumer = make_consumer(FROM_CM_TOPIC, group_suffix="-cm")
        print(f"[Donna] [THREAD START] Listening for CaseManager results on: {FROM_CM_TOPIC}")
        sys.stdout.flush()
        
        # Explicit polling loop instead of iterator
        while True:
            msg_batch = consumer.poll(timeout_ms=1000, max_records=10)
            for topic_partition, messages in msg_batch.items():
                for msg in messages:
                    print(f"[Donna][DEBUG] Received CM Result: {msg.value}")
                    handle_cm_result(msg.value, producer)
                    sys.stdout.flush()
    except Exception as e:
        print(f"[Donna][FATAL ERR] CM Result Consumer loop failed: {e}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()


def loop_pl_results():
    try:
        print(f"[Donna][PL] Creating consumer for topic: {FROM_PL_TOPIC}")
        sys.stdout.flush()
        consumer = make_consumer(FROM_PL_TOPIC, group_suffix="-pl")
        print(f"[Donna][PL] Consumer created, subscription: {consumer.subscription()}")
        sys.stdout.flush()
        
        # Wait for partition assignment
        print(f"[Donna][PL] Waiting for partition assignment...")
        sys.stdout.flush()
        while not consumer.assignment():
            consumer.poll(timeout_ms=100)
        
        print(f"[Donna][PL] Assigned partitions: {consumer.assignment()}")
        sys.stdout.flush()
        
        # Force seek to beginning to read all messages
        for partition in consumer.assignment():
            consumer.seek_to_beginning(partition)
            position = consumer.position(partition)
            print(f"[Donna][PL] Seeked {partition} to position {position}")
            sys.stdout.flush()
        
        print(f"[Donna] [THREAD START] Listening for Paralegal results on: {FROM_PL_TOPIC}")
        sys.stdout.flush()
        
        poll_count = 0
        # Explicit polling loop
        while True:
            poll_count += 1
            if poll_count % 10 == 0:
                positions = {tp: consumer.position(tp) for tp in consumer.assignment()}
                print(f"[Donna][PL] Poll #{poll_count}, positions: {positions}")
                sys.stdout.flush()
            
            msg_batch = consumer.poll(timeout_ms=1000, max_records=10)
            
            if msg_batch:
                print(f"[Donna][PL] Received batch with {sum(len(msgs) for msgs in msg_batch.values())} messages")
                sys.stdout.flush()
                
            for topic_partition, messages in msg_batch.items():
                for msg in messages:
                    print(f"[Donna][DEBUG] Received PL Result: {msg.value}")
                    handle_pl_result(msg.value)
                    sys.stdout.flush()
    except Exception as e:
        print(f"[Donna][FATAL ERR] PL Result Consumer loop failed: {e}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()


# -----------------------------
# Bootstrap
# -----------------------------
if __name__ == "__main__":
    print(f"[Donna] Bootstrapping. Kafka @ {BOOTSTRAP}")
    sys.stdout.flush()
    
    producer = make_producer()

    Thread(target=loop_caseevents, args=(producer,), daemon=True).start()
    Thread(target=loop_cm_results, args=(producer,), daemon=True).start()
    Thread(target=loop_pl_results, daemon=True).start()

    # Keep process alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[Donna] Shutting down...")
        sys.stdout.flush()