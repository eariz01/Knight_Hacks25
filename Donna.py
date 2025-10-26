import os
import json
import shutil
import subprocess

PRODUCT_PATH = "product.json"
MASTER_PATH = "master.json"
TEMPLATE_PATH = "Template.json"
SEED_MASTER_PATH = "test.json"   # 👈 your big array file (case-001 … case-005)

MASTER_FIELDS = [
    "id",
    "client_name",
    "main_summary",
    "key_findings",
    "hipaa_necessity",
    "medical_history_summary",
    "political_reading",
    "litigation_phase",
    "status",
    "venue",
    "relevant_cases",
    "federal_cases",
    "notes",
    "checklist"
]

def run_script(script_name):
    if os.path.exists(script_name):
        print(f"➡ Running {script_name} ...")
        subprocess.run(["python", script_name], shell=True)
    else:
        print(f"⚠ {script_name} not found, skipping...")

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def _filtered_entry(product: dict) -> dict:
    entry = {}
    for key in MASTER_FIELDS:
        if key in ("venue", "checklist"):
            entry[key] = product.get(key, {}) or {}
        elif key in ("key_findings", "relevant_cases", "federal_cases"):
            entry[key] = product.get(key, []) or []
        else:
            entry[key] = product.get(key, "")
    return entry

def _upsert_by_id(master_list: list, new_entry: dict) -> list:
    if not isinstance(master_list, list):
        master_list = []
    new_id = (new_entry.get("id") or "").strip()
    if new_id:
        for i, item in enumerate(master_list):
            if isinstance(item, dict) and (item.get("id") or "").strip() == new_id:
                master_list[i] = new_entry
                return master_list
    master_list.append(new_entry)
    return master_list

def _load_or_seed_master(master_path: str, seed_path: str) -> list:
    """Load master.json, or if missing, seed from test.json."""
    if os.path.exists(master_path):
        try:
            data = load_json(master_path)
            return data if isinstance(data, list) else []
        except Exception:
            return []
    if os.path.exists(seed_path):
        try:
            data = load_json(seed_path)
            print(f"🌱 Seeded master from {seed_path}")
            return data if isinstance(data, list) else []
        except Exception:
            return []
    return []

def copy_product_to_master():
    """Upsert product.json into master.json using only MASTER_FIELDS."""
    product = load_json(PRODUCT_PATH)
    entry = _filtered_entry(product)

    master = _load_or_seed_master(MASTER_PATH, SEED_MASTER_PATH)
    master = _upsert_by_id(master, entry)
    save_json(MASTER_PATH, master)

    print(f"✅ Upserted case '{entry.get('id','<no id>')}' into {MASTER_PATH}")

def reset_product():
    if os.path.exists(PRODUCT_PATH):
        os.remove(PRODUCT_PATH)
        print("🗑 Removed old product.json")
    shutil.copy(TEMPLATE_PATH, PRODUCT_PATH)
    print("📄 Reset product.json using Template.json")

def run_donna():
    print("\n🚀 DONNA STARTED")
    run_script("recordAgent.py")
    run_script("paralegal.py")
    run_script("MessageSender.py")
    copy_product_to_master()
    reset_product()
    shutil.move(r"master.json", os.path.join(r"morgan-case-tracker\public", "master.json"))
    print("🎯 DONNA COMPLETE\n")

if __name__ == "__main__":
    run_donna()
