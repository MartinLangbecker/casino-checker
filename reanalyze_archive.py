#!/usr/bin/env python3
"""Re-analyze archived PDFs and rebuild the weekly findings JSONs.

Use after changing consistency rules (consistency.py) to bring the historical
findings/ files in line with the current logic. Operates purely on archive/ —
no downloads.

Usage:
    python reanalyze_archive.py [--dry-run] [--week 2026_kw34] [--verbose] [--debug]

--dry-run   Show per-week finding-count diffs, write nothing.
--week      Restrict to a single week (repeatable). Default: all.
--verbose   List added/removed findings per week.
--debug     Log full tracebacks for parse errors (DEBUG level).
"""
import argparse
import json
import logging
import os
import re

from casino_core import analyze_pdfs, build_findings_data

logger = logging.getLogger("casino")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_DIR = os.path.join(PROJECT_DIR, 'archive')
FINDINGS_DIR = os.path.join(PROJECT_DIR, 'findings')

ARCHIVE_RE = re.compile(r'^(20\d{2})_kw(\d{1,2})_([a-z]+)_(.+)\.pdf$')


def group_archive_by_week():
    """Return {(year, kw): [(code, path), ...]} from archive/ PDFs."""
    weeks = {}
    for filename in sorted(os.listdir(ARCHIVE_DIR)):
        match = ARCHIVE_RE.match(filename)
        if not match:
            continue
        year, kw, code = int(match.group(1)), int(match.group(2)), match.group(3)
        weeks.setdefault((year, kw), []).append((code, os.path.join(ARCHIVE_DIR, filename)))
    return weeks


def build_week(year, kw, pdfs):
    """Analyze one week's archived PDFs, return findings_data dict (batch format)."""
    pdfs_by_code = dict(pdfs)
    all_stats, all_issues, all_dishes, errors = analyze_pdfs(pdfs_by_code, year, kw)
    return build_findings_data(
        year, kw, all_stats, all_issues, all_dishes,
        download_errors=0, parse_errors=len(errors),
        extra_meta={'reanalyzed_from_archive': True},
    )


def finding_key(finding):
    return (finding['casino_code'], finding['day'], finding['row'],
            finding['issue_type'], finding['issue'])


def main():
    parser = argparse.ArgumentParser(description="Re-analyze archived PDFs, rebuild findings JSONs.")
    parser.add_argument('--dry-run', action='store_true', help="Show diffs, write nothing.")
    parser.add_argument('--week', action='append', default=None,
                        help="Restrict to week(s), e.g. 2026_kw34. Repeatable.")
    parser.add_argument('--verbose', action='store_true', help="List added/removed findings.")
    parser.add_argument('--debug', action='store_true',
                        help="Log full tracebacks for parse errors (DEBUG level).")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    weeks = group_archive_by_week()
    if not weeks:
        print("Keine archivierten PDFs gefunden.")
        return

    week_filter = set(args.week) if args.week else None
    total_before = total_after = 0

    for (year, kw) in sorted(weeks):
        tag = f"{year}_kw{kw:02d}"
        if week_filter and tag not in week_filter:
            continue

        new_data = build_week(year, kw, weeks[(year, kw)])
        new_findings = new_data['findings']

        out_path = os.path.join(FINDINGS_DIR, f"{tag}_findings.json")
        old_findings = []
        if os.path.exists(out_path):
            with open(out_path, encoding='utf-8') as findings_file:
                old_findings = json.load(findings_file).get('findings', [])

        old_keys = {finding_key(finding) for finding in old_findings}
        new_keys = {finding_key(finding) for finding in new_findings}
        added = [finding for finding in new_findings if finding_key(finding) not in old_keys]
        removed = [finding for finding in old_findings if finding_key(finding) not in new_keys]

        total_before += len(old_findings)
        total_after += len(new_findings)

        action = "würde schreiben" if args.dry_run else "geschrieben"
        print(f"{tag}: findings {len(old_findings)} -> {len(new_findings)} "
              f"(+{len(added)} / -{len(removed)}) [{action}]")

        if args.verbose:
            for finding in added:
                print(f"    + {finding['casino_code']} {finding['day']} row{finding['row']} "
                      f"[{finding['confidence']}] {finding['issue']}")
            for finding in removed:
                print(f"    - {finding['casino_code']} {finding['day']} row{finding['row']} "
                      f"[{finding['confidence']}] {finding['issue']}")

        if not args.dry_run:
            with open(out_path, 'w', encoding='utf-8') as findings_file:
                json.dump(new_data, findings_file, ensure_ascii=False, indent=2)

    mode = "DRY-RUN, nichts geschrieben" if args.dry_run else "geschrieben"
    print(f"\nGesamt: findings {total_before} -> {total_after} [{mode}]")


if __name__ == '__main__':
    main()
