#!/usr/bin/env python3
"""Reset personal/example data in the repository to start fresh for a new user.

Removes:
- `input/*` (except files starting with `_` or `.`, e.g., `_template_master_resume.md`)
- `variants/*.yaml` (except files starting with `_`)
- `jobs/*.md` (except `_template.md` and `README.md`)
- `rendercv_output/*`

By default, asks for interactive confirmation unless `--yes` is passed.
Use `--dry-run` to preview what would be removed without deleting anything.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def collect_targets() -> list[pathlib.Path]:
    targets: list[pathlib.Path] = []

    input_dir = ROOT / "input"
    if input_dir.exists():
        for p in sorted(input_dir.iterdir()):
            if p.name.startswith("_") or p.name.startswith("."):
                continue
            targets.append(p)

    variants_dir = ROOT / "variants"
    if variants_dir.exists():
        for p in sorted(variants_dir.glob("*.yaml")):
            if p.name.startswith("_"):
                continue
            targets.append(p)

    jobs_dir = ROOT / "jobs"
    if jobs_dir.exists():
        for p in sorted(jobs_dir.glob("*.md")):
            if p.name.startswith("_") or p.name.lower() == "readme.md":
                continue
            targets.append(p)

    output_dir = ROOT / "rendercv_output"
    if output_dir.exists():
        for p in sorted(output_dir.iterdir()):
            if p.name.startswith("."):
                continue
            targets.append(p)

    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean personal/example data to start a fresh resume workspace.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files/folders that would be deleted without removing them.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with code 1 if any personal/example files are present (for hooks/CI).",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip interactive confirmation prompt.",
    )
    args = parser.parse_args()

    targets = collect_targets()
    if not targets:
        print("Workspace is already clean (no personal/example files found).")
        return 0

    if args.check:
        print("ERROR: Personal/example files detected in workspace:", file=sys.stderr)
        for t in targets:
            rel = t.relative_to(ROOT)
            suffix = "/" if t.is_dir() else ""
            print(f"  - {rel}{suffix}", file=sys.stderr)
        return 1

    print("The following personal/example files and directories will be removed:")
    for t in targets:
        rel = t.relative_to(ROOT)
        suffix = "/" if t.is_dir() else ""
        print(f"  - {rel}{suffix}")

    if args.dry_run:
        print("\nDry run complete. Nothing was deleted.")
        return 0

    if not args.yes:
        try:
            answer = input("\nProceed with deletion? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in {"y", "yes"}:
            print("Aborted.")
            return 1

    for t in targets:
        if t.is_dir():
            shutil.rmtree(t)
        else:
            t.unlink(missing_ok=True)

    print("\nWorkspace reset complete! Next steps:")
    print("  1. Drop your existing resume (PDF/DOCX/MD) into `input/`")
    print("  2. Ask your AI assistant to run the `resume-onboarding` (or `resume-workflow`) skill.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
