# Jobs (`jobs/`)

Archive of target job postings, one Markdown file per job offer.

## Conventions

- Filename: `YYYY-MM-company-role.md` in ASCII kebab-case (e.g., `2026-10-acme-software-engineer.md`).
- YAML front matter at the top of the file (see [`_template.md`](_template.md)), followed by the verbatim job description text.
- Files prefixed with `_` (e.g., `_template.md`) are templates and ignored by scripts.

| Field | Purpose |
| --- | --- |
| `company`, `title`, `location`, `url` | Job posting identification |
| `date` | Posting or import date (`YYYY-MM-DD`) |
| `variant` | Target resume variant (`normal`, `faang`, `<custom-slug>`…) |
| `status` | `to_apply`, `applied`, `interview`, `rejected`, `dropped` |
| `keywords.required` | Must-have keywords checked in the rendered PDF (WARN if missing) |
| `keywords.bonus` | Nice-to-have keywords listed for reference and scoring |

Aliases are separated by `|`: `Kubernetes|K8s`, `PostgreSQL|Postgres`. Matching is case-insensitive, accent-insensitive, and separator-insensitive (`CI/CD` = `ci-cd`).

## Import, Search, and Score Jobs from the CLI

```bash
# Import a job offer by URL (Greenhouse, SmartRecruiters, Lever, Ashby, any page with JSON-LD JobPosting…)
make job URL="https://..."

# Search job boards (LinkedIn + Indeed + HelloWork + Glassdoor + Google via python-jobspy),
# deduplicate, score every resume variant, and interactively pick jobs to save into jobs/
make search Q="software engineer" LOC="Paris, France"
make search Q="backend" LOC="Paris, France" SITES=linkedin,indeed,hellowork
make search Q="backend" LOC="London" COUNTRY=UK     # Indeed country (default: France)
make search Q="backend" LOC="Paris, France" SITES=linkedin SAVE="top2"

# Rank all archived job postings in jobs/ against all resume variants
make score
```

The `/100` match score is 100% deterministic (no LLM calls):
- **55 pts**: `keywords.required` coverage (2x weight for keywords appearing in the job title);
- **20 pts**: `keywords.bonus` coverage;
- **15 pts**: presence of required keywords in the core sections of the resume (`headline`, `Summary`, `Skills`, current role);
- **10 pts**: overall lexical similarity (TF-IDF cosine similarity over domain vocabulary).

## Check a Resume Variant Against a Job Offer

```bash
make ats V=faang JOB=jobs/<offer>.md

# Multiple job postings at once
make ats V=normal JOB="jobs/a.md jobs/b.md"
```

Keep keywords phrased as they appear in the job posting (or add `|` aliases): that exact terminology is what both ATS parsers and recruiters scan for.
