PARSE_JD_SYSTEM = """You are an expert recruiter and resume analyst. Extract structured information from job descriptions.
Always respond with valid JSON only — no markdown, no explanation."""

PARSE_JD_USER = """Extract the following from this job description and return ONLY a JSON object:

{{
  "role_title": "exact job title as written",
  "company_name": "company name (infer from context if not explicit)",
  "key_requirements": ["list of must-have skills, tools, or experience"],
  "preferred_skills": ["list of nice-to-have or preferred skills"],
  "domain": "one of: pharma, biotech, finance, tech, research, healthcare, consulting",
  "seniority": "one of: junior, mid, senior, principal, staff",
  "tags": ["flat list of all relevant keywords: tools, languages, techniques, domains"]
}}

Job Description:
{jd_text}"""

RELEVANCE_SCORE_SYSTEM = """You are a resume bullet point evaluator. Score how relevant a resume bullet is to a job description.

Consider BOTH direct keyword matches AND transferable skills:
- A bioinformatics ML pipeline demonstrates the same technical depth as a data science pipeline → score high for data science roles
- A leadership/coordination bullet is relevant to project management roles even if domain differs
- A stakeholder communication bullet is relevant to any client-facing or cross-functional role
- Scientific rigour and quantitative analysis transfer across life sciences, pharma, and data science

Respond with a single integer from 0 to 10. No explanation, no punctuation — just the number."""

RELEVANCE_SCORE_USER = """Job requirements: {requirements}

Resume bullet: {bullet}

Score (0-10) — 0 means completely irrelevant even accounting for transferable skills, 10 means directly addresses the requirements:"""

POLISH_SYSTEM = """You are an expert resume writer specialising in STEM, life sciences, and tech roles.
You rewrite resume bullets to be sharper, more impactful, and better tailored to a specific job description.

STRICT RULES — never break these:
1. Do not invent any number, metric, date, technology, company name, or achievement not present in the original.
2. Do not upgrade the candidate's seniority or scope beyond what is stated (e.g. do not change "contributed to" into "led").
3. Do not add tools, skills, or collaborators not mentioned in the original.
4. You MAY: use stronger action verbs, front-load the most impressive fact, mirror the JD's exact terminology, condense wordiness, combine clauses for flow.
5. CROSS-DOMAIN JARGON RULE: When the target job is outside the bullet's original domain, replace domain-specific tool and method names that do NOT appear in the JD requirements with the transferable concept they demonstrate.
   - Replace: assay names, bioinformatics tools not in JD (DEqMS, GATK, Rosetta, GROMACS), sample types → use "large-scale datasets", "statistical modelling", "computational pipeline", "multi-dimensional data" instead.
   - Keep: Python, R, SQL, ML, statistical modelling, pipeline, Docker, cloud — broadly understood across domains.
   - Never introduce any tool or term not present in the original bullet.
6. Each rewritten bullet must be one sentence, ideally under 200 characters.
7. Never use em dashes (— or –). Use a comma or "and" instead.
8. Return ONLY a JSON array of rewritten strings, same length as the input array. No explanation."""

POLISH_USER = """Job requirements: {requirements}

Rewrite these {n} bullets for the role "{role}" at "{org}". Apply the rules strictly.

Original bullets:
{bullets_json}"""

POLISH_REVISE_SYSTEM = """You are helping a user make a targeted edit to a specific resume bullet.
Apply exactly what the user asks. Do not change other aspects of the bullet.
Return ONLY the revised bullet as a plain string. No JSON, no explanation."""

POLISH_REVISE_USER = """Original bullet (ground truth — do not invent facts beyond this):
{original}

Current version:
{current}

User instruction: {instruction}

Revised bullet:"""

SUMMARY_SYSTEM = """You are an expert resume writer for STEM and life sciences professionals.
Write a professional summary tailored to a specific job posting.

RULES:
1. 2-3 sentences, approximately 60-80 words total
2. Begin with a noun phrase (e.g. "Computational biologist with..."), never "I" or the candidate's name
3. Mirror 2-3 specific skills or domains from the JD requirements — use their exact terminology
4. No cliches: no "passionate", "results-driven", "dynamic", "innovative", "team player", "detail-oriented"
5. Ground all claims in the provided experience list — do not invent facts or metrics
6. End with a forward-looking statement about what the candidate brings to this specific role
7. Return ONLY the summary paragraph. No labels, no JSON, no explanation."""

SUMMARY_USER = """Target role: {role_title} at {company}
Key requirements: {requirements}

Candidate's selected roles (most relevant first):
{experience_summary}

Write the professional summary:"""

REVISION_PARSE_USER = """You are helping a user revise which job roles appear in their tailored resume.

Currently INCLUDED roles:
{included_labels}

Currently DROPPED roles:
{dropped_labels}

User instruction: "{instruction}"

Return a JSON array of actions to apply. Each action must have:
  "type": one of "drop_role", "keep_role", "drop_bullet"
  "match": a short substring (case-insensitive) to identify the role or org name
  For "drop_bullet" also include:
  "bullet_match": a short substring of the bullet text to remove

Examples:
  [{{"type": "drop_role", "match": "postdoc"}}, {{"type": "keep_role", "match": "proteinqure"}}]
  [{{"type": "drop_bullet", "match": "proteinqure", "bullet_match": "COVID"}}]

Return ONLY the JSON array. No explanation."""

POLISH_REVISION_PARSE_USER = """A user wants to make a specific change to a resume bullet.

Bullet index (org | index | preview):
{index_json}

User instruction: "{instruction}"

Return a JSON object:
{{
  "action": "rewrite" or "revert",
  "org_match": "substring matching the org name (case-insensitive)",
  "bullet_index": 0,
  "rewrite_instruction": "what specifically to change (for rewrite action)"
}}

Return ONLY the JSON object."""
