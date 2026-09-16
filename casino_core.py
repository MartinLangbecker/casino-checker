"""
Casino Core — Analyse-Aggregation
=================================
Geteilte Analyse-, Statistik- und Aggregationslogik für die Casino-Checker-Pipeline.
Verwendet von casino_batch.py (wöchentlicher Live-Download) und reanalyze_archive.py
(Re-Analyse aus dem Archiv).

Enthält:
- CASINOS: Mapping der Casino-Kürzel auf Klarnamen
- _price_stats / _signet_stats: Preis- und Signet-Statistik pro Gerichtmenge
- analyze_pdfs: Extraktion und Konsistenzprüfung einer Menge von PDFs
- build_findings_data: Aufbau der Findings-JSON-Struktur (meta/statistics/casinos/findings)

Die Funktionen arbeiten rein auf übergebenen PDF-Pfaden und liefern Datenstrukturen
zurück. Aufrufer verantworten Download, Konsolenausgabe und das Schreiben der JSON-Dateien.
"""
import datetime
from statistics import median
from collections import Counter

from casino_analyzer import (
    extract_menu, check_consistency,
    SACHBEZUGSWERT, SIGNET_ORDER, NON_DIET_SIGNETS,
)

# All known casino PDFs from the DB Planet listing
CASINOS = {
    # Basel
    'fba': 'Casino Basel',
    # Berlin
    'bbu': 'Casino Berlin Potsdamer Platz',
    'bdg': 'Casino Berlin Buchberger Straße',
    'bds': 'Casino Berlin Schöneweide',
    'bbm': 'Casino Berlin Granitzstraße',
    'bdo': 'Casino Hauptbahnhof Berlin',
    'bdj': 'Casino ICE-Betriebswerk Berlin',
    'bdm': 'Casino Berlin Markgrafendamm',
    'bdn': 'Casino Nordbahnhof Berlin',
    'bbo': 'Casino Ostbahnhof Berlin',
    # Bremen
    'acc': 'Casino Werk Bremen',
    # Cottbus
    'bca': 'Casino Werk Cottbus',
    # Dessau
    'ehc': 'Casino Werk Dessau',
    # Dortmund
    'chd': 'Casino Dortmund Werkmeisterstraße',
    # Dresden
    'eda': 'Casino Dresden Ammonstraße',
    # Duisburg
    'cde': 'Casino Duisburg Masurenallee',
    'cdd': 'Casino Duisburg Hansastraße',
    # Düsseldorf
    'cnb': 'Casino Werk Düsseldorf',
    # Erfurt
    'dec': 'Casino Erfurt Bahnhofstraße',
    # Frankfurt
    'dhh': 'Casino Frankfurt Adlerwerke',
    'dhp': 'Casino Frankfurt DB Brick | DB Tower',
    'dhz': 'Casino Frankfurt Netzwerk',
    'dhc': 'Casino Frankfurt Griesheim',
    'dfs': 'Casino Frankfurt Silberturm',
    'dhg': 'Casino Frankfurt Galluspark',
    'dha': 'Casino Hauptbahnhof Frankfurt',
    # Fulda
    'dbc': 'Casino Fulda',
    # Hamburg
    'aec': 'Casino Hamburg Försterweg',
    'aef': 'Casino Hamburg Hammerbrookhöfe',
    'ada': 'Casino Hauptbahnhof Hamburg',
    'aeb': 'Casino ICE-Betriebswerk Hamburg',
    'adb': 'Casino S-Bahn Hamburg',
    # Hamm
    'chl': 'Casino Hamm Unionstraße',
    'cha': 'Casino Hamm Banningstraße',
    # Hannover
    'ahu': 'Casino Hannover Lindemannallee',
    'ahz': 'Casino Hannover Lister Dreieck',
    # Karlsruhe
    'fln': 'Casino Karlsruhe Schwarzwaldstraße',
    # Kassel
    'clm': 'Casino Kassel Wilhelmshöhe',
    'clb': 'Casino Werk Kassel',
    # Krefeld
    'cma': 'Casino Werk Krefeld',
    # Köln
    'ckc': 'Casino Hauptbahnhof Köln',
    'cke': 'Casino Köln Deutz',
    'ckb': 'Casino Köln Gladbacher Wall',
    'ckf': 'Casino Köln Gremberg',
    'ckn': 'Casino Köln Nippes',
    # Leipzig
    'elp': 'Casino Leipzig Brandenburgerstraße',
    'ela': 'Casino Hauptbahnhof Leipzig',
    # Ludwigshafen
    'fmd': 'Casino Ludwigshafen',
    # Magdeburg
    'bmj': 'Casino Hauptbahnhof Magdeburg',
    # Mainz
    'dmk': 'Casino Mainz Rheinstraße',
    # Mannheim
    'fmk': 'Casino Hauptbahnhof Mannheim',
    # Maschen
    'adh': 'Casino Maschen',
    # Minden
    'cof': 'Casino Minden Pionierstraße',
    # München
    'gha': 'Casino Hauptbahnhof München',
    'gmg': 'Casino ICE-Betriebswerk München',
    'geb': 'Casino München Bergsonstraße',
    'gms': 'Casino München Freimann',
    'gma': 'Casino München Richelstraße',
    'gmn': 'Casino Rangierbahnhof München',
    'gme': 'Casino S-Bahn München',
    # Neumünster
    'ana': 'Casino Werk Neumünster',
    # Neuseddin
    'bpe': 'Casino Neuseddin',
    # Nürnberg
    'goa': 'Casino Hauptbahnhof Nürnberg',
    'gna': 'Casino Nürnberg Sandstraße',
    'gpb': 'Casino Rangierbahnhof Nürnberg',
    'gpa': 'Casino Werk Nürnberg',
    # Offenburg
    'foc': 'Casino Offenburg',
    # Paderborn
    'cpb': 'Casino Werk Paderborn',
    # Plochingen
    'fpa': 'Casino Plochingen',
    # Saarbrücken
    'fra': 'Casino Hauptbahnhof Saarbrücken',
    # Seelze
    'ahq': 'Casino Seelze',
    # Stuttgart
    'fsa': 'Casino Hauptbahnhof Stuttgart',
    # Trier
    'ftc': 'Casino Trier',
    # Tübingen
    'fpe': 'Casino Tübingen',
    # Witten
    'cgw': 'Casino Werk Witten',
    # Wittenberge
    'bwg': 'Casino Werk Wittenberge',
    # Würzburg
    'dwf': 'Casino Hauptbahnhof Würzburg',
    # Wuppertal
    'cwe': 'Casino Trainingszentrum Wuppertal',
    'cwa': 'Casino Werk Wuppertal',
}


def _price_stats(prices):
    """Compute min/max/median/avg for a list of prices."""
    if not prices:
        return None
    return {
        'count': len(prices),
        'min': round(min(prices), 2),
        'max': round(max(prices), 2),
        'median': round(median(prices), 2),
        'avg': round(sum(prices) / len(prices), 2),
    }


def _signet_stats(dishes):
    """Compute signet distribution and price stats for a list of dishes."""
    regular_dishes = [dish for dish in dishes if not dish.get('is_addon')]
    addon_dishes = [dish for dish in dishes if dish.get('is_addon')]

    signet_groups = {}
    prices = []
    for dish in regular_dishes:
        price = dish.get('price_db')
        if price:
            prices.append(price)
        for signet in dish['signets']:
            if signet in NON_DIET_SIGNETS:
                continue
            if signet not in signet_groups:
                signet_groups[signet] = {'count': 0, 'prices': []}
            signet_groups[signet]['count'] += 1
            if price:
                signet_groups[signet]['prices'].append(price)

    total_with_signet = sum(group['count'] for group in signet_groups.values())

    by_signet = {}
    for signet in SIGNET_ORDER:
        group = signet_groups.get(signet, {'count': 0, 'prices': []})
        if group['count'] > 0:
            by_signet[signet] = {
                'count': group['count'],
                'ratio': round(group['count'] / total_with_signet, 3) if total_with_signet else 0,
                'price': _price_stats(group['prices']),
            }

    vegan_count = signet_groups.get('VEGAN', {'count': 0})['count']

    # Vegan strategy metrics
    vegan_dishes = [dish for dish in regular_dishes if 'VEGAN' in dish['signets']]
    vegan_strategy = None
    if vegan_dishes:
        vegan_with_price = [dish for dish in vegan_dishes if dish.get('price_db')]
        vegan_at_stammessen = sum(1 for dish in vegan_with_price if dish['price_db'] == SACHBEZUGSWERT)
        vegan_at_row0 = sum(1 for dish in vegan_dishes if dish['row'] == 0)
        vegan_neutral_name = sum(1 for dish in vegan_dishes
                                 if dish['category'] and 'vegan' not in dish['category'].lower())

        # Multi-option: count days with >1 vegan
        vegan_per_day = Counter(dish['day'] for dish in vegan_dishes)
        days_with_multi = sum(1 for day_count in vegan_per_day.values() if day_count > 1)

        vegan_strategy = {
            'count': len(vegan_dishes),
            'row0_ratio': round(vegan_at_row0 / len(vegan_dishes), 3),
            'stammessen_ratio': round(vegan_at_stammessen / len(vegan_with_price), 3) if vegan_with_price else 0,
            'neutral_name_ratio': round(vegan_neutral_name / len(vegan_dishes), 3),
            'days_with_choice': days_with_multi,
            'days_total': len(vegan_per_day),
        }

    return {
        'dishes': len(regular_dishes),
        'addons': len(addon_dishes),
        'with_price': len(prices),
        'price': _price_stats(prices),
        'vegan_ratio': round(vegan_count / total_with_signet, 3) if total_with_signet else 0,
        'by_signet': by_signet,
        'vegan_strategy': vegan_strategy,
    }


def analyze_pdfs(pdfs_by_code, year, calendar_week):
    """Extract + consistency-check a set of PDFs.

    Args:
        pdfs_by_code: dict {casino_code: pdf_path}
        year, calendar_week: for finding ID generation

    Returns:
        (all_stats, all_issues, all_dishes, errors)
        - all_stats:  per-casino dicts (code, name, dishes, days, issues, results)
        - all_issues: flat list of issue_record dicts
        - all_dishes: flat list of dish records (for statistics)
        - errors:     list of (code, name, message) for parse failures
    """
    all_issues = []
    all_dishes = []
    all_stats = []
    errors = []

    for code, path in sorted(pdfs_by_code.items()):
        name = CASINOS.get(code, code)
        try:
            results, casino_name, date_range = extract_menu(path)
            if not results:
                errors.append((code, name, "Keine Gerichte extrahiert"))
                continue

            stats = {
                'code': code,
                'name': name,
                'dishes': len(results),
                'days': len(set(dish_record['day'] for dish_record in results)),
                'issues': [],
                'results': results,
            }
            all_dishes.extend(results)

            for dish_record in results:
                issues = check_consistency(dish_record)
                for finding in issues:
                    issue_record = {
                        'id': f"{year}_kw{calendar_week:02d}_{code}_{dish_record['day'][:2].lower()}_{dish_record['row']}",
                        'casino_code': code,
                        'casino_name': name,
                        'day': dish_record['day'],
                        'row': dish_record['row'],
                        'category': dish_record['category'],
                        'signets': dish_record['signets'],
                        'allergene': [allergen.strip() for allergen in dish_record['allergene'].split(',') if allergen.strip()],
                        'confidence': finding['confidence'],
                        'issue_type': finding['issue_type'],
                        'issue': finding['issue'],
                        'recommendation': finding['recommendation'],
                    }
                    stats['issues'].append(issue_record)
                    all_issues.append(issue_record)

            all_stats.append(stats)

        except Exception as error:
            errors.append((code, name, str(error)[:80]))

    return all_stats, all_issues, all_dishes, errors


def build_findings_data(year, calendar_week, all_stats, all_issues, all_dishes,
                        download_errors=0, parse_errors=0, extra_meta=None):
    """Assemble the findings JSON structure (meta/statistics/casinos/findings).

    extra_meta: optional dict merged into the meta block (e.g. source markers).
    """
    statistics = _signet_stats(all_dishes)

    casinos_stats = {}
    for stat in all_stats:
        results = stat.get('results', [])
        if results:
            casinos_stats[stat['code']] = {
                'name': stat['name'],
                **_signet_stats(results),
            }

    meta = {
        'year': year,
        'kw': calendar_week,
        'timestamp': datetime.datetime.now().isoformat(),
        'casinos_analyzed': len(all_stats),
        'dishes_total': sum(stat['dishes'] for stat in all_stats),
        'findings_count': len(all_issues),
        'casinos_with_issues': len([stat for stat in all_stats if stat['issues']]),
        'casinos_clean': len([stat for stat in all_stats if not stat['issues']]),
        'download_errors': download_errors,
        'parse_errors': parse_errors,
    }
    if extra_meta:
        meta.update(extra_meta)

    return {
        'meta': meta,
        'statistics': statistics,
        'casinos': casinos_stats,
        'findings': all_issues,
    }
