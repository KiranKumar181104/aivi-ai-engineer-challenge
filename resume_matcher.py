import os
import json
import time
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# 1. Enforce Strict Pydantic Schema based on report requirements
class EvaluationResult(BaseModel):
    match_score: int = Field(description="Strict integer score 0-100")
    top_strengths: list[str] = Field(description="0-5 concise strings linking resume evidence to the JD")
    missing_skills: list[str] = Field(description="0-10 concise strings of missing requirements")
    summary: str = Field(description="Exactly two nonempty lines within one string")

def evaluate_candidate(resume_text: str, jd_text: str, max_retries: int = 3) -> str:
    # Ensure GEMINI_API_KEY environment variable is set
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return json.dumps({"error": "GEMINI_API_KEY environment variable not set. Evaluation aborted."})
        
    # Initialize the new SDK client
    client = genai.Client(api_key=api_key)
    
    prompt = f"Resume:\n{resume_text}\n\nJob Description:\n{jd_text}"

    for attempt in range(max_retries):
        try:
            # Use the correct model and new generate_content syntax
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "You are a resume-to-job-description evidence evaluator. Return ONLY one JSON object "
                        "with exactly match_score, top_strengths, missing_skills, and summary. No markdown, "
                        "greeting, preamble, reasoning trace, or extra fields."
                    ),
                    response_mime_type="application/json",
                    response_schema=EvaluationResult,
                    temperature=0.0,
                )
            )
            
            # Sanitize and validate
            parsed_json = json.loads(response.text.strip())
            
            # Enforce score boundaries
            parsed_json["match_score"] = max(0, min(100, parsed_json.get("match_score", 0)))
            
            return json.dumps(parsed_json, indent=2)

        except Exception as e:
            error_msg = str(e).lower()
            # Handle transient network errors and rate limits
            if "429" in error_msg or "503" in error_msg or "timeout" in error_msg:
                sleep_time = (2 ** attempt) + 1 
                print(f"Attempt {attempt + 1} failed (Network/Rate Limit). Retrying in {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                return json.dumps({"error": f"API or parsing failure: {str(e)}"})
                
    return json.dumps({"error": "Exceeded maximum retries for transient errors."})

if __name__ == "__main__":
    # Test based on the few-shot examples in the report
    sample_resume = "Built a food ordering app with Django and MySQL."
    sample_jd = "Build backend apps with Django and MySQL."
    
    print("--- Final Output ---")
    print(evaluate_candidate(sample_resume, sample_jd))