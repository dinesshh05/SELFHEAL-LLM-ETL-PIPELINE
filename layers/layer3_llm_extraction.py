from __future__ import annotations

import os

from groq import Groq # type:ignore

from models.schemas import PipelineContext
from utils.logger import log_error, log_info, log_layer, log_success


# Prompt template
EXTRACTION_PROMPT = """\
You are a precise data extraction assistant.

Extract the following fields from the resume/CV text below and return ONLY a valid JSON object.
No explanation, no markdown, no code blocks — just raw JSON.

Required JSON schema:
{{
  "name":             string,
  "email":            string (valid email),
  "phone":            string or null,
  "skills":           [string, ...],
  "education": [
    {{
      "degree":          string or null,
      "institution":     string or null,
      "graduation_year": integer or null
    }}
  ],
  "experience": [
    {{
      "company":        string or null,
      "role":           string or null,
      "duration_years": float or null
    }}
  ],
  "confidence_score": float between 0.0 and 1.0
}}

Rules:
- confidence_score must reflect how complete and certain your extraction is
- Return ONLY the JSON — no surrounding text whatsoever
- Preserve suspicious or malformed values exactly as written in the source whenever possible
- Do NOT normalize invalid emails, phone numbers, years, or durations unless they are explicitly clear
- If a field cannot be found, use null (not empty string)
- skills must be an array of strings

Document text:
──────────────
{document_text}
──────────────
"""

# Public API

def run(ctx: PipelineContext, api_key: str | None = None) -> PipelineContext:
    """
    Layer 3 entry point.
    Sends ctx.raw_text to Groq API and stores the raw response string
    in ctx.raw_llm_response.
    """
    log_layer("LLM EXTRACTION", "Sending document to Groq API…")

    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        raise ValueError(
            "GROQ_API_KEY not set. "
            "Create one at: https://console.groq.com/keys"
        )

    model_name = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
    client = Groq(api_key=key)

    prompt = EXTRACTION_PROMPT.format(document_text=ctx.raw_text)
    log_info(f"Prompt length: {len(prompt):,} chars | Model: {model_name}")

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You return only raw JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
    except Exception as exc:
        log_error(f"LLM extraction failed: {exc}")
        raise RuntimeError(f"LLM extraction failed: {exc}") from exc

    raw_response = (response.choices[0].message.content or "").strip()
    ctx.raw_llm_response = raw_response

    log_success(f"Groq responded — {len(raw_response):,} chars received")
    log_info(f"Preview: {raw_response[:120]}…")

    return ctx