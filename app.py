"""
Prism — tailor your resume to a specific job posting.
Give it your resume + the job; it selects, rewrites, and surfaces the
transferable skills that fit, then produces a tailored Word doc.
Run: streamlit run app.py
"""
import copy
import json
import os
import tempfile

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

# On Streamlit Community Cloud, config lives in the Secrets panel (st.secrets).
# Mirror it into the environment so os.getenv(...) works the same way across
# local (.env), Railway (dashboard vars), and Streamlit Cloud (secrets).
try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except Exception:
    pass
from pydantic import ValidationError

from resume_agent import (
    MasterResume, TRACK_CONFIG,
    build_docx,
    extract_text_from_file, convert_resumes_to_json,
    parse_jd, fetch_jd_from_url, score_and_select,
    apply_revision, apply_project_revision,
    polish_experiences, apply_polish_revision,
    finalize_experiences, generate_summary,
)
from resume_agent.freetier import (
    free_key, free_available, free_status, record_free_use, per_session_limit,
)

st.set_page_config(page_title="Prism", page_icon="🔮", layout="wide")

# ── Prismatic theme: CSS + gradient hero ──────────────────────────────────────
_PRISM_SVG = """<svg width="58" height="58" viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
<line x1="2" y1="66" x2="44" y2="58" stroke="#F5F7FF" stroke-width="3" stroke-linecap="round"/>
<line x1="74" y1="56" x2="118" y2="30" stroke="#FF4D4D" stroke-width="2.6" stroke-linecap="round"/>
<line x1="74" y1="59" x2="118" y2="44" stroke="#FFB84D" stroke-width="2.6" stroke-linecap="round"/>
<line x1="74" y1="62" x2="118" y2="58" stroke="#FFE84D" stroke-width="2.6" stroke-linecap="round"/>
<line x1="74" y1="65" x2="118" y2="72" stroke="#4DFF88" stroke-width="2.6" stroke-linecap="round"/>
<line x1="74" y1="68" x2="118" y2="86" stroke="#4DD2FF" stroke-width="2.6" stroke-linecap="round"/>
<line x1="74" y1="71" x2="118" y2="100" stroke="#B84DFF" stroke-width="2.6" stroke-linecap="round"/>
<path d="M60 26 L88 84 L32 84 Z" fill="url(#pg)" fill-opacity="0.28" stroke="#CFD6FF" stroke-width="2.6" stroke-linejoin="round"/>
<defs><linearGradient id="pg" x1="32" y1="26" x2="88" y2="84" gradientUnits="userSpaceOnUse">
<stop stop-color="#8B5CF6"/><stop offset="0.5" stop-color="#22D3EE"/><stop offset="1" stop-color="#EC4899"/>
</linearGradient></defs></svg>"""

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500&display=swap');
html, body, [class*="css"] { font-family:'Inter',sans-serif; }
.stApp { background: radial-gradient(1100px 550px at 18% -12%, #1b2145 0%, #0E1117 58%); }
.prism-hero { display:flex; align-items:center; gap:16px; margin:4px 0 2px; }
.prism-title { font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:46px;
  letter-spacing:3px; margin:0; line-height:1;
  background:linear-gradient(90deg,#8B5CF6,#22D3EE,#EC4899);
  -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent;
  filter:drop-shadow(0 0 14px rgba(139,92,246,0.35)); }
.prism-tag { color:#AAB1C4; font-size:15px; max-width:720px; margin:2px 0 6px; line-height:1.5; }
h2, h3 { font-family:'Space Grotesk',sans-serif; letter-spacing:.3px; }
hr { border:none; height:2px; opacity:.55;
  background:linear-gradient(90deg,#8B5CF6,#22D3EE,#EC4899); }
.stButton>button[kind="primary"] { border:0; font-weight:600; color:#fff;
  background:linear-gradient(90deg,#7C3AED,#DB2777);
  box-shadow:0 0 18px rgba(124,58,237,0.45); transition:box-shadow .2s ease; }
.stButton>button[kind="primary"]:hover { box-shadow:0 0 28px rgba(219,39,119,0.6); }
[data-testid="stSidebar"] { background:#12151F; border-right:1px solid #232838; }
/* input step cards */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background:rgba(20,24,36,0.55); border:1px solid #262C3D !important;
  border-radius:16px; }
.step { font-family:'Space Grotesk',sans-serif; font-size:19px; font-weight:600;
  display:flex; align-items:center; gap:11px; margin:2px 0 12px; color:#EEF1F8; }
.step-num { display:inline-flex; width:27px; height:27px; border-radius:50%;
  align-items:center; justify-content:center; font-size:14px; font-weight:700; color:#fff;
  background:linear-gradient(135deg,#7C3AED,#22D3EE);
  box-shadow:0 0 12px rgba(124,58,237,0.5); }
/* uploader dropzone */
[data-testid="stFileUploaderDropzone"] { background:rgba(139,92,246,0.06);
  border:1px dashed #3A4560; }
</style>""", unsafe_allow_html=True)

st.markdown(
    f'<div class="prism-hero">{_PRISM_SVG}<div class="prism-title">PRISM</div></div>'
    '<div class="prism-tag">Upload your resume and the job you\'re applying for. '
    'Prism tailors your experience to fit the role, surfacing the transferable skills that match.</div>',
    unsafe_allow_html=True,
)

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
    # Pre-fill the field from OPENAI_API_KEY ONLY in local dev (explicit opt-in).
    # On the server this stays empty, so a stray OPENAI_API_KEY can never become
    # an uncapped shared key. The only server-funded key is PRISM_FREE_KEY (capped).
    _default_key = os.getenv("OPENAI_API_KEY", "") if os.getenv("PRISM_ALLOW_ENV_KEY") == "1" else ""
    user_key = st.text_input("OpenAI API key", type="password",
                             value=_default_key,
                             placeholder="sk-proj-...",
                             help="Required for JD parsing, scoring, and bullet polishing.")

    # Resolve the effective key: the visitor's own key takes priority; otherwise
    # fall back to the owner-funded free tier. Free use requires BOTH the global
    # daily cap to have room AND this session's per-visitor allowance to remain.
    sess_limit = per_session_limit()
    sess_used = st.session_state.get("free_runs_used", 0)
    sess_left = max(0, sess_limit - sess_used)
    using_free = False

    if user_key:
        api_key = user_key
    elif free_available() and sess_left > 0:
        api_key = free_key()
        using_free = True
    else:
        api_key = ""

    if user_key:
        st.caption("🔑 Using your own key — never stored or logged.")
    elif using_free:
        st.success(f"✨ Free trial — {sess_left} of {sess_limit} runs left. "
                   "No key needed. Add your own key above for unlimited use.")
    elif free_key() and sess_left == 0:  # this visitor used their session allowance
        st.warning("You've used your free runs. Add your own OpenAI key above to continue. "
                   "Get one at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).")
    elif free_key():  # free tier exists but the global daily cap is exhausted
        st.warning("Free runs for today are used up. Add your own OpenAI key above to continue. "
                   "Get one at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).")
    else:
        st.caption("🔑 Prism runs on your own OpenAI key — it's never stored or logged. "
                   "Get one at [platform.openai.com/api-keys](https://platform.openai.com/api-keys). "
                   "A full CV costs roughly $0.05–0.15 in API usage.")
    st.divider()

    # Advanced: reuse a previously built master_resume.json instead of re-uploading
    # a resume. Optional — most users just upload their resume on the main screen.
    with st.expander("Advanced: reuse a saved master_resume.json"):
        uploaded_json = st.file_uploader("Upload master_resume.json", type=["json"])
        if uploaded_json:
            try:
                raw = json.loads(uploaded_json.read())
                st.session_state["resume"] = MasterResume.model_validate(raw)
                st.success("Loaded. Add a job description on the main screen.")
            except (json.JSONDecodeError, ValidationError) as e:
                st.error(f"Invalid JSON: {e}")
        with open("templates/master_resume_template.json") as f:
            st.download_button("Download blank template", f.read(),
                               "master_resume_template.json",
                               mime="application/json", use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE: landing — collect BOTH inputs (resume + job description), then run
# ═══════════════════════════════════════════════════════════════════════════════
if get_stage() == "load":
    saved_resume = st.session_state.get("resume")

    col_a, col_b = st.columns(2, gap="large")

    # ---- Input 1: the resume ----
    with col_a:
        with st.container(border=True):
            st.markdown('<div class="step"><span class="step-num">1</span>Your résumé</div>',
                        unsafe_allow_html=True)
            if saved_resume:
                st.success(f"Using your saved résumé — {len(saved_resume.experiences)} experiences.")
                if st.button("Upload a different résumé"):
                    st.session_state.pop("resume", None)
                    st.rerun()
                files = None
            else:
                files = st.file_uploader("Drop your résumé here — PDF, Word, or text.",
                                         type=["pdf", "docx", "txt"],
                                         accept_multiple_files=True)
                if files and len(files) > 3:
                    st.warning("Using the first 3 files.")
                    files = files[:3]
                if files:
                    st.caption("Loaded: " + ", ".join(f.name for f in files))
                else:
                    st.caption("Tip: add 1–3 versions covering different roles for a richer match.")

    # ---- Input 2: the job description (REQUIRED) ----
    with col_b:
        with st.container(border=True):
            st.markdown('<div class="step"><span class="step-num">2</span>The job you\'re applying for</div>',
                        unsafe_allow_html=True)
            jd_url = st.text_input("Job posting URL",
                                   placeholder="https://company.com/careers/the-role")
            jd_text = st.text_area("...or paste the job description", height=150,
                                   placeholder="Paste the full job posting text...")

    # ---- Role type + action ----
    with st.container(border=True):
        st.markdown('<div class="step"><span class="step-num">3</span>What kind of role is this?</div>',
                    unsafe_allow_html=True)
        track = st.radio(
            "Role type", list(TRACK_CONFIG.keys()),
            format_func=lambda k: TRACK_CONFIG[k]["label"],
            horizontal=True, label_visibility="collapsed",
        )

        has_resume = bool(saved_resume) or bool(files)
        has_jd = bool(jd_url.strip()) or bool(jd_text.strip())

        st.write("")
        bcol, hcol = st.columns([1, 2])
        with bcol:
            go = st.button("Generate tailored CV →", type="primary",
                           use_container_width=True,
                           disabled=not (has_resume and has_jd and api_key))
        with hcol:
            if not api_key:
                st.caption("→ Add an API key in the sidebar (or use the free trial).")
            elif not has_resume:
                st.caption("→ Upload your résumé to continue.")
            elif not has_jd:
                st.caption("→ Add the job — paste a URL or the text.")

    if go:
        # Count one free run against caps (this triggers the bulk of API spend).
        if using_free:
            record_free_use()
            st.session_state["free_runs_used"] = sess_used + 1

        st.session_state["track"] = track

        # 1. Resume → structured MasterResume (skip if we already have one)
        resume = saved_resume
        if resume is None:
            texts = []
            with st.spinner("Reading your resume..."):
                for f in files:
                    try:
                        texts.append((f.name, extract_text_from_file(f.name, f.read())))
                    except Exception as e:
                        st.error(f"Could not read {f.name}: {e}")
            if not texts:
                st.stop()
            with st.spinner("Understanding your experience..."):
                try:
                    raw_dict = convert_resumes_to_json(texts, api_key=api_key)
                    resume = MasterResume.model_validate(raw_dict)
                    st.session_state["resume"] = resume
                    st.session_state["resume_json"] = json.dumps(raw_dict, indent=2)
                except Exception as e:
                    st.error(f"Could not parse your resume: {e}")
                    st.stop()

        # 2. Job description → text (fetch URL if given)
        with st.spinner("Reading the job posting..."):
            jd = jd_text.strip()
            if jd_url.strip():
                try:
                    jd = fetch_jd_from_url(jd_url.strip())
                except Exception as e:
                    st.error(f"Could not fetch that URL ({e}). Paste the text instead.")
                    st.stop()
            if not jd:
                st.error("The job description came back empty. Paste the text instead.")
                st.stop()

        # 3. Parse JD + score/select against the resume
        with st.spinner("Analysing the job and matching your experience..."):
            try:
                parsed_jd = parse_jd(jd, api_key=api_key)
                st.session_state["parsed_jd"] = parsed_jd
                sel = score_and_select(resume, parsed_jd, track=track, api_key=api_key)
                st.session_state["selection"] = sel
                set_stage("review_selection")
                st.rerun()
            except Exception as e:
                st.error(f"Analysis failed: {e}")
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

    dcol1, dcol2 = st.columns(2)

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
        st.caption("Editable Word doc. Export to PDF from Word/Pages/Google Docs if you need one.")

    with dcol2:
        if st.button("Start over", use_container_width=True):
            reset_pipeline()
            st.rerun()
