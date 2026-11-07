---
name: resume-onboarding
description: >-
  Phase 1 of the Resume Toolkit: Extract raw resume files from input/ (PDF,
  DOCX, Markdown, TXT) and conduct a structured interactive interview with the
  user to build or enrich input/master_resume.md (the exhaustive single source
  of truth for all resume variants). Use when setting up a new user profile,
  ingesting an existing CV, or expanding the Master Resume.
---

# Phase 1: Resume Onboarding & Interview (`resume-onboarding`)

## Goal

Build or enrich `input/master_resume.md` — the **exhaustive, zero-loss knowledge base** of the candidate's career — by combining raw documents placed in `input/` with a targeted interactive interview.

> **Why a Master Resume?** A 1-page PDF resume compresses away 70% of a candidate's real technical depth, context, and stories. `input/master_resume.md` preserves *every* detail, metric, tool, link, and NDA boundary so future variants (`normal`, `faang`, or job-specific) can be generated without ever hallucinating.

---

## Workflow

### Step 1: Extract Raw Files from `input/`

1. Check if the workspace still contains example data that the user wants to clear. If the user is starting fresh and hasn't cleared the repo yet, offer to run `make reset`.
2. Run the extraction helper to read any PDF, DOCX, Markdown, or text files dropped into `input/` (or pass an external folder of annual performance reviews / career docs directly):
   ```bash
   make extract
   # Or extract an external directory of annual reviews / career documents:
   uv run python scripts/extract_input.py /path/to/reviews_dir
   ```
   *(Note: `scripts/extract_input.py` extracts both full text and embedded hyperlink URLs from PDFs and DOCX files. Ask the user if they have a folder of annual performance reviews, promotion packets, or Brags/Workday exports that can be extracted automatically).*
3. Read `input/_template_master_resume.md` (and `input/master_resume.md` if it already exists).

### Step 2: Analyze Gaps & Plan the Interview

Analyze the extracted CV content and identify high-value gaps across these 6 dimensions:

1. **Target Roles & Positioning**:
   - What roles, seniority levels, industries, and locations are they targeting?
   - What languages do they need for their default resumes (e.g., local language or English for `normal`, English for `faang`)?
2. **Timeline, Promotions & Internal Project Dates**:
   - Start and end dates (`YYYY-MM` or `YYYY`) for every company, role, and internship (ATS parsers penalize free-form dates like `"2018 (6 months)"`).
   - For long tenures at a single company (e.g., 3+ years): exact dates of **internal promotions** AND the **start/end dates (or year ranges) of each major internal project** so projects can be ordered chronologically and mapped to the candidate's seniority progression.
3. **Scope & Impact Metrics (The "XYZ" gaps)**:
   - For each major role/project: team size, leadership scope, production scale (users, devices, revenue, sites, latency, throughput, % improvement).
4. **Unlisted Technical Stack & Architecture**:
   - Tools, languages, protocols, hardware, or cloud/AI workflows used in practice but omitted from the old 1-page resume.
5. **Projects, Open Source & Achievements**:
   - Notable GitHub repositories, merged open-source PRs, competitions, patents, or side ventures (with dates).
6. **Confidentiality / NDA Constraints**:
   - Which internal metrics or project names are confidential and require a sanitized public phrasing?

### Step 3: Conduct the Interview in Short Batches (Never Guess — Always Ask!)

- **Golden Rule — NEVER invent, extrapolate, or guess anything**:
  - Do not infer what an internal project/feature/patent codename does from its name alone (e.g., if an annual review mentions a patent or feature codename like `"Project Phoenix"` or `"SmartSync"`, **never guess its technical mechanism** — ask the user what it actually does!).
  - Do not assume a patent is "published" or "granted" just because a review says "filed" or "extended internationally" — ask the user whether it is published or still unpublished/confidential.
  - Whenever a fact, technical description, date, metric, or confidentiality boundary is ambiguous or missing, **ask the user instead of filling in the blanks**.
- **Do NOT overwhelm the user** with 20 questions at once.
- Ask **3 to 5 focused questions per turn**, starting with the most recent/important experience and overall career target.
- Whenever the user doesn't know an exact number off the top of their head, **do not invent one**: record a `[X]` placeholder (e.g., `[X] customer sites`, `[X]% latency reduction`) and list it in Section 7 (`Open Questions & Metrics to Consolidate ([X])`) of `input/master_resume.md`.

### Step 4: Write & Iterate on `input/master_resume.md`

1. Structure `input/master_resume.md` following `input/_template_master_resume.md`.
2. Preserve all extracted URLs (LinkedIn, GitHub, company websites, open-source projects).
3. Use `> [!CAUTION]` blocks to explicitly mark any NDA / confidential details alongside their approved public phrasing so downstream skills (`resume-defaults`, `resume-tailor`) never leak restricted specs.

### Step 5: Master Resume Proofreading (`resume-proofread`)

1. Run the 2-stage proofreading pipeline from `.agents/skills/resume-proofread/SKILL.md` on `input/master_resume.md`:
   - **Sub-agent 1 (`CV Proofreader`)**: Scans `input/master_resume.md` for typos, grammar mistakes, and unclear phrasing.
   - **Sub-agent 2 (`Critical Editor`)**: Validates technical terminology and presents any stylistic/clarity choices to the user.
2. Present a concise summary of the finalized `input/master_resume.md`, highlight any remaining `[X]` placeholders, and confirm that the candidate's single source of truth is clean and ready for **Phase 2 (`resume-defaults`)**.
