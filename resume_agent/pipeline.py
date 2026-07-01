"""
Core pipeline: JD parsing → bullet scoring → polishing → summary generation.
Uses OpenAI (GPT-4o / GPT-4o-mini). Reads OPENAI_API_KEY from environment or .env.
Each stage returns plain dicts so the UI (Streamlit or CLI) can orchestrate.
"""
from __future__ import annotations
import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from .prompts import (
    PARSE_JD_SYSTEM, PARSE_JD_USER,
    RELEVANCE_SCORE_SYSTEM, RELEVANCE_SCORE_USER,
    POLISH_SYSTEM, POLISH_USER,
    POLISH_REVISE_SYSTEM, POLISH_REVISE_USER,
    SUMMARY_SYSTEM, SUMMARY_USER,
    REVISION_PARSE_USER, POLISH_REVISION_PARSE_USER,
)
from .schema import MasterResume

load_dotenv()

# Model routing: complex reasoning → GPT-4o, high-volume scoring → GPT-4o-mini
_GPT4O      = "gpt-4o"
_GPT4O_MINI = "gpt-4o-mini"

MIN_ROLES           = 2
MIN_BULLETS_ALWAYS  = 2
MAX_BULLETS         = 5
ROLE_THRESHOLD      = 0.30   # aggregate score below this → role is de-emphasised
ACHIEVEMENT_THRESH  = 0.40
PROJECT_THRESH      = 0.40
TAG_WEIGHT          = 0.15
LLM_WEIGHT          = 0.85


def _client(api_key: str | None = None) -> OpenAI:
    return OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))


def _chat(client: OpenAI, model: str, system: str, user: str, max_tokens: int) -> str:
    resp = client.chat.completions.create(
        model=model, max_tokens=max_tokens, temperature=0.1,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return resp.choices[0].message.content.strip()


def _strip_fences(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    return re.sub(r"\s*```$", "", text)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


# ── Stage 1: Parse JD ─────────────────────────────────────────────────────────

def parse_jd(jd_text: str, api_key: str | None = None) -> dict:
    """Extract role, company, requirements, tags from raw JD text."""
    c = _client(api_key)
    raw = _chat(c, _GPT4O, PARSE_JD_SYSTEM, PARSE_JD_USER.format(jd_text=jd_text[:8000]), 1024)
    parsed = json.loads(_strip_fences(raw))
    parsed["jd_text"] = jd_text
    return parsed


# ── Stage 2: Score and select ─────────────────────────────────────────────────

def _llm_score(bullet_text: str, requirements: list[str], api_key: str | None) -> float:
    req_summary = "; ".join(requirements[:12])
    c = _client(api_key)
    try:
        raw = _chat(c, _GPT4O_MINI, RELEVANCE_SCORE_SYSTEM,
                    RELEVANCE_SCORE_USER.format(requirements=req_summary, bullet=bullet_text), 8)
        score = int(re.search(r"\d+", raw).group())
        return min(score, 10) / 10.0
    except Exception:
        return 0.0


def _score_bullets(bullets: list[dict], jd_tags: set, requirements: list[str],
                   api_key: str | None) -> list[dict]:
    scored = []
    for b in bullets:
        tag_score = _jaccard(set(b.get("tags", [])), jd_tags)
        llm = _llm_score(b["text"], requirements, api_key)
        final = TAG_WEIGHT * tag_score + LLM_WEIGHT * llm
        scored.append({**b, "_score": final, "_tag_score": tag_score, "_llm_score": llm})
    return scored


def score_and_select(
    resume: MasterResume,
    parsed_jd: dict,
    api_key: str | None = None,
) -> dict:
    """
    Score every experience, bullet, achievement, and project against the JD.
    Returns: { included, dropped, achievements, projects, skills, all_scored_roles, all_projects_scored }
    all_scored_roles and all_projects_scored are kept so the UI can restore dropped items.
    """
    requirements = parsed_jd.get("key_requirements", []) + parsed_jd.get("preferred_skills", [])
    jd_tags: set[str] = set()
    for t in parsed_jd.get("tags", []):
        jd_tags |= _tokenize(t)
    for r in requirements:
        jd_tags |= _tokenize(r)

    included, dropped, all_scored = [], [], []

    for exp in resume.experiences:
        exp_dict = exp.model_dump()
        scored_bullets = _score_bullets(exp_dict.get("bullets", []), jd_tags, requirements, api_key)
        scored_bullets.sort(key=lambda b: b["_score"], reverse=True)

        always_keep = scored_bullets[:MIN_BULLETS_ALWAYS]
        extra = [b for b in scored_bullets[MIN_BULLETS_ALWAYS:] if b["_llm_score"] >= 0.50]
        selected = (always_keep + extra)[:MAX_BULLETS]
        if not selected:
            continue

        agg = sum(b["_score"] for b in selected) / len(selected)
        entry = {
            "role": exp.role, "org": exp.org, "dates": exp.dates,
            "bullets": [{"text": b["text"], "tags": b.get("tags", [])} for b in selected],
            "_agg_score": agg, "_note": "",
        }
        all_scored.append(entry)

        if agg >= ROLE_THRESHOLD:
            included.append(entry)
        else:
            dropped.append({
                "role": exp.role, "org": exp.org,
                "reason": f"low relevance ({agg:.2f})",
                "_agg_score": agg, "_entry": entry,
            })

    # Guarantee minimum roles
    if len(included) < MIN_ROLES:
        dropped.sort(key=lambda r: r.get("_agg_score", 0), reverse=True)
        while len(included) < MIN_ROLES and dropped:
            best = dropped.pop(0)
            entry = best.pop("_entry", None)
            best.pop("_agg_score", None)
            if entry:
                entry["_note"] = "(included to meet minimum)"
                included.append(entry)

    for r in dropped:
        r.pop("_entry", None)
        r.pop("_agg_score", None)

    included.sort(key=lambda r: r["_agg_score"], reverse=True)

    # Score achievements
    all_ach = [a.model_dump() for a in resume.achievements]
    scored_ach = _score_bullets(all_ach, jd_tags, requirements, api_key)
    scored_ach.sort(key=lambda a: a["_score"], reverse=True)
    achievements = [
        {"text": a["text"], "tags": a.get("tags", [])}
        for a in scored_ach if a["_llm_score"] >= ACHIEVEMENT_THRESH
    ][:3]

    # Score projects
    all_proj_scored = []
    for proj in resume.projects:
        pd = proj.model_dump()
        tag_score = _jaccard(set(pd.get("tags", [])), jd_tags)
        rep_text = pd["bullets"][0]["text"] if pd.get("bullets") else pd.get("name", "")
        llm = _llm_score(rep_text, requirements, api_key)
        final = TAG_WEIGHT * tag_score + LLM_WEIGHT * llm
        all_proj_scored.append({**pd, "_score": final, "_llm": llm})
    all_proj_scored.sort(key=lambda p: p["_score"], reverse=True)
    projects = [
        {"name": p["name"], "url": p.get("url", ""), "bullets": p["bullets"]}
        for p in all_proj_scored if p["_llm"] >= PROJECT_THRESH
    ][:3]

    # Reorder skills by JD token overlap
    raw_skills = resume.skills
    skill_scores = {}
    for cat, items in raw_skills.items():
        tokens: set = set()
        for item in items:
            tokens |= _tokenize(str(item))
        skill_scores[cat] = len(tokens & jd_tags)
    ordered_skills = dict(sorted(raw_skills.items(), key=lambda kv: skill_scores.get(kv[0], 0), reverse=True))

    return {
        "included": included,
        "dropped": dropped,
        "achievements": achievements,
        "projects": projects,
        "skills": ordered_skills,
        "all_scored_roles": all_scored,
        "all_projects_scored": all_proj_scored,
    }


# ── Revision helpers (used by UI after score_and_select) ─────────────────────

def apply_revision(
    instruction: str,
    included: list[dict],
    dropped: list[dict],
    resume: MasterResume,
    api_key: str | None = None,
) -> tuple[list[dict], list[dict], str]:
    """Apply a plain-English revision instruction. Returns (included, dropped, feedback_msg)."""
    import json
    included_labels = json.dumps([f"{r['role']} | {r['org']}" for r in included], indent=2)
    dropped_labels  = json.dumps([f"{r['role']} | {r['org']}" for r in dropped], indent=2)

    c = _client(api_key)
    try:
        raw = _chat(c, _GPT4O_MINI, "You parse resume revision instructions. Return only JSON.",
                    REVISION_PARSE_USER.format(
                        included_labels=included_labels,
                        dropped_labels=dropped_labels,
                        instruction=instruction,
                    ), 300)
        actions = json.loads(_strip_fences(raw))
    except Exception as e:
        return included, dropped, f"Could not parse instruction: {e}"

    feedback = []
    for action in actions:
        match = action.get("match", "").lower()
        atype = action.get("type")

        if atype == "drop_role":
            to_drop = [r for r in included if match in r["role"].lower() or match in r["org"].lower()]
            for r in to_drop:
                included.remove(r)
                dropped.append({"role": r["role"], "org": r["org"], "reason": "manually dropped"})
                feedback.append(f"Dropped: {r['role']} | {r['org']}")

        elif atype == "keep_role":
            to_keep = [r for r in dropped if match in r["role"].lower() or match in r["org"].lower()]
            for r in to_keep:
                dropped.remove(r)
                orig = next((e for e in resume.experiences if e.org == r["org"]), None)
                if orig:
                    included.append({
                        "role": orig.role, "org": orig.org, "dates": orig.dates,
                        "bullets": [{"text": b.text, "tags": b.tags} for b in orig.bullets],
                        "_agg_score": 0.0, "_note": "(manually included)",
                    })
                    feedback.append(f"Restored: {orig.role} | {orig.org}")

        elif atype == "drop_bullet":
            bullet_match = action.get("bullet_match", "").lower()
            for r in included:
                if match in r["role"].lower() or match in r["org"].lower():
                    before = len(r["bullets"])
                    r["bullets"] = [b for b in r["bullets"] if bullet_match not in b["text"].lower()]
                    removed = before - len(r["bullets"])
                    if removed:
                        feedback.append(f"Removed {removed} bullet(s) from {r['org']}")

    return included, dropped, " | ".join(feedback) if feedback else "No matching roles found."


def apply_project_revision(
    instruction: str,
    selected: list[dict],
    all_scored: list[dict],
) -> tuple[list[dict], str]:
    """Add or drop a project by keyword. Returns (selected, feedback_msg)."""
    lowered = instruction.lower()
    selected_names = {p["name"].lower() for p in selected}

    if any(w in lowered for w in ("add", "include", "keep")):
        keyword = re.sub(r"\b(add|include|keep|project)\b", "", lowered).strip()
        for p in all_scored:
            if keyword and keyword in p["name"].lower() and p["name"].lower() not in selected_names:
                selected.append({"name": p["name"], "url": p.get("url", ""), "bullets": p["bullets"]})
                return selected, f"Added project: {p['name']}"
        return selected, f"No unselected project matching '{keyword}' found."

    elif any(w in lowered for w in ("drop", "remove")):
        keyword = re.sub(r"\b(drop|remove|project)\b", "", lowered).strip()
        before = len(selected)
        selected = [p for p in selected if keyword not in p["name"].lower()]
        if len(selected) < before:
            return selected, f"Dropped project matching '{keyword}'."
        return selected, f"No selected project matching '{keyword}' found."

    return selected, "Unrecognised instruction."


# ── Stage 3: Polish bullets ───────────────────────────────────────────────────

def polish_experiences(
    experiences: list[dict],
    parsed_jd: dict,
    api_key: str | None = None,
) -> list[dict]:
    """
    Rewrite bullets in-place to match JD language. Stores originals in b["original"].
    Returns the updated experiences list.
    """
    requirements = (
        parsed_jd.get("key_requirements", []) + parsed_jd.get("preferred_skills", [])
    )[:12]
    c = _client(api_key)

    for exp in experiences:
        if not exp.get("bullets"):
            continue
        bullets = [b["text"] for b in exp["bullets"]]
        prompt = POLISH_USER.format(
            requirements="; ".join(requirements),
            n=len(bullets),
            role=exp["role"],
            org=exp["org"],
            bullets_json=json.dumps(bullets, indent=2),
        )
        try:
            raw = _chat(c, _GPT4O, POLISH_SYSTEM, prompt, 1200)
            rewritten = json.loads(_strip_fences(raw))
            if len(rewritten) != len(bullets):
                continue
            for i, b in enumerate(exp["bullets"]):
                b["original"] = b["text"]
                b["text"] = rewritten[i]
        except Exception:
            pass

    return experiences


def apply_polish_revision(
    instruction: str,
    experiences: list[dict],
    parsed_jd: dict,
    api_key: str | None = None,
) -> tuple[list[dict], str]:
    """Targeted rewrite or revert of a single bullet."""
    index = [
        {"org": exp["org"], "bullet_index": i, "text_preview": b["text"][:80]}
        for exp in experiences for i, b in enumerate(exp["bullets"])
    ]
    c = _client(api_key)
    try:
        raw = _chat(c, _GPT4O_MINI, "You parse resume revision instructions. Return only JSON.",
                    POLISH_REVISION_PARSE_USER.format(
                        index_json=json.dumps(index, indent=2), instruction=instruction
                    ), 150)
        action = json.loads(_strip_fences(raw))
    except Exception as e:
        return experiences, f"Could not parse instruction: {e}"

    org_match   = action.get("org_match", "").lower()
    bullet_idx  = action.get("bullet_index", 0)
    act         = action.get("action", "")
    requirements = (parsed_jd.get("key_requirements", []) + parsed_jd.get("preferred_skills", []))[:12]

    for exp in experiences:
        if org_match not in exp["org"].lower():
            continue
        bullets = exp["bullets"]
        if bullet_idx >= len(bullets):
            return experiences, f"Bullet index {bullet_idx} out of range."
        b = bullets[bullet_idx]

        if act == "revert":
            if "original" in b:
                b["text"] = b["original"]
                return experiences, f"Reverted {exp['org']} bullet {bullet_idx + 1}."
            return experiences, "No original stored for that bullet."

        elif act == "rewrite":
            rewrite_prompt = POLISH_REVISE_USER.format(
                original=b.get("original", b["text"]),
                current=b["text"],
                instruction=action.get("rewrite_instruction", instruction),
            )
            try:
                b["text"] = _chat(c, _GPT4O, POLISH_REVISE_SYSTEM, rewrite_prompt, 200).strip('"')
                return experiences, f"Rewrote {exp['org']} bullet {bullet_idx + 1}."
            except Exception as e:
                return experiences, f"Rewrite failed: {e}"

    return experiences, "No matching org found."


def finalize_experiences(experiences: list[dict]) -> list[dict]:
    """Strip internal keys (_agg_score, _note, original) before CV generation."""
    for exp in experiences:
        exp.pop("_agg_score", None)
        exp.pop("_note", None)
        for b in exp.get("bullets", []):
            b.pop("original", None)
    return experiences


# ── Stage 4: Summary generation ───────────────────────────────────────────────

def generate_summary(parsed_jd: dict, experiences: list[dict], api_key: str | None = None) -> str:
    requirements = (
        parsed_jd.get("key_requirements", []) + parsed_jd.get("preferred_skills", [])
    )[:10]
    exp_summary = "\n".join(
        f"- {e['role']} at {e['org']} ({e['dates']})" for e in experiences
    )
    c = _client(api_key)
    return _chat(c, _GPT4O, SUMMARY_SYSTEM, SUMMARY_USER.format(
        role_title=parsed_jd.get("role_title", ""),
        company=parsed_jd.get("company_name", ""),
        requirements="; ".join(requirements),
        experience_summary=exp_summary,
    ), 200)
