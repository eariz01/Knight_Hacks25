# gcs_case_summarizer.py
# Loops through all files under a GCS prefix ("a case"), extracts text,
# asks Gemini for a STRICT JSON summary, then saves it to disk.

import os
import json
from io import BytesIO
from datetime import datetime
from typing import Optional, List, Tuple

import google.generativeai as genai
from google.cloud import storage
from pypdf import PdfReader

# ------------------ CONFIG ------------------
# Auth:
#   - Set GOOGLE_API_KEY in your environment (recommended):
#       PowerShell:  setx GOOGLE_API_KEY "YOUR_KEY"  (then open a new shell)
#   - or put it here temporarily (not recommended for prod)
GENAI_API_KEY = "AIzaSyBWE1PlorpDVBUxfO9WFpchyB8U7leQweo"

# Model (fast + long context)
MODEL_NAME = "gemini-2.5-flash"

# How much text to include to keep prompts manageable
MAX_CHARS_PER_FILE = 3_000         # per file cap
MAX_TOTAL_CHARS = 70_000           # total cap across files

# What to skip (by extension)
SKIP_EXTS = (
    ".m4a", ".mp3", ".wav", ".flac",
    ".jpg", ".jpeg", ".png", ".gif", ".heic", ".webp",
    ".mp4", ".mov", ".avi", ".mkv",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".exe", ".dll"
)

# ------------------ Helper: extraction ------------------
TEXT_LIKE_MIMES = {
    "text/plain", "text/csv", "text/markdown",
    "application/json", "application/xml",
    "application/x-yaml", "application/yaml",
}

def _safe_extract_text(blob) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (text, warning). Truncates per-file. Skips obvious binaries.
    """
    try:
        name = blob.name.lower()

        if name.endswith(SKIP_EXTS):
            return None, f"Skipped binary/media file '{blob.name}'."

        # Prefer content_type if present
        mime = blob.content_type or ""

        # PDF path
        if "pdf" in mime or name.endswith(".pdf"):
            pdf_bytes = blob.download_as_bytes()
            reader = PdfReader(BytesIO(pdf_bytes))
            pages_text = []
            for p in reader.pages:
                try:
                    pages_text.append(p.extract_text() or "")
                except Exception:
                    # Some PDFs have extractable text only on some pages
                    continue
            text = "\n".join(pages_text).strip()
            if not text:
                return None, f"No extractable text in PDF '{blob.name}'."
            return text[:MAX_CHARS_PER_FILE], None

        # JSON / texty
        if mime.startswith("text/") or mime in TEXT_LIKE_MIMES or name.endswith((".txt", ".csv", ".md", ".json", ".xml", ".yaml", ".yml")):
            raw = blob.download_as_text()
            if name.endswith(".json"):
                try:
                    obj = json.loads(raw)
                    raw = json.dumps(obj, indent=2)
                except Exception:
                    # keep raw if it isn’t valid JSON
                    pass
            return (raw[:MAX_CHARS_PER_FILE], None) if raw else (None, f"Empty text in '{blob.name}'.")
        
        # Unknown non-texty content type → skip
        return None, f"Skipped non-text file '{blob.name}' (content_type={mime or 'unknown'})."
    except Exception as e:
        return None, f"Error reading '{blob.name}': {e}"

def _maybe_extract_political_from_courts_json(text: str) -> Optional[str]:
    try:
        data = json.loads(text)
    except Exception:
        return None
    for key in ("political_reading", "political", "lean", "district_lean"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.split()[0]
    return None

# ------------------ Core: build context from GCS ------------------
def gather_case_text(bucket: str, prefix: str) -> dict:
    """
    Reads all blobs under gs://{bucket}/{prefix}, extracts text,
    returns dict with:
      - joined_text (capped)
      - notes (skips/errors)
      - politcal_reading (best-effort)
      - files_processed (count)
    """
    client = storage.Client()
    aggregated_parts: List[str] = []
    notes: List[str] = []
    files_processed = 0
    polit = None
    total_chars = 0

    for blob in client.list_blobs(bucket, prefix=prefix):
        text, warn = _safe_extract_text(blob)
        if warn:
            notes.append(warn)
            continue
        if not text:
            # Already handled by warn, but just in case
            notes.append(f"No text from '{blob.name}'.")
            continue

        # track political reading if this looks like Courts.json
        if blob.name.lower().endswith("courts.json"):
            maybe = _maybe_extract_political_from_courts_json(text)
            if maybe:
                polit = maybe

        header = f"[FILE {blob.name}]"
        chunk = f"{header}\n{text}"
        if total_chars + len(chunk) > MAX_TOTAL_CHARS:
            # Stop once we’ve hit our cap
            notes.append("Reached MAX_TOTAL_CHARS cap; remaining files omitted from prompt.")
            break

        aggregated_parts.append(chunk)
        total_chars += len(chunk)
        files_processed += 1

    return {
        "joined_text": "\n\n".join(aggregated_parts),
        "notes": notes,
        "politcal_reading": polit or "Unknown",  # intentional spelling to match consumer
        "files_processed": files_processed,
    }

# ------------------ LLM call ------------------
def run_case_synthesis(case_text: str, politcal_reading: str) -> str:
    """
    Calls Gemini and asks for STRICT JSON.
    Returns the raw LLM text (which should be JSON).
    """
    system = (
        'You are "Para-Synth", an AI legal assistant. '
        "Using ONLY the provided text, produce STRICT JSON with keys:\n"
        '{\n'
        '  "main_summary": "string",\n'
        '  "key_findings": ["string","string","string"],\n'
        '  "hippa_necessity": "string",\n'
        '  "medical_history_summary": "string",\n'
        '  "politcal_reading": "string",\n'
        '  "litigation_phase": "string"\n'
        '}\n'
        "- The array key_findings MUST have EXACTLY 3 items.\n"
        "- Return ONLY JSON. No prose, no markdown."
    )

    prompt = (
        f"{system}\n\n"
        f"politcal_reading: {politcal_reading}\n\n"
        "TEXT START\n"
        f"{case_text}\n"
        "TEXT END"
    )

    genai.configure(api_key=GENAI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    resp = model.generate_content(prompt)
    return resp.text or ""

# ------------------ Orchestrator ------------------
def summarize_case_to_file(bucket: str, prefix: str, out_dir: str = ".") -> Optional[str]:
    """
    Orchestrates: gather → LLM → validate → write JSON file.
    Returns path to JSON file if successful, else None.
    """
    g = gather_case_text(bucket, prefix)
    if not g["joined_text"]:
        # No text to summarize; write a minimal JSON so the pipeline still completes.
        minimal = {
            "main_summary": "No readable text was found under the provided case prefix.",
            "key_findings": ["No data", "No data", "No data"],
            "hippa_necessity": "Unknown",
            "medical_history_summary": "Unknown",
            "politcal_reading": g["politcal_reading"],
            "litigation_phase": "Unknown",
            "_meta": {
                "files_processed": g["files_processed"],
                "notes": g["notes"],
            }
        }
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(out_dir, f"synthesis_empty_{safe_prefix(prefix)}_{ts}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(minimal, f, indent=2)
        return out_path

    raw = run_case_synthesis(g["joined_text"], g["politcal_reading"])

    # Simplify output file name to just the case identifier, e.g. "1-12564888.json"
    case_name = prefix.strip("/").replace("File ", "").replace("/", "")
    out_path = os.path.join(out_dir, f"{case_name}.json")


    # Try to coerce into JSON; if it fails, save raw for debugging
    try:
        data = json.loads(raw)

        # Safety: enforce exactly 3 findings if the model drifted
        if isinstance(data.get("key_findings"), list):
            if len(data["key_findings"]) < 3:
                data["key_findings"] = (data["key_findings"] + [""]*3)[:3]
            elif len(data["key_findings"]) > 3:
                data["key_findings"] = data["key_findings"][:3]
        else:
            data["key_findings"] = ["", "", ""]

        # Ensure politcal_reading field is present (consistent spelling)
        data["politcal_reading"] = data.get("politcal_reading") or g["politcal_reading"]

        # Attach meta (non-schema) to help you debug; safe to remove later
        data["_meta"] = {
            "files_processed": g["files_processed"],
            "notes": g["notes"],
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return out_path

    except Exception:
        # Save raw text so you can inspect what the model returned
        raw_path = os.path.join(out_dir, f"{case_name}_raw.txt")
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw)
        return None

def safe_prefix(prefix: str) -> str:
    """Sanitize prefix for filename parts."""
    s = prefix.strip("/").replace("/", "_")
    return s or "root"

# ------------------ CLI ------------------
if __name__ == "__main__":
    # EXAMPLE: edit these two lines
    BUCKET = "knighthacks-mm"
    PREFIX = "File 1-12564888/"   # the "case" folder; use "" for whole bucket

    out = summarize_case_to_file(BUCKET, PREFIX, out_dir=".")
    if out:
        print(f"✅ Wrote JSON: {out}")
    else:
        print("⚠️ Model output wasn’t valid JSON; wrote a raw .txt instead.")
