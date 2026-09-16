"""
Batch-Analyse aller DB Casino Speisekarten
==========================================
Downloads all PDFs, archives them, runs signet/allergen consistency check, reports results.
"""
import argparse
import datetime
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from casino_analyzer import CONFIDENCE_ICONS  # noqa: E402
from casino_core import CASINOS, analyze_pdfs, build_findings_data  # noqa: E402

# Project root — used for archive/ and findings/ output directories.
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_URL = "https://casino-net.app.db.de/casinoservice/Speisekarten"

CURL_BIN = "curl.exe" if sys.platform == "win32" else "curl"

logger = logging.getLogger("casino")



def download_pdf(code, target_dir):
    """Download a casino PDF. Returns path or None."""
    url = f"{BASE_URL}/{code}.pdf"
    path = os.path.join(target_dir, f"{code}.pdf")
    result = subprocess.run(
        [CURL_BIN, "-s", "-o", path, "-w", "%{http_code}", url],
        capture_output=True, text=True
    )
    status = result.stdout.strip()
    if status == '200' and os.path.getsize(path) > 1000:
        return path
    return None


def main():
    tmp_dir = os.path.join(tempfile.gettempdir(), 'casino-batch')
    os.makedirs(tmp_dir, exist_ok=True)
    
    # Determine current calendar week for archiving
    today = datetime.date.today()
    year = today.isocalendar()[0]
    calendar_week = today.isocalendar()[1]

    archive_dir = os.path.join(PROJECT_DIR, 'archive')

    print("DB Casino Speisekarten Batch-Analyse")
    print(f"{'='*90}")
    print(f"Casinos: {len(CASINOS)}")
    print(f"Kalenderwoche: {year}/KW{calendar_week:02d}")
    print(f"Archiv: {archive_dir}")
    print()
    
    # Download all
    print("Downloading PDFs...")
    downloaded = {}
    failed_downloads = []
    for code, name in CASINOS.items():
        path = download_pdf(code, tmp_dir)
        if path:
            downloaded[code] = path
        else:
            failed_downloads.append((code, name))
    
    print(f"  ✅ {len(downloaded)} heruntergeladen")
    if failed_downloads:
        print(f"  ❌ {len(failed_downloads)} nicht verfügbar: {', '.join(code for code, _ in failed_downloads)}")
    print()
    
    # Archive all downloaded PDFs
    os.makedirs(archive_dir, exist_ok=True)
    archived = 0
    for code, path in downloaded.items():
        name = CASINOS[code]
        # Extract location from casino name: "Casino Erfurt Bahnhofstraße" -> "Erfurt_Bahnhofstraße"
        location = name.replace('Casino ', '').replace(' ', '_').replace('|', '').replace('/', '-')
        archive_name = f"{year}_kw{calendar_week:02d}_{code}_{location}.pdf"
        archive_path = os.path.join(archive_dir, archive_name)
        shutil.copy2(path, archive_path)
        archived += 1
    
    print(f"Archiviert: {archived} PDFs → {archive_dir}")
    print()
    
    # Analyze all — isolated so a failure here never invalidates the
    # already-completed download+archive step. The weekly PDFs are the
    # critical, non-reproducible artifact; analysis can be re-run anytime
    # from the archive via reanalyze_archive.py.
    print("Analyzing...")
    try:
        all_stats, all_issues, all_dishes, errors = analyze_pdfs(downloaded, year, calendar_week)

        # Progress indicator (per successfully analyzed casino)
        for stat in all_stats:
            status = f"❌ {len(stat['issues'])}" if stat['issues'] else "✅"
            sys.stdout.write(f"  {stat['code']} {stat['name']:<40} {stat['dishes']:>2} Gerichte  {status}\n")
        sys.stdout.flush()

        # Summary
        print(f"\n\n{'#'*90}")
        print("ERGEBNIS")
        print(f"{'#'*90}")
        print(f"  Casinos analysiert:    {len(all_stats)}")
        print(f"  Gerichte gesamt:       {sum(stat['dishes'] for stat in all_stats)}")
        print(f"  Inkonsistenzen:        {len(all_issues)}")
        print(f"  Casinos mit Fehlern:   {len([stat for stat in all_stats if stat['issues']])}")
        print(f"  Casinos fehlerfrei:    {len([stat for stat in all_stats if not stat['issues']])}")
        print(f"  Download-Fehler:       {len(failed_downloads)}")
        print(f"  Parse-Fehler:          {len(errors)}")

        if all_issues:
            print(f"\n{'─'*90}")
            print("ALLE INKONSISTENZEN:")
            print(f"{'─'*90}")
            for issue_record in all_issues:
                confidence_icon = CONFIDENCE_ICONS.get(issue_record['confidence'], '?')
                print(f"\n  {confidence_icon} {issue_record['casino_name']} ({issue_record['casino_code']})")
                print(f"     {issue_record['day']}, {issue_record['category'] or '?'} | Signet: {', '.join(issue_record['signets'])}")
                print(f"     ⚠️  {issue_record['issue']}")
                print(f"     💡 {issue_record['recommendation']['reason']}")

        if errors:
            print(f"\n{'─'*90}")
            print("PARSE-FEHLER:")
            print(f"{'─'*90}")
            for code, name, err in errors:
                print(f"  {code} {name}: {err}")

        if failed_downloads:
            print(f"\n{'─'*90}")
            print("NICHT VERFÜGBAR:")
            print(f"{'─'*90}")
            for code, name in failed_downloads:
                print(f"  {code} {name}")

        # Write findings as JSON
        findings_dir = os.path.join(PROJECT_DIR, 'findings')
        os.makedirs(findings_dir, exist_ok=True)
        findings_path = os.path.join(findings_dir, f"{year}_kw{calendar_week:02d}_findings.json")

        findings_data = build_findings_data(
            year, calendar_week, all_stats, all_issues, all_dishes,
            download_errors=len(failed_downloads), parse_errors=len(errors),
        )

        with open(findings_path, 'w', encoding='utf-8') as findings_file:
            json.dump(findings_data, findings_file, ensure_ascii=False, indent=2)

        print(f"\nFindings gespeichert: {findings_path}")
    except Exception as analysis_error:
        logger.exception("Analyse fehlgeschlagen")
        print(f"\n⚠️  Analyse fehlgeschlagen: {analysis_error}")
        print(f"    Download und Archiv sind abgeschlossen ({archived} PDFs). "
              f"Analyse nachholbar mit: reanalyze_archive.py")

    # Cleanup tmp directory
    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Download, archive and analyze all DB casino menus.")
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="Log full tracebacks for parse/analysis errors (DEBUG level).")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
