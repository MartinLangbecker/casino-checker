"""
DB Casino Speisekarten — Analyse & Trends
==========================================
Reads weekly findings JSONs and generates trend reports, casino scorecards,
anomaly detection, and repeat-offender tracking.

Usage:
    python casino_report.py [--mode MODE] [--casino CODE] [--top N] [-q]

Modes:
    overview   Weekly overview with key metrics (default)
    trend      Multi-week trend analysis (signets, prices, vegan strategy)
    scorecard  Casino rankings by vegan strategy metrics
    anomaly    Week-over-week changes per casino
    findings   Aggregated findings with repeat-offender detection
    all        Run all modes
"""
import argparse
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Single source of truth for signet order and confidence icons.
from constants import CONFIDENCE_ICONS, SIGNET_ORDER  # noqa: E402

FINDINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'findings')


# =============================================================================
# DATA LOADING
# =============================================================================

def load_all_weeks():
    """Load all findings JSONs sorted by (year, kw)."""
    pattern = os.path.join(FINDINGS_DIR, '*_kw*_findings.json')
    files = sorted(glob.glob(pattern))
    weeks = []
    for path in files:
        with open(path, encoding='utf-8') as findings_file:
            weeks.append(json.load(findings_file))
    return weeks


def week_label(week):
    return f"KW{week['meta']['kw']:02d}"


def week_labels(weeks):
    return [week_label(week) for week in weeks]


def casino_view(week, code):
    """Return a statistics-shaped view for a single casino, or None if absent.

    The per-casino object in week['casinos'][code] mirrors the aggregate
    week['statistics'] structure (by_signet, vegan_ratio, vegan_strategy, price,
    dishes, addons), so it can be used as a drop-in stats source when filtering.
    """
    casino = week['casinos'].get(code)
    if not casino:
        return None
    return {
        'dishes': casino.get('dishes', 0),
        'addons': casino.get('addons', 0),
        'by_signet': casino.get('by_signet', {}),
        'vegan_ratio': casino.get('vegan_ratio', 0),
        'vegan_strategy': casino.get('vegan_strategy'),
        'price': casino.get('price', {}),
        'name': casino.get('name', code),
    }


# =============================================================================
# OVERVIEW
# =============================================================================

def print_overview(weeks, quiet=False, casino_filter=None):
    """Print a summary table across all available weeks."""
    week = weeks[-1]
    meta = week['meta']

    if casino_filter:
        stats = casino_view(week, casino_filter)
        if stats is None:
            print(f'  Casino {casino_filter} in {week_label(week)} nicht vorhanden.')
            return
        casino_finding_count = sum(1 for finding in week['findings']
                                   if finding.get('casino_code') == casino_filter)
    else:
        stats = week['statistics']

    print()
    print('=' * 70)
    if casino_filter:
        print(f'  DB CASINO CHECKER — {meta["year"]}/KW{meta["kw"]:02d} — {casino_filter} ({stats["name"]})')
    else:
        print(f'  DB CASINO CHECKER — {meta["year"]}/KW{meta["kw"]:02d}')
    print('=' * 70)
    print()
    if casino_filter:
        print(f'  Gerichte:      {stats["dishes"]} (+{stats["addons"]} Add-ons)')
        print(f'  Findings:      {casino_finding_count}')
    else:
        print(f'  Casinos:       {meta["casinos_analyzed"]} analysiert, {meta["casinos_clean"]} fehlerfrei, {meta["parse_errors"]} Parse-Fehler')
        print(f'  Gerichte:      {stats["dishes"]} (+{stats["addons"]} Add-ons)')
        print(f'  Findings:      {meta["findings_count"]} ({meta["casinos_with_issues"]} Casinos betroffen)')
    print()

    # Signet distribution
    print(f'  {"Signet":16} {"Anzahl":>8} {"Anteil":>8} {"Ø Preis":>10}')
    print(f'  {"─" * 16} {"─" * 8} {"─" * 8} {"─" * 10}')
    for signet in SIGNET_ORDER:
        signet_stats = stats['by_signet'].get(signet)
        if signet_stats:
            avg = f'{signet_stats["price"]["avg"]:.2f}€' if signet_stats.get('price') else '—'
            print(f'  {signet:16} {signet_stats["count"]:>8} {signet_stats["ratio"]:>7.1%} {avg:>10}')

    print()
    total_meat = sum(stats['by_signet'].get(signet, {}).get('count', 0)
                     for signet in ['SCHWEIN', 'SCHWEIN+RIND', 'RIND', 'GEFLÜGEL', 'FISCH'])
    total_plant = sum(stats['by_signet'].get(signet, {}).get('count', 0)
                      for signet in ['VEGAN', 'VEGETARISCH'])
    print(f'  Pflanzlich: {total_plant} ({total_plant / stats["dishes"]:.1%})  |  Tierisch: {total_meat} ({total_meat / stats["dishes"]:.1%})')

    # Vegan strategy
    strategy = stats.get('vegan_strategy')
    if strategy:
        print()
        print('  Vegan-Steuerung:')
        print(f'    Platzierung (Row 0):  {strategy["row0_ratio"]:.1%}   (Ziel: 100%)')
        print(f'    Stammessen-Preis:    {strategy["stammessen_ratio"]:.1%}   (Ziel: ≥50%)')
        print(f'    Neutraler Name:      {strategy["neutral_name_ratio"]:.1%}   (Ziel: ≥50%)')

    # Casinos without vegan (only meaningful in aggregate view)
    if not casino_filter:
        casinos = week['casinos']
        zero_vegan = [(code, casino['name']) for code, casino in casinos.items()
                      if casino.get('vegan_ratio', 0) == 0]
        print()
        print(f'  Casinos ohne Vegan: {len(zero_vegan)} von {len(casinos)} ({len(zero_vegan) / len(casinos):.0%})')
        if not quiet and zero_vegan:
            for code, name in sorted(zero_vegan)[:10]:
                print(f'    {code:5} {name}')
            if len(zero_vegan) > 10:
                print(f'    ... und {len(zero_vegan) - 10} weitere')
    print()


# =============================================================================
# TREND
# =============================================================================

def print_trend(weeks, casino_filter=None):
    """Print multi-week trend analysis."""
    if len(weeks) < 2:
        print('  Trend-Analyse benötigt mindestens 2 Wochen Daten.')
        return

    # When filtering, drop weeks where the casino is absent so trends stay valid.
    if casino_filter:
        weeks = [week for week in weeks if casino_view(week, casino_filter) is not None]
        if len(weeks) < 2:
            print(f'  Casino {casino_filter}: zu wenige Wochen mit Daten für Trend.')
            return

    def stats_of(week):
        return casino_view(week, casino_filter) if casino_filter else week['statistics']

    def findings_of(week):
        if casino_filter:
            return [finding for finding in week['findings']
                    if finding.get('casino_code') == casino_filter]
        return week['findings']

    labels = week_labels(weeks)

    print()
    print('=' * 70)
    if casino_filter:
        casino_name = casino_view(weeks[-1], casino_filter)['name']
        print(f'  TREND-ANALYSE — {casino_filter} ({casino_name})')
    else:
        print('  TREND-ANALYSE')
    print('=' * 70)

    # Key metrics
    print()
    header = f'  {"":20}'
    for label in labels:
        header += f' {label:>8}'
    header += f'  {"Δ":>8}'
    print(header)
    print(f'  {"─" * 20}' + f' {"─" * 8}' * len(labels) + f'  {"─" * 8}')

    if casino_filter:
        metrics = [
            ('Gerichte', lambda week: stats_of(week)['dishes']),
            ('Findings', lambda week: len(findings_of(week))),
            ('Findings (high)', lambda week: sum(1 for finding in findings_of(week) if finding.get('confidence') == 'high')),
        ]
    else:
        metrics = [
            ('Casinos', lambda week: week['meta']['casinos_analyzed']),
            ('Gerichte', lambda week: week['statistics']['dishes']),
            ('Findings', lambda week: week['meta']['findings_count']),
            ('Findings (high)', lambda week: sum(1 for finding in week['findings'] if finding.get('confidence') == 'high')),
            ('Ohne Vegan', lambda week: sum(1 for casino in week['casinos'].values() if casino.get('vegan_ratio', 0) == 0)),
        ]

    for label, metric_fn in metrics:
        values = [metric_fn(week) for week in weeks]
        row = f'  {label:20}'
        for value in values:
            row += f' {value:>8}'
        delta = values[-1] - values[0]
        trend = f'+{delta}' if delta > 0 else str(delta) if delta < 0 else '='
        row += f'  {trend:>8}'
        print(row)

    # Signet counts
    print()
    print('  Signet-Entwicklung:')
    print(f'  {"":20}' + ''.join(f' {label:>8}' for label in labels) + f'  {"Δ":>8}')
    print(f'  {"─" * 20}' + f' {"─" * 8}' * len(labels) + f'  {"─" * 8}')

    for signet in SIGNET_ORDER:
        values = [stats_of(week)['by_signet'].get(signet, {}).get('count', 0) for week in weeks]
        delta = values[-1] - values[0]
        trend = f'+{delta}' if delta > 0 else str(delta) if delta < 0 else '='
        row = f'  {signet:20}'
        for value in values:
            row += f' {value:>8}'
        row += f'  {trend:>8}'
        print(row)

    # Vegan ratio
    print()
    print('  Vegan-Anteil:')
    values = [stats_of(week)['vegan_ratio'] for week in weeks]
    row = f'  {"Anteil gesamt":20}'
    for value in values:
        row += f' {value:>7.1%} '
    delta = values[-1] - values[0]
    trend = f'{delta:+.1%}' if abs(delta) > 0.001 else '='
    row += f'  {trend:>8}'
    print(row)

    # Vegan strategy metrics
    vegan_metrics = [
        ('Row-0 (Platzierung)', 'row0_ratio'),
        ('Stammessen-Preis', 'stammessen_ratio'),
        ('Neutraler Name', 'neutral_name_ratio'),
    ]
    for label, key in vegan_metrics:
        values = []
        for week in weeks:
            strategy = stats_of(week).get('vegan_strategy')
            values.append(strategy.get(key, 0) if strategy else 0)
        delta = values[-1] - values[0]
        trend = f'{delta:+.1%}' if abs(delta) > 0.001 else '='
        row = f'  {label:20}'
        for value in values:
            row += f' {value:>7.1%} '
        row += f'  {trend:>8}'
        print(row)

    # Price trends
    print()
    print('  Preise (Ø):')
    for signet in SIGNET_ORDER:
        values = [stats_of(week)['by_signet'].get(signet, {}).get('price', {}).get('avg', 0) for week in weeks]
        if all(value == 0 for value in values):
            continue
        delta = values[-1] - values[0]
        trend = f'{delta:+.2f}€' if abs(delta) > 0.01 else '='
        row = f'  {signet:20}'
        for value in values:
            row += f' {value:>7.2f}€'
        row += f'  {trend:>8}'
        print(row)

    print()


# =============================================================================
# SCORECARD
# =============================================================================

def print_scorecard(weeks, top=20, casino_filter=None):
    """Rank casinos by vegan strategy composite score."""
    week = weeks[-1]
    if casino_filter:
        casino = week['casinos'].get(casino_filter)
        if not casino:
            print(f'  Casino {casino_filter} in {week_label(week)} nicht vorhanden.')
            return
        casinos = {casino_filter: casino}
    else:
        casinos = week['casinos']

    print()
    print('=' * 70)
    print('  CASINO SCORECARDS')
    print('=' * 70)

    # Calculate composite score per casino
    scores = []
    for code, casino in casinos.items():
        strategy = casino.get('vegan_strategy')
        vegan_ratio = casino.get('vegan_ratio', 0)
        dishes = casino.get('dishes', 0)
        if dishes == 0:
            continue

        # Composite: weighted sum of strategy metrics
        # All 0–1 range, higher = better
        if strategy:
            score = (
                vegan_ratio * 30 +                          # vegan ratio (0-30)
                strategy.get('row0_ratio', 0) * 25 +        # placement (0-25)
                strategy.get('stammessen_ratio', 0) * 25 +  # pricing (0-25)
                strategy.get('neutral_name_ratio', 0) * 20  # naming (0-20)
            )
        else:
            score = 0

        scores.append({
            'code': code,
            'name': casino['name'],
            'score': round(score, 1),
            'vegan_ratio': vegan_ratio,
            'row0': strategy.get('row0_ratio', 0) if strategy else 0,
            'stammessen': strategy.get('stammessen_ratio', 0) if strategy else 0,
            'neutral': strategy.get('neutral_name_ratio', 0) if strategy else 0,
            'dishes': dishes,
        })

    scores.sort(key=lambda entry: -entry['score'])

    # Top N
    print()
    if casino_filter:
        print(f'  🏆 Vegan-Score — {casino_filter}:')
    else:
        print(f'  🏆 Top {min(top, len(scores))} (höchster Vegan-Score):')
    print()
    print(f'  {"#":>3} {"Code":5} {"Casino":35} {"Score":>6} {"Veg%":>6} {"Row0":>6} {"StE":>6} {"Name":>6}')
    print(f'  {"─" * 3} {"─" * 5} {"─" * 35} {"─" * 6} {"─" * 6} {"─" * 6} {"─" * 6} {"─" * 6}')

    for rank, entry in enumerate(scores[:top]):
        print(f'  {rank + 1:>3} {entry["code"]:5} {entry["name"]:35} {entry["score"]:>5.1f} {entry["vegan_ratio"]:>5.1%} '
              f'{entry["row0"]:>5.1%} {entry["stammessen"]:>5.1%} {entry["neutral"]:>5.1%}')

    # Bottom N (only meaningful in aggregate view)
    if not casino_filter:
        bottom = [entry for entry in scores if entry['score'] == 0]
        print()
        print(f'  🚫 Score 0 ({len(bottom)} Casinos ohne veganes Gericht):')
        if bottom:
            for entry in sorted(bottom, key=lambda item: item['code'])[:15]:
                print(f'      {entry["code"]:5} {entry["name"]:35} ({entry["dishes"]} Gerichte)')
            if len(bottom) > 15:
                print(f'      ... und {len(bottom) - 15} weitere')

    # Price comparison: vegan vs meat
    print()
    stats = casino_view(week, casino_filter) if casino_filter else week['statistics']
    by_signet = stats['by_signet']
    vegan_avg = by_signet.get('VEGAN', {}).get('price', {}).get('avg', 0)
    schwein_avg = by_signet.get('SCHWEIN', {}).get('price', {}).get('avg', 0)
    gesamt_avg = stats['price'].get('avg', 0)
    print('  Preisvergleich:')
    print(f'    Vegan Ø:     {vegan_avg:.2f}€')
    print(f'    Schwein Ø:   {schwein_avg:.2f}€')
    print(f'    Gesamt Ø:    {gesamt_avg:.2f}€')
    if vegan_avg > 0 and schwein_avg > 0:
        diff = vegan_avg - schwein_avg
        print(f'    Δ Vegan–Schwein: {diff:+.2f}€ ({diff / schwein_avg:+.1%})')

    print()


# =============================================================================
# ANOMALY
# =============================================================================

def print_anomaly(weeks, casino_filter=None):
    """Detect week-over-week changes per casino."""
    if len(weeks) < 2:
        print('  Anomaly-Detection benötigt mindestens 2 Wochen Daten.')
        return

    prev, curr = weeks[-2], weeks[-1]
    label_prev, label_curr = week_label(prev), week_label(curr)

    print()
    print('=' * 70)
    print(f'  ANOMALIEN ({label_prev} → {label_curr})')
    print('=' * 70)

    changes = []

    all_codes = set(prev['casinos'].keys()) | set(curr['casinos'].keys())
    for code in sorted(all_codes):
        if casino_filter and code != casino_filter:
            continue

        casino_prev = prev['casinos'].get(code)
        casino_curr = curr['casinos'].get(code)

        if not casino_prev or not casino_curr:
            if casino_prev and not casino_curr:
                changes.append((code, casino_prev['name'], '❌ Casino verschwunden'))
            elif casino_curr and not casino_prev:
                changes.append((code, casino_curr['name'], '🆕 Neues Casino'))
            continue

        name = casino_curr['name']

        # Vegan ratio change
        vegan_prev = casino_prev.get('vegan_ratio', 0)
        vegan_curr = casino_curr.get('vegan_ratio', 0)
        if vegan_prev > 0 and vegan_curr == 0:
            changes.append((code, name, f'🔴 Vegan verloren: {vegan_prev:.1%} → 0%'))
        elif vegan_prev == 0 and vegan_curr > 0:
            changes.append((code, name, f'🟢 Vegan gewonnen: 0% → {vegan_curr:.1%}'))
        elif abs(vegan_curr - vegan_prev) > 0.05:
            arrow = '📈' if vegan_curr > vegan_prev else '📉'
            changes.append((code, name, f'{arrow} Vegan: {vegan_prev:.1%} → {vegan_curr:.1%}'))

        # Dish count change
        dishes_prev = casino_prev.get('dishes', 0)
        dishes_curr = casino_curr.get('dishes', 0)
        if dishes_prev > 0 and abs(dishes_curr - dishes_prev) / dishes_prev > 0.3:
            changes.append((code, name, f'📊 Gerichte: {dishes_prev} → {dishes_curr} ({dishes_curr - dishes_prev:+d})'))

        # Price change (avg)
        price_prev = (casino_prev.get('price') or {}).get('avg', 0)
        price_curr = (casino_curr.get('price') or {}).get('avg', 0)
        if price_prev > 0 and price_curr > 0 and abs(price_curr - price_prev) > 0.20:
            changes.append((code, name, f'💰 Ø Preis: {price_prev:.2f}€ → {price_curr:.2f}€ ({price_curr - price_prev:+.2f}€)'))

        # Finding count change
        findings_prev = sum(1 for finding in prev['findings'] if finding.get('casino_code') == code)
        findings_curr = sum(1 for finding in curr['findings'] if finding.get('casino_code') == code)
        if findings_prev == 0 and findings_curr > 0:
            changes.append((code, name, f'⚠️ Neue Findings: {findings_curr}'))
        elif findings_prev > 0 and findings_curr == 0:
            changes.append((code, name, f'✅ Findings behoben (war {findings_prev})'))

    if changes:
        print()
        for code, name, message in changes:
            print(f'  {code:5} {name:35} {message}')
    else:
        print()
        print('  Keine signifikanten Änderungen.')

    print()


# =============================================================================
# FINDINGS
# =============================================================================

def print_findings(weeks, casino_filter=None, quiet=False):
    """Aggregated findings with repeat-offender detection."""
    print()
    print('=' * 70)
    print('  FINDINGS & REPEAT OFFENDERS')
    print('=' * 70)

    # Count findings by type across latest week
    week = weeks[-1]
    label = week_label(week)

    by_type = {}
    by_confidence = {}
    for finding in week['findings']:
        issue_type = finding.get('issue_type', 'unknown')
        confidence = finding.get('confidence', 'unknown')
        by_type[issue_type] = by_type.get(issue_type, 0) + 1
        by_confidence[confidence] = by_confidence.get(confidence, 0) + 1

    print()
    print(f'  {label} — {week["meta"]["findings_count"]} Findings:')
    print(f'    Nach Konfidenz:  {by_confidence}')
    print(f'    Nach Typ:        {by_type}')

    # Repeat offenders across all weeks
    if len(weeks) >= 2:
        print()
        print(f'  Repeat Offenders (Findings in jeder Woche, {len(weeks)} Wochen):')
        print()

        weeks_with_findings_per_casino = {}
        for week in weeks:
            casino_codes_seen = set()
            for finding in week['findings']:
                casino_codes_seen.add(finding.get('casino_code', ''))
            for code in casino_codes_seen:
                weeks_with_findings_per_casino[code] = weeks_with_findings_per_casino.get(code, 0) + 1

        repeaters = {code: count for code, count in weeks_with_findings_per_casino.items()
                     if count == len(weeks)}

        if repeaters:
            print(f'  {"Code":5} {"Casino":35} {"Findings":>10}  {"Typen"}')
            print(f'  {"─" * 5} {"─" * 35} {"─" * 10}  {"─" * 30}')

            for code in sorted(repeaters):
                name = weeks[-1]['casinos'].get(code, {}).get('name', code)
                latest_findings = [finding for finding in weeks[-1]['findings']
                                   if finding.get('casino_code') == code]
                issue_types = {finding.get('issue_type', '') for finding in latest_findings}
                print(f'  {code:5} {name:35} {len(latest_findings):>10}  {", ".join(sorted(issue_types))}')
        else:
            print('  Keine Casinos mit durchgängigen Findings.')

    # Detailed findings for specific casino
    if casino_filter:
        print()
        print(f'  Details für Casino {casino_filter}:')
        print()
        for week in weeks:
            label = week_label(week)
            findings = [finding for finding in week['findings']
                        if finding.get('casino_code') == casino_filter]
            if findings:
                print(f'  {label}: {len(findings)} Findings')
                for finding in findings:
                    confidence_icon = CONFIDENCE_ICONS.get(finding['confidence'], '?')
                    print(f'    {confidence_icon} {finding["day"]}: {finding["issue"]}')
                    print(f'       → {finding["recommendation"]["reason"]}')
            else:
                print(f'  {label}: keine Findings')
        print()

    # Most common issues (latest week)
    if not quiet:
        print()
        print(f'  Häufigste Issues ({label}):')
        print()
        issue_counter = {}
        for finding in weeks[-1]['findings']:
            issue = finding.get('issue', '')
            issue_counter[issue] = issue_counter.get(issue, 0) + 1

        for issue, count in sorted(issue_counter.items(), key=lambda item: -item[1])[:10]:
            print(f'    {count:>3}×  {issue}')

    print()


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='DB Casino Analyse & Trends')
    parser.add_argument('--mode', default='overview',
                        choices=['overview', 'trend', 'scorecard', 'anomaly', 'findings', 'all'],
                        help='Analyse-Modus (default: overview)')
    parser.add_argument('--casino', default=None,
                        help='Filter auf Casino-Code (z.B. cma, dmk)')
    parser.add_argument('--top', type=int, default=20,
                        help='Anzahl Einträge in Rankings (default: 20)')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Kompakte Ausgabe')
    args = parser.parse_args()

    weeks = load_all_weeks()
    if not weeks:
        print('Keine Findings-Daten gefunden.')
        sys.exit(1)

    mode = args.mode
    if mode == 'all':
        modes = ['overview', 'trend', 'scorecard', 'anomaly', 'findings']
    else:
        modes = [mode]

    for mode_name in modes:
        if mode_name == 'overview':
            print_overview(weeks, quiet=args.quiet, casino_filter=args.casino)
        elif mode_name == 'trend':
            print_trend(weeks, casino_filter=args.casino)
        elif mode_name == 'scorecard':
            print_scorecard(weeks, top=args.top, casino_filter=args.casino)
        elif mode_name == 'anomaly':
            print_anomaly(weeks, casino_filter=args.casino)
        elif mode_name == 'findings':
            print_findings(weeks, casino_filter=args.casino, quiet=args.quiet)


if __name__ == '__main__':
    main()
