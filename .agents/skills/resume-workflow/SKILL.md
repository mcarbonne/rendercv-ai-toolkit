---
name: resume-workflow
description: >-
  Master orchestrator for the 3-phase Resume & Job Search Toolkit. Inspects the
  repository state (input/, input/master_resume.md, variants/, jobs/) and
  dispatches to Phase 1 (resume-onboarding), Phase 2 (resume-defaults), or
  Phase 3 (resume-tailor). Trigger whenever the user asks to start, manage,
  update, or tailor their resume/CV or isn't sure which step to run next.
---

# Resume Toolkit Orchestrator (`resume-workflow`)

This repository is an AI-powered toolkit for managing a candidate's **Master Resume** (`input/master_resume.md`), baseline RenderCV profiles (`variants/normal.yaml` and `variants/faang.yaml`), and job-tailored variants (`variants/<job-slug>.yaml`) scored against archived job postings (`jobs/`).

## Overview of the Workflow

```
Phase 1: resume-onboarding
  input/<raw-cv.pdf|docx|md> + Interview  ──►  input/master_resume.md  ──►  [resume-proofread]
                                                                                   │
Phase 2: resume-defaults                                                           ▼
  input/master_resume.md  ──►  variants/{normal,faang}.yaml  ──►  [resume-proofread]  ──►  make ats
                                                                                   │
Job Search (optional): resume-job-search                                           ▼
  User criteria + job boards  ──►  Score vs CVs  ──►  User picks offers  ──►  Saved in jobs/<job>.md
                                                                                   │
Phase 3: resume-tailor                                                             ▼
  jobs/<job>.md + input/master_resume.md  ──►  variants/<slug>.yaml  ──►  [resume-proofread]  ──►  make ats
       (enrich master_resume.md if user confirms missing skills)
```

## Step 1: Diagnose Workspace State

When invoked, inspect the workspace to determine which phase applies:

1. **Check `input/`**:
   - Does `input/master_resume.md` exist?
   - Are there raw files in `input/` (e.g., `.pdf`, `.docx`, `.txt`, `.md` other than `_template_master_resume.md` and `master_resume.md`)?
   - Does the user want to reset example data first? (If yes, run `uv run python scripts/reset_workspace.py --dry-run` and confirm before running `make reset`).
2. **Check `variants/`**:
   - Do `variants/normal.yaml` and `variants/faang.yaml` exist?
3. **Check user intent**:
   - Did the user provide a job posting URL, job description text, or path to `jobs/*.md`?

## Step 2: Dispatch to the Appropriate Skill

Read and follow the corresponding skill's `SKILL.md` file:

- **Phase 1 — Onboarding & Master Resume Creation**:
  - **When**: `input/master_resume.md` is missing, or the user dropped a new CV in `input/`, or wants to enrich their background via interview.
  - **Action**: Read `.agents/skills/resume-onboarding/SKILL.md` and execute its workflow.

- **Phase 2 — Generate Default Profiles (`normal` & `faang`)**:
  - **When**: `input/master_resume.md` is ready, and the user wants to generate or refresh `variants/normal.yaml` and `variants/faang.yaml`.
  - **Action**: Read `.agents/skills/resume-defaults/SKILL.md` and execute its workflow.

- **Phase 3 — Tailor Resume to a Job Offer**:
  - **When**: The user shares a job URL, a file in `jobs/`, or asks to adapt their resume for a specific role/company.
  - **Action**: Read `.agents/skills/resume-tailor/SKILL.md` and execute its workflow.

- **CV Proofreading & Critical Polish (`resume-proofread`)**:
  - **When**: The user asks to review, proofread, check grammar/spelling, or polish any resume variant or `master_resume.md`.
  - **Action**: Read `.agents/skills/resume-proofread/SKILL.md` and execute its 2-stage sub-agent workflow.

- **Interactive Job Search & Selection (`resume-job-search`)**:
  - **When**: The user wants to search for jobs, explore openings matching their profile, or rank archived jobs against existing variants.
  - **Action**: Read `.agents/skills/resume-job-search/SKILL.md` and execute its workflow.

## Golden Rule Across All Phases

- **Never invent, extrapolate, or guess anything — always ask the user!**
  - Whether extracting raw CVs, reading internal performance reviews, or tailoring a variant for a job posting, never guess technical mechanisms from internal project/patent codenames, never assume a patent is published vs. pending/confidential, and never fabricate metrics. If a detail is not explicitly confirmed by the user, ask them before writing it into `input/master_resume.md` or `variants/*.yaml`.
