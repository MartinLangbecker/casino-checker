"""
DB Casino Speisekarten-Analyzer — facade + CLI.
===============================================
Thin aggregation layer over the split modules. Kept as the historical import
surface so existing callers (casino_core, casino_report) and the CLI keep working:

    signet_classifier — pixel-based icon recognition
    pdf_extractor      — PDF → dish records
    consistency        — signet/allergen/keyword rule checks
    constants          — shared signets, keywords, allergen sets

Standalone usage:
    python casino_analyzer.py <pdf_path>
"""
import sys

sys.stdout.reconfigure(encoding='utf-8')

from consistency import check_consistency  # noqa: E402, F401
from constants import (  # noqa: E402, F401 — re-exported for backwards compatibility
    CONFIDENCE_ICONS,
    MEAT_FISH_SIGNETS,
    NON_DIET_SIGNETS,
    SACHBEZUGSWERT,
    SIGNET_ORDER,
)
from pdf_extractor import extract_menu, extract_page  # noqa: E402, F401
from signet_classifier import classify_signet, crop_to_content  # noqa: E402, F401


def main():
    if len(sys.argv) < 2:
        print("Usage: python casino_analyzer.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    results, casino_name, date_range = extract_menu(pdf_path)

    if not results:
        print("Keine Gerichte extrahiert")
        sys.exit(1)

    print(f"{casino_name} ({date_range})")
    print(f"{len(results)} Gerichte\n")

    for dish_record in results:
        signet_str = ', '.join(dish_record['signets']) if dish_record['signets'] else '—'
        issues = check_consistency(dish_record)
        status = '✅' if not issues else '❌ ' + '; '.join(issue['issue'] for issue in issues)
        addon = ' [Add-on]' if dish_record.get('is_addon') else ''
        price = f" {dish_record['price_db']:.2f}€" if dish_record.get('price_db') else ''
        print(f"  [{signet_str:15s}] {dish_record['category']:25s}{price}{addon} {status}")


if __name__ == '__main__':
    main()
