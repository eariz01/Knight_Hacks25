import google.generativeai as genai
import json
genai.configure(api_key="OWN KEY")

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
        # Clean the response to ensure it's valid JSON.
        # AI models sometimes add backticks or "json" at the start.
        clean_response = response.text.strip().replace("```json", "").replace("```", "")
        data = json.loads(clean_response)
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
    model = genai.GenerativeModel("gemini-2.5-flash")
    resp = model.generate_content(verify_prompt)

    #Making sure the output is valid JSON
    try:
        # Clean the response to ensure it's valid JSON
        clean_response = resp.text.strip().replace("```json", "").replace("```", "")
        check = json.loads(clean_response)
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
    
    # Also verify federal cases if they exist
    verified_federal = []
    for case in research.get("federal_cases", []):
        v = verify_case(case["case_name"], case["citation"])
        case["verification"] = v
        verified_federal.append(case)
    
    research["federal_cases"] = verified_federal
    
    return research


#Where we are pulling the query then calling the pipeline to get the cases and verify them
if __name__ == "__main__":

    json_file_path = "product.json"  # 
    data = {}

    #Reading the JSON file
    try:
        with open(json_file_path, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found at {json_file_path}")
        print("Dude, create the file first with a 'main_summary' key.")
        exit()  # Kills the script if the file isn't there
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {json_file_path}.")
        exit()

    #Grabbing the query from that "main_summary" key
    query = data.get("main_summary")

    if not query:
        print(f"Error: 'main_summary' key not found or is empty in {json_file_path}.")
    else:
        print(f"Running research for query: {query}")
        
        # Running the full pipeline with that query
        research_results = run_pipeline(query)

        if research_results:
            #Stuffs the new results back into the original 'data'
            #This will overwrite the old keys or add the new ones
            data["topic"] = research_results.get("topic", query)
            data["jurisdiction"] = research_results.get("jurisdiction", "Florida")
            data["relevant_cases"] = research_results.get("relevant_cases", [])
            data["federal_cases"] = research_results.get("federal_cases", [])
            data["notes"] = research_results.get("notes", "No notes generated.")

            #Writes everything back to the *same* file
            try:
                with open(json_file_path, "w") as f:
                    json.dump(data, f, indent=4)  # indent=4 just makes it look nice
                print(f"Successfully updated {json_file_path} with new legal research.")
            except Exception as e:
                print(f"Error writing back to file: {e}")
        else:
            print("Failed to get research results. File not updated.")
