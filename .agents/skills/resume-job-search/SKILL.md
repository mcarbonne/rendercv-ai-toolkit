---
name: resume-job-search
description: >-
  Interactive AI Job Search & Selection skill: interviews the user on their job
  search criteria (or reads input/master_resume.md), searches multiple job boards
  and scores results against existing CV variants, presents top matches for
  user selection (yes/no), saves chosen offers into jobs/ with refined keywords,
  and offers to tailor a resume variant via resume-tailor.
---

# Interactive Job Search & Selection (`resume-job-search`)

## Goal

Help the candidate discover relevant job openings across multiple job boards (`linkedin`, `indeed`, `hellowork` by default, via `python-jobspy`), rank them deterministically against their existing resume variants (`variants/*.yaml`), let the user pick which offers to keep, archive selected offers in `jobs/`, and transition seamlessly into **Phase 3 (`resume-tailor`)**.

---

## Step-by-Step Workflow

### Step 1: Load Candidate Preferences & Ask Search Criteria

1. Read `input/master_resume.md` (specifically **Section 1 › Target Roles & Executive Pitch** and **Section 5: Skills**) if it exists.
2. Ask the user to confirm or specify their current search criteria (keep it brief — 3 to 4 questions max):
   - **Target keywords / roles** (e.g., `"software engineer"`, `"data engineer"`, `"backend Rust"`).
   - **Target location(s)** (e.g., `"Paris, France"`, `"London, UK"`) — and the matching **country** for Indeed (`--country`, default `France`; e.g. `UK`, `Germany`, `USA`).
   - **Target seniority / contract type** (e.g., Senior/Lead only, exclude internships/apprenticeships) — you (the AI agent) will filter out non-matching roles when presenting the results.
   - **Job boards** (default: `linkedin,indeed,hellowork`; also supports `glassdoor,google,zip_recruiter,bayt,naukri,bdjobs` via `python-jobspy`) and **languages** for stopword filtering if not English/French (default `LANGS="en,fr"`, e.g. `LANGS="en,de"` for Germany).

### Step 2: Run Multi-Board Search & Score Against Resume Variants

Run the non-interactive CLI search so you can inspect and present the results cleanly to the user:

```bash
uv run python scripts/jobs.py search "<query>" \
  --location "<location>" \
  --country "<country>" \
  --sites "<sites>" \
  --limit 10 \
  --langs "<langs>" \
  --no-interactive
```

*(Tip: If the candidate targets 2 or 3 distinct role keywords or languages, you can run a couple of targeted queries to gather the strongest pool of openings.)*

*(Note: company career pages (Greenhouse, SmartRecruiters, Lever, Ashby, or any page exposing a JSON-LD `JobPosting`) are not searchable boards; import those offers by URL with `make job URL="<url>"`.)*

### Step 3: Present Top Matches & Ask User Selection (Yes / No)

1. Present a concise, scannable summary of the best matching job offers:
   - **# / Title / Company / Location / Seniority / Salary (if listed)**
   - **Best matching CV variant & `/100` score**
   - **Key matched skills (`✓`) vs. missing skills (`✗`)**
   - **Direct URL**
2. Ask the user:
   - **Which offers do you want to save into `jobs/`?** (e.g., *"Yes to #1 and #3"*, or *"Show me the full description of #2 first"*).

### Step 4: Save Selected Offers into `jobs/` & Refine Keywords

1. Save the user-approved offers into `jobs/`:
   - Either via the `--save` flag on the search command (`--save "1,3"`) or by importing their URLs directly:
     ```bash
     make job URL="<approved_job_url>" LANGS="<langs>"
     ```
2. **Inspect and refine `keywords.required` and `keywords.bonus`** in each newly saved `jobs/<YYYY-MM-company-role>.md` file:
   - Read the full verbatim job description in `jobs/<file>.md`.
   - Ensure `keywords.required` (must-have requirements) and `keywords.bonus` (nice-to-have requirements) accurately capture the recruiter's real requirements, using `|` for synonyms/aliases (e.g., `"Kubernetes|K8s"`, `"PostgreSQL|Postgres"`).
3. Re-run `make score LANGS="<langs>"` to display the updated, accurate match scores across all saved offers in `jobs/`.

### Step 5: Propose CV Tailoring (`resume-tailor`)

Ask the user:
> *"Would you like to tailor a dedicated resume variant (`resume-tailor`) for one of these saved job offers now?"*

- If **Yes**: Read and execute `.agents/skills/resume-tailor/SKILL.md` on the chosen `jobs/<offer>.md` file (including checking any missing skills with the user before updating `input/master_resume.md` and generating `variants/<slug>.yaml`).
