# Prism

**Tailor your resume to the job you're actually applying for.**

Give Prism your resume and a job posting. It reads the role, finds the experience of yours that fits, drops what doesn't, rewrites your bullets in the language the role uses, and surfaces the transferable skills that match — then hands you a tailored Word doc. Like light through a prism, one background is refocused for whatever role you're aiming at.

## The problem it solves

Most people send the same resume to every job, or hand-edit it for hours per application. Prism does the tailoring for you: you paste the job, it decides what of *your* experience is relevant to *this* role and how to phrase it.

The key distinction: **nothing is invented**. All content comes from your own experience. Prism selects, reorders, and rephrases to fit the job — but never fabricates skills or accomplishments you don't have.

## How it works

```
master_resume.json  +  job description URL / text
         │
         ▼
Stage 1  Parse JD           → extract role, company, requirements, domain (GPT-4o)
         │
         ▼
Stage 2  Score & select     → LLM scores every bullet 0–10 against JD requirements
         │                    (85% LLM judgment + 15% tag overlap via GPT-4o-mini)
         │                    Human review: accept / drop roles / drop bullets
         ▼
Stage 3  Polish bullets     → GPT-4o rewrites selected bullets to match JD language
         │                    Cross-domain rule: removes jargon the JD doesn't use,
         │                    replaces with the transferable concept it demonstrates
         │                    Human review: before/after diff, targeted revisions
         ▼
Stage 4  Generate CV        → professional summary (GPT-4o) + docx + PDF output
```

## Tracks

The same master resume generates materially different CVs depending on which track you select:

| Track | Best for |
|---|---|
| **Technical / IC** | ML Engineer, Data Scientist, Research Scientist, SWE |
| **Leadership / People Manager** | Principal DS, Team Lead, Manager, Director |
| **Domain Expert** | Pharma, Biotech, Academic-adjacent, Clinical Research |

Track affects which bullets score highest during selection and how skills are reordered.

## Bring your own key

Prism runs on **your** OpenAI API key — you paste it into the app and it's never stored or logged. A full tailored CV costs roughly **$0.05–0.15** in API usage. Get a key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).

> _Demo GIF coming here — shows the full flow without needing a key._

## Quick start

```bash
# Install uv
curl -Ls https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/shilpasy/prism
cd prism
uv sync

# Add your OpenAI key (copy the example and fill it in)
cp .env.example .env   # then edit .env

# Run
uv run streamlit run app.py
```

### Deploying (Railway etc.)

Set these in the host's dashboard — **never commit them**:

| Variable | Purpose |
|---|---|
| `PRISM_FREE_KEY` | Owner-funded key for the free trial. Spend-capped (below). |
| `PRISM_DAILY_FREE_LIMIT` | Global hard cap on free runs per day (default `10`, ~$1/day). |
| `PRISM_FREE_PER_SESSION` | Free runs per visitor before they need their own key (default `2`). |

`OPENAI_API_KEY` is **ignored on the server** — it only takes effect locally when `PRISM_ALLOW_ENV_KEY=1` is also set. This is deliberate: it means a stray `OPENAI_API_KEY` can never become an uncapped shared key in production. Do not set `PRISM_ALLOW_ENV_KEY` on a server.

## How you give Prism your experience

You upload your resume (1–3 versions if you have them — different roles, different formats) and Prism reads it into a structured record of everything you've done. This is *not* the product — it's just how Prism learns your background so it has the full picture to draw from when tailoring. Under the hood this record is a `master_resume.json`; you never have to touch it.

If you'd rather build that record by hand, download `templates/master_resume_template.json` from the sidebar and fill it in. See `examples/example_master_resume.json` for a realistic reference.

**The actual work happens next:** you paste the job you're applying for, and Prism selects the most relevant experience, drops what doesn't fit, rewrites bullets in the role's language, and surfaces the transferable skills that match — then hands you a tailored Word doc.

## Tagging

Each bullet has a `tags` list. Tags are keywords that describe what type of work the bullet represents — not what it says, but what it demonstrates. The scoring algorithm uses these tags alongside LLM judgment to decide what to include for each track.

```json
{
  "text": "Built XGBoost churn model reducing churn 18%, deployed via FastAPI.",
  "tags": ["ml", "python", "xgboost", "production", "cloud"]
}
```

Full tag vocabulary is in `templates/master_resume_template.json`.

## Architecture

```
resume_agent/
├── schema.py       Pydantic models: MasterResume, Experience, Bullet, Project, ...
├── pipeline.py     Four-stage LLM pipeline (parse → score → polish → summarise)
├── prompts.py      All LLM prompts — tuned for GPT-4o / GPT-4o-mini
├── cv_builder.py   Generates .docx (python-docx) and .pdf (Chrome headless)
├── parser.py       Converts uploaded PDF/DOCX resume → master_resume.json via GPT-4o
└── selector.py     Tag-based fallback selector (no LLM, for testing)

app.py              Streamlit UI — multi-stage with human-in-the-loop review
templates/          Annotated master_resume_template.json
examples/           Realistic anonymized example resume
```

## Output

- `.docx` — Georgia font, navy section headers, gray dates, proper bullet indentation
- `.pdf` — Chrome headless with `--no-pdf-header-footer`, letter size, 0.75in margins

## License

MIT
