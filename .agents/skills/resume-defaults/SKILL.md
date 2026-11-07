---
name: resume-defaults
description: >-
  Phase 2 of the Resume Toolkit: Generate or update the two default RenderCV
  v2.8 resume profiles (variants/normal.yaml and variants/faang.yaml) from
  input/master_resume.md, render them to PDF, and validate them with the local
  ATS checker. Use when the user asks to generate their default resumes or
  sync normal/faang variants with master_resume.md.
---

# Phase 2: Generate Default Profiles (`resume-defaults`)

## Goal

Generate and validate the two baseline RenderCV v2.8 variants from `input/master_resume.md`:
1. **`variants/normal.yaml`** — Standard European/local market format (with headline & executive summary, using `../shared/design.yaml`).
2. **`variants/faang.yaml`** — Big Tech / international engineering format (strict 1-page, English, no summary paragraph, dense impact-first Google XYZ bullets, using `../shared/design-faang.yaml`).

---

## Prerequisites & Guardrails

1. Read `input/master_resume.md` completely. If it does not exist, run `.agents/skills/resume-onboarding/SKILL.md` first.
2. Consult `.agents/skills/rendercv/SKILL.md` if you need any RenderCV v2.8 schema details.
3. **Strict Factuality, Zero Extrapolation & NDA Compliance**:
   - **Never invent, extrapolate, or guess** facts, technical mechanisms, patent statuses (e.g., published vs. pending/extended), tools, or numbers not explicitly confirmed by the user in `input/master_resume.md`. If anything is unclear, **ask the user first**.
   - Respect every `> [!CAUTION]` / NDA block in `input/master_resume.md` (use only the approved public phrasing).
   - Keep `[X]` placeholders wherever metrics are not yet finalized in `input/master_resume.md`.
4. **RenderCV v2.8 Rules**:
   - Pin the YAML schema comment on line 1:
     `# yaml-language-server: $schema=https://raw.githubusercontent.com/rendercv/rendercv/refs/tags/v2.8/schema.json`
   - Do **not** use YAML anchors/aliases (`&`, `*`, `<<:`).
   - All paths in `settings.render_command` are relative to `variants/*.yaml`.

---

## Step 1: Generate `variants/normal.yaml`

- **Audience**: Local/European companies, industrial R&D, scale-ups, consulting, general engineering applications.
- **Language**: Candidate's primary target language as defined in `input/master_resume.md` (default: French with `locale: ../shared/locale-fr.yaml`; omit `locale:` if English).
- **Structure** (translate section titles into the candidate's target language):
  - `cv.headline`: Clear role title + core specialization domains.
  - `Profile` / `Summary` section: 3–4 line executive pitch highlighting versatility, core strengths, and unique DNA.
  - `Professional Experience`: Chronological roles, promotions summary if applicable, and structured bullet points (`**Project/Topic (Role):** context, technical stack, and impact`).
  - `Projects` / `Entrepreneurship` (adapt section title to the candidate's profile and language).
  - `Education`.
  - `Skills`: Grouped logically via `label` + `details`.
  - `Honors & Awards` / `Publications` / `Open Source` (adapt to the candidate's achievements).
- **Settings block**:
  ```yaml
  settings:
    current_date: today
    render_command:
      output_folder: ../rendercv_output/normal
      design: ../shared/design.yaml
      locale: ../shared/locale-fr.yaml # Omit if English
      typst_path: OUTPUT_FOLDER/NAME_IN_SNAKE_CASE_CV_NORMAL.typ
      pdf_path: OUTPUT_FOLDER/NAME_IN_SNAKE_CASE_CV_NORMAL.pdf
      markdown_path: OUTPUT_FOLDER/NAME_IN_SNAKE_CASE_CV_NORMAL.md
      html_path: OUTPUT_FOLDER/NAME_IN_SNAKE_CASE_CV_NORMAL.html
      png_path: OUTPUT_FOLDER/NAME_IN_SNAKE_CASE_CV_NORMAL.png
      dont_generate_markdown: false
      dont_generate_html: false
      dont_generate_typst: false
      dont_generate_pdf: false
      dont_generate_png: false
    bold_keywords: []
    pdf_title: NAME - CV
  ```

---

## Step 2: Generate `variants/faang.yaml`

- **Audience**: Big Tech (FAANG/MAMAA), US/international tech companies, high-bar Staff/Senior IC & Tech Lead roles.
- **Language**: **English** (using `locale: ../shared/locale-en.yaml` for standardized 3-letter month abbreviations).
- **Editorial Rules**:
  - **Strict 1-page target**: Every line must earn its place.
  - **No `Profile` / `Summary` section** and empty `headline:` (standard `engineeringresumes` / r/EngineeringResumes convention).
  - **Google XYZ Formula**: Write bullets as *"Accomplished [X] as measured by [Y], by doing [Z]"* — lead with strong action verbs (`Architected`, `Engineered`, `Led`, `Eliminated`, `Cut`), bold key systems and technologies, and emphasize scale, concurrency, latency, reliability, and technical leadership.
  - **Clear Section Titles**: Choose clear, ATS-friendly section headings suited to the candidate's profile (e.g., `Experience`, `Projects` or `Projects & Entrepreneurship`, `Technical Skills`, `Education`, `Honors & Open Source` or `Honors & Awards`).
- **Settings block**:
  ```yaml
  settings:
    current_date: today
    render_command:
      output_folder: ../rendercv_output/faang
      design: ../shared/design-faang.yaml
      locale: ../shared/locale-en.yaml
      typst_path: OUTPUT_FOLDER/NAME_IN_SNAKE_CASE_CV_FAANG.typ
      pdf_path: OUTPUT_FOLDER/NAME_IN_SNAKE_CASE_CV_FAANG.pdf
      markdown_path: OUTPUT_FOLDER/NAME_IN_SNAKE_CASE_CV_FAANG.md
      html_path: OUTPUT_FOLDER/NAME_IN_SNAKE_CASE_CV_FAANG.html
      png_path: OUTPUT_FOLDER/NAME_IN_SNAKE_CASE_CV_FAANG.png
      dont_generate_markdown: false
      dont_generate_html: false
      dont_generate_typst: false
      dont_generate_pdf: false
      dont_generate_png: false
    bold_keywords: []
    pdf_title: NAME - Resume
  ```

---

## Step 3: Multi-Agent Proofreading & Polish (`resume-proofread`)

Before running the technical compilation and ATS checks, execute the 2-stage proofreading pipeline from `.agents/skills/resume-proofread/SKILL.md` on both variants:

1. **`variants/normal.yaml` (French / Local Market)**:
   - **Sub-agent 1 (`CV Proofreader`)**: Scans all sections, summary, and bullet points for spelling, grammar, and typography.
   - **Sub-agent 2 (`Critical Editor`)**: Critically assesses proposals against `master_resume.md`, applies safe fixes directly, and prompts the user for any stylistic reformulations.
2. **`variants/faang.yaml` (English / Big Tech)**:
   - **Sub-agent 1 (`CV Proofreader`)**: Audits action verbs, Google XYZ consistency, and grammatical agreements.
   - **Sub-agent 2 (`Critical Editor`)**: Verifies that technical terms/acronyms remain intact, checks line length against the strict 1-page limit, and collects user validation for stylistic changes.

---

## Step 4: Verification & ATS Loop (Mandatory)

After proofreading has been finalized and validated with the user:

1. Render and run the ATS checker on both profiles:
   ```bash
   make ats V=normal
   make ats V=faang
   ```
   *(If `[X]` placeholders are still present from Phase 1, also check that the only failure is `placeholders` by running `uv run python scripts/ats_check.py variants/normal.yaml --ignore-placeholders` and `uv run python scripts/ats_check.py variants/faang.yaml --ignore-placeholders`).*
2. Verify page count in the ATS output (`1 page` expected for `faang`, `1 page` preferred for `normal`). If a variant spills onto page 2 by a few lines, tighten bullet wording so it fits cleanly on 1 page.
3. Report the generated PDF paths and any remaining `[X]` placeholders to the user.
