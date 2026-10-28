#!/usr/bin/env python3
"""Gemini REST resume matcher. Success: validated JSON stdout. Failure: JSON stderr."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import random
import re
import socket
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class MatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    match_score: int = Field(ge=0, le=100)
    top_strengths: list[str] = Field(max_length=5)
    missing_skills: list[str] = Field(max_length=10)
    summary: str

    @field_validator("top_strengths", "missing_skills")
    @classmethod
    def valid_items(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 600 for v in values):
            raise ValueError("items must be nonempty and at most 600 characters")
        if len({v.strip().casefold() for v in values}) != len(values):
            raise ValueError("duplicate list items")
        return values

    @field_validator("summary")
    @classmethod
    def two_lines(cls, value: str) -> str:
        lines = value.split("\n")
        if len(lines) != 2 or any(not line.strip() for line in lines) or len(value) > 1600:
            raise ValueError("summary must contain exactly two nonempty lines")
        return value


class MatchError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code, self.message, self.retryable = code, message, retryable
        super().__init__(message)


def _unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def parse_result(text: str) -> MatchResult:
    """Sanitize BOM/outer whitespace and a single whole-document JSON fence only.

    Never repair numbers, fill fields, or extract a convenient object from prose.
    """
    if not isinstance(text, str) or len(text) > 32_000:
        raise MatchError("invalid_output", "Missing or oversized model output")
    cleaned = text.lstrip("\ufeff").strip()
    fence = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned, object_pairs_hook=_unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        return MatchResult.model_validate(data)
    except (ValueError, ValidationError) as exc:
        raise MatchError("invalid_output", "Model response failed strict JSON/schema validation") from exc


def response_text(envelope: dict) -> str:
    try:
        candidates = envelope.get("candidates", [])
        if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
            raise ValueError("blocked, truncated, or absent candidate")
        parts = candidates[0]["content"]["parts"]
        text = "".join(p["text"] for p in parts if "text" in p and not p.get("thought"))
        if not text.strip():
            raise ValueError("empty response")
        return text
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise MatchError("invalid_output", "No complete unblocked model response") from exc


def request_once(payload: dict, api_key: str, model: str, timeout: float) -> dict:
    # API key stays in a header, never in a URL, log, or command argument.
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), method="POST",
                      headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise MatchError("invalid_output", "API response exceeded size limit")
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("not an object")
        return parsed
    except (ValueError, UnicodeError) as exc:
        raise MatchError("invalid_output", "API returned invalid JSON") from exc


def match_resume(resume: str, jd: str, *, api_key: str, model: str,
                 timeout: float = 15, deadline: float = 50, attempts: int = 3,
                 transport=request_once, sleep=time.sleep, clock=time.monotonic,
                 jitter=random.uniform) -> MatchResult:
    if not api_key:
        raise MatchError("configuration", "Set GEMINI_API_KEY before a live request")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise MatchError("configuration", "Invalid model identifier")
    if not (math.isfinite(timeout) and math.isfinite(deadline) and timeout > 0 and deadline > 0 and 1 <= attempts <= 3):
        raise MatchError("configuration", "Use positive finite time limits and 1-3 attempts")
    if not isinstance(resume, str) or not isinstance(jd, str) or not resume.strip() or not jd.strip():
        raise MatchError("invalid_input", "Resume and job description must be nonempty text")
    if len(resume) > 60_000 or len(jd) > 30_000:
        raise MatchError("invalid_input", "Input exceeds resume/JD character limits")
    prompt = Path(__file__).with_name("system_prompt.txt").read_text(encoding="utf-8")
    payload = {
        "systemInstruction": {"parts": [{"text": prompt}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(
            {"resume_text": resume, "job_description": jd}, ensure_ascii=False)}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 4096,
                             "responseMimeType": "application/json",
                             "responseJsonSchema": MatchResult.model_json_schema()},
    }
    end = clock() + deadline
    last = MatchError("unavailable", "Request did not complete", True)
    for attempt in range(attempts):
        remaining = end - clock()
        if remaining <= 0:
            break
        retry_after = 0.0
        try:
            envelope = transport(payload, api_key, model, min(timeout, remaining))
            result = parse_result(response_text(envelope))
            if clock() > end:
                raise MatchError("timeout", "Evaluation exceeded latency budget", True)
            return result
        except HTTPError as exc:
            transient = exc.code in {408, 429, 500, 502, 503, 504}
            if not transient:
                raise MatchError("api_error", f"Gemini HTTP {exc.code}; check credentials/model/request") from exc
            last = MatchError("rate_limited" if exc.code == 429 else "unavailable",
                              f"Gemini HTTP {exc.code}; retry later", True)
            # Honour numeric Retry-After. Longer delays defer instead of waiting indefinitely.
            try:
                retry_after = max(0.0, float(exc.headers.get("Retry-After", "0")))
                if not math.isfinite(retry_after):
                    retry_after = deadline
            except (ValueError, AttributeError):
                retry_after = 0.0
        except (TimeoutError, socket.timeout, URLError) as exc:
            last = MatchError("timeout", "Network failure or timeout; retry later", True)
        except MatchError as exc:
            if exc.code != "invalid_output":
                last = exc
                if not exc.retryable:
                    raise
            else:
                # One regeneration at most for malformed/schema-invalid output.
                last = exc
                if attempt >= 1:
                    raise
        if attempt + 1 >= attempts:
            break
        delay = max(retry_after, min(8.0, 2 ** attempt) + jitter(0, 0.5))
        if clock() + delay >= end:
            break
        sleep(delay)
    raise last


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", type=Path, required=True)
    parser.add_argument("--jd", type=Path, required=True)
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"))
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--deadline", type=float, default=50)
    args = parser.parse_args(argv)
    try:
        if args.resume.stat().st_size > 240_000 or args.jd.stat().st_size > 120_000:
            raise MatchError("invalid_input", "Input files exceed byte limits")
        result = match_resume(args.resume.read_text(encoding="utf-8-sig"),
                              args.jd.read_text(encoding="utf-8-sig"),
                              api_key=os.environ.get("GEMINI_API_KEY", ""),
                              model=args.model, timeout=args.timeout, deadline=args.deadline)
        print(result.model_dump_json(indent=2))
        return 0
    except MatchError as exc:
        error = {"code": exc.code, "message": exc.message, "retryable": exc.retryable}
    except (OSError, UnicodeError):
        error = {"code": "file_error", "message": "Cannot read UTF-8 input or system prompt", "retryable": False}
    except Exception:
        # Do not leak resume data, API keys, response bodies, or tracebacks.
        error = {"code": "internal_error", "message": "Unexpected local failure", "retryable": False}
    print(json.dumps({"error": error}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
