#!/usr/bin/env python3
"""Import, search, and score job postings from the command line.

Subcommands:
- `import <url>` : fetch a job posting by URL (schema.org JSON-LD `JobPosting`
  when the page provides it, e.g. Lever, Ashby, Workday, Welcome to the Jungle…;
  public JSON APIs for Greenhouse and SmartRecruiters, which don't; raw HTML
  fallback otherwise) and create a Markdown file in `jobs/`.
- `search <query>` : query job boards via `python-jobspy` (LinkedIn, Indeed,
  HelloWork, Glassdoor, Google, ZipRecruiter…), deduplicate results, and
  score each resume variant.
- `score` : score all archived job postings in `jobs/` against all resume variants.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import pathlib
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import asdict
from typing import Any

import yaml
from ats_check import (
    BOLD,
    BRIGHT_CYAN,
    BRIGHT_GREEN,
    BRIGHT_RED,
    BRIGHT_YELLOW,
    CYAN,
    DIM,
    GREEN,
    RED,
    YELLOW,
    CVProfile,
    OfferScore,
    extract_offer_keywords,
    fold,
    format_score_badge,
    get_offer_fields,
    load_all_cv_profiles,
    load_offer,
    score_color,
    score_offer_against_cv,
    set_stopword_langs,
    style,
)
from bs4 import BeautifulSoup
from jobspy import scrape_jobs
from markdownify import markdownify as md_convert

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"
JOBS_DIR = pathlib.Path(__file__).resolve().parent.parent / "jobs"


# --------------------------------------------------------------------------- #
# HTTP & Text Utilities
# --------------------------------------------------------------------------- #


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def http_get_json(url: str) -> Any:
    return json.loads(http_get(url))


def slugify(value: str, max_len: int = 45) -> str:
    folded = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(c for c in folded if not unicodedata.combining(c)).casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0]
    return slug or "job"


def html_to_markdown(raw: str) -> str:
    if not raw:
        return ""
    cleaned = md_convert(html.unescape(raw), heading_style="ATX", bullets="-")
    lines = [line.rstrip() for line in cleaned.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# --------------------------------------------------------------------------- #
# Salary Extraction & Formatting
# --------------------------------------------------------------------------- #

UNIT_LABELS = {
    "YEAR": "/ yr",
    "YEARLY": "/ yr",
    "MONTH": "/ mo",
    "MONTHLY": "/ mo",
    "HOUR": "/ hr",
    "HOURLY": "/ hr",
    "DAY": "/ day",
    "DAILY": "/ day",
}
CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF"}


def _fmt_num(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).replace("\u202f", " ").replace("\u00a0", " ").strip()
    s = re.sub(r"[,.]00$", "", s)
    try:
        num = int(float(s.replace(" ", "").replace(",", ".")))
        return f"{num:,}".replace(",", " ")
    except ValueError:
        return s


def format_base_salary(base_salary: Any) -> str:
    if not isinstance(base_salary, dict):
        return ""
    currency = CURRENCY_SYMBOLS.get(str(base_salary.get("currency") or "EUR").upper(), "€")
    val = base_salary.get("value")
    if isinstance(val, dict):
        unit = UNIT_LABELS.get(str(val.get("unitText") or "").upper(), "")
        low = _fmt_num(val.get("minValue"))
        high = _fmt_num(val.get("maxValue"))
        exact = _fmt_num(val.get("value"))
        if low and high and low != high:
            return f"{low} - {high} {currency} {unit}".strip()
        if low or exact:
            return f"{low or exact} {currency} {unit}".strip()
    elif val is not None:
        exact = _fmt_num(val)
        if exact:
            return f"{exact} {currency}".strip()
    return ""


# --------------------------------------------------------------------------- #
# ATS Job Board Fetchers
# --------------------------------------------------------------------------- #


def fetch_greenhouse(url: str) -> dict[str, str]:
    parsed = urllib.parse.urlsplit(url)
    parts = [p for p in parsed.path.split("/") if p]
    idx = parts.index("jobs") if "jobs" in parts else -1
    if not 0 < idx < len(parts) - 1:
        raise ValueError(f"Unrecognized Greenhouse URL (expected .../<board>/jobs/<id>): {url}")
    board = parts[idx - 1]
    job_id = parts[idx + 1]
    api = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}?content=true"
    job = http_get_json(api)
    return {
        "company": board.replace("-", " ").title(),
        "title": job.get("title") or "Role",
        "location": (job.get("location") or {}).get("name") or "",
        "url": job.get("absolute_url") or url,
        "date": parse_date(job.get("updated_at")),
        "body": html_to_markdown(job.get("content") or ""),
    }


def fetch_smartrecruiters(url: str) -> dict[str, str]:
    parsed = urllib.parse.urlsplit(url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Unrecognized SmartRecruiters URL: {url}")
    company = parts[0]
    posting_id = parts[1].split("-")[0]
    api = f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{posting_id}"
    job = http_get_json(api)
    sections_dict = (job.get("jobAd") or {}).get("sections") or {}
    blocks = []
    for key in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"):
        sec = sections_dict.get(key) or {}
        if sec.get("text"):
            title = sec.get("title") or key
            blocks.append(f"## {title}\n\n{html_to_markdown(sec['text'])}")
    loc = job.get("location") or {}
    location = ", ".join(x for x in (loc.get("city"), loc.get("country")) if x)
    return {
        "company": (job.get("company") or {}).get("name") or company,
        "title": job.get("name") or "Role",
        "location": location,
        "url": url,
        "date": parse_date(job.get("releasedDate")),
        "body": "\n\n".join(blocks),
    }


def _site_name(soup: BeautifulSoup, url: str) -> str:
    """Best-effort company name: `og:site_name` meta tag, else the URL hostname."""
    meta = soup.find("meta", attrs={"property": "og:site_name"})
    name = (meta.get("content") or "").strip() if meta else ""
    return name or urllib.parse.urlsplit(url).hostname or "Company"


def parse_jobposting_jsonld(soup: BeautifulSoup, url: str) -> dict[str, str] | None:
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        raw_json = script.string or script.get_text() or ""
        try:
            payload = json.loads(html.unescape(raw_json.strip()), strict=False)
        except json.JSONDecodeError:
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        if isinstance(payload, dict) and isinstance(payload.get("@graph"), list):
            candidates.extend(payload["@graph"])
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                org = item.get("hiringOrganization") or {}
                company = org.get("name") if isinstance(org, dict) else ""
                loc = item.get("jobLocation")
                if isinstance(loc, list) and loc:
                    loc = loc[0]
                addr = (loc.get("address") if isinstance(loc, dict) else {}) or {}
                location = (
                    ", ".join(
                        str(addr.get(k)) for k in ("addressLocality", "addressRegion", "addressCountry") if addr.get(k)
                    )
                    if isinstance(addr, dict)
                    else ""
                )
                desc = html_to_markdown(str(item.get("description") or ""))
                quals = html_to_markdown(str(item.get("qualifications") or ""))
                body = f"{desc}\n\n## Qualifications\n\n{quals}".strip() if quals else desc
                salary = format_base_salary(item.get("baseSalary"))
                return {
                    "company": str(company or _site_name(soup, url)),
                    "title": str(item.get("title") or "Role"),
                    "location": location,
                    "url": str(item.get("url") or url),
                    "date": parse_date(str(item.get("datePosted") or "")),
                    "salary": salary,
                    "body": body,
                    "basic_quals": quals,
                }
    return None


def fetch_generic_jsonld(url: str) -> dict[str, str]:
    """Extract a JSON-LD `@type: JobPosting` block or fallback to DOM main/body via BeautifulSoup."""
    page = http_get(url)
    soup = BeautifulSoup(page, "html.parser")
    parsed = parse_jobposting_jsonld(soup, url)
    if parsed:
        return parsed
    og_title = soup.find("meta", attrs={"property": "og:title"})
    title = (og_title.get("content") or "").strip() if og_title else ""
    title = title or (soup.title.get_text(strip=True) if soup.title else "") or "Role"
    container = soup.find("main") or soup.body or soup
    for tag in container.find_all(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    body = html_to_markdown(str(container))
    return {
        "company": _site_name(soup, url),
        "title": title,
        "location": "",
        "url": url,
        "date": today(),
        "salary": "",
        "body": body,
    }


def today() -> str:
    return dt.date.today().isoformat()


def parse_date(raw: str | None) -> str:
    if not raw:
        return today()
    raw = raw.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return today()


def fetch_offer(url: str) -> dict[str, str]:
    host = (urllib.parse.urlsplit(url).hostname or "").casefold()
    # Only ATS platforms whose pages lack JSON-LD need a dedicated API fetcher.
    if "greenhouse.io" in host:
        return fetch_greenhouse(url)
    if "smartrecruiters.com" in host:
        return fetch_smartrecruiters(url)
    return fetch_generic_jsonld(url)


# --------------------------------------------------------------------------- #
# Markdown File Generation
# --------------------------------------------------------------------------- #


def render_offer_markdown(
    info: dict[str, str],
    variant: str,
    required: list[str],
    bonus: list[str],
) -> str:
    def q(value: str) -> str:
        # JSON strings are valid YAML scalars: safely escapes `#`, `: `, leading `*`/`&`/`[`, quotes…
        return json.dumps(str(value), ensure_ascii=False)

    yaml_lines = [
        "---",
        f"company: {q(info['company'])}",
        f"title: {q(info['title'])}",
        f"location: {q(info['location'])}",
    ]
    if info.get("salary"):
        yaml_lines.append(f"salary: {q(info['salary'])}")
    yaml_lines.extend(
        [
            f"url: {q(info['url'])}",
            f"date: {q(info['date'])}",
            f"variant: {q(variant)}",
            "status: to_apply",
            "keywords:",
        ]
    )
    if required:
        yaml_lines.append("  required:")
        yaml_lines.extend(f"    - {q(k)}" for k in required)
    else:
        yaml_lines.append("  required: []")
    if bonus:
        yaml_lines.append("  bonus:")
        yaml_lines.extend(f"    - {q(k)}" for k in bonus)
    else:
        yaml_lines.append("  bonus: []")
    yaml_lines.extend(
        [
            "---",
            "",
            f"# {info['title']}",
            "",
            info["body"],
            "",
        ]
    )
    return "\n".join(yaml_lines)


def format_variant_scores(scores: list[OfferScore]) -> str:
    if not scores:
        return ""
    best = max(s.total for s in scores)
    parts = []
    for s in scores:
        is_best = s.total == best and best > 0
        v_name = style(s.variant, BOLD) if is_best else style(s.variant, DIM)
        badge = format_score_badge(s.total)
        star = f" {style('★', BRIGHT_YELLOW)}" if is_best else "  "
        parts.append(f"{v_name} {badge}{star}")
    return style(" │ ", DIM).join(parts)


def short_kw(spec: str) -> str:
    return spec.split("|")[0]


def cmd_import(args: argparse.Namespace) -> int:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    profiles = load_all_cv_profiles()
    exit_code = 0
    for url in args.urls:
        try:
            info = fetch_offer(url)
        except Exception as error:  # noqa: BLE001
            print(f"{style('[ERROR]', BRIGHT_RED)} {url}: {error}", file=sys.stderr)
            exit_code = 1
            continue
        required, bonus = extract_offer_keywords(info["title"], info["body"])
        scores = [score_offer_against_cv(p, info["title"], info["body"], required, bonus) for p in profiles]
        best_variant = max(scores, key=lambda s: s.total).variant if scores else "normal"
        variant = args.variant or best_variant
        ym = info["date"][:7]
        filename = f"{ym}-{slugify(info['company'], 20)}-{slugify(info['title'], 35)}.md"
        target = JOBS_DIR / filename
        if target.exists() and not args.overwrite:
            rel_t = target.relative_to(JOBS_DIR.parent)
            print(f"{style('[EXISTS]', BRIGHT_YELLOW)} {rel_t} (use --overwrite to replace)")
            continue
        target.write_text(render_offer_markdown(info, variant, required, bonus), encoding="utf-8")
        sal_badge = f"  {style('💰 ' + info['salary'], BRIGHT_CYAN)}" if info.get("salary") else ""
        print(
            f"{style('[OK]', BRIGHT_GREEN)}     {style(str(target.relative_to(JOBS_DIR.parent)), CYAN)} "
            f"({style(info['company'], BOLD)} — {info['title']}){sal_badge}"
        )
        if scores:
            print(f"         {style('Resume Scores:', DIM)} {format_variant_scores(scores)}")
    return exit_code


# --------------------------------------------------------------------------- #
# Search, Deduplication & Scoring (python-jobspy: LinkedIn, Indeed, HelloWork…)
# --------------------------------------------------------------------------- #


def _norm_company(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", fold(name or ""))


def _norm_title(title: str) -> str:
    s = re.sub(r"\b[a-z]/[a-z](?:/[a-z])?\b", " ", fold(title or ""))
    return re.sub(r"[^a-z0-9]+", "", s)


def _norm_city(location: str) -> str:
    first = (location or "").split(",")[0].split("-")[0].strip()
    return re.sub(r"[^a-z0-9]+", "", fold(first))


def deduplicate_offers(items: list[dict[str, str]]) -> list[dict[str, str]]:
    """Merge intra-site and cross-site duplicates (same company, title, and city)."""
    by_key: dict[tuple[str, str, str], dict[str, str]] = {}
    for item in items:
        key = (
            _norm_company(item.get("company") or ""),
            _norm_title(item.get("title") or ""),
            _norm_city(item.get("location") or ""),
        )
        if not key[0] and not key[1]:
            continue
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = dict(item)
            continue
        sites = existing.get("site", "").split("+")
        new_site = item.get("site") or ""
        if new_site and new_site not in sites:
            sites.append(new_site)
            existing["site"] = "+".join(s for s in sites if s)
        if len(item.get("body") or "") > len(existing.get("body") or ""):
            existing["body"] = item.get("body") or ""
            existing["basic_quals"] = item.get("basic_quals") or existing.get("basic_quals") or ""
            existing["pref_quals"] = item.get("pref_quals") or existing.get("pref_quals") or ""
        if not existing.get("salary") and item.get("salary"):
            existing["salary"] = item["salary"]
    return list(by_key.values())


def search_jobspy(query: str, location: str, sites: list[str], limit: int, country: str) -> list[dict[str, str]]:
    def _val(x: Any) -> str:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return ""
        return str(x)

    try:
        df = scrape_jobs(
            site_name=sites,
            search_term=query,
            location=location or None,
            results_wanted=limit,
            country_indeed=country,
            description_format="markdown",
            fetch_description=True,
            linkedin_fetch_description=True,
            verbose=0,
        )
    except Exception as error:  # noqa: BLE001
        print(f"[WARN] JobSpy search error ({error})", file=sys.stderr)
        return []

    out: list[dict[str, str]] = []
    for _, row in df.iterrows():
        lo = _val(row.get("min_amount"))
        hi = _val(row.get("max_amount"))
        cur = _val(row.get("currency")) or "€"
        iv = _val(row.get("interval"))
        if lo and hi:
            sal = f"{lo} - {hi} {cur} ({iv})".strip()
        elif lo or hi:
            sal = f"{lo or hi} {cur}".strip()
        else:
            sal = ""
        job_type = _val(row.get("job_type"))
        job_level = _val(row.get("job_level")) or _val(row.get("experience_range"))
        meta_tag = ", ".join(x for x in (job_type, job_level) if x)
        out.append(
            {
                "site": _val(row.get("site")),
                "company": _val(row.get("company")),
                "title": _val(row.get("title")),
                "location": _val(row.get("location")),
                "job_type": meta_tag,
                "date": _val(row.get("date_posted")),
                "url": _val(row.get("job_url")),
                "salary": sal,
                "body": _val(row.get("description")),
            }
        )
    return out


def score_and_enrich_offer(item: dict[str, Any], profiles: list[CVProfile]) -> dict[str, Any]:
    title = item.get("title") or ""
    body = item.get("body") or ""
    salary = item.get("salary") or ""
    required, bonus = extract_offer_keywords(
        title,
        body,
        basic_quals=item.get("basic_quals") or "",
        pref_quals=item.get("pref_quals") or "",
    )
    scores = [score_offer_against_cv(p, title, body, required, bonus) for p in profiles]
    best = max(scores, key=lambda s: s.total) if scores else None
    return {
        "site": item.get("site") or "",
        "company": item.get("company") or "",
        "title": title,
        "location": item.get("location") or "",
        "job_type": item.get("job_type") or "",
        "salary": salary,
        "date": item.get("date") or "",
        "url": item.get("url") or "",
        "best_variant": best.variant if best else "",
        "best_score": best.total if best else 0,
        "scores": {s.variant: asdict(s) for s in scores},
        "_score_objs": scores,
        "_best_obj": best,
        "_body": body,
        "_required": required,
        "_bonus": bonus,
    }


def print_cv_and_market_summary(
    enriched: list[dict[str, Any]],
    profiles: list[CVProfile],
) -> None:
    if not profiles:
        return
    n_offers = len(enriched)

    offer_kw_counts: Counter[str] = Counter()
    for item in enriched:
        scores: list[OfferScore] = item.get("_score_objs") or []
        if not scores:
            continue
        first = scores[0]
        all_kws = set(first.matched_req + first.missing_req + first.matched_bonus + first.missing_bonus)
        for k in all_kws:
            offer_kw_counts[k] += 1

    print(style("Resume Variants & ATS Diagnostics", BOLD))
    for p in profiles:
        wins = [item for item in enriched if item.get("best_variant") == p.name and item.get("best_score", 0) > 0]
        p_scores = [s.total for item in enriched for s in (item.get("_score_objs") or []) if s.variant == p.name]
        max_s = max(p_scores, default=0)
        hl = style(f'"{p.headline}"', DIM) if p.headline else style("(no headline)", DIM)
        win_badge = style(f"★ #1 on {len(wins)}/{n_offers} jobs", BRIGHT_GREEN if wins else DIM)
        max_badge = style(f"(max {max_s}/100)", score_color(max_s))
        print(f"  • {style(f'{p.name:<13}', BOLD)} {win_badge} {max_badge} — {hl}")

        weak_parts = []
        for w in p.weaknesses:
            col = RED if "placeholder" in w else (YELLOW if "free-form" in w else DIM)
            weak_parts.append(style(w, col))

        missing_vs_others = []
        for k, cnt in offer_kw_counts.most_common():
            in_self = any(
                k in (s.matched_req + s.matched_bonus)
                for item in enriched
                for s in (item.get("_score_objs") or [])
                if s.variant == p.name
            )
            in_other = any(
                k in (s.matched_req + s.matched_bonus)
                for item in enriched
                for s in (item.get("_score_objs") or [])
                if s.variant != p.name
            )
            if not in_self and in_other:
                missing_vs_others.append(f"{short_kw(k)} ({cnt}x)")
        if weak_parts:
            print(f"      {style('ATS Weaknesses:', DIM)} " + style(" · ", DIM).join(weak_parts))
        if missing_vs_others:
            print(
                f"      {style('Missing vs other variants:', DIM)} " + style(", ".join(missing_vs_others[:7]), YELLOW)
            )
    print()

    if not offer_kw_counts:
        return

    missing_all: list[tuple[str, int]] = []
    partial_cov: list[tuple[str, int, list[str]]] = []
    covered_any: list[tuple[str, int]] = []

    for k, cnt in offer_kw_counts.most_common():
        present_variants = sorted(
            {
                s.variant
                for item in enriched
                for s in (item.get("_score_objs") or [])
                if k in (s.matched_req + s.matched_bonus)
            }
        )
        if not present_variants:
            missing_all.append((short_kw(k), cnt))
        else:
            covered_any.append((short_kw(k), cnt))
            if len(present_variants) < len(profiles):
                partial_cov.append((short_kw(k), cnt, present_variants))

    print(style(f"Key Skills Across {n_offers} Job(s)", BOLD))
    if missing_all:
        items_str = style(" • ", DIM).join(
            f"{style(name, RED)} {style(f'({cnt}/{n_offers})', DIM)}" for name, cnt in missing_all[:8]
        )
        print(f"  {style('✗ Missing from all variants :', RED):<35} {items_str}")
    if partial_cov:
        items_str = style(" • ", DIM).join(
            f"{style(name, BRIGHT_YELLOW)} {style(f'({cnt}x, only in {",".join(vs)})', DIM)}"
            for name, cnt, vs in partial_cov[:6]
        )
        print(f"  {style('◐ Present in 1–2 variants  :', BRIGHT_YELLOW):<35} {items_str}")
    if covered_any:
        items_str = style(" • ", DIM).join(
            f"{style(name, GREEN)} {style(f'({cnt}/{n_offers})', DIM)}" for name, cnt in covered_any[:8]
        )
        print(f"  {style('✓ Already covered          :', GREEN):<35} {items_str}")
    print()


def print_scored_offers(
    enriched: list[dict[str, Any]],
    profiles: list[CVProfile] | None = None,
) -> None:
    if profiles:
        print_cv_and_market_summary(enriched, profiles)
    saved_urls = _load_saved_job_urls()
    for idx, item in enumerate(enriched, 1):
        scores: list[OfferScore] = item["_score_objs"]
        best: OfferScore | None = item["_best_obj"]
        best_col = score_color(best.total) if best else BOLD
        rank = style(f"{idx:2d}.", best_col)
        site = style(f"[{item['site']}]", CYAN)
        type_badge = f" {style('[' + str(item['job_type']) + ']', DIM)}" if item.get("job_type") else ""
        company = style(str(item["company"]), BOLD)
        title = style(str(item["title"]), best_col if (best and best.total >= 45) else BOLD)
        loc = style(f" ({item['location']})", DIM) if item.get("location") else ""
        sal = f"  {style('💰 ' + str(item['salary']), BRIGHT_CYAN)}" if item.get("salary") else ""
        target_path = _offer_target_path(item)
        is_saved = (
            item.get("site", "").endswith(".md")
            or target_path.exists()
            or (item.get("url") and item["url"] in saved_urls)
        )
        saved_badge = (
            f"  {style('[saved]', GREEN)}" if (is_saved and not str(item.get("site", "")).endswith(".md")) else ""
        )
        print(f"{rank} {site}{type_badge} {company} — {title}{loc}{sal}{saved_badge}")
        if scores:
            print(f"    {style('Resume Scores:', DIM)} {format_variant_scores(scores)}")
        if best:
            matched = [short_kw(k) for k in best.matched_req + best.matched_bonus]
            missing = [short_kw(k) for k in best.missing_req]
            parts = []
            if matched:
                parts.append(style("✓ " + ", ".join(matched[:8]), GREEN))
            if missing:
                parts.append(style("✗ " + ", ".join(missing[:6]), RED))
            if parts:
                sep = style("  │  ", DIM)
                v_tag = style(f"({best.variant})", DIM)
                print(f"    {style('Keywords', DIM)} {v_tag}: " + sep.join(parts))
        if item.get("url"):
            print(f"    {style(str(item['url']), DIM)}")


def _offer_target_path(item: dict[str, Any]) -> pathlib.Path:
    date_str = str(item.get("date") or today())
    ym = date_str[:7] if len(date_str) >= 7 else today()[:7]
    company = str(item.get("company") or "company")
    title = str(item.get("title") or "role")
    filename = f"{ym}-{slugify(company, 20)}-{slugify(title, 35)}.md"
    return JOBS_DIR / filename


def _load_saved_job_urls() -> set[str]:
    urls: set[str] = set()
    if not JOBS_DIR.exists():
        return urls
    for p in JOBS_DIR.glob("*.md"):
        if p.name.startswith("_") or p.name.lower() == "readme.md":
            continue
        try:
            meta, _ = load_offer(p)
            u = str(meta.get("url") or "").strip()
            if u:
                urls.add(u)
        except Exception:  # noqa: BLE001
            continue
    return urls


def parse_selection(spec: str, max_idx: int) -> list[int]:
    """Parse selection string like '1, 3, 5-7', 'all', 'top3' into 1-based indices."""
    raw = spec.strip().casefold()
    if not raw or raw in {"q", "quit", "exit", "n", "no", "none"}:
        return []
    if raw in {"a", "all", "*"}:
        return list(range(1, max_idx + 1))
    m_top = re.fullmatch(r"top\s*(\d+)", raw)
    if m_top:
        k = min(max_idx, int(m_top.group(1)))
        return list(range(1, k + 1))

    selected: list[int] = []
    for token in re.split(r"[\s,;]+", raw):
        if not token:
            continue
        m_range = re.fullmatch(r"(\d+)\s*-\s*(\d+)", token)
        if m_range:
            lo, hi = int(m_range.group(1)), int(m_range.group(2))
            if lo > hi:
                lo, hi = hi, lo
            for idx in range(lo, hi + 1):
                if 1 <= idx <= max_idx and idx not in selected:
                    selected.append(idx)
        elif token.isdigit():
            idx = int(token)
            if 1 <= idx <= max_idx and idx not in selected:
                selected.append(idx)
        else:
            raise ValueError(f"Invalid selection token: '{token}'")
    return selected


def save_enriched_offer(item: dict[str, Any], overwrite: bool = False) -> pathlib.Path | None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    body = str(item.get("_body") or "").strip()
    url = str(item.get("url") or "").strip()
    company = str(item.get("company") or "Company")
    title = str(item.get("title") or "Role")
    location = str(item.get("location") or "")
    date_str = str(item.get("date") or today())
    salary = str(item.get("salary") or "")

    # If the search card had an empty/minimal description, fetch the full job page by URL
    if len(body) < 120 and url:
        try:
            fetched = fetch_offer(url)
            body = fetched.get("body") or body
            company = fetched.get("company") or company
            title = fetched.get("title") or title
            location = fetched.get("location") or location
            date_str = fetched.get("date") or date_str
            salary = salary or fetched.get("salary") or ""
        except Exception as error:  # noqa: BLE001
            print(f"{style('[WARN]', YELLOW)} Could not fetch full page for {url} ({error}); saving search snippet.")

    required = list(item.get("_required") or [])
    bonus = list(item.get("_bonus") or [])
    if not required and not bonus:
        required, bonus = extract_offer_keywords(title, body)

    variant = str(item.get("best_variant") or "") or "normal"
    info = {
        "company": company,
        "title": title,
        "location": location,
        "salary": salary,
        "url": url,
        "date": date_str,
        "body": body,
    }
    target = _offer_target_path(info)
    if target.exists() and not overwrite:
        print(
            f"{style('[EXISTS]', BRIGHT_YELLOW)} {target.relative_to(JOBS_DIR.parent)} "
            f"(already saved — pass --overwrite or prefix with '!' e.g. '!1' to overwrite)"
        )
        return None
    target.write_text(render_offer_markdown(info, variant, required, bonus), encoding="utf-8")
    print(
        f"{style('[SAVED]', BRIGHT_GREEN)}  {style(str(target.relative_to(JOBS_DIR.parent)), CYAN)} "
        f"({style(company, BOLD)} — {title}, variant={style(variant, BOLD)})"
    )
    return target


def preview_enriched_offer(idx: int, item: dict[str, Any]) -> None:
    body = str(item.get("_body") or "").strip()
    url = str(item.get("url") or "").strip()
    if len(body) < 120 and url:
        try:
            fetched = fetch_offer(url)
            body = fetched.get("body") or body
            item["_body"] = body
        except Exception:  # noqa: BLE001
            pass
    print("\n" + style("─" * 78, DIM))
    comp_s = style(str(item.get("company")), BOLD)
    title_s = style(str(item.get("title")), BOLD)
    print(f"{style(f'#{idx}', BRIGHT_CYAN)} {comp_s} — {title_s}")
    meta_parts = [p for p in (item.get("location"), item.get("job_type"), item.get("salary"), item.get("date")) if p]
    if meta_parts:
        print(style(" · ".join(str(p) for p in meta_parts), DIM))
    if url:
        print(style(url, CYAN))
    print(style("─" * 78, DIM))
    if body:
        lines = body.splitlines()
        preview_lines = lines[:45]
        print("\n".join(preview_lines))
        if len(lines) > 45:
            print(style(f"\n... ({len(lines) - 45} more lines — save to jobs/ to view full text)", DIM))
    else:
        print(style("(No description body available)", DIM))
    print(style("─" * 78, DIM) + "\n")


def interactive_save_loop(enriched: list[dict[str, Any]], overwrite: bool = False) -> None:
    max_idx = len(enriched)
    print()
    while True:
        hint = f"[1-{max_idx}, e.g. 1,3 or 1-3 | all | top3 | v1 to preview #1 | !1,3 to overwrite | Enter to quit]"
        prompt = f"{style('Save to jobs/', BOLD)} {style(hint, DIM)}: "
        try:
            raw = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw or raw.casefold() in {"q", "quit", "exit"}:
            break

        # Preview command: v1, view 1, ?1
        m_view = re.fullmatch(r"(?:v|view|\?)\s*(\d+)", raw.casefold())
        if m_view:
            idx = int(m_view.group(1))
            if 1 <= idx <= max_idx:
                preview_enriched_offer(idx, enriched[idx - 1])
            else:
                print(f"{style('[WARN]', YELLOW)} Please enter a job number between 1 and {max_idx}.")
            continue

        force_overwrite = overwrite
        if raw.startswith("!"):
            force_overwrite = True
            raw = raw[1:].strip()

        try:
            indices = parse_selection(raw, max_idx)
        except ValueError as err:
            print(f"{style('[WARN]', YELLOW)} {err}")
            continue

        if not indices:
            break

        saved_paths: list[pathlib.Path] = []
        for idx in indices:
            path = save_enriched_offer(enriched[idx - 1], overwrite=force_overwrite)
            if path:
                saved_paths.append(path)

        if saved_paths:
            rel_first = saved_paths[0].relative_to(JOBS_DIR.parent)
            best_v = enriched[indices[0] - 1].get("best_variant") or "faang"
            print(
                f"\n{style('Next steps:', DIM)} "
                f"`make ats V={best_v} JOB={rel_first}` or ask your AI agent to run `resume-tailor` on `{rel_first}`."
            )
        break


def cmd_search(args: argparse.Namespace) -> int:
    sites = [s.strip().casefold() for s in args.sites.split(",") if s.strip()]
    raw_results = search_jobspy(args.query, args.location, sites, args.limit, args.country) if sites else []

    deduped = deduplicate_offers(raw_results)
    profiles = load_all_cv_profiles()
    enriched = [score_and_enrich_offer(item, profiles) for item in deduped]
    enriched.sort(key=lambda x: -x["best_score"])

    if args.json:
        clean = [{k: v for k, v in item.items() if not k.startswith("_")} for item in enriched]
        print(json.dumps(clean, ensure_ascii=False, indent=2))
        return 0

    if not enriched:
        print("No matching jobs found.")
        return 0

    print_scored_offers(enriched, profiles)

    if args.save:
        indices = parse_selection(args.save, len(enriched))
        for idx in indices:
            save_enriched_offer(enriched[idx - 1], overwrite=args.overwrite)
        return 0

    if not args.no_interactive and sys.stdin.isatty():
        interactive_save_loop(enriched, overwrite=args.overwrite)

    return 0


def cmd_score(args: argparse.Namespace) -> int:
    profiles = load_all_cv_profiles()
    files = args.jobs or sorted(
        p for p in JOBS_DIR.glob("*.md") if not p.name.startswith("_") and p.name.lower() != "readme.md"
    )
    if not files:
        print("No archived jobs found in jobs/.")
        return 0

    enriched = []
    for path in files:
        try:
            meta, body = load_offer(path)
        except (OSError, ValueError, yaml.YAMLError) as error:
            print(f"{style('[WARN]', YELLOW)} Skipping {path}: {error}", file=sys.stderr)
            continue
        fields = get_offer_fields(meta, default_title=path.stem)
        title = fields["title"]
        required = fields["required"]
        bonus = fields["bonus"]
        if not required and not bonus:
            required, bonus = extract_offer_keywords(title, body)
        salary = fields["salary"]
        scores = [score_offer_against_cv(p, title, body, required, bonus) for p in profiles]
        best = max(scores, key=lambda s: s.total) if scores else None
        enriched.append(
            {
                "site": path.name,
                "company": fields["company"],
                "title": title,
                "location": fields["location"],
                "job_type": "",
                "salary": salary,
                "date": fields["date"],
                "url": fields["url"],
                "best_variant": best.variant if best else "",
                "best_score": best.total if best else 0,
                "scores": {s.variant: asdict(s) for s in scores},
                "_score_objs": scores,
                "_best_obj": best,
            }
        )
    enriched.sort(key=lambda x: -x["best_score"])
    if args.json:
        clean = [{k: v for k, v in item.items() if not k.startswith("_")} for item in enriched]
        print(json.dumps(clean, ensure_ascii=False, indent=2))
        return 0
    if not enriched:
        print("No jobs found.")
        return 0
    print_scored_offers(enriched, profiles)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import, search, and score job postings.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_import = sub.add_parser("import", help="Import one or more job postings by URL into jobs/")
    p_import.add_argument("urls", nargs="+", help="Job posting URL(s) (Greenhouse, SmartRecruiters, any JSON-LD page…)")
    p_import.add_argument(
        "--variant",
        dest="variant",
        help="Force target resume variant (e.g., normal, faang)",
    )
    p_import.add_argument("--overwrite", action="store_true", help="Overwrite target file if it already exists")
    p_import.add_argument("--langs", default="en,fr", help="Stopword language codes (default: 'en,fr')")
    p_import.set_defaults(func=cmd_import)

    p_search = sub.add_parser("search", help="Search job boards by keyword")
    p_search.add_argument("query", help="Search query (e.g., 'software engineer')")
    p_search.add_argument("--location", default="", help="Location filter (e.g., 'Paris, France')")
    p_search.add_argument(
        "--sites",
        default="linkedin,indeed,hellowork",
        help=(
            "Comma-separated job boards (python-jobspy): "
            "linkedin,indeed,hellowork,glassdoor,google,zip_recruiter,bayt,naukri,bdjobs"
        ),
    )
    p_search.add_argument("--country", default="France", help="Country for Indeed (default: France)")
    p_search.add_argument("--limit", type=int, default=10, help="Results per board (default: 10)")
    p_search.add_argument(
        "--save",
        default="",
        help="Non-interactive selection of results to save into jobs/ (e.g., '1,3', '1-3', 'top3', 'all')",
    )
    p_search.add_argument("--overwrite", action="store_true", help="Overwrite existing files in jobs/ when saving")
    p_search.add_argument("--no-interactive", action="store_true", help="Disable interactive save prompt after search")
    p_search.add_argument("--langs", default="en,fr", help="Stopword language codes (default: 'en,fr')")
    p_search.add_argument("--json", action="store_true", help="Output JSON")
    p_search.set_defaults(func=cmd_search)

    p_score = sub.add_parser("score", help="Score archived job postings in jobs/ against all resume variants")
    p_score.add_argument("jobs", nargs="*", type=pathlib.Path, help="Specific job files (default: all in jobs/)")
    p_score.add_argument("--langs", default="en,fr", help="Stopword language codes (default: 'en,fr')")
    p_score.add_argument("--json", action="store_true", help="Output JSON")
    p_score.set_defaults(func=cmd_score)

    args = parser.parse_args()
    set_stopword_langs(args.langs)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
