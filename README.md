# RenderCV AI Toolkit

An AI-first **Resume-as-Code & Job Search Toolkit** powered by [RenderCV](https://github.com/rendercv/rendercv) (Typst), Agent Skills (`.agents/skills/`), a deterministic local ATS checker, and a multi-board job matcher.

**Why this toolkit?** Ask a generic LLM to *"tailor my resume for this job"* and it will happily hallucinate skills, invent metrics, or distort your background. This repository solves that by enforcing an **Interview-First, Zero-Hallucination workflow** around a single source of truth (`input/master_resume.md`): whenever a job offer requires a skill or metric not in your knowledge base, **the agent asks you first instead of making it up**.

> [!NOTE]
> **100% AI-Written Project**: This entire toolkit—scripts, ATS checker, job search CLI, and agent skills—was designed and written by AI coding agents.

> [!CAUTION]
> **Data Privacy, AI Confidentiality & Human Review Disclaimer**:
> - **Always proofread before sending**: While the skills enforce strict anti-hallucination rules and include a two-agent proofreading pass (`resume-proofread`), AI models can still introduce subtle inaccuracies or phrasing quirks. **Always read and verify every generated PDF line by line before submitting an application.**
> - **Mind the AI models you use**: Any document you place in `input/` (CVs, phone/email, annual performance reviews, internal project docs) will be read by your AI coding assistant and sent to its LLM provider. Verify your AI tool's privacy & data-retention settings (disable training on your data / use Zero-Data-Retention or local models), and **never drop unredacted employer trade secrets or strict NDA material** without sanitizing them first.
> - **Keep your repository Private**: When using this template on GitHub, always create your repository as **Private** so you never publish `input/` or personal resume variants to a public repository.
> - **`make hooks-maintainer` is for template maintainers only**: it installs a pre-commit hook that *blocks* committing anything in `input/`, `variants/`, and `jobs/` (except templates). Don't enable it in your own private repository, or you won't be able to version your resume data.

---

## How It Works (At a Glance)

You don't edit YAML by hand. Open this repository in your AI coding assistant (**Claude Code, Antigravity, Cursor, OpenCode…**) and talk to it:

```text
1. Drop your career docs in input/ ──► "Run resume-onboarding" ──► Builds input/master_resume.md (via interview)
   (old CVs, annual reviews, brag docs…)
2. Generate base resumes           ──► "Run resume-defaults"   ──► Creates variants/normal.yaml & faang.yaml + PDF
3. Search & select job offers      ──► "Run resume-job-search" ──► Searches boards, scores CVs & saves chosen offers in jobs/
4. Tailor for a job offer          ──► "Tailor my CV for <job>"──► Confirms missing skills, creates variants/<job>.yaml + PDF
```

| Skill | Role | Example Prompt to Tell Your Agent |
| :--- | :--- | :--- |
| **`resume-workflow`** | Auto-detects what step you need next | *"Start or update my resume"* |
| **`resume-onboarding`** | **Phase 1**: Extracts `input/*` (CVs, annual reviews…) & interviews you to build `input/master_resume.md` | *"Run resume-onboarding on my files in input/"* |
| **`resume-defaults`** | **Phase 2**: Generates `normal.yaml` (EU/FR) and `faang.yaml` (1-page EN Big Tech) | *"Generate my default resumes"* |
| **`resume-job-search`** | Asks your criteria, searches job boards, scores offers, saves your picks to `jobs/`, and offers tailoring | *"Find senior backend jobs for me"* |
| **`resume-tailor`** | **Phase 3**: Imports a job offer, checks missing skills with you, and optimizes ATS score | *"Tailor my resume for https://..."* |
| **`resume-proofread`** | Two-agent grammar, spelling & impact review before sending | *"Proofread variants/faang.yaml"* |

---

## Quick Start

**Prerequisite**: [uv](https://docs.astral.sh/uv/) *(Python, RenderCV, Typst, and all dependencies are automatically fetched by `uv run` on first use—no manual install needed).*

1. **Create your private repo**: Click **`Use this template` → `Create a new repository`** on GitHub *(choose **Private** to keep your personal data private)*.
2. **Drop your career documents into `input/`**:
   - Your existing CV(s) (`.pdf`, `.docx`, `.md`, `.txt`)
   - **Optional but supercharged**: Your **annual performance reviews, promotion packets, brag docs, or LinkedIn exports** — the onboarding agent will automatically reconstruct your full career timeline, promotions, project dates, and impact metrics!
3. **Open your AI coding agent** and prompt:
   > *"Run `resume-workflow`"*

### Updating from the template

Repositories created with **`Use this template`** are independent copies (no fork link, unrelated history), so toolkit updates are pulled manually:

```bash
git remote add template https://github.com/mcarbonne/rendercv-ai-toolkit.git   # once
git fetch template
git merge template/main --allow-unrelated-histories   # first time only; afterwards: git merge template/main
```

The template never ships personal files in `input/`, `variants/`, or `jobs/` (only `_template*` / `README.md`), so conflicts are limited to scripts, skills, and shared designs.

---

## CLI Commands (Optional / Manual Use)

```bash
# Render & preview
make render V=normal                               # Render variants/normal.yaml to PDF/PNG/HTML/MD
make watch V=normal                                # Live preview on file changes
make all                                           # Render all variants

# Local ATS check & keyword scoring (deterministic, 0 external API)
make ats V=faang                                   # Check PDF readability, layout, fonts, dates & sections
make ats V=faang JOB=jobs/<offer>.md               # Also compute /100 keyword & lexical match score
make ats-all                                       # Render and ATS-check every variant

# Job import (Greenhouse, SmartRecruiters, Lever, Ashby, any JSON-LD page…) & search (LinkedIn, Indeed, HelloWork…)
make job URL="https://..."                         # Import a job offer into jobs/
make search Q="software engineer" LOC="Paris, France" # Search boards & score results against your CVs
make search Q="backend" LOC="London" COUNTRY=UK    # COUNTRY selects the Indeed country (default: France)
make score                                         # Rank all archived offers in jobs/ against your CVs

# Workspace utilities
make extract                                       # Extract raw text & URLs from files in input/
make reset                                         # Wipe personal data (input/, variants/, jobs/, output)

# Development
make lint                                          # ruff (lint + format check) & shellcheck, also run in GitHub CI
make fmt                                           # Auto-fix & format Python code with ruff
```

---

## Repository Layout

```text
├── .agents/skills/       # AI Agent Skills (workflow, onboarding, defaults, tailor, proofread, rendercv)
├── input/                # Raw CVs, annual reviews + master_resume.md (your single source of truth)
├── variants/             # RenderCV YAML variants (normal.yaml, faang.yaml, <job>.yaml)
├── shared/               # Shared RenderCV design & locale overlays (EN/FR)
├── jobs/                 # Archived job postings (YAML front matter + verbatim text)
├── scripts/              # Local CLI tools (ats_check.py, jobs.py, extract_input.py, reset_workspace.py)
└── rendercv_output/      # Generated PDFs, PNGs, HTML, Markdown (gitignored)
```
