"""
Resume parser: extract text from uploaded files and convert to MasterResume JSON via Claude.
Supports PDF, DOCX, and plain text.
"""
from __future__ import annotations
import io
import json
import re

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

try:
    import pdfplumber
    _PDF_OK = True
except ImportError:
    _PDF_OK = False

try:
    from docx import Document as DocxDocument
    _DOCX_OK = True
except ImportError:
    _DOCX_OK = False


SCHEMA_DESCRIPTION = """
{
  "contact": {
    "name": "string",
    "email": "string",
    "phone": "string",
    "linkedin": "string (URL or handle)",
    "github": "string (URL or handle, or empty)",
    "location": "string (City, Province/Country)",
    "scholar_url": "string (Google Scholar URL or empty)"
  },
  "experiences": [
    {
      "role": "exact job title from resume",
      "org": "company or institution name",
      "dates": "date range string, e.g. 'Jan 2021 – Mar 2023'",
      "tags": ["list of tags from vocabulary"],
      "bullets": [
        {
          "text": "bullet text exactly as written or lightly cleaned",
          "tags": ["list of tags from vocabulary"]
        }
      ]
    }
  ],
  "projects": [
    {
      "name": "project name",
      "url": "github or demo URL or empty",
      "tags": ["list of tags"],
      "bullets": [{ "text": "...", "tags": [...] }]
    }
  ],
  "skills": {
    "Category Name": ["skill1", "skill2"]
  },
  "education": [
    {
      "degree": "degree name",
      "institution": "school name",
      "dates": "date range or graduation year",
      "location": "city, country or empty",
      "details": ["thesis title, GPA, awards etc."]
    }
  ],
  "achievements": [
    { "text": "achievement text", "tags": ["list of tags"] }
  ]
}
"""

TAG_VOCABULARY = """
Technical track tags: ml, python, statistics, modeling, pipeline, hpc, algorithms, deep-learning,
nlp, sql, data-engineering, software-engineering, api, docker, cloud, pytorch, scikit-learn,
xgboost, lightgbm, shap, explainability, r, production, open-source

Leadership track tags: leadership, mentoring, stakeholder-management, cross-functional,
program-management, communication, strategy, hiring, project-management, roadmap,
executive-reporting, team-size, budget

Domain expert track tags: bioinformatics, genomics, proteomics, drug-discovery, cheminformatics,
molecular-dynamics, structural-biology, publications, research, clinical-data, ngs, multi-omics,
biomarker, qsar, scientific-communication, patent, collaboration, peer-reviewed
"""

SYSTEM_PROMPT = f"""You are an expert resume parser. You extract structured data from resume text
and output valid JSON matching the MasterResume schema exactly.

Rules:
- Do NOT fabricate skills, roles, dates, or accomplishments not present in the source text.
- Use exact job titles as written — do not rename or simplify them.
- Apply tags from the vocabulary below based on what each bullet/experience actually demonstrates.
  A bullet can have multiple tags across tracks. Tag generously but accurately.
- If multiple resumes are provided, merge experiences by deduplicating the same role at the same org.
  Combine their bullets, keeping all unique ones.
- Normalize dates to a readable range like "Jan 2021 – Mar 2023".
- For skills, group by category (Languages, ML / AI, Bioinformatics, Cloud / Infra, etc.).
- Output ONLY the JSON object. No markdown fences, no commentary.

Schema:
{SCHEMA_DESCRIPTION}

Tag vocabulary:
{TAG_VOCABULARY}
"""


def extract_text_from_file(filename: str, content: bytes) -> str:
    """Extract plain text from a PDF, DOCX, or text file."""
    ext = filename.lower().rsplit(".", 1)[-1]

    if ext == "pdf":
        if not _PDF_OK:
            raise ImportError("pdfplumber not installed. Run: uv add pdfplumber")
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
        return "\n".join(pages)

    if ext in ("docx", "doc"):
        if not _DOCX_OK:
            raise ImportError("python-docx not installed.")
        doc = DocxDocument(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    # Treat everything else as plain text
    return content.decode("utf-8", errors="replace")


def _build_user_message(resume_texts: list[tuple[str, str]]) -> str:
    """Build the user message containing all resume texts."""
    if len(resume_texts) == 1:
        filename, text = resume_texts[0]
        return f"Resume ({filename}):\n\n{text}"

    parts = []
    for i, (filename, text) in enumerate(resume_texts, 1):
        parts.append(f"=== Resume {i}: {filename} ===\n{text}")
    return (
        "I'm providing multiple resume versions for the same person. "
        "Merge them into one master resume JSON.\n\n"
        + "\n\n".join(parts)
    )


def convert_resumes_to_json(
    resume_texts: list[tuple[str, str]],
    api_key: str | None = None,
    model: str = "gpt-4o",
) -> dict:
    """
    Send resume text(s) to OpenAI and get back a MasterResume-compatible dict.
    resume_texts: list of (filename, extracted_text) tuples.
    Returns parsed dict (not yet validated against Pydantic).
    """
    client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        temperature=0.1,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(resume_texts)},
        ],
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)
