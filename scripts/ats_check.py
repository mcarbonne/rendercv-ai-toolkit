#!/usr/bin/env python3
"""Deterministic local ATS compatibility checker and job scorer for RenderCV variants.

The variant YAML is loaded through RenderCV's validated model builder (including
design/locale overlays, theme defaults, and resolved PDF path), then compared
against text extracted from the generated PDF via `pypdf` and, when available,
Poppler (`pdftotext`).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

import stopwordsiso
import yaml
from pypdf import PdfReader
from rendercv.exception import RenderCVUserValidationError
from rendercv.renderer.path_resolver import resolve_rendercv_file_path
from rendercv.schema.models.rendercv_model import RenderCVModel
from rendercv.schema.rendercv_model_builder import build_rendercv_dictionary_and_model

PASS, WARN, FAIL = "pass", "warn", "fail"
RANK = {PASS: 0, WARN: 1, FAIL: 2}

USE_COLOR = "NO_COLOR" not in os.environ
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BRIGHT_RED = "\033[1;31m"
BRIGHT_GREEN = "\033[1;32m"
BRIGHT_YELLOW = "\033[1;33m"
BRIGHT_CYAN = "\033[1;36m"


def style(text: str, *codes: str) -> str:
    if not USE_COLOR or not codes:
        return text
    return f"{''.join(codes)}{text}{RESET}"


def score_color(score: int) -> str:
    if score >= 70:
        return BRIGHT_GREEN
    if score >= 45:
        return BRIGHT_YELLOW
    if score >= 25:
        return RED
    return f"{DIM}{RED}"


def format_score_badge(score: int, width: int = 8) -> str:
    filled = round((max(0, min(100, score)) / 100) * width)
    col = score_color(score)
    bar = style("█" * filled, col) + style("░" * (width - filled), DIM)
    num = style(f"{score:2d}/100", col)
    return f"{bar} {num}"


TYPOGRAPHIC = str.maketrans(
    {
        "\u00ad": "",
        "\u200b": "",
        "\u00a0": " ",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)
DATE_RE = re.compile(r"\d{4}(?:-\d{2}(?:-\d{2})?)?")
PLACEHOLDER_RE = re.compile(r"\[[Xx]+\]")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")


@dataclass
class Check:
    id: str
    label: str
    status: str = PASS
    message: str = ""
    details: list[str] = field(default_factory=list)

    def warn(self, detail: str) -> None:
        self._add(WARN, detail)

    def fail(self, detail: str) -> None:
        self._add(FAIL, detail)

    def _add(self, status: str, detail: str) -> None:
        if RANK[status] > RANK[self.status]:
            self.status = status
        self.details.append(detail)


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #


def fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.translate(TYPOGRAPHIC))
    return "".join(c for c in value if not unicodedata.combining(c)).casefold()


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", fold(value)).strip()


def compact(value: str) -> str:
    return "".join(c for c in fold(value) if c.isalnum())


def strip_markdown(value: str) -> str:
    value = MARKDOWN_LINK_RE.sub(r"\1", value)
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
    value = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", value)
    value = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", value)
    return value.replace("\\", "").strip()


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def load_variant(variant_path: pathlib.Path) -> tuple[dict[str, Any], RenderCVModel]:
    """Load the variant exactly as `rendercv render` does (overlays included)."""
    raw = yaml.safe_load(variant_path.read_text(encoding="utf-8")) or {}
    render_command = (raw.get("settings") or {}).get("render_command") or {}
    overlays = {}
    for key, kwarg in (("design", "design_yaml_file"), ("locale", "locale_yaml_file")):
        if render_command.get(key):
            overlay = (variant_path.parent / render_command[key]).resolve()
            overlays[kwarg] = overlay.read_text(encoding="utf-8")
    data, model = build_rendercv_dictionary_and_model(
        variant_path.read_text(encoding="utf-8"),
        input_file_path=variant_path,
        **overlays,
    )
    return data, model


def pdf_path_of(model: RenderCVModel) -> pathlib.Path:
    return resolve_rendercv_file_path(model, model.settings.render_command.pdf_path)


def walk_strings(node: Any, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key != "network":
                yield from walk_strings(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk_strings(value, f"{path}[{index}]")
    elif isinstance(node, str):
        yield path, node


def cv_fields(cv: dict[str, Any]) -> list[tuple[str, str]]:
    """Extract all text strings from YAML that must appear in the PDF (excluding dates and raw URLs)."""
    fields = [("sections", str(title)) for title in cv.get("sections") or {}]
    for path, raw in walk_strings(cv):
        if re.search(r"\.(start_date|end_date|date)$", path):
            continue
        value = strip_markdown(raw)
        if value and re.search(r"\w", value) and not re.fullmatch(r"https?://\S+", value):
            fields.append((path, value))
    seen: set[str] = set()
    unique = []
    for path, value in fields:
        key = compact(value)
        if key and key not in seen:
            seen.add(key)
            unique.append((path, value))
    return unique


def entry_dates(cv: dict[str, Any]) -> Iterable[tuple[str, str, str]]:
    for title, entries in (cv.get("sections") or {}).items():
        for index, entry in enumerate(entries if isinstance(entries, list) else []):
            if isinstance(entry, dict):
                for key in ("start_date", "end_date", "date"):
                    if key in entry:
                        yield f"{title}[{index}].{key}", key, str(entry[key])


def pdftotext(pdf: pathlib.Path) -> str | None:
    exe = shutil.which("pdftotext")
    if exe is None:
        return None
    try:
        result = subprocess.run([exe, str(pdf), "-"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


# --------------------------------------------------------------------------- #
# ATS Checks
# --------------------------------------------------------------------------- #


def check_pdf(reader: PdfReader, text: str, check: Check) -> None:
    pages = len(reader.pages)
    if pages > 2:
        check.warn(f"{pages} pages: ATS and recruiters prefer 1 to 2 pages")

    images = 0
    unembedded: set[str] = set()
    for page in reader.pages:
        resources = page.get("/Resources")
        resources = resources.get_object() if resources is not None else {}
        for xobject in (resources.get("/XObject") or {}).values():
            if xobject.get_object().get("/Subtype") == "/Image":
                images += 1
        for font in (resources.get("/Font") or {}).values():
            font = font.get_object()
            descriptors = [font] + [d.get_object() for d in font.get("/DescendantFonts") or []]
            embedded = font.get("/Subtype") != "/Type3" and any(
                any(k in (d.get("/FontDescriptor") or {}) for k in ("/FontFile", "/FontFile2", "/FontFile3"))
                for d in descriptors
            )
            if not embedded:
                unembedded.add(str(font.get("/BaseFont") or "?"))

    if images:
        check.fail(f"{images} image(s): image content is invisible to ATS parsers")
    if unembedded:
        check.fail("unembedded fonts: " + ", ".join(sorted(unembedded)))
    if len(text.strip()) < 500:
        check.fail(f"only {len(text.strip())} characters extracted: PDF is unreadable by ATS")
    check.message = f"{pages} page(s), {len(text)} characters extracted"

    if "\ufffd" in text:
        check.fail(f"{text.count(chr(0xFFFD))} replacement character(s) (U+FFFD) in extracted text")
    icons = sum(1 for c in text if 0xE000 <= ord(c) <= 0xF8FF)
    if icons:
        check.warn(f"{icons} icon glyph(s) (Unicode Private Use Area) pollute extracted text")


def match_fields(fields: list[tuple[str, str]], text: str) -> tuple[list[str], list[str]]:
    """Return (scattered, missing) fields."""
    flat, dense = normalize(text), compact(text)
    scattered, missing = [], []
    for path, value in fields:
        needle = compact(value)
        if normalize(value) in flat:
            continue
        if len(needle) >= 6 and needle in dense:
            continue
        if len(needle) < 6 and re.search(rf"(?<!\w){re.escape(normalize(value))}(?!\w)", flat):
            continue
        label = f'{path}: "{value[:90]}"'
        start = dense.find(needle[:4]) if len(needle) >= 12 else -1
        end = dense.find(needle[-8:], start + 4) if start != -1 else -1
        if end != -1 and end - start <= max(200, 3 * len(needle)):
            scattered.append(label)
        else:
            missing.append(label)
    return scattered, missing


def check_fidelity(fields: list[tuple[str, str]], text: str, check: Check) -> None:
    scattered, missing = match_fields(fields, text)
    found = len(fields) - len(missing)
    check.message = f"{found}/{len(fields)} YAML fields found in PDF"
    for item in scattered:
        check.warn(f"non-contiguous: {item}")
    for item in missing:
        check.fail(f"missing: {item}")


def check_poppler(fields: list[tuple[str, str]], text: str | None, check: Check) -> None:
    if text is None:
        check.message = "pdftotext unavailable, check skipped"
        return
    scattered, missing = match_fields(fields, text)
    check.message = f"{len(fields) - len(scattered) - len(missing)}/{len(fields)} contiguous fields"
    for item in scattered:
        check.warn(f"broken reading order: {item}")
    for item in missing:
        check.warn(f"missing: {item}")


def check_contacts(cv: dict[str, Any], text: str, check: Check) -> None:
    flat, dense = normalize(text), compact(text)
    email = cv.get("email")
    if email and fold(str(email)) not in flat:
        check.fail(f"email missing from text: {email}")
    phone = re.sub(r"\D", "", str(cv.get("phone") or ""))
    if phone and phone[-9:] not in re.sub(r"\D", "", text):
        check.fail(f"phone missing from text: {cv.get('phone')}")
    location = cv.get("location")
    if location and compact(str(location)) not in dense:
        check.warn(f"location missing from text: {location}")
    for social in cv.get("social_networks") or []:
        username = str(social.get("username") or "")
        if username and compact(username) not in dense:
            check.fail(f"{social.get('network')}: {username} missing from text")
    if check.status == PASS:
        check.message = "email, phone, location, and social networks present"


def check_dates(cv: dict[str, Any], text: str, present: str, check: Check) -> None:
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", text))
    missing_years: set[str] = set()
    count = 0
    for path, key, raw in entry_dates(cv):
        count += 1
        if key == "end_date" and fold(raw) in {"present", fold(present)}:
            continue
        if not DATE_RE.fullmatch(raw.strip()):
            check.warn(f'free-form date poorly parsed by ATS: {path} = "{raw}"')
        elif raw[:4] not in years:
            missing_years.add(raw[:4])
    if missing_years:
        check.warn("year(s) missing from text: " + ", ".join(sorted(missing_years)))
    if check.status == PASS:
        check.message = f"{count} structured date(s)"


def check_titles(cv: dict[str, Any], check: Check) -> None:
    sections = cv.get("sections") or {}
    if not sections:
        check.fail("no sections defined in cv.sections")
        return
    empty = [f'"{title}"' for title, entries in sections.items() if not entries]
    if empty:
        check.warn("empty section(s): " + ", ".join(empty))
    else:
        check.message = f"{len(sections)} section(s) defined"


def check_design(model: RenderCVModel, check: Check) -> None:
    """Inspect resolved design settings (overlay + theme defaults)."""
    design = model.design
    page = getattr(design, "page", None)
    connections = getattr(getattr(design, "header", None), "connections", None)
    typography = getattr(design, "typography", None)

    if model.cv.photo:
        check.fail("photo present: invisible to ATS and discouraged for ATS parsing")
    if connections is not None and getattr(connections, "show_icons", False):
        check.warn("`header.connections.show_icons: true`: non-text icon glyphs in header")
    if connections is not None and getattr(connections, "display_urls_instead_of_usernames", True) is False:
        check.warn("`display_urls_instead_of_usernames: false`: full URLs are more reliably parsed")
    if page is not None and (getattr(page, "show_footer", False) or getattr(page, "show_top_note", False)):
        check.warn("footer or top note enabled: adds repeated noise to extracted text")
    body = str(getattr(getattr(typography, "font_size", None), "body", "") or "")
    match = re.fullmatch(r"([\d.]+)\s*pt", body.strip())
    if match and float(match.group(1)) < 9:
        check.warn(f"body font size at {body}: aim for >= 9–10 pt")
    if check.status == PASS:
        check.message = "no known ATS pitfalls in design"


def check_placeholders(cv: dict[str, Any], check: Check, ignore: bool) -> None:
    hits = [(path, len(PLACEHOLDER_RE.findall(raw))) for path, raw in walk_strings(cv)]
    hits = [(path, n) for path, n in hits if n]
    if not hits:
        check.message = "no unresolved placeholders"
        return
    total = sum(n for _, n in hits)
    detail = f"{total} `[X]` placeholder(s): " + ", ".join(f"{p} ({n})" for p, n in hits)
    (check.warn if ignore else check.fail)(detail)


# --------------------------------------------------------------------------- #
# Job Postings & Deterministic Scoring (/100)
# --------------------------------------------------------------------------- #

DEFAULT_LANGS = ("en", "fr")
_ACTIVE_STOPWORDS: frozenset[str] = frozenset(fold(w) for w in stopwordsiso.stopwords(DEFAULT_LANGS))


def set_stopword_langs(langs_spec: str) -> None:
    """Configure ISO stopword languages from a comma-separated spec (e.g. 'en,fr' or 'en,fr,de')."""
    global _ACTIVE_STOPWORDS
    langs = [lang.strip().casefold() for lang in (langs_spec or "").split(",") if lang.strip()]
    if not langs:
        langs = list(DEFAULT_LANGS)
    loaded = stopwordsiso.stopwords(langs)
    if loaded:
        _ACTIVE_STOPWORDS = frozenset(fold(w) for w in loaded)


@dataclass
class OfferScore:
    variant: str
    total: int
    req_score: int
    bonus_score: int
    core_score: int
    lexical_score: int
    matched_req: list[str]
    missing_req: list[str]
    matched_bonus: list[str]
    missing_bonus: list[str]


@dataclass
class CVProfile:
    name: str
    full_text: str
    core_text: str
    headline: str = ""
    weaknesses: list[str] = field(default_factory=list)


def load_offer(path: pathlib.Path) -> tuple[dict[str, Any], str]:
    content = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if not match:
        raise ValueError(f"{path}: missing YAML front matter")
    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError(f"{path}: invalid YAML front matter")
    return meta, match.group(2).strip()


def get_offer_fields(meta: dict[str, Any], default_title: str = "") -> dict[str, Any]:
    """Normalize job metadata from YAML front matter."""
    kw = meta.get("keywords") or {}
    return {
        "company": str(meta.get("company") or "?"),
        "title": str(meta.get("title") or default_title),
        "location": str(meta.get("location") or ""),
        "salary": str(meta.get("salary") or ""),
        "date": str(meta.get("date") or ""),
        "url": str(meta.get("url") or ""),
        "variant": str(meta.get("variant") or ""),
        "status": str(meta.get("status") or ""),
        "required": [str(k) for k in (kw.get("required") or [])],
        "bonus": [str(k) for k in (kw.get("bonus") or [])],
    }


def keyword_pattern(keyword: str) -> re.Pattern[str]:
    words = re.sub(r"[\s\-_/]+", " ", fold(keyword)).strip()
    body = r"[\s\-_/]*".join(re.escape(w) for w in words.split(" "))
    return re.compile(rf"(?<![a-z0-9+#°']){body}(?![a-z0-9+#'])")


def keyword_found(spec: str, haystack: str) -> bool:
    """`spec` accepts `|`-separated aliases (e.g., `Kubernetes|K8s`)."""
    return any(keyword_pattern(alias).search(haystack) for alias in spec.split("|") if alias.strip())


def _discover_workspace_vocabulary(repo_root: pathlib.Path | None = None) -> list[str]:
    """Dynamically collect skill terms from `OneLineEntry` items across `variants/*.yaml`."""
    root = repo_root or pathlib.Path(__file__).resolve().parent.parent
    terms: list[str] = []
    seen: set[str] = set()

    def _add(raw_item: str) -> None:
        cleaned = strip_markdown(raw_item).strip(" ,.;:()[]•-*")
        if not cleaned or len(cleaned) > 32 or cleaned.isdigit():
            return
        key = fold(cleaned)
        if not ((len(cleaned) >= 2 and key not in _ACTIVE_STOPWORDS) or cleaned in ("C", "R")):
            return
        if key not in seen:
            seen.add(key)
            terms.append(cleaned)

    def _add_chunk(text: str, filter_text: str = "") -> None:
        for m in re.finditer(r"\(([^)]+)\)", text):
            for sub in re.split(r"[,;]", m.group(1)):
                if not filter_text or fold(sub.strip()) in filter_text:
                    _add(sub)
        outside = re.sub(r"\([^)]*\)", "", text)
        for part in re.split(r"[,;&—•]", outside):
            if not filter_text or fold(part.strip()) in filter_text:
                _add(part)
            if "/" in part and len(part.strip()) <= 20:
                for sp in part.split("/"):
                    if len(sp.strip()) >= 3 and (not filter_text or fold(sp.strip()) in filter_text):
                        _add(sp)

    variants_dir = root / "variants"
    if variants_dir.is_dir():
        raw_variants = []
        for v_path in sorted(variants_dir.glob("*.yaml")):
            if v_path.name.startswith("_"):
                continue
            try:
                raw_variants.append(yaml.safe_load(v_path.read_text(encoding="utf-8")) or {})
            except Exception:  # noqa: BLE001
                continue
        headlines_fold = fold(" ".join(str((r.get("cv") or {}).get("headline") or "") for r in raw_variants))
        for raw in raw_variants:
            sections = (raw.get("cv") or {}).get("sections") or {}
            for entries in sections.values():
                for entry in entries if isinstance(entries, list) else []:
                    if isinstance(entry, dict) and "label" in entry and "details" in entry:
                        raw_details = str(entry.get("details") or "")
                        raw_parts = [p.strip() for p in raw_details.split(",") if p.strip()]
                        # Skip spoken-language lines where every comma-separated item has a parenthetical level
                        if raw_parts and all("(" in p and ")" in p for p in raw_parts):
                            continue
                        if headlines_fold:
                            _add_chunk(str(entry.get("label") or ""), filter_text=headlines_fold)
                        _add_chunk(raw_details)

    return terms


TECH_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"C\+\+|C/C\+\+|C#|\.NET"
    r"|[A-Z][a-z]+[A-Z][A-Za-z0-9]*"
    r"|[A-Z]{3,6}(?:/[A-Z0-9]{2,6})?"
    r"|[A-Za-z]{2,10}\d{1,4}[A-Za-z0-9]*"
    r")(?![A-Za-z0-9])"
)


def extract_offer_keywords(
    title: str,
    body: str,
    basic_quals: str = "",
    pref_quals: str = "",
    max_req: int = 6,
    max_bonus: int = 6,
) -> tuple[list[str], list[str]]:
    """Extract `(required, bonus)` keywords from candidate skill vocabulary and technical tokens."""
    bullet_lines = [
        line for line in body.splitlines() if re.match(r"^\s*[-*•]", line) and any(c.islower() for c in line)
    ]
    desc_zone = body
    basic_zone = basic_quals or "\n".join(bullet_lines)
    bonus_zone = pref_quals

    candidate_specs = list(_discover_workspace_vocabulary())
    for m in TECH_TOKEN_RE.finditer("\n".join([title, *bullet_lines])):
        tok = m.group(0)
        if fold(tok) not in _ACTIVE_STOPWORDS:
            candidate_specs.append(tok)

    title_fold = fold(title)
    desc_fold = fold(desc_zone)
    basic_fold = fold(basic_zone)
    bonus_fold = fold(bonus_zone)
    seen: set[str] = set()
    req_hits: list[tuple[int, str]] = []
    bonus_hits: list[tuple[int, str]] = []

    for spec in candidate_specs:
        k = fold(spec)
        if k in seen:
            continue
        in_title = 1 if keyword_found(spec, title_fold) else 0
        desc_count = sum(len(keyword_pattern(a).findall(desc_fold)) for a in spec.split("|") if a.strip())
        basic_count = sum(len(keyword_pattern(a).findall(basic_fold)) for a in spec.split("|") if a.strip())
        bonus_count = sum(len(keyword_pattern(a).findall(bonus_fold)) for a in spec.split("|") if a.strip())

        if in_title or basic_count >= 1 or (not basic_fold and desc_count >= 2) or desc_count >= 3:
            seen.add(k)
            req_hits.append((in_title * 10 + basic_count * 4 + desc_count, spec))
        elif bonus_count >= 1 or desc_count >= 1:
            seen.add(k)
            bonus_hits.append((bonus_count * 3 + desc_count, spec))

    req_hits.sort(key=lambda item: -item[0])
    bonus_hits.sort(key=lambda item: -item[0])

    all_req_candidates = [s for _, s in req_hits]
    required = all_req_candidates[:max_req]
    overflow_req = all_req_candidates[max_req:]
    bonus_candidates = overflow_req + [s for _, s in bonus_hits if s not in required and s not in overflow_req]
    bonus = bonus_candidates[:max_bonus]
    return required, bonus


def _domain_tokens(text: str) -> Counter[str]:
    words = re.findall(r"[a-z0-9+#]{3,}", fold(text))
    return Counter(w for w in words if w not in _ACTIVE_STOPWORDS and not w.isdigit())


def score_offer_against_cv(
    profile: CVProfile,
    title: str,
    body: str,
    required: list[str] | None = None,
    bonus: list[str] | None = None,
    salary: str = "",
) -> OfferScore:
    """Compute a deterministic `/100` match score between a CV profile and a job posting."""
    del salary  # kept for interface compatibility; score is purely content-based
    if not required and not bonus:
        required, bonus = extract_offer_keywords(title, body)
    required = list(required or [])
    bonus = list(bonus or [])

    haystack = profile.full_text
    core = profile.core_text
    title_f = fold(title)

    matched_req = [k for k in required if keyword_found(k, haystack)]
    missing_req = [k for k in required if k not in matched_req]
    matched_bonus = [k for k in bonus if keyword_found(k, haystack)]
    missing_bonus = [k for k in bonus if k not in matched_bonus]

    # 1. Required keywords (55 pts, or 75 pts if no bonus defined) — 2x weight if in job title
    req_max = 55 if bonus else 75
    total_kw = len(required) + len(bonus)
    depth_factor = min(1.0, total_kw / 4.0)
    if required:
        weights = [2.0 if keyword_found(k, title_f) else 1.0 for k in required]
        earned = sum(w for k, w in zip(required, weights, strict=True) if k in matched_req)
        req_ratio = (earned / sum(weights)) * depth_factor
    else:
        req_ratio = 0.0
    req_score = round(req_max * req_ratio)

    # 2. Bonus keywords (20 pts)
    bonus_score = round(20 * (len(matched_bonus) / len(bonus))) if bonus else 0

    # 3. Core CV visibility: headline, summary, skills, current role (15 pts)
    if required:
        core_hits = sum(1 for k in required if keyword_found(k, core))
        core_score = round(15 * (core_hits / len(required)) * depth_factor)
    else:
        core_score = 0

    # 4. Lexical TF-IDF cosine similarity over domain vocabulary (10 pts)
    offer_counts = _domain_tokens((title + " ") * 3 + body)
    cv_counts = _domain_tokens(haystack)
    common = set(offer_counts) & set(cv_counts)
    if offer_counts and cv_counts and common:
        dot = sum((1.0 + math.log(offer_counts[w])) * (1.0 + math.log(cv_counts[w])) for w in common)
        norm_o = math.sqrt(sum((1.0 + math.log(v)) ** 2 for v in offer_counts.values()))
        norm_c = math.sqrt(sum((1.0 + math.log(v)) ** 2 for v in cv_counts.values()))
        cosine = dot / (norm_o * norm_c)
        lexical_score = round(min(1.0, cosine / 0.28) * 10)
    else:
        lexical_score = 0

    total = min(100, req_score + bonus_score + core_score + lexical_score)
    return OfferScore(
        variant=profile.name,
        total=total,
        req_score=req_score,
        bonus_score=bonus_score,
        core_score=core_score,
        lexical_score=lexical_score,
        matched_req=matched_req,
        missing_req=missing_req,
        matched_bonus=matched_bonus,
        missing_bonus=missing_bonus,
    )


def build_cv_profile(variant_name: str, cv: dict[str, Any], texts: list[str], pages: int = 1) -> CVProfile:
    full = " \n ".join(fold(t) for t in texts if t)
    full += " \n " + re.sub(r"-\s*\n\s*", "", full)
    headline = str(cv.get("headline") or "").strip()
    # Core CV: headline + text summary + skills (OneLineEntry) + most recent role (ExperienceEntry)
    core_parts: list[str] = [headline]
    sections = cv.get("sections") or {}
    for entries in sections.values():
        if not isinstance(entries, list) or not entries:
            continue
        if all(isinstance(e, str) for e in entries) or any(
            isinstance(e, dict) and "label" in e and "details" in e for e in entries
        ):
            for _, s in walk_strings(entries):
                core_parts.append(strip_markdown(s))
        elif any(isinstance(e, dict) and "company" in e and "position" in e for e in entries):
            for _, s in walk_strings(entries[0]):
                core_parts.append(strip_markdown(s))

    # Quick structural / ATS weakness summary for the variant
    weaknesses: list[str] = []
    n_ph = sum(len(PLACEHOLDER_RE.findall(raw)) for _, raw in walk_strings(cv))
    if n_ph:
        weaknesses.append(f"{n_ph} placeholder(s) [X]")
    # No "missing headline" check: an empty headline is the standard for FAANG-style resumes (Jake's Resume,
    # r/EngineeringResumes), so it is an editorial choice rather than an ATS weakness.
    free_dates = sum(
        1
        for _, k, raw in entry_dates(cv)
        if not (k == "end_date" and not any(c.isdigit() for c in raw)) and not DATE_RE.fullmatch(raw.strip())
    )
    if free_dates:
        weaknesses.append(f"{free_dates} free-form date(s)")
    if pages > 1:
        weaknesses.append(f"{pages} pages")
    if texts and any(0xE000 <= ord(c) <= 0xF8FF for c in texts[0]):
        weaknesses.append("header icons (show_icons)")

    return CVProfile(
        name=variant_name,
        full_text=full,
        core_text=fold(" \n ".join(core_parts)),
        headline=headline,
        weaknesses=weaknesses,
    )


def load_all_cv_profiles(repo_root: pathlib.Path | None = None) -> list[CVProfile]:
    """Load all `variants/*.yaml` profiles (using rendered PDF if available, else YAML)."""
    root = repo_root or pathlib.Path(__file__).resolve().parent.parent
    profiles: list[CVProfile] = []
    for variant_path in sorted((root / "variants").glob("*.yaml")):
        if variant_path.name.startswith("_"):
            continue
        raw = yaml.safe_load(variant_path.read_text(encoding="utf-8")) or {}
        cv = raw.get("cv") or {}
        out_dir = root / "rendercv_output" / variant_path.stem
        pdfs = sorted(out_dir.glob("*.pdf")) if out_dir.is_dir() else []
        pages = 1
        if pdfs:
            reader = PdfReader(str(pdfs[0]))
            pages = len(reader.pages)
            texts = ["\n".join(page.extract_text() or "" for page in reader.pages)]
        else:
            texts = ["\n".join(strip_markdown(s) for _, s in walk_strings(cv))]
        profiles.append(build_cv_profile(variant_path.stem, cv, texts, pages=pages))
    return profiles


def check_offer(path: pathlib.Path, profile: CVProfile, check: Check) -> None:
    meta, body = load_offer(path)
    fields = get_offer_fields(meta, default_title=path.stem)
    title = fields["title"]
    check.label = f"Job: {fields['company']} — {title}"
    required = fields["required"]
    bonus = fields["bonus"]

    score = score_offer_against_cv(profile, title, body, required, bonus)
    req_total = len(score.matched_req) + len(score.missing_req)
    bonus_total = len(score.matched_bonus) + len(score.missing_bonus)
    parts = [f"score {score.total}/100"]
    if req_total:
        parts.append(f"required {len(score.matched_req)}/{req_total}")
    if bonus_total:
        parts.append(f"bonus {len(score.matched_bonus)}/{bonus_total}")
    check.message = " — ".join(parts[:2]) + (", " + ", ".join(parts[2:]) if len(parts) > 2 else "")
    if score.missing_req:
        check.warn("missing required keywords: " + ", ".join(score.missing_req))
    if score.missing_bonus:
        check.details.append("missing bonus keywords: " + ", ".join(score.missing_bonus))


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


STATUS_COLOR = {PASS: BRIGHT_GREEN, WARN: BRIGHT_YELLOW, FAIL: BRIGHT_RED}


def colorize_inline_scores(text: str) -> str:
    return re.sub(
        r"score\s+(\d+)/100",
        lambda m: f"score {style(m.group(1) + '/100', score_color(int(m.group(1))))}",
        text,
    )


def print_report(variant: pathlib.Path, pdf: pathlib.Path, checks: list[Check], strict: bool) -> None:
    print(f"{style('ATS check', BOLD)} — {style(str(variant), CYAN)}")
    print(f"{style('PDF      ', BOLD)} — {style(str(pdf), DIM)}\n")
    for check in checks:
        tag = style(f"[{check.status.upper()}]", STATUS_COLOR[check.status])
        print(f"{tag} {style(check.label, BOLD)}")
        if check.message:
            print(f"       {colorize_inline_scores(check.message)}")
        for detail in check.details:
            bullet_col = RED if check.status == FAIL else (YELLOW if check.status == WARN else DIM)
            print(f"         {style('-', bullet_col)} {detail}")
    counts = {s: sum(c.status == s for c in checks) for s in (PASS, WARN, FAIL)}
    failed = counts[FAIL] > 0 or (strict and counts[WARN] > 0)
    summary = (
        f"{style(f'{counts[PASS]} PASS', BRIGHT_GREEN)}, "
        f"{style(f'{counts[WARN]} WARN', BRIGHT_YELLOW if counts[WARN] else DIM)}, "
        f"{style(f'{counts[FAIL]} FAIL', BRIGHT_RED if counts[FAIL] else DIM)}"
    )
    res_label = style("FAILED", BRIGHT_RED) if failed else style("OK", BRIGHT_GREEN)
    print(f"\n{style('Summary:', BOLD)} {summary}")
    print(f"{style('Result :', BOLD)} {res_label}" + (" (--strict)" if strict else ""))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check ATS compatibility and job keyword match for a RenderCV variant."
    )
    parser.add_argument("variant", type=pathlib.Path, help="Path to the variant YAML file")
    parser.add_argument(
        "--job",
        dest="jobs",
        type=pathlib.Path,
        action="append",
        default=[],
        help="Job posting Markdown file (with YAML front matter) to score against; repeatable",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--strict", action="store_true", help="Treat WARN as failure")
    parser.add_argument(
        "--ignore-placeholders",
        action="store_true",
        help="Downgrade [X] placeholders from FAIL to WARN",
    )
    parser.add_argument(
        "--langs",
        default="en,fr",
        help="Comma-separated ISO 639-1 language codes for stopwords (default: 'en,fr')",
    )
    args = parser.parse_args()
    set_stopword_langs(args.langs)

    variant = args.variant.resolve()
    try:
        data, model = load_variant(variant)
        pdf = pdf_path_of(model)
        if not pdf.is_file():
            raise FileNotFoundError(f"{pdf} not found: run `make render V={variant.stem}` first")
        reader = PdfReader(str(pdf))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except RenderCVUserValidationError as error:
        print(
            f"Error: invalid RenderCV YAML ({len(error.validation_errors)} validation error(s)); "
            f"run `make render V={variant.stem}` for details",
            file=sys.stderr,
        )
        return 2
    except Exception as error:  # noqa: BLE001 - readable CLI message
        print(f"Error: {error}", file=sys.stderr)
        return 2

    cv = data["cv"]
    fields = cv_fields(cv)
    poppler_text = pdftotext(pdf)
    checks = [
        Check("pdf", "Readable PDF"),
        Check("fidelity", "YAML -> PDF Fidelity (pypdf)"),
        Check("poppler", "Reading Order (Poppler)"),
        Check("contacts", "Contact Info"),
        Check("dates", "Structured Dates"),
        Check("titles", "Section Titles"),
        Check("design", "Design & Formatting"),
        Check("placeholders", "Placeholders"),
    ]
    by_id = {c.id: c for c in checks}
    check_pdf(reader, text, by_id["pdf"])
    check_fidelity(fields, text, by_id["fidelity"])
    check_poppler(fields, poppler_text, by_id["poppler"])
    check_contacts(cv, text, by_id["contacts"])
    check_dates(cv, text, model.locale.present, by_id["dates"])
    check_titles(cv, by_id["titles"])
    check_design(model, by_id["design"])
    check_placeholders(cv, by_id["placeholders"], args.ignore_placeholders)

    profile = build_cv_profile(variant.stem, cv, [text] + ([poppler_text] if poppler_text else []))
    for job_path in args.jobs:
        check = Check(f"job:{job_path.stem}", f"Job: {job_path.stem}")
        try:
            check_offer(job_path, profile, check)
        except (OSError, ValueError, yaml.YAMLError) as error:
            check.fail(str(error))
        checks.append(check)

    fails = sum(c.status == FAIL for c in checks)
    warns = sum(c.status == WARN for c in checks)
    if args.json:
        payload = {
            "variant": str(variant),
            "pdf": str(pdf),
            "strict": args.strict,
            "ready": not fails and not (args.strict and warns),
            "checks": [asdict(c) for c in checks],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_report(variant, pdf, checks, args.strict)
    return 1 if fails or (args.strict and warns) else 0


if __name__ == "__main__":
    raise SystemExit(main())
