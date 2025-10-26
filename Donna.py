# Donna.py

import os
import json
import shutil
import subprocess

PRODUCT_PATH = "product.json"
MASTER_PATH = "master.json"
TEMPLATE_PATH = "Template.json"

### ✅ Only the fields YOU requested will be copied into master
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
    """Run helper scripts that edit product.json"""
    if os.path.exists(script_name):
        print(f"➡ Running {script_name} ...")
        subprocess.run(["python", script_name], shell=True)
    else:
        print(f"⚠ {script_name} not found, skipping...")

def load_json(path):
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def copy_product_to_master():
    """Copy only allowed fields from product.json to master.json"""
    product = load_json(PRODUCT_PATH)

    # Build final master entry
    entry = {}
    for key in MASTER_FIELDS:
        entry[key] = product.get(key, "")

    # Load or create master file
    try:
        master = load_json(MASTER_PATH)
        if not isinstance(master, list):
            master = []
    except FileNotFoundError:
        master = []

    master.append(entry)
    save_json(MASTER_PATH, master)

    print("✅ Copied final product data into master.json")

def reset_product():
    """Delete product.json and recreate it from Template.json"""
    if os.path.exists(PRODUCT_PATH):
        os.remove(PRODUCT_PATH)
        print("🗑 Removed old product.json")

    shutil.copy(TEMPLATE_PATH, PRODUCT_PATH)
    print("📄 Reset product.json using Template.json")

def run_donna():
    print("\n🚀 DONNA STARTED")

    # ✅ 1. Run the helpers FIRST — they modify product.json
    run_script("gcs_case_summarizer.py")
    run_script("paralegal.py")
    run_script("MessageSender.py")

    # ✅ 2. Copy final result from product → master
    copy_product_to_master()

    # ✅ 3. Reset product.json
    reset_product()

    print("🎯 DONNA COMPLETE\n")

if __name__ == "__main__":
    run_donna()
