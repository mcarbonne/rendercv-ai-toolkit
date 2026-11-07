---
name: resume-tailor
description: >-
  Phase 3 of the Resume Toolkit: Create a tailored RenderCV variant
  (variants/<slug>.yaml) for a specific job posting (URL or file in jobs/),
  enrich input/master_resume.md when the user confirms missing skills, and
  optimize ATS keyword coverage via make ats. Use when the user wants to adapt
  their resume for a job posting.
---

# Phase 3: Tailor Resume to a Job Posting (`resume-tailor`)

## Goal

Produce a high-scoring, truthful, 1-page tailored resume variant (`variants/<slug>.yaml`) targeted at a specific job posting in `jobs/`, while continuously enriching `input/master_resume.md` whenever the user confirms new relevant skills or metrics.

---

## Step-by-Step Workflow

### Step 1: Import or Load the Job Posting

1. **If the user provided a URL**:
   Import it into `jobs/` using the CLI importer:
   ```bash
   make job URL="<url>"
   ```
2. **If the user pasted raw text without a URL**:
   Create `jobs/<YYYY-MM>-<company>-<role-slug>.md` following `jobs/_template.md` and paste the verbatim job description text below the YAML front matter.
3. **Read the job file** in `jobs/<job>.md`.

### Step 2: Populate Job Keywords (`keywords.required` & `keywords.bonus`)

Inspect the YAML front matter of `jobs/<job>.md`:
- Ensure `keywords.required` and `keywords.bonus` are thorough and accurate for the role:
  - Use `|` for synonyms/aliases so the ATS checker matches any valid form (e.g., `"Kubernetes|K8s"`, `"PostgreSQL|Postgres"`, `"CI/CD|GitHub Actions"`).
  - Put must-have requirements in `required` and nice-to-have requirements in `bonus`.

### Step 3: Cross-Reference with `input/master_resume.md` & Enrich Knowledge Base

Read `input/master_resume.md` and compare it against `keywords.required` and `keywords.bonus`:

1. **Direct Matches**: Identify which projects, roles, open-source contributions, and skills in `input/master_resume.md` directly prove the job's requirements.
2. **Terminology Alignment**: Map the candidate's real experience to the exact terminology used by the recruiter (e.g., if the job asks for *"distributed tracing"* or *"event-driven architecture"* and `master_resume.md` documents OpenTelemetry and Kafka, highlight those explicitly).
3. **Missing Keywords, Ambiguities & Continuous Master Resume Enrichment (Never Guess — Always Ask!)**:
   - If the job requires or values skills not yet mentioned in `input/master_resume.md`, or if you are unsure whether a past project/patent/experience in `input/master_resume.md` involved a specific mechanism or status, **never invent, extrapolate, or guess**. Always ask the user!
   - Ask the user concisely:
     *"This job mentions [Skill A, Skill B] which are not listed in `input/master_resume.md`. Do you have experience with them that we can add?"*
   - If the user confirms they have that experience, **update `input/master_resume.md` first** so the Master Resume permanently learns this fact for all future applications!

### Step 4: Select the Base Profile & Generate `variants/<slug>.yaml`

1. Choose the best starting profile:
   - **`variants/faang.yaml`** (`../shared/design-faang.yaml`, English, no summary, Google XYZ bullets) for Big Tech / international English-speaking roles.
   - **`variants/normal.yaml`** (`../shared/design.yaml`, with headline & summary, local language or English) for local/European roles.
2. Create `variants/<slug>.yaml` with:
   - Distinct `output_folder: ../rendercv_output/<slug>` and distinct output filenames (`OUTPUT_FOLDER/NAME_IN_SNAKE_CASE_CV_<SLUG_UPPER>.*`).
   - Reverse-chronological order for roles AND internal projects within a long company tenure (or explicit year ranges `(YYYY–YYYY)` in each project bullet if reordered by relevance, so recruiters never confuse an older project with the candidate's current Lead role).
   - Tailored bullet density: expand the projects that best match the job posting and condense less-relevant ones.
   - Highlighted open-source or side projects when they directly prove a required technology (e.g., an open-source library or CLI tool that directly demonstrates a required stack).
   - Tailored `Technical Skills` / `Skills` section (in the CV's target language) ordering the job's core domain first.
   - Strict respect for all `> [!CAUTION]` NDA rules in `input/master_resume.md`.

### Step 5: Multi-Agent Proofreading & Polish (`resume-proofread`)

Before final ATS scoring, execute the 2-stage proofreading pipeline from `.agents/skills/resume-proofread/SKILL.md` on `variants/<slug>.yaml`:

1. **Sub-agent 1 (`CV Proofreader`)**:
   - Focus specifically on newly adapted bullets and injected job keywords to ensure phrasing reads naturally, without awkward "keyword stuffing" or broken syntax.
2. **Sub-agent 2 (`Critical Editor`)**:
   - Critically verifies that keyword aliases and technical terms match recruiter expectations without distorting historical truth from `input/master_resume.md`.
   - Ensures adapted bullets do not overflow the 1-page budget.
   - Applies direct typo/grammar fixes and prompts the user for validation on any stylistic reformulations.

### Step 6: Closed-Loop ATS & Keyword Verification

Run the render and ATS check against the job posting (pass `LANGS="en,fr,..."` if the job/CV uses languages other than English or French):
```bash
make ats V=<slug> JOB=jobs/<job>.md
```
- Check the **ATS status** (no `FAIL` except unresolved `[X]` placeholders if any; check with `--ignore-placeholders` if needed).
- Check the **page count** (ensure it does not spill over onto an unintended extra page).
- Check the **Job Match Score (`/100`)** and the list of missing required/bonus keywords. If a keyword is genuinely covered in `input/master_resume.md` but phrased differently in `variants/<slug>.yaml`, adjust the phrasing or alias and re-run `make ats V=<slug> JOB=jobs/<job>.md`.
- Update `variant: <slug>` in the front matter of `jobs/<job>.md`.
- Report the final score, matched/missing keywords, and generated PDF path (`rendercv_output/<slug>/...`) to the user.
