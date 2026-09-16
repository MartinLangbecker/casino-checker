#!/usr/bin/env python3
"""Re-analyze archived PDFs and rebuild the weekly findings JSONs.

Use after changing consistency rules in casino_analyzer.py to bring the
historical findings/ files in line with the current logic. Operates purely
on archive/ — no downloads.

Usage:
    python reanalyze_archive.py [--dry-run] [--week 2026_kw34] [--verbose]

--dry-run   Show per-week finding-count diffs, write nothing.
--week      Restrict to a single week (repeatable). Default: all.
--verbose   List added/removed findings per week.
"""
import os
import re
import json
import argparse

from casino_core import analyze_pdfs, build_findings_data

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_DIR = os.path.join(PROJECT_DIR, 'archive')
FINDINGS_DIR = os.path.join(PROJECT_DIR, 'findings')

ARCHIVE_RE = re.compile(r'^(20\d{2})_kw(\d{1,2})_([a-z]+)_(.+)\.pdf$')


def group_archive_by_week():
    """Return {(year, kw): [(code, path), ...]} from archive/ PDFs."""
    weeks = {}
    for fn in sorted(os.listdir(ARCHIVE_DIR)):
        m = ARCHIVE_RE.match(fn)
        if not m:
            continue
        year, kw, code = int(m.group(1)), int(m.group(2)), m.group(3)
        weeks.setdefault((year, kw), []).append((code, os.path.join(ARCHIVE_DIR, fn)))
    return weeks


def build_week(year, kw, pdfs):
    """Analyze one week's archived PDFs, return findings_data dict (batch format)."""
    pdfs_by_code = {code: path for code, path in pdfs}
    all_stats, all_issues, all_dishes, errors = analyze_pdfs(pdfs_by_code, year, kw)
    return build_findings_data(
        year, kw, all_stats, all_issues, all_dishes,
        download_errors=0, parse_errors=len(errors),
        extra_meta={'reanalyzed_from_archive': True},
    )


def finding_key(f):
    return (f['casino_code'], f['day'], f['row'], f['issue_type'], f['issue'])


def main():
    parser = argparse.ArgumentParser(description="Re-analyze archived PDFs, rebuild findings JSONs.")
    parser.add_argument('--dry-run', action='store_true', help="Show diffs, write nothing.")
    parser.add_argument('--week', action='append', default=None,
                        help="Restrict to week(s), e.g. 2026_kw34. Repeatable.")
    parser.add_argument('--verbose', action='store_true', help="List added/removed findings.")
    args = parser.parse_args()

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
            with open(out_path, encoding='utf-8') as f:
                old_findings = json.load(f).get('findings', [])

        old_keys = {finding_key(f) for f in old_findings}
        new_keys = {finding_key(f) for f in new_findings}
        added = [f for f in new_findings if finding_key(f) not in old_keys]
        removed = [f for f in old_findings if finding_key(f) not in new_keys]

        total_before += len(old_findings)
        total_after += len(new_findings)

        action = "würde schreiben" if args.dry_run else "geschrieben"
        print(f"{tag}: findings {len(old_findings)} -> {len(new_findings)} "
              f"(+{len(added)} / -{len(removed)}) [{action}]")

        if args.verbose:
            for f in added:
                print(f"    + {f['casino_code']} {f['day']} row{f['row']} "
                      f"[{f['confidence']}] {f['issue']}")
            for f in removed:
                print(f"    - {f['casino_code']} {f['day']} row{f['row']} "
                      f"[{f['confidence']}] {f['issue']}")

        if not args.dry_run:
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)

    mode = "DRY-RUN, nichts geschrieben" if args.dry_run else "geschrieben"
    print(f"\nGesamt: findings {total_before} -> {total_after} [{mode}]")


if __name__ == '__main__':
    main()
