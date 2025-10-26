import google.generativeai as genai
import json

##Reminder DELETE API KEY BEFORE COMMITTING TO GITHUB
genai.configure(api_key="AIzaSyBWE1PlorpDVBUxfO9WFpchyB8U7leQweo")
##Made jurisdiction a parameter so we can change it as needed
def run_legal_research(query, jurisdiction="Florida"):
    prompt = f"""
You are "Para," an AI Legal Researcher for Morgan & Morgan.

Your role: Assist attorneys by identifying relevant case law, statutes, and precedents based on {jurisdiction} and national law.

Instructions:
- Search and summarize at least 3–5 relevant cases or statutes.
- Include case name, citation, court, year, and a 1–2 sentence summary.
- Prioritize {jurisdiction} law, but include key federal precedents when applicable.
- Focus on outcomes and reasoning that strengthen the plaintiff’s position.
- Output results in strict JSON format following this schema:

{{
  "topic": "{query}",
  "jurisdiction": "{jurisdiction}",
  "relevant_cases": [
    {{
      "case_name": "string",
      "citation": "string",
      "court": "string",
      "summary": "string",
      "relevance_score": float
    }}
  ],
  "federal_cases": [],
  "notes": "string"
}}
"""
    ##Can change model whenever we want to test different ones
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)

    #Making sure the output is valid JSON
    try:
        data = json.loads(response.text)
    except Exception:
        print("Not a valid JSON!")
        print(response.text)
        return None

    return data



def verify_case(case_name, citation):
    verify_prompt = f"""
You are "LexiVerify," an AI case-law verifier for Morgan & Morgan.

Given this case citation and name, verify if it exists and summarize its validity.

Case: "{case_name}, {citation}"

Instructions:
1. Check if the case is a real, published decision.
2. Confirm citation format matches the court and year.
3. Flag as:
   - "valid" if exists.
   - "suspicious" if format seems off or incomplete.
   - "invalid" if likely fabricated.
4. Output JSON only:
{{
  "case_name": "{case_name}",
  "citation": "{citation}",
  "status": "valid | suspicious | invalid",
  "confidence": 0-1.0,
  "notes": "short reason"
}}
"""
    ##Can change model whenever we want to test different ones
    model = genai.GenerativeModel("gemini-1.5-flash")
    resp = model.generate_content(verify_prompt)

    #Making sure the output is valid JSON
    try:
        check = json.loads(resp.text)
    except Exception:
        check = {"case_name": case_name, "citation": citation,
                 "status": "suspicious", "confidence": 0.3,
                 "notes": "Could not parse verification response."}
    return check



def run_pipeline(query):
    research = run_legal_research(query)
    if not research:
        return
    ##Store verified cases separately
    verified = []
    for case in research.get("relevant_cases", []):
        v = verify_case(case["case_name"], case["citation"])
        case["verification"] = v
        verified.append(case)

    research["relevant_cases"] = verified
    return research


#Where we are pulling the query then calling the pipeline to get the cases and verify them
if __name__ == "__main__":

    ##Need to scan based on the Case Manager queries for "Headliners"
    query = "pain and suffering damages in low-impact auto accidents"
    result = run_legal_research(query)
    print(json.dumps(result, indent=2))
