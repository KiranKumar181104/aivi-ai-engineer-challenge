# AIVI Deliverables 2 and 3

This project contains a Gemini-powered resume-to-job-description matcher and
the supporting prompt, schema, examples, tests, and Hack My Website audit notes.
It is a local deliverable; it is not deployed into Campus OS or Hack My Website.

## Run the matcher

Install the dependencies:

```powershell
python -m pip install -r requirements.txt
```

Set your Gemini API key in PowerShell, then run the script:

```powershell
$env:GEMINI_API_KEY = 'your-own-key'
python resume_matcher.py
```

Do not commit or share your API key. The current script uses the sample resume
and job description defined in `resume_matcher.py`. It sends those texts to
Google's Gemini API and prints a JSON result. The model response can vary.

## Example output

The following is the output from a successful run with the included example
texts. It shows a complete match for the Django and MySQL requirements:

```json
{
  "match_score": 100,
  "top_strengths": [
    "Demonstrated experience developing backend applications using Django",
    "Proven track record of utilizing MySQL for database management"
  ],
  "missing_skills": [],
  "summary": "The candidate possesses direct hands-on experience building applications with Django and MySQL.\nThis background directly satisfies all core technical requirements outlined in the job description."
}
```

This is one model-generated example, not a guaranteed score or an objective
measure of candidate suitability. The matcher is advisory and should not be used
as the sole basis for hiring decisions.

## Project files

- `resume_matcher.py` calls the Gemini API and formats the result as JSON.
- `system_prompt.txt` contains the evaluator instructions used by the project.
- `schema.json` documents the expected response fields.
- `sample_resume.txt` and `sample_jd.txt` provide example input documents.
- `test_resume_matcher.py` contains offline matcher tests.
- `hmw_audit_status.md` documents the Hack My Website audit status and limitation.
- `hmw_evidence/` contains screenshots documenting the audit account and target
  registration prerequisite.

## Validation and limitations

The example output confirms a successful model response for the sample run; it
does not establish the model's factual accuracy across other resumes, jobs, or
prompt-injection attempts. Resume and job-description content is sent to Google's
Gemini API when the script is run.

The offline test file currently expects matcher functions that are not exposed
by the script, so `python -m unittest -v` does not pass with the current files.
The Hack My Website scan also remains blocked because an owned and verified
target domain is required; see `hmw_audit_status.md`.

## References

- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/generate-content/structured-output
- https://ai.google.dev/gemini-api/docs/troubleshooting
- https://ai.google.dev/gemini-api/docs/models
