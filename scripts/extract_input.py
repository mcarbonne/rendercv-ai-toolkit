#!/usr/bin/env python3
"""Extract text and hyperlinks from raw resume files placed in `input/`.

Supports:
- PDF (`.pdf`) via `pypdf` (plus `pdftotext` if available), including embedded URLs
- Word (`.docx`) via Python stdlib (`zipfile` + `xml.etree.ElementTree`)
- Text / Markdown / YAML / JSON (`.md`, `.txt`, `.yaml`, `.yml`, `.json`)

Files prefixed with `_` (templates) and `master_resume.md` (unless `--include-master`
is passed) are skipped by default so the onboarding skill only reads raw user inputs.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

from pypdf import PdfReader

INPUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "input"
SUPPORTED_EXTS = {".pdf", ".docx", ".md", ".txt", ".yaml", ".yml", ".json"}


def _display_path(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(INPUT_DIR.parent))
    except ValueError:
        return str(path)


def extract_pdf(path: pathlib.Path) -> dict[str, Any]:
    pages_text: list[str] = []
    links: list[str] = []
    seen_links: set[str] = set()
    num_pages: int | None = None

    try:
        reader = PdfReader(str(path))
        num_pages = len(reader.pages)
        for idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages_text.append(f"--- Page {idx} ---\n{text.strip()}")
            annots = page.get("/Annots")
            if annots:
                for annot_ref in annots:
                    try:
                        annot = annot_ref.get_object()
                        action = annot.get("/A")
                        if action and "/URI" in action:
                            uri = str(action["/URI"]).strip()
                            if uri and uri not in seen_links:
                                seen_links.add(uri)
                                links.append(uri)
                    except Exception:  # noqa: BLE001
                        continue
    except Exception as exc:  # noqa: BLE001
        if shutil.which("pdftotext"):
            res = subprocess.run(
                ["pdftotext", str(path), "-"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                pages_text.append(res.stdout.strip())
            else:
                pages_text.append(f"[Could not extract PDF: {exc}]")
        else:
            pages_text.append(f"[Could not extract PDF: {exc}]")

    return {
        "file": _display_path(path),
        "type": "pdf",
        "pages": num_pages,
        "text": "\n\n".join(pages_text).strip(),
        "links": links,
    }


def extract_docx(path: pathlib.Path) -> dict[str, Any]:
    paragraphs: list[str] = []
    links: list[str] = []
    seen_links: set[str] = set()

    with zipfile.ZipFile(path, "r") as zf:
        if "word/document.xml" in zf.namelist():
            xml_bytes = zf.read("word/document.xml")
            root = ET.fromstring(xml_bytes)
            for para in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                texts = [
                    node.text
                    for node in para.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
                    if node.text
                ]
                line = "".join(texts).strip()
                if line:
                    paragraphs.append(line)

        if "word/_rels/document.xml.rels" in zf.namelist():
            rels_bytes = zf.read("word/_rels/document.xml.rels")
            rels_root = ET.fromstring(rels_bytes)
            for rel in rels_root:
                target = rel.attrib.get("Target", "").strip()
                if target.startswith(("http://", "https://", "mailto:")) and target not in seen_links:
                    seen_links.add(target)
                    links.append(target)

    return {
        "file": _display_path(path),
        "type": "docx",
        "pages": None,
        "text": "\n".join(paragraphs).strip(),
        "links": links,
    }


def extract_plain(path: pathlib.Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return {
        "file": _display_path(path),
        "type": path.suffix.lstrip(".").lower(),
        "pages": None,
        "text": text,
        "links": [],
    }


def discover_input_files(
    input_dir: pathlib.Path,
    include_master: bool = False,
) -> list[pathlib.Path]:
    if not input_dir.exists():
        return []
    files: list[pathlib.Path] = []
    for path in sorted(input_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name.startswith("_") or path.name.startswith("."):
            continue
        if not include_master and path.name.lower() == "master_resume.md":
            continue
        if path.suffix.lower() in SUPPORTED_EXTS:
            files.append(path)
    return files


def extract_file(path: pathlib.Path) -> dict[str, Any]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_pdf(path)
    if ext == ".docx":
        return extract_docx(path)
    return extract_plain(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract text and links from raw resume files in input/.")
    parser.add_argument(
        "paths",
        nargs="*",
        type=pathlib.Path,
        help="Optional specific files to extract (defaults to all raw files in input/).",
    )
    parser.add_argument(
        "--include-master",
        action="store_true",
        help="Also include input/master_resume.md in the output.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output extracted content as JSON.",
    )
    args = parser.parse_args()

    if args.paths:
        targets: list[pathlib.Path] = []
        for raw_p in args.paths:
            p = raw_p.expanduser().resolve()
            if p.is_dir():
                for child in sorted(p.rglob("*")):
                    if child.is_file() and not child.name.startswith(".") and child.suffix.lower() in SUPPORTED_EXTS:
                        targets.append(child)
            elif p.is_file():
                targets.append(p)
    else:
        targets = discover_input_files(INPUT_DIR, include_master=args.include_master)

    if not targets:
        msg = "No raw input files found in input/ (place a PDF, DOCX, MD, or TXT file in input/)."
        if args.json:
            print(json.dumps({"files": [], "message": msg}, ensure_ascii=False, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 1

    results = [extract_file(path) for path in targets]

    if args.json:
        print(json.dumps({"files": results}, ensure_ascii=False, indent=2))
        return 0

    for item in results:
        header = f"=== {item['file']} ({item['type'].upper()}) ==="
        print(header)
        print(item["text"])
        if item["links"]:
            print("\n--- Extracted Hyperlinks ---")
            for link in item["links"]:
                print(f"- {link}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
