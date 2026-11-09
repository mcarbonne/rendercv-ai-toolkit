# AGENTS.md

## Overview

AI-assisted Resume & Job Search Toolkit using **RenderCV v2.8** (Typst) and **uv** (Python 3.12).

- `input/master_resume.md` — Single source of truth for all candidate facts, metrics, links, and NDA rules (created from `input/_template_master_resume.md`).
- `variants/*.yaml` — Complete RenderCV v2.8 YAML files referencing `../shared/design*.yaml` and `../shared/locale-*.yaml`, outputting to `../rendercv_output/<variant>`.
- `jobs/*.md` — Job postings (YAML front matter with `keywords.required` / `keywords.bonus` + verbatim text; see `jobs/README.md`).
- `scripts/` — `extract_input.py` (`make extract`), `ats_check.py` (`make ats`), `jobs.py` (`make job` / `search` / `score`), `reset_workspace.py` (`make reset`).

## Skills (`.agents/skills/`)

Always read the relevant `SKILL.md` before executing a phase:
- **`resume-workflow`** — Orchestrator: inspects repo state and dispatches to the right skill.
- **`resume-onboarding`** (Phase 1) — Runs `make extract` on `input/` and interviews the user to build `input/master_resume.md`.
- **`resume-defaults`** (Phase 2) — Generates `variants/normal.yaml` and `variants/faang.yaml` from `input/master_resume.md`.
- **`resume-job-search`** — Interviews the user on search criteria, queries job boards (`make search`), lets the user select offers to save in `jobs/`, refines keywords, and offers `resume-tailor`.
- **`resume-tailor`** (Phase 3) — Imports a job into `jobs/`, confirms missing skills with the user, creates `variants/<slug>.yaml`, and optimizes `make ats V=<slug> JOB=jobs/<job>.md`.
- **`resume-proofread`** — Two-stage multi-agent proofreading (detector sub-agent + critical editor sub-agent).
- **`rendercv`** — Vendored RenderCV v2.8 schema/theme reference (do not hand-edit; update via `npx skills update`).

## Key Commands

```bash
make extract                                  # Extract text/links from raw files in input/
make render V=normal                          # Render variants/<V>.yaml via uv run rendercv
make ats V=faang [JOB=jobs/<job>.md]          # Render + run deterministic PDF ATS & keyword check
make ats-all                                  # Render + ATS check all variants
make job URL="https://..."                    # Import job posting into jobs/
make search Q="..." [LOC="..."] [COUNTRY=...] # Multi-board job search & CV scoring
make score                                    # Score all jobs/*.md against all variants/*.yaml
make lint                                     # ruff check + format check, shellcheck (also run in GitHub CI)
make fmt                                      # Auto-fix/format Python with ruff
```

## Critical Rules & Gotchas

1. **Zero Hallucination & NDA Compliance**: Never invent or extrapolate metrics, skills, or internal codenames/patents. Every fact in `variants/*.yaml` must come from `input/master_resume.md` and respect `> [!CAUTION]` NDA blocks. Always ask the user when in doubt.
2. **Verification**: A variant is only complete when `make ats V=<variant>` passes with **0 FAIL** (no unresolved `[X]` placeholders).
3. **RenderCV v2.8 Constraints**:
   - Always invoke via `uv run` (dependency must remain `rendercv[full]`).
   - **No YAML anchors/aliases** (`&`, `*`, `<<:` are unsupported); duplicate content across variants.
   - Relative paths in `settings.render_command` resolve relative to `variants/<name>.yaml`, not repo root.
   - Keep `yaml-language-server` schema URL pinned to `v2.8`.
