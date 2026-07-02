# Prism

**One resume in, every angle out.**

A multi-track CV generator for multi-domain professionals — people whose career spans more than one field and who need materially different CVs depending on the role, not just a reformatted version of the same document. Like light through a prism, your master resume splits into tailored versions for each track.

## The problem it solves

Most AI resume tools rewrite your existing resume. This agent does something different: it starts from a **master resume JSON** that holds your complete work history — every role, bullet, project, and achievement — and uses a four-stage LLM pipeline to generate a tailored CV for any job posting.

The key distinction: **nothing is invented**. All content comes from bullets you wrote and approved. The agent selects, reorders, and rephrases — but never fabricates.

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

## Building your master_resume.json

Two ways:

**Option A — Upload existing resumes (recommended)**
Upload 1–3 versions of your resume (PDF, DOCX, or plain text). GPT-4o reads all of them, merges them, and builds the JSON automatically — with tags suggested based on what each bullet actually demonstrates.

**Option B — Fill in the template manually**
Download `templates/master_resume_template.json` from the app sidebar. The template includes inline instructions and the full tag vocabulary.

See `examples/example_master_resume.json` for a realistic reference.

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
