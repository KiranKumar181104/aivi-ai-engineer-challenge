# AIVI Deliverables 2 and 3

Production prompt and Gemini API resume/JD matcher. This is a reviewable local
implementation, not a claim of deployment into Campus OS or Hack My Website.

## Run (Python 3.10+)

```bash
python -m pip install -r requirements.txt
export GEMINI_API_KEY='your-own-key'
python resume_matcher.py --resume sample_resume.txt --jd sample_jd.txt
python -m unittest -v
```

PowerShell: `$env:GEMINI_API_KEY = 'your-own-key'`. Do not put the key in a repo.
Set `GEMINI_MODEL` or use `--model` for a structured-output-capable model available
to your account. Default is gemini-3.8-flash, as listed in the official model docs
when this implementation was prepared. Model access and quotas can differ.

The API key is sent in a header. Resume/JD content is transmitted to Google's
Gemini API when you run the live command. The included examples are synthetic.
Success prints only the four-field JSON to stdout. Summary is a string containing
exactly two lines (`\\n` in serialized JSON). Failure returns exit code 1 and a
separate JSON error on stderr; stdout stays empty. No fake score is returned for
rate limits, timeouts, blocked responses, or invalid output.

## Architecture and fallback

- System instructions are separate from JSON-encoded untrusted resume/JD data.
- Gemini structured output requests the Pydantic-derived JSON Schema; local
  Pydantic validation remains authoritative for types, ranges, keys and two lines.
- Only whole-output JSON fences, BOM and outer whitespace are sanitized. Prose,
  duplicate keys, NaN, extra fields, numeric strings and booleans as scores fail.
- Up to three calls for transient 408/429/500/502/503/504 or network timeouts;
  exponential backoff with jitter, numeric Retry-After, 15-second socket timeout,
  50-second best-effort wall budget. Socket timeouts are not hard process deadlines
  (DNS/OS scheduling can exceed them); use an external worker deadline in deployment.
- Malformed output gets at most one regeneration. Permanent 4xx do not retry.
- On exhaustion, defer/requeue or show an explicit error; do not fabricate output,
  silently truncate input, or switch to an unvalidated model. A future fallback
  model must use the same prompt/schema and pass evaluation first.
- CLI rejects empty/oversized input before transmission. The prompt also defines
  empty-document behavior for callers that use the prompt outside this CLI.
- JSON validity does not establish factual correctness or injection resistance.
  Scoring is model-assigned; the rubric is not mechanically enforced. This is
  advisory job-requirement matching, not an automated hiring decision.

## Validation status

Offline transport/schema tests exercise real parser and application code using
synthetic API envelopes; they do not establish live model quality. No live Gemini
request was run because GEMINI_API_KEY was not configured. A successful live smoke
test plus an adversarial/grounding evaluation is required before claiming the
script is validated end-to-end. Test the baseline and injected resume with the
same JD, compare factual claims, and retain request/model/version metadata.

## Deliverable 2 notes

`system_prompt.txt` is the exact production prompt used by the script. It includes
an evidence rubric, untrusted-input handling, no-preamble JSON, no cross-candidate
reuse, Hindi/Hinglish support, empty/OCR/contradictory input guidance, and few-shot
examples. API failure handling is intentionally implemented in application code;
a system prompt cannot catch HTTP 429 or enforce request deadlines.

Audit findings motivated explicit evidence grounding and no invented metrics.
Do not characterize identical demo outputs as proof of a static backend or
successful prompt-injection protection. Text fluency is not pronunciation evidence.

## Submission still required

The assignment requires a public/viewable GitHub repo or Google Colab link, plus
the audit document/PDF. This package has not been published, sent to the recruiter,
or live API-tested. HMW remains blocked as described in hmw_audit_status.md.

## Primary documentation

- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/generate-content/structured-output
- https://ai.google.dev/gemini-api/docs/troubleshooting
- https://ai.google.dev/gemini-api/docs/models
