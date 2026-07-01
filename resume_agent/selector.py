"""
Core selection logic: given a master resume + job description + track,
return a tailored set of experiences, bullets, projects, and skills.

No LLM required — pure tag-based scoring. Optional Claude enhancement
for bullet rewriting can be layered on top.
"""
from __future__ import annotations
import re
from collections import Counter
from .schema import MasterResume, Experience, Project, Track, TRACK_CONFIG


def _extract_keywords(text: str) -> set[str]:
    """Rough keyword extraction from JD text."""
    text = text.lower()
    stopwords = {
        "and", "or", "the", "a", "an", "to", "of", "in", "for", "with",
        "on", "at", "by", "we", "you", "our", "your", "will", "be", "is",
        "are", "have", "has", "that", "this", "as", "from", "experience",
        "ability", "skills", "work", "team", "role", "position", "job",
    }
    words = re.findall(r"[a-z][a-z0-9\-\_]+", text)
    return {w for w in words if w not in stopwords and len(w) > 2}


def _score_tags(item_tags: list[str], jd_keywords: set[str],
                track: str) -> float:
    cfg = TRACK_CONFIG[track]
    priority = set(cfg["priority_tags"])
    boost = set(cfg["boost_tags"])
    depriority = set(cfg["depriority_tags"])

    score = 0.0
    tags = set(t.lower() for t in item_tags)

    # JD keyword overlap
    score += len(tags & jd_keywords) * 2.0
    # Track priority match
    score += len(tags & priority) * 1.5
    # Track boost
    score += len(tags & boost) * 1.0
    # Depriority penalty
    score -= len(tags & depriority) * 1.0

    return score


def select_experiences(
    resume: MasterResume,
    jd_text: str,
    track: Track,
    max_experiences: int = 4,
    max_bullets_per_exp: int = 4,
    always_include_orgs: list[str] | None = None,
) -> list[dict]:
    """
    Score and select experiences and bullets.
    Returns list of dicts ready for CV generation.
    """
    jd_keywords = _extract_keywords(jd_text)
    always_include_orgs = [o.lower() for o in (always_include_orgs or [])]

    scored = []
    for exp in resume.experiences:
        exp_score = _score_tags(exp.tags, jd_keywords, track)

        # Score and select top bullets
        bullet_scores = [
            (_score_tags(b.tags, jd_keywords, track), b)
            for b in exp.bullets
        ]
        bullet_scores.sort(key=lambda x: x[0], reverse=True)
        top_bullets = [b for _, b in bullet_scores[:max_bullets_per_exp]]

        forced = any(org in exp.org.lower() for org in always_include_orgs)
        scored.append((exp_score, forced, exp, top_bullets))

    # Sort: forced first, then by score descending
    scored.sort(key=lambda x: (not x[1], -x[0]))

    selected = []
    for _, _, exp, bullets in scored[:max_experiences]:
        selected.append({
            "role": exp.role,
            "org": exp.org,
            "dates": exp.dates,
            "bullets": [{"text": b.text} for b in bullets],
        })
    return selected


def select_projects(
    resume: MasterResume,
    jd_text: str,
    track: Track,
    max_projects: int = 3,
) -> list[dict]:
    jd_keywords = _extract_keywords(jd_text)
    scored = [
        (_score_tags(p.tags, jd_keywords, track), p)
        for p in resume.projects
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    result = []
    for _, proj in scored[:max_projects]:
        result.append({
            "name": proj.name,
            "url": proj.url,
            "bullets": [{"text": b.text} for b in proj.bullets],
        })
    return result


def select_skills(
    resume: MasterResume,
    track: Track,
) -> dict[str, list[str]]:
    """Return skills dict, reordered so track-relevant categories come first."""
    cfg = TRACK_CONFIG[track]
    priority_terms = set(cfg["priority_tags"])

    def category_score(cat: str) -> float:
        return sum(1 for term in priority_terms if term in cat.lower())

    categories = list(resume.skills.items())
    categories.sort(key=lambda x: category_score(x[0]), reverse=True)
    return dict(categories)


def build_cv_data(
    resume: MasterResume,
    jd_text: str,
    track: Track,
    max_experiences: int = 4,
    max_bullets: int = 4,
    max_projects: int = 3,
    always_include_orgs: list[str] | None = None,
) -> dict:
    """Return all data needed to generate a CV."""
    return {
        "contact": resume.contact.model_dump(),
        "experiences": select_experiences(
            resume, jd_text, track, max_experiences, max_bullets, always_include_orgs
        ),
        "projects": select_projects(resume, jd_text, track, max_projects),
        "skills": select_skills(resume, track),
        "achievements": [{"text": a.text} for a in resume.achievements],
        "education": [e.model_dump() for e in resume.education],
    }
