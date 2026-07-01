"""
Resume Agent — multi-track CV generator with full LLM pipeline.
Run: streamlit run app.py
"""
import copy
import json
import os
import tempfile

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
from pydantic import ValidationError

from resume_agent import (
    MasterResume, TRACK_CONFIG,
    build_docx, build_pdf_via_html,
    extract_text_from_file, convert_resumes_to_json,
    parse_jd, score_and_select,
    apply_revision, apply_project_revision,
    polish_experiences, apply_polish_revision,
    finalize_experiences, generate_summary,
)

st.set_page_config(page_title="Resume Agent", page_icon="📄", layout="wide")
st.title("Resume Agent")
st.caption("Multi-track CV generator for multi-domain professionals")

# ── Helpers ───────────────────────────────────────────────────────────────────

def reset_pipeline():
    for k in ["stage", "resume", "resume_json", "parsed_jd", "selection",
              "polished_exps", "final_summary"]:
        st.session_state.pop(k, None)


def get_stage():
    return st.session_state.get("stage", "load")


def set_stage(s):
    st.session_state["stage"] = s


# ── Sidebar: API key + resume load ───────────────────────────────────────────
with st.sidebar:
    api_key = st.text_input("OpenAI API key", type="password",
                            value=os.getenv("OPENAI_API_KEY", ""),
                            placeholder="sk-proj-...",
                            help="Required for JD parsing, scoring, and bullet polishing.")
    st.divider()

    mode = st.radio("Starting point", ["Convert existing resumes", "Upload master_resume.json"],
                    on_change=reset_pipeline)

    if mode == "Upload master_resume.json":
        uploaded_json = st.file_uploader("Upload JSON", type=["json"])
        if uploaded_json:
            try:
                raw = json.loads(uploaded_json.read())
                resume = MasterResume.model_validate(raw)
                if st.session_state.get("resume") is None:
                    st.session_state["resume"] = resume
                    set_stage("jd")
            except (json.JSONDecodeError, ValidationError) as e:
                st.error(f"Invalid JSON: {e}")

        with st.expander("Download blank template"):
            with open("templates/master_resume_template.json") as f:
                st.download_button("template", f.read(), "master_resume_template.json",
                                   mime="application/json", use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE: convert existing resumes
# ═══════════════════════════════════════════════════════════════════════════════
if mode == "Convert existing resumes" and get_stage() == "load":
    st.subheader("Upload your existing resumes (1–3 files)")
    st.markdown("PDF, Word (.docx), or plain text. The agent merges all versions into "
                "a single `master_resume.json` with every bullet tagged.")

    files = st.file_uploader("Resume files", type=["pdf", "docx", "txt"],
                             accept_multiple_files=True)
    if files and len(files) > 3:
        st.warning("Max 3 files.")
        files = files[:3]

    if st.button("Convert", type="primary", disabled=not (files and api_key)):
        texts = []
        for f in files:
            try:
                text = extract_text_from_file(f.name, f.read())
                texts.append((f.name, text))
                st.success(f"Read {f.name} ({len(text):,} chars)")
            except Exception as e:
                st.error(f"{f.name}: {e}")

        if texts:
            with st.spinner("Building master_resume.json..."):
                try:
                    raw_dict = convert_resumes_to_json(texts, api_key=api_key)
                    resume = MasterResume.model_validate(raw_dict)
                    st.session_state["resume"] = resume
                    st.session_state["resume_json"] = json.dumps(raw_dict, indent=2)
                    set_stage("review_json")
                    st.rerun()
                except Exception as e:
                    st.error(f"Conversion failed: {e}")

if get_stage() == "review_json":
    resume = st.session_state["resume"]
    raw_json = st.session_state["resume_json"]
    st.subheader(f"Resume built for {resume.contact.name}")
    st.markdown(f"{len(resume.experiences)} experiences · {len(resume.projects)} projects · "
                f"{len(resume.achievements)} achievements")

    with st.expander("Preview JSON"):
        st.code(raw_json, language="json")

    c1, c2 = st.columns(2)
    c1.download_button("Download master_resume.json", raw_json,
                       "master_resume.json", mime="application/json", use_container_width=True)
    if c2.button("Continue to CV generation →", type="primary", use_container_width=True):
        set_stage("jd")
        st.rerun()
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE: enter job description
# ═══════════════════════════════════════════════════════════════════════════════
if get_stage() == "jd":
    resume = st.session_state.get("resume")
    if not resume:
        st.info("Load your resume in the sidebar first.")
        st.stop()

    st.success(f"Resume loaded: **{resume.contact.name}** · "
               f"{len(resume.experiences)} experiences")

    st.subheader("Job Description")
    jd_text = st.text_area("Paste the full job posting", height=300,
                           placeholder="Copy the entire job description here...")

    if st.button("Analyse JD & score bullets", type="primary",
                 disabled=not (jd_text.strip() and api_key)):
        with st.spinner("Parsing JD..."):
            try:
                parsed_jd = parse_jd(jd_text, api_key=api_key)
                st.session_state["parsed_jd"] = parsed_jd
            except Exception as e:
                st.error(f"JD parsing failed: {e}")
                st.stop()

        with st.spinner(f"Scoring bullets against {parsed_jd.get('role_title', 'role')}..."):
            try:
                sel = score_and_select(resume, parsed_jd, api_key=api_key)
                st.session_state["selection"] = sel
                set_stage("review_selection")
                st.rerun()
            except Exception as e:
                st.error(f"Scoring failed: {e}")
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE: review selection (human-in-the-loop)
# ═══════════════════════════════════════════════════════════════════════════════
if get_stage() == "review_selection":
    resume    = st.session_state["resume"]
    parsed_jd = st.session_state["parsed_jd"]
    sel       = st.session_state["selection"]
    included  = sel["included"]
    dropped   = sel["dropped"]

    st.subheader(f"Selection for {parsed_jd.get('role_title')} at {parsed_jd.get('company_name')}")
    st.caption(f"Domain: {parsed_jd.get('domain')} · Seniority: {parsed_jd.get('seniority')}")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("**Included roles**")
        for r in included:
            score_str = f" (score: {r.get('_agg_score', 0):.2f})" if "_agg_score" in r else ""
            note = f" — {r['_note']}" if r.get("_note") else ""
            with st.expander(f"✅ {r['role']} | {r['org']}{score_str}{note}"):
                for b in r["bullets"]:
                    st.markdown(f"- {b['text']}")

        if dropped:
            st.markdown("**Dropped roles**")
            for r in dropped:
                st.markdown(f"- ❌ **{r['role']} | {r['org']}** — {r['reason']}")

        if sel.get("projects"):
            st.markdown("**Projects**")
            for p in sel["projects"]:
                st.markdown(f"- {p['name']}")

        if sel.get("achievements"):
            st.markdown("**Achievements**")
            for a in sel["achievements"]:
                st.markdown(f"- {a['text'][:100]}{'…' if len(a['text']) > 100 else ''}")

    with col2:
        st.markdown("**Revise selection**")
        st.caption("e.g. 'keep ProteinQure', 'drop postdoc', 'drop the COVID bullet from A*STAR'")
        rev_instruction = st.text_input("Instruction", key="rev_input",
                                        placeholder="keep X / drop Y / drop bullet from Z")
        if st.button("Apply revision", disabled=not rev_instruction):
            if "project" in rev_instruction.lower():
                new_projects, msg = apply_project_revision(
                    rev_instruction, sel["projects"], sel["all_projects_scored"])
                sel["projects"] = new_projects
                st.info(msg)
            else:
                new_inc, new_drop, msg = apply_revision(
                    rev_instruction, included, dropped, resume, api_key=api_key)
                sel["included"] = new_inc
                sel["dropped"] = new_drop
                st.info(msg)
            st.session_state["selection"] = sel
            st.rerun()

    st.divider()
    if st.button("Accept selection & polish bullets →", type="primary"):
        with st.spinner("Polishing bullets to match JD language..."):
            exps_copy = copy.deepcopy(sel["included"])
            polished = polish_experiences(exps_copy, parsed_jd, api_key=api_key)
            st.session_state["polished_exps"] = polished
            set_stage("review_polish")
            st.rerun()
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE: review polished bullets
# ═══════════════════════════════════════════════════════════════════════════════
if get_stage() == "review_polish":
    parsed_jd    = st.session_state["parsed_jd"]
    polished_exps = st.session_state["polished_exps"]

    st.subheader("Polished bullets — review before saving")
    st.caption("Each bullet shown as BEFORE → AFTER. Accept, revert, or give targeted instructions.")

    changed_any = False
    for exp in polished_exps:
        st.markdown(f"**{exp['role']} | {exp['org']}**")
        for i, b in enumerate(exp["bullets"]):
            if b.get("original") and b["original"] != b["text"]:
                changed_any = True
                with st.expander(f"[{i+1}] Changed"):
                    st.markdown(f"**Before:** {b['original']}")
                    st.markdown(f"**After:** {b['text']}")
            else:
                st.markdown(f"[{i+1}] {b['text']}")

    if not changed_any:
        st.info("No bullets were changed during polishing.")

    col1, col2 = st.columns([2, 1])
    with col2:
        st.markdown("**Targeted revision**")
        st.caption("e.g. 'rewrite SickKids bullet 2 to be more concise', 'revert A*STAR bullet 1'")
        polish_instr = st.text_input("Instruction", key="polish_input",
                                     placeholder="rewrite X bullet N to...")
        if st.button("Apply", disabled=not polish_instr):
            updated, msg = apply_polish_revision(
                polish_instr, polished_exps, parsed_jd, api_key=api_key)
            st.session_state["polished_exps"] = updated
            st.info(msg)
            st.rerun()

        if st.button("Revert all to originals"):
            for exp in polished_exps:
                for b in exp["bullets"]:
                    if "original" in b:
                        b["text"] = b.pop("original")
            st.session_state["polished_exps"] = polished_exps
            st.rerun()

    st.divider()
    if st.button("Accept & generate CV →", type="primary"):
        set_stage("generate")
        st.rerun()
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE: generate CV
# ═══════════════════════════════════════════════════════════════════════════════
if get_stage() == "generate":
    resume        = st.session_state["resume"]
    parsed_jd     = st.session_state["parsed_jd"]
    sel           = st.session_state["selection"]
    polished_exps = st.session_state["polished_exps"]

    with st.spinner("Writing professional summary..."):
        clean_exps = finalize_experiences(copy.deepcopy(polished_exps))
        try:
            summary = generate_summary(parsed_jd, clean_exps, api_key=api_key)
            st.session_state["final_summary"] = summary
        except Exception:
            summary = ""

    cv_data = {
        "contact":      resume.contact.model_dump(),
        "summary":      summary,
        "experiences":  clean_exps,
        "projects":     sel.get("projects", []),
        "skills":       sel.get("skills", resume.skills),
        "achievements": sel.get("achievements", []),
        "education":    [e.model_dump() for e in resume.education],
    }

    st.subheader(f"CV ready: {parsed_jd.get('role_title')} at {parsed_jd.get('company_name')}")
    if summary:
        st.markdown(f"**Summary:** {summary}")

    with st.expander("Experiences"):
        for exp in clean_exps:
            st.markdown(f"**{exp['role']} | {exp['org']}**")
            for b in exp["bullets"]:
                st.markdown(f"- {b['text']}")

    st.divider()
    name_slug = resume.contact.name.replace(" ", "_")
    co_slug   = parsed_jd.get("company_name", "Company").replace(" ", "_")

    dcol1, dcol2, dcol3 = st.columns(3)

    with dcol1:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            dpath = tmp.name
        build_docx(cv_data, dpath)
        with open(dpath, "rb") as f:
            docx_bytes = f.read()
        os.unlink(dpath)
        st.download_button("Download .docx", docx_bytes,
                           f"CV_{name_slug}_{co_slug}.docx",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                           use_container_width=True)

    with dcol2:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            ppath = tmp.name
        result = build_pdf_via_html(cv_data, ppath)
        if result:
            with open(ppath, "rb") as f:
                pdf_bytes = f.read()
            os.unlink(ppath)
            st.download_button("Download .pdf", pdf_bytes,
                               f"CV_{name_slug}_{co_slug}.pdf",
                               mime="application/pdf", use_container_width=True)
        else:
            st.info("PDF needs Chrome installed.")

    with dcol3:
        if st.button("Start over", use_container_width=True):
            reset_pipeline()
            st.rerun()
