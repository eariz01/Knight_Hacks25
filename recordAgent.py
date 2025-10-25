#Google ADK Tools
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool, ToolContext
#Using Google Cloud to save data
from google.cloud import storage
# Import Pydantic models for structured output
from pydantic import BaseModel, Field
from typing import List

class SynthesisResult(BaseModel):
    """
    The final, structured JSON output that the LlmAgent must conform to.
    The descriptions here guide the LLM's reasoning and generation process.
    """
    
    main_summary: str = Field(
        description="A concise, one sentence, high-level summary of the entire body of synthesized documents. Focusing just on the classification of the incident so a paralegal can find relevant cases for precedent"
    )
    key_findings: List[str] = Field(
        description="A bulleted list of the top 3 critical, actionable findings extracted from the files."
    )
    hippa_necessity: str = Field(
        description="A brief explanation of whether HIPAA compliance is necessary based on the synthesized data, and if we will need to proceed with requesting medical records"
    )
    medical_history_summary: str = Field(
        description="A concise summary of the patient's medical history as derived from the documents. Take attention to detail if there are any related conditions that could be related or attributed to pre-existing conditions."
    )
    politcal_reading: str = Field(
        description="A one word assessment of the political leaning of the district, which is found in the json file Courts.json"
    )
    litigation_phase: str = Field(
        description="An assessment of the current phase of litigation based on the synthesized data, such as discovery, pre-trial, trial, or settlement discussions."
    )

def synthesize_data_from_gcs(
    input_paths: List[str],
    tool_context: ToolContext
) -> str:
    """
    Reads content from GCS URIs, aggregates it, and generates a concise summary
    for the LLM's context window.
    """
    print(f"--- TOOL: Processing {len(input_paths)} files from GCS... ---")
    
    storage_client = storage.Client()
    aggregated_text = ""
    
    for gcs_uri in input_paths:
        try:
            # Parse bucket and blob name from gs://bucket/path/to/file
            bucket_name = gcs_uri.split("//")[1].split("/")[0]
            blob_name = "/".join(gcs_uri.split("/")[3:])
            
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            
            # Download and read the file content (Use streaming for very large files!)
            # For simplicity, we assume text-based files here
            file_content = blob.download_as_text()
            
            # CRITICAL STEP: Summarize/Condense the content immediately
            # We are *not* passing the raw file, but a summary of it
            # A simple rule for now, but a more complex summary logic is better:
            summary_snippet = f"File {blob_name} summary: First 100 chars: {file_content[:100]}... "
            
            aggregated_text += summary_snippet
            
        except Exception as e:
            aggregated_text += f"Error reading {gcs_uri}: {e}. "
    
    # Send the combined, small summary to a powerful external LLM for final context reduction
    # (If the aggregated_text is still too large for the ADK agent's prompt, 
    # you'd call a dedicated summarizer here before returning.)
    
    # Store the final synthesized text in the session state for the agent to use
    tool_context.state['synthesized_data'] = aggregated_text
    
    # Return a message that confirms success and prompts the agent to check the state
    return "Data aggregation complete. Check session state for 'synthesized_data' and begin your final conclusion."
#Function Tool for the file processor
file_processor_tool = FunctionTool(
    synthesize_data_from_gcs,
    name="FileProcessorTool",
    description="Processes a list of scattered files, aggregates content, and uploads it to the Gemini Files API, returning a reference ID for the full context."
)

#AI Agent
record_agent = LlmAgent(
    model='gemini-2.5-flash', 
    name="Record Agent",
    tools=[file_processor_tool],
    description="Sorts through records and various data forms gathered from Google File API with a tool and synthesizes them into concise reports.",
    instruction="You will gather data from a variety of data types all gathered from a Google File API which you will call with your helper tool. You will then synthesize those findings into the JSON format provided from our Pydantic specification."
)