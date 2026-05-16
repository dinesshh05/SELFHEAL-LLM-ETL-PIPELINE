from __future__ import annotations

import json
import os
import re
from typing import Any

_EXTRACTION_PROMPT = """\
You are a precise data extraction assistant.

Extract the following fields from the resume/CV text below and return ONLY a valid JSON object.
No explanation, no markdown, no code blocks - just raw JSON.

Required JSON schema:
{
  "name": string,
  "email": string (valid email),
  "phone": string or null,
  "skills": [string, ...],
  "education": [
    {
      "degree": string or null,
      "institution": string or null,
      "graduation_year": integer or null
    }
  ],
  "experience": [
    {
      "company": string or null,
      "role": string or null,
      "duration_years": float or null
    }
  ],
  "confidence_score": float between 0.0 and 1.0
}

Rules:
- confidence_score must reflect how complete and certain your extraction is
- Return ONLY the JSON - no surrounding text whatsoever
- Preserve suspicious or malformed values exactly as written in the source whenever possible
- Do NOT normalize invalid emails, phone numbers, years, or durations unless they are explicitly clear
- If a field cannot be found, use null (not empty string)
- skills must be an array of strings

Document text:
---
{document_text}
---
"""

_REPAIR_PROMPT = """\
You previously extracted structured data from a document, but the output
contains validation errors that must be fixed.

INVALID JSON you produced:
{invalid_json}

VALIDATION ERRORS that were found:
{error_list}

Your task:
- Fix ONLY the fields mentioned in the errors above.
- Keep all other fields exactly as they were.
- Return ONLY the corrected, complete JSON object - no explanation, no markdown.
- Follow these rules strictly:
    - email must be a valid email address
    - confidence_score must be a float between 0.0 and 1.0
    - graduation_year must be an integer between 1950 and 2030 (or null)
    - duration_years must be a non-negative float (or null)
    - skills must be an array of strings
    - phone must have at least 7 digits (or null)

Corrected JSON:
"""

_VALID_MODES = {"auto", "mock", "groq"}
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_YEAR_RE = re.compile(r"(19\d{2}|20\d{2})")


def resolve_llm_mode(api_key: str | None = None) -> str:
    requested = os.environ.get("LLM_MODE", "auto").strip().lower()
    if requested not in _VALID_MODES:
        requested = "auto"

    if requested == "mock":
        return "mock"

    if requested == "groq":
        _ensure_groq_available()
        if not (api_key or os.environ.get("GROQ_API_KEY")):
            raise ValueError("GROQ_API_KEY is required when LLM_MODE=groq")
        return "groq"

    if api_key or os.environ.get("GROQ_API_KEY"):
        try:
            _ensure_groq_available()
            return "groq"
        except ImportError:
            return "mock"
    return "mock"


def build_extraction_response(document_text: str, api_key: str | None = None) -> tuple[str, str]:
    mode = resolve_llm_mode(api_key)
    if mode == "groq":
        return _groq_response(_EXTRACTION_PROMPT.format(document_text=document_text), api_key), mode
    return json.dumps(_mock_extract(document_text), indent=2), mode


def build_repair_response(
    invalid_json: dict[str, Any],
    errors: list[str],
    api_key: str | None = None,
) -> tuple[str, str]:
    mode = resolve_llm_mode(api_key)
    if mode == "groq":
        prompt = _REPAIR_PROMPT.format(
            invalid_json=json.dumps(invalid_json, indent=2),
            error_list="\n".join(f"- {error}" for error in errors),
        )
        return _groq_response(prompt, api_key), mode
    return json.dumps(_mock_repair(invalid_json, errors), indent=2), mode


def _ensure_groq_available() -> None:
    try:
        __import__("groq")
    except ImportError as exc:
        raise ImportError(
            "Groq mode was requested, but the groq package is not installed."
        ) from exc


def _groq_response(prompt: str, api_key: str | None) -> str:
    from groq import Groq  # type: ignore

    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        raise ValueError("GROQ_API_KEY is required for Groq mode")

    model_name = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
    client = Groq(api_key=key)
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You return only raw JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )
    return (response.choices[0].message.content or "").strip()


def _mock_extract(document_text: str) -> dict[str, Any]:
    lines = [line.strip() for line in document_text.splitlines() if line.strip()]
    upper_text = document_text.upper()

    name = _match_field(lines, "name") or _guess_name(lines)
    email = _match_field(lines, "email") or _EMAIL_RE.search(document_text)
    phone = _match_field(lines, "phone") or _guess_phone(document_text)
    skills = _extract_skills(lines, document_text)
    education = _extract_education(lines, document_text)
    experience = _extract_experience(lines, document_text)

    if name is None:
        name = "Demo Candidate"

    if isinstance(email, re.Match):
        email_value = email.group(0)
    else:
        email_value = email or "demo.candidate@example.com"

    if phone is None:
        phone_value = None
    else:
        phone_value = phone

    confidence = 0.91
    if not skills or not education or not experience:
        confidence = 0.74

    if "HEAL_ME" in upper_text or "BROKEN_EMAIL" in upper_text:
        email_value = "demo.candidate[at]example.com"
        confidence = 0.42
    if "BROKEN_PHONE" in upper_text:
        phone_value = "12345"
        confidence = min(confidence, 0.48)
    if "BROKEN_YEAR" in upper_text and education:
        education[0]["graduation_year"] = 1800
        confidence = min(confidence, 0.52)
    if "BROKEN_DURATION" in upper_text and experience:
        experience[0]["duration_years"] = -1.0
        confidence = min(confidence, 0.52)

    return {
        "name": name,
        "email": email_value,
        "phone": phone_value,
        "skills": skills,
        "education": education,
        "experience": experience,
        "confidence_score": round(confidence, 2),
    }


def _mock_repair(data: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    repaired = json.loads(json.dumps(data))
    fields = " ".join(errors).lower()

    if "name" in fields and not repaired.get("name"):
        repaired["name"] = "Demo Candidate"

    if "email" in fields:
        repaired["email"] = "demo.candidate@example.com"

    if "phone" in fields:
        repaired["phone"] = "+91-9000000000"

    if "confidence_score" in fields:
        repaired["confidence_score"] = 0.87
    else:
        score = repaired.get("confidence_score", 0.87)
        repaired["confidence_score"] = min(max(float(score), 0.0), 1.0)

    if "graduation_year" in fields:
        education = repaired.get("education") or []
        for item in education:
            if isinstance(item, dict):
                item["graduation_year"] = 2024
        repaired["education"] = education

    if "duration_years" in fields:
        experience = repaired.get("experience") or []
        for item in experience:
            if isinstance(item, dict):
                duration = item.get("duration_years")
                item["duration_years"] = abs(float(duration)) if duration is not None else 1.0
        repaired["experience"] = experience

    skills = repaired.get("skills") or []
    if not isinstance(skills, list):
        skills = [str(skills)]
    repaired["skills"] = [str(skill) for skill in skills]
    repaired.setdefault("education", [])
    repaired.setdefault("experience", [])
    repaired["confidence_score"] = max(0.87, float(repaired.get("confidence_score", 0.87)))
    return repaired


def _match_field(lines: list[str], label: str) -> str | None:
    pattern = re.compile(rf"^{label}\s*:\s*(.+)$", re.IGNORECASE)
    for line in lines:
        match = pattern.match(line)
        if match:
            return match.group(1).strip()
    return None


def _guess_name(lines: list[str]) -> str | None:
    for line in lines[:3]:
        if len(line.split()) in (2, 3) and not _EMAIL_RE.search(line):
            return line
    return None


def _guess_phone(document_text: str) -> str | None:
    match = re.search(r"(\+?\d[\d\s\-()]{6,}\d)", document_text)
    if match:
        return match.group(1).strip()
    return None


def _extract_skills(lines: list[str], document_text: str) -> list[str]:
    skills_line = _match_field(lines, "skills")
    if skills_line:
        return [skill.strip() for skill in skills_line.split(",") if skill.strip()]

    keywords = ["python", "sql", "fastapi", "pandas", "excel", "git", "aws"]
    found = [keyword.title() if keyword != "sql" else "SQL" for keyword in keywords if keyword in document_text.lower()]
    return found or ["Communication", "Problem Solving"]


def _extract_education(lines: list[str], document_text: str) -> list[dict[str, Any]]:
    education_line = _match_field(lines, "education")
    if education_line:
        parts = [part.strip() for part in education_line.split(",")]
        degree = parts[0] if parts else None
        institution = parts[1] if len(parts) > 1 else None
        year_match = _YEAR_RE.search(education_line)
        year = int(year_match.group(1)) if year_match else None
        return [{"degree": degree, "institution": institution, "graduation_year": year}]

    year_match = _YEAR_RE.search(document_text)
    return [
        {
            "degree": "B.Tech",
            "institution": "Demo University",
            "graduation_year": int(year_match.group(1)) if year_match else 2024,
        }
    ]


def _extract_experience(lines: list[str], document_text: str) -> list[dict[str, Any]]:
    experience_line = _match_field(lines, "experience")
    if experience_line:
        parts = [part.strip() for part in experience_line.split(",")]
        company = parts[0] if parts else None
        role = parts[1] if len(parts) > 1 else None
        duration_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:years?|yr)", experience_line, re.IGNORECASE)
        duration = float(duration_match.group(1)) if duration_match else 1.0
        return [{"company": company, "role": role, "duration_years": duration}]

    if "intern" in document_text.lower() or "developer" in document_text.lower():
        return [
            {
                "company": "Demo Labs",
                "role": "Intern",
                "duration_years": 0.5,
            }
        ]

    return [
        {
            "company": "Demo Labs",
            "role": "Contributor",
            "duration_years": 1.0,
        }
    ]
