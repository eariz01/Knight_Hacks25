# gcs_case_summarizer.py
# Summarize files in a GCS case prefix with Gemini (JSON-only), then
# fill selected fields in ./product.json. political_reading and venue.court_type
# are resolved from ./Courts.json (format: {"courts": [ {name, county, leaning}, ... ]}).
# Also sets checklist booleans to true if the model finds evidence.

import os
import re
import json
from io import BytesIO
from typing import Optional, List, Tuple, Dict

import google.generativeai as genai
from google.cloud import storage
from pypdf import PdfReader

# ------------------ CONFIG ------------------
GENAI_API_KEY = "API_KEY"  # replace if not using env var
MODEL_NAME = "gemini-2.5-flash"

TEMPLATE_PATH = "product.json"   # your blank template to fill
COURTS_PATH   = "Courts.json"    # county -> (leaning, court via name)

MAX_CHARS_PER_FILE = 3_000
MAX_TOTAL_CHARS    = 70_000

SKIP_EXTS = (
    ".m4a", ".mp3", ".wav", ".flac",
    ".jpg", ".jpeg", ".png", ".gif", ".heic", ".webp",
    ".mp4", ".mov", ".avi", ".mkv",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".exe", ".dll"
)

TEXT_LIKE_MIMES = {
    "text/plain", "text/csv", "text/markdown",
    "application/json", "application/xml",
    "application/x-yaml", "application/yaml",
}

# ------------------ Helpers: normalization ------------------
def _normalize_county(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    # Normalize "St. Johns" variants
    s = re.sub(r"\bSt\.?\s+", "St. ", s)
    base = s
    if base.lower().endswith(" county"):
        base = base[:-7]
    # alnum-only lowercase key
    key = "".join(ch for ch in base.lower() if ch.isalnum())
    return key

def _split_county_list(s: str) -> List[str]:
    # counties may be comma-separated or ranges like "(Circuits ...)" which we ignore
    s = (s or "").strip()
    if not s or s.startswith("("):
        return []
    return [c.strip() for c in s.split(",") if c.strip()]

# ------------------ Courts.json loading & resolution ------------------
def _load_courts(path: str) -> List[Dict[str, str]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    # Expected: {"courts": [ { "name": "...", "county": "...", "leaning": "..." }, ... ]}
    arr = data.get("courts", []) if isinstance(data, dict) else []
    return [x for x in arr if isinstance(x, dict)]

def _parse_mixed_leaning(leaning_str: str, county: str) -> Optional[str]:
    """
    Handles strings like: "Mixed (e.g., Orange: Liberal, Polk: Conservative)".
    Tries to extract the exact county's leaning if present.
    Builds a flexible county regex for names like "St. Lucie" / "St Lucie".
    """
    if not leaning_str or "mixed" not in leaning_str.lower():
        return None

    county_plain = (county or "").strip()

    # Build a flexible regex for the county name:
    # If it starts with "St" variants, allow "St", "St.", and flexible spaces
    m = re.match(r"(?i)st\.?\s*(.+)", county_plain)
    if m:
        rest = m.group(1)  # everything after St./St
        county_pat = r"St\.?\s*" + re.escape(rest)
    else:
        county_pat = re.escape(county_plain)

    # Now capture "...: LeaningWord"
    regex = re.compile(rf"{county_pat}\s*:\s*([A-Za-z]+)", re.IGNORECASE)
    m = regex.search(leaning_str)
    if m:
        return m.group(1).capitalize()
    return None

def _derive_court_type_from_name(name: str) -> str:
    """
    Map the 'name' field to a simple court_type label we want in product.json.
    Priority:
      - "* County Court" -> "County Court"
      - "* Judicial Circuit Court" -> "Circuit Court"
      - "District Court of Appeal" -> "District Court of Appeal"
      - "U.S. District Court" -> "U.S. District Court"
      - "Supreme Court" -> "Supreme Court"
      - else -> ""
    """
    n = (name or "").lower()
    if "county court" in n:
        return "County Court"
    if "judicial circuit court" in n or "judicial circuit" in n:
        return "Circuit Court"
    if "district court of appeal" in n:
        return "District Court of Appeal"
    if "u.s. district court" in n or "us district court" in n:
        return "U.S. District Court"
    if "supreme court" in n:
        return "Supreme Court"
    return ""

def _resolve_politics_and_court(county: str, courts: List[Dict[str, str]]) -> Tuple[str, str]:
    """
    Given a county (e.g., "Putnam"), scan Courts.json and return:
      (political_reading, court_type)
    """
    if not county:
        return "Unknown", ""

    norm_target = _normalize_county(county)
    matches: List[Dict[str, str]] = []

    for rec in courts:
        rec_counties = rec.get("county", "")
        if rec_counties.startswith("("):
            # skip entries like "(Circuits ...)"
            continue
        items = _split_county_list(rec_counties)
        for c in items if items else [rec_counties]:
            if _normalize_county(c) == norm_target:
                matches.append(rec)
                break

    # Resolve leaning
    leaning_final = "Unknown"
    for rec in matches:
        lean = rec.get("leaning", "")
        parsed = _parse_mixed_leaning(lean, county)
        if parsed:
            leaning_final = parsed
            break
        if lean and "mixed" not in lean.lower():
            leaning_final = lean
            break

    # Resolve court_type by priority
    priority = ["County Court", "Circuit Court", "District Court of Appeal", "U.S. District Court", "Supreme Court"]
    best_type = ""
    for tier in priority:
        for rec in matches:
            ctype = _derive_court_type_from_name(rec.get("name", ""))
            if ctype == tier:
                best_type = ctype
                break
        if best_type:
            break

    return leaning_final, best_type

# ------------------ GCS text extraction ------------------
def _safe_extract_text(blob) -> Tuple[Optional[str], Optional[str]]:
    try:
        name = blob.name.lower()
        if name.endswith(SKIP_EXTS):
            return None, f"Skipped binary/media file '{blob.name}'."

        mime = blob.content_type or ""

        # PDF
        if "pdf" in mime or name.endswith(".pdf"):
            pdf_bytes = blob.download_as_bytes()
            reader = PdfReader(BytesIO(pdf_bytes))
            parts = []
            for p in reader.pages:
                try:
                    parts.append(p.extract_text() or "")
                except Exception:
                    continue
            text = "\n".join(parts).strip()
            if not text:
                return None, f"No extractable text in PDF '{blob.name}'."
            return text[:MAX_CHARS_PER_FILE], None

        # Text-like
        if mime.startswith("text/") or mime in TEXT_LIKE_MIMES or name.endswith((".txt", ".csv", ".md", ".json", ".xml", ".yaml", ".yml")):
            raw = blob.download_as_text()
            if name.endswith(".json"):
                try:
                    obj = json.loads(raw)
                    raw = json.dumps(obj, indent=2)
                except Exception:
                    pass
            return (raw[:MAX_CHARS_PER_FILE], None) if raw else (None, f"Empty text in '{blob.name}'.")
        
        return None, f"Skipped non-text file '{blob.name}' (content_type={mime or 'unknown'})."
    except Exception as e:
        return None, f"Error reading '{blob.name}': {e}"

def gather_case_text(bucket: str, prefix: str) -> dict:
    client = storage.Client()
    parts: List[str] = []
    notes: List[str] = []
    files_processed = 0
    total = 0

    for blob in client.list_blobs(bucket, prefix=prefix):
        text, warn = _safe_extract_text(blob)
        if warn:
            notes.append(warn)
            continue
        if not text:
            notes.append(f"No text from '{blob.name}'.")
            continue

        chunk = f"[FILE {blob.name}]\n{text}"
        if total + len(chunk) > MAX_TOTAL_CHARS:
            notes.append("Reached MAX_TOTAL_CHARS cap; remaining files omitted from prompt.")
            break

        parts.append(chunk)
        total += len(chunk)
        files_processed += 1

    return {
        "joined_text": "\n\n".join(parts),
        "notes": notes,
        "files_processed": files_processed,
    }

# ------------------ JSON-only LLM call ------------------
def _extract_json_block(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    # strip triple-fence wrappers
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)
    # grab first {...}
    start = t.find("{")
    end   = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return t[start:end+1]
    return t

def run_case_synthesis(case_text: str) -> str:
    """
    Ask Gemini for a JSON object with EXACT fields to fill in product.json.
    political_reading must be "", we will set it from Courts.json using county.
    Includes a checklist object; model sets items true when evidence exists.
    """
    if not GENAI_API_KEY or GENAI_API_KEY == "GOOGLE API KEY":
        raise RuntimeError("Set GOOGLE_API_KEY env var or replace GENAI_API_KEY string.")

    genai.configure(api_key=GENAI_API_KEY)

    generation_config = {
        "temperature": 0,
        "response_mime_type": "application/json",
    }
    model = genai.GenerativeModel(MODEL_NAME, generation_config=generation_config)

    prompt = f"""
You are "Synthia", an AI legal assistant.

USING ONLY the text between TEXT START / TEXT END, return a SINGLE JSON object with EXACTLY these keys and types.
Your main_summary is to be a strong headliner that is 8 words or less that grasps the exact essence of the case and its outcome.
If a value is not stated in the text, use an empty string "" (NOT null). "key_findings" MUST be 3 strings.
Set "political_reading" to "" (empty), it will be filled via a separate table.
For "checklist", set an item to true only if there is clear textual evidence that the criterion has been met; otherwise leave it false.

REQUIRED JSON SHAPE:
{{
  "main_summary": "string",
  "key_findings": ["string","string","string"],
  "hipaa_necessity": "string",
  "medical_history_summary": "string",
  "political_reading": "",
  "litigation_phase": "string",
  "status": "string",
  "venue": {{
    "court_type": "string",
    "county": "string"
  }},
  "checklist": {{
    "Discovery": {{
      "Medical record summary has been received and summarized": false,
      "Defendant responded to the discovery request": false,
      "Did we respond to defendants discovery request": false,
      "Scheduled Defendant Deposition": false,
      "Scheduled Plaintiff Deposition": false,
      "Do we need to bring in an expert": false
    }},
    "Settlement Discussion": {{
      "Have depositions been transcripted and summarized": false,
      "Has mediation been scheduled": false,
      "Have we scheduled a talk with the client": false
    }},
    "Pre-Trial": {{
      "Do we have certified copies of records": false,
      "Client and experts are notified": false,
      "Prepared trial notebook": false,
      "Prepare jury charges, motions, and pretrial order": false
    }},
    "Trial": {{
      "Payment received": false
    }}
  }}
}}

RULES:
- Return JSON ONLY (no prose, no markdown, no extra fields).
- "key_findings": 3 concise, outcome/liability/damages-oriented statements.
- If litigation stage implied (e.g., discovery answers), set "litigation_phase"; else "".
- If status not stated, default to "Pending".
- "hipaa_necessity": be explicit re: whether HIPAA-compliant records collection is needed and scope.
- Checklist: set booleans true ONLY where the documents clearly confirm the item (e.g., deposition notice/scheduling, mediation order, discovery responses, payment confirmation, etc.).
- Be faithful to the text; do not invent facts.

TEXT START
{case_text}
TEXT END
"""
    resp = model.generate_content(prompt)
    return (resp.text or "").strip()

# ------------------ Merge into product.json ------------------
def _ensure_3_findings(lst) -> List[str]:
    if not isinstance(lst, list):
        return ["", "", ""]
    out = [("" if x is None else str(x)) for x in lst]
    if len(out) < 3:
        out = (out + ["", "", ""])[:3]
    elif len(out) > 3:
        out = out[:3]
    return out

def _coerce_str(x) -> str:
    return "" if x is None else str(x)

def _deep_merge_checklist(base: Dict, new: Dict) -> Dict:
    """
    Deep-merge checklist booleans: overwrite only matching keys;
    keep structure and unrelated keys intact.
    """
    if not isinstance(new, dict):
        return base
    for section, tasks in new.items():
        if not isinstance(tasks, dict):
            continue
        base.setdefault(section, {})
        for task, val in tasks.items():
            if isinstance(val, bool):
                base[section][task] = val
    return base

def _merge_into_template(template_path: str, llm_obj: dict, courts: List[Dict[str, str]]) -> dict:
    """
    Load product.json, overwrite ONLY selected fields, and save.
    Also set political_reading & (if needed) court_type from Courts.json via venue.county.
    Merge checklist booleans from model output.
    """
    with open(template_path, "r", encoding="utf-8") as f:
        product = json.load(f)

    # Read LLM values
    main_summary            = _coerce_str(llm_obj.get("main_summary"))
    key_findings            = _ensure_3_findings(llm_obj.get("key_findings", []))
    hipaa_necessity         = _coerce_str(llm_obj.get("hipaa_necessity"))
    medical_history_summary = _coerce_str(llm_obj.get("medical_history_summary"))
    litigation_phase        = _coerce_str(llm_obj.get("litigation_phase"))
    status                  = _coerce_str(llm_obj.get("status")) or "Pending"

    venue_in = llm_obj.get("venue") or {}
    court_type_in = _coerce_str(venue_in.get("court_type"))
    county_in     = _coerce_str(venue_in.get("county"))

    # Resolve from Courts.json
    leaning, mapped_court = _resolve_politics_and_court(county_in, courts)
    court_type_final = court_type_in or mapped_court

    # Apply core fields
    product["main_summary"] = main_summary
    product["key_findings"] = key_findings
    product["hipaa_necessity"] = hipaa_necessity
    product["medical_history_summary"] = medical_history_summary
    product["political_reading"] = leaning or "Unknown"
    product["litigation_phase"] = litigation_phase
    product["status"] = status

    product.setdefault("venue", {})
    product["venue"]["court_type"] = court_type_final
    product["venue"]["county"] = county_in

    # Checklist merge
    model_checklist = llm_obj.get("checklist", {})
    product.setdefault("checklist", {})
    product["checklist"] = _deep_merge_checklist(product["checklist"], model_checklist)

    with open(template_path, "w", encoding="utf-8") as f:
        json.dump(product, f, indent=2)

    return product

# ------------------ Orchestrator ------------------
def summarize_case_to_product(bucket: str, prefix: str) -> Optional[str]:
    # Gather text
    g = gather_case_text(bucket, prefix)

    # Load Courts.json now (used in both branches)
    courts = _load_courts(COURTS_PATH)

    if not g["joined_text"]:
        # No LLM call; still try to fill from Courts.json if county exists in template
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            product = json.load(f)
        county_in = product.get("venue", {}).get("county", "")
        leaning, mapped_court = _resolve_politics_and_court(county_in, courts)
        if leaning:
            product["political_reading"] = leaning
        if mapped_court and not product.get("venue", {}).get("court_type"):
            product["venue"]["court_type"] = mapped_court
        with open(TEMPLATE_PATH, "w", encoding="utf-8") as f:
            json.dump(product, f, indent=2)
        return TEMPLATE_PATH

    # Call model
    raw = run_case_synthesis(g["joined_text"])

    # Parse JSON (with fallback)
    try:
        llm_obj = json.loads(raw)
    except Exception:
        candidate = _extract_json_block(raw)
        try:
            llm_obj = json.loads(candidate)
        except Exception:
            with open("product_raw.txt", "w", encoding="utf-8") as f:
                f.write(raw)
            return None

    # Merge into template + resolve politics/court + checklist
    _merge_into_template(TEMPLATE_PATH, llm_obj, courts)
    return TEMPLATE_PATH

# ------------------ CLI ------------------
if __name__ == "__main__":
    # EDIT THESE to your case location in GCS:
    with open("ticket.json", "r", encoding="utf-8") as f:
        ticket = json.load(f)
    PREFIX = ticket.get("case_number", "")
    BUCKET = "knighthacks-mm"
    CLIENT_NAME = ticket.get("client_name", "")
    try:
        with open("product.json", "r+", encoding="utf-8") as f:
            product = json.load(f)
            product["id"] = PREFIX
            product["client_name"] = CLIENT_NAME
            f.seek(0)
            json.dump(product, f, indent=2)
            f.truncate()
    except Exception as e:
        print(f"⚠️ Could not update product.json ID/client_name: {e}")

    out = summarize_case_to_product(BUCKET, PREFIX)
    if out:
        print(f"✅ Updated template: {out}")
    else:
        print("⚠️ Model output wasn’t valid JSON; wrote product_raw.txt for inspection.")
