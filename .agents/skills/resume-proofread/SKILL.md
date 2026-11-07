---
name: resume-proofread
description: >-
  Two-stage multi-agent proofreading & critical correction skill for CVs
  (variants in variants/ or input/master_resume.md). Runs an initial detection
  pass via a proofreader sub-agent, followed by a critical filtering, application,
  and user validation pass via an editor sub-agent. Use when the user requests a
  CV review, proofreading, grammar/spelling check, or as part of the post-generation
  quality loop.
---

# Multi-Agent CV Proofreading & Critical Correction (`resume-proofread`)

## Goal

Ensure flawless linguistic quality, technical accuracy, and stylistic punch across resume variants (`variants/*.yaml`) or the Master Resume (`input/master_resume.md`) through a **two-stage sub-agent pipeline**:
1. **Sub-agent 1 (`CV Proofreader`)**: Impartial, thorough scan detecting typos, grammatical errors, awkward phrasings, and stylistic inconsistencies.
2. **Sub-agent 2 (`Critical Editor`)**: Critical sanity-check of Sub-agent 1's findings against technical reality and 1-page constraints, separating direct fixes from stylistic choices, and submitting choices to the user for validation.

---

## When to Use

- **Standalone**: When the user asks to review, proofread, or check the spelling/grammar/style of a CV or `master_resume.md`.
- **Integrated**: At the end of **Phase 2 (`resume-defaults`)** on `normal.yaml` and `faang.yaml`, or **Phase 3 (`resume-tailor`)** on `variants/<slug>.yaml` before final delivery.

---

## The 2-Stage Sub-Agent Architecture

> **Tool-agnostic sub-agents**: Launch each stage with your tool's sub-agent capability (e.g., the `Agent` / Task tool in Claude Code, `invoke_subagent` in Antigravity, or the equivalent in Cursor / OpenCode), giving it a fresh context with the prompt below.
> **Fallback**: If your environment has no sub-agent capability, run both stages yourself sequentially, strictly playing each role in turn (finish and write down the full Stage 1 findings table before starting Stage 2).

```
  variants/<variant>.yaml (or master_resume.md)
                      │
                      ▼
 ┌──────────────────────────────────────────────┐
 │ Stage 1: Sub-agent 1 (CV Proofreader)        │
 │  - Exhaustive scan (typos, grammar, style)   │
 │  - Zero edits: outputs structured findings   │
 └──────────────────────┬───────────────────────┘
                        │
                        ▼ Findings Report
 ┌──────────────────────────────────────────────┐
 │ Stage 2: Sub-agent 2 (Critical Editor)       │
 │  - Technical sanity-check against context    │
 │  - Enforces 1-page line budget & NDA rules   │
 │  - Categorizes:                              │
 │      * Type A: Direct non-breaking fixes     │
 │      * Type B: Stylistic options for user    │
 │  - Applies Type A edits to file              │
 └──────────────────────┬───────────────────────┘
                        │
                        ▼
         User Validation on Type B Choices
                        │
                        ▼
       make ats V=<variant> (Layout & Score Check)
```

---

## Detailed Step-by-Step Workflow

### Step 1: Identify Target & Context

1. Identify the target file:
   - Specific variant: e.g. `variants/normal.yaml`, `variants/faang.yaml`, or `variants/<slug>.yaml`.
   - Or knowledge base: `input/master_resume.md`.
2. Confirm the target language:
   - French for `variants/normal.yaml` (when using `shared/locale-fr.yaml`).
   - English for `variants/faang.yaml`.
   - Variant-specific for tailored resumes.

---

### Step 2: Stage 1 — Launch Sub-agent 1 (`CV Proofreader`)

Launch a sub-agent (see *Tool-agnostic sub-agents* above) with:

* **Role**: `CV Proofreader`
* **Prompt Instructions**:
  ```markdown
  You are an expert technical resume proofreader and copy editor.
  Your task is to conduct an exhaustive, cold-eye review of the file: <PATH_TO_TARGET_FILE>.

  Language to review: <French | English>

  Examine the text across 4 criteria:
  1. Orthography & Typography: spelling errors, accentuation, capitalization of technical terms, bullet punctuation consistency.
  2. Grammar & Syntax: verb agreements, participle agreements, verb tense consistency (present for current role, past for completed roles).
  3. Clarity & Concision: elimination of filler words, awkward translations, or clunky phrasing.
  4. Impact: active phrasing, strong action verbs, avoidance of passive voice.

  IMPORTANT: Do NOT modify the file directly.
  Return a structured markdown table with your findings:
  | # | Section / Location | Original Text | Proposed Correction | Category (Typo / Grammar / Style / Clarity) | Rationale |
  ```

---

### Step 3: Stage 2 — Launch Sub-agent 2 (`Critical Editor`)

Once Sub-agent 1 returns its findings, launch a second sub-agent (see *Tool-agnostic sub-agents* above) with:

* **Role**: `Critical Editor`
* **Prompt Instructions**:
  ```markdown
  You are a Senior Technical Lead and Critical Editor reviewing proofreading suggestions for a CV.
  Target file: <PATH_TO_TARGET_FILE>
  Master Resume source of truth: input/master_resume.md

  Here are the proposed changes from Sub-agent 1:
  <FINDINGS_REPORT_FROM_SUBAGENT_1>

  Your role is to CRITICALLY challenge every single proposal:
  1. Technical Integrity: Does the proposed change accidentally alter a technical term, framework name, acronym, or industry standard (e.g., translating standard technical terms like "event loop" or "deadlock" into an inappropriate literal phrase)?
  2. Factuality & NDA: Does it change the meaning or claim something not verified in input/master_resume.md? Does it respect NDA cautions?
  3. Brevity & Page Budget: Does the rephrasing add words that would cause a bullet to wrap onto an extra line and break the strict 1-page layout?

  Classify each valid finding into:
  - Category A (Direct Fixes): Pure typos, indisputable grammar mistakes, or missing accents that don't alter meaning or line length.
  - Category B (Stylistic / Meaning Arbitrations): Rephrased sentences, stylistic alternatives, or word choices that impact tone or nuance.

  Actions:
  - If Category A fixes exist, apply them directly to <PATH_TO_TARGET_FILE>.
  - Prepare a concise report separating:
    1. Applied Direct Fixes (Category A)
    2. Proposals for User Validation (Category B) with Before / After / Trade-off
    3. Rejected Suggestions from Sub-agent 1 with rationale (e.g., "Rejected: would alter technical meaning of async/await concurrency model").
  ```

---

### Step 4: User Validation & Interaction

The main agent receives Sub-agent 2's report and presents the results to the user:

1. **Applied Fixes (Category A)**: Brief summary of confirmed typos/grammar fixes already applied.
2. **Rejected Suggestions**: Briefly mention any false positives from Sub-agent 1 that were correctly dismissed by Sub-agent 2.
3. **Proposals Requiring User Decision (Category B)**:
   Present clear options in the user's preferred language:
   ```markdown
   ### 📝 Suggested Rephrasings for Your Approval:

   1. **Experience Section — Project X**:
      - *Current*: "..."
      - *Proposed*: "..."
      - *Rationale*: Stronger action verb / avoids repetition.
      -> Would you like to apply this change?
   ```
4. Collect the user's decision and apply any approved Category B edits to the file.

---

### Step 5: Verification & ATS Check

1. If the target was a RenderCV variant (`variants/*.yaml`):
   Run the ATS and page budget check:
   ```bash
   make ats V=<variant>
   ```
2. Verify that:
   - ATS score did not drop.
   - Page count remains strictly 1 page (no line-wrap overflow from longer words).
   - Render passes without any syntax errors.
3. Confirm to the user that the proofread variant is clean, compiled, and validated.
