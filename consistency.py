"""
Consistency checker — signet vs. allergens vs. dish description.
================================================================
Validates each dish record's signet against declared allergens and keywords in
the dish name/category. Returns structured findings with a confidence level.

Public API:
    check_consistency(dish_record) -> list[finding]
"""
import re

from constants import (
    DAIRY_ALLERGENS,
    EGG_ALLERGENS,
    FISCH_KEYWORDS,
    GEFLÜGEL_KEYWORDS,
    MARINE_ALLERGENS,
    MEAT_FISH_SIGNETS,
    RIND_KEYWORDS,
    SCHWEIN_KEYWORDS,
    SIGNET_KEYWORDS,
    VEGAN_CONFLICTS,
)

ALL_MEAT_FISH_KEYWORDS = SCHWEIN_KEYWORDS + RIND_KEYWORDS + GEFLÜGEL_KEYWORDS + FISCH_KEYWORDS

_VEGAN_PREFIX_RE = re.compile(r'\b(?:vegane?[rsn]?|vegetarisch(?:e[rsn]?)?)\b', re.IGNORECASE)


def signet_for_keyword(dish_lower):
    """Return the signet whose keyword list first matches the dish, else None.

    Priority follows SIGNET_KEYWORDS insertion order (SCHWEIN, GEFLÜGEL, FISCH, RIND).
    """
    for signet, keywords in SIGNET_KEYWORDS.items():
        if any(keyword in dish_lower for keyword in keywords):
            return signet
    return None


def _has_keyword_without_vegan_prefix(dish_lower, keywords):
    """First keyword found in dish that is NOT in a vegan/vegetarisch context.

    Returns None if the dish carries a vegan/vegetarisch qualifier anywhere
    (e.g. "vegane Bratwurst") or no keyword matches.
    """
    if _VEGAN_PREFIX_RE.search(dish_lower):
        return None
    for keyword in keywords:
        if keyword in dish_lower:
            return keyword
    return None


def _allergen_conflicts(allergene_set):
    """Return list of (allergen_kind, matched_codes, suggested_signet) tuples.

    Shared by both the VEGAN-signet and the vegan-category allergen checks.
    """
    conflicts = []
    dairy = allergene_set & DAIRY_ALLERGENS
    if dairy:
        conflicts.append(('dairy', dairy, 'VEGETARISCH'))
    egg = allergene_set & EGG_ALLERGENS
    if egg:
        conflicts.append(('egg', egg, 'VEGETARISCH'))
    marine = allergene_set & MARINE_ALLERGENS
    if marine:
        conflicts.append(('marine', marine, 'FISCH'))
    return conflicts


_ALLERGEN_LABELS = {
    'dairy': 'Milch-Allergen',
    'egg': 'Ei-Allergen',
    'marine': 'Fisch/Krebstier/Weichtier-Allergen',
}


def check_consistency(dish_record):
    """Check signet vs dish description/allergens. Returns list of structured findings."""
    findings = []
    dish = dish_record['dish'].lower()
    category = dish_record['category'].lower()
    allergene_set = {allergen.strip() for allergen in dish_record['allergene'].split(',') if allergen.strip()}

    # Add-ons (Upgrades, Extras, Beilagen unter Sachbezugswert) sind keine
    # eigenständigen Gerichte. Sie werden aus Statistik und Konsistenzprüfung
    # ausgeschlossen, da ihre Allergenangaben in den PDFs häufig zur
    # benachbarten Hauptgericht-Zeile gehören.
    if dish_record.get('is_addon'):
        return findings

    # Multi-option dishes ("oder") — keyword conflicts are not meaningful.
    is_multi_option = ' oder ' in dish

    def add_finding(issue_type, confidence, issue, recommendation):
        findings.append({
            'issue_type': issue_type,
            'confidence': confidence,
            'issue': issue,
            'recommendation': recommendation,
        })

    # Missing signet check: only for dishes with a recognized category.
    if (not dish_record['signets'] and not is_multi_option
            and dish_record['dish'].strip() and dish_record['category']):
        add_finding('missing_signet', 'low',
            f"Kein Signet bei '{dish_record['category']}'",
            {'action': 'verify_signet',
             'reason': f"Kategorie '{dish_record['category']}' vorhanden, aber kein Signet erkannt"})

    for signet in dish_record['signets']:
        if 'UNKNOWN' in signet or signet == 'NACHHALTIG':
            continue

        if signet == 'VEGAN':
            _check_vegan_signet(dish, allergene_set, add_finding)

        elif signet == 'VEGETARISCH':
            meat_keyword = _has_keyword_without_vegan_prefix(dish, ALL_MEAT_FISH_KEYWORDS)
            if meat_keyword and not is_multi_option:
                suggested = signet_for_keyword(dish)
                add_finding('signet_keyword_conflict', 'medium',
                    f"VEGETARISCH-Signet + '{meat_keyword}' in Beschreibung",
                    {'action': 'change_signet', 'suggested_signet': suggested,
                     'reason': f"'{meat_keyword}' in Beschreibung → nicht vegetarisch"})

        elif signet in ('SCHWEIN', 'SCHWEIN+RIND'):
            has_schwein_rind = any(keyword in dish for keyword in SCHWEIN_KEYWORDS + RIND_KEYWORDS)
            if not has_schwein_rind:
                other_keywords = [keyword for keyword in GEFLÜGEL_KEYWORDS + FISCH_KEYWORDS if keyword in dish]
                if other_keywords:
                    suggested = 'GEFLÜGEL' if other_keywords[0] in GEFLÜGEL_KEYWORDS else 'FISCH'
                    add_finding('signet_keyword_conflict', 'medium',
                        f"{signet}-Signet, aber '{other_keywords[0]}' im Gericht",
                        {'action': 'change_signet', 'suggested_signet': suggested,
                         'reason': f"'{other_keywords[0]}' im Gericht → {suggested}-Signet passender"})
                elif 'vegetar' in category or 'vegan' in category:
                    add_finding('signet_category_conflict', 'medium',
                        f"{signet}-Signet auf {dish_record['category']}",
                        {'action': 'verify_signet',
                         'reason': f"Kategorie '{dish_record['category']}' passt nicht zu {signet}-Signet"})

        elif signet == 'GEFLÜGEL':
            has_geflügel = any(keyword in dish for keyword in GEFLÜGEL_KEYWORDS)
            if not has_geflügel:
                if 'vegetar' in category or 'vegan' in category:
                    add_finding('signet_category_conflict', 'medium',
                        f"GEFLÜGEL-Signet auf {dish_record['category']}",
                        {'action': 'verify_signet',
                         'reason': f"Kategorie '{dish_record['category']}' passt nicht zu GEFLÜGEL-Signet"})
                elif any(keyword in dish for keyword in FISCH_KEYWORDS) and not is_multi_option:
                    add_finding('signet_keyword_conflict', 'medium',
                        "GEFLÜGEL-Signet, aber Fisch im Gericht",
                        {'action': 'change_signet', 'suggested_signet': 'FISCH',
                         'reason': "Fisch in Beschreibung → FISCH-Signet passender"})

        elif signet == 'FISCH':
            if not any(keyword in dish for keyword in FISCH_KEYWORDS):
                add_finding('signet_keyword_conflict', 'low',
                    "FISCH-Signet, aber kein Fisch in Beschreibung",
                    {'action': 'verify_signet',
                     'reason': "Kein Fisch-Keyword gefunden → Signet oder Beschreibung prüfen"})

        elif signet == 'RIND':
            if not any(keyword in dish for keyword in RIND_KEYWORDS):
                if 'vegetar' in category or 'vegan' in category:
                    add_finding('signet_category_conflict', 'medium',
                        f"RIND-Signet auf {dish_record['category']}",
                        {'action': 'verify_signet',
                         'reason': f"Kategorie '{dish_record['category']}' passt nicht zu RIND-Signet"})

        # Category vs Signet cross-check.
        # Eine vegane Kategorie erlaubt ausschließlich das VEGAN-Signet; jedes
        # andere Diät-Signet (auch VEGETARISCH) widerspricht der Überschrift.
        # (signet ist hier stets ein Diät-Signet, da UNKNOWN/NACHHALTIG übersprungen.)
        if 'vegan' in category and signet != 'VEGAN':
            add_finding('signet_category_conflict', 'high',
                f"Kategorie '{dish_record['category']}' + Signet {signet}",
                {'action': 'change_signet', 'suggested_signet': 'VEGAN',
                 'reason': f"Kategorie sagt vegan, Signet sagt {signet}"})
        if 'vegetar' in category and signet in MEAT_FISH_SIGNETS:
            add_finding('signet_category_conflict', 'high',
                f"Kategorie '{dish_record['category']}' + Signet {signet}",
                {'action': 'change_signet', 'suggested_signet': 'VEGETARISCH',
                 'reason': f"Kategorie sagt vegetarisch, Signet sagt {signet}"})

    # Category vs Allergen checks (highest confidence).
    if 'vegan' in category:
        for kind, codes, suggested in _allergen_conflicts(allergene_set):
            label = _ALLERGEN_LABELS[kind]
            codes_str = ', '.join(sorted(codes))
            if kind == 'marine':
                reason = "Fisch/Krebstier/Weichtier-Allergen deklariert → weder vegan noch vegetarisch"
            else:
                reason = f"{label} deklariert → Kategorie 'Vegetarisches Gericht' verwenden"
            add_finding('category_allergen_conflict', 'high',
                f"Kategorie 'Veganes Gericht' + {label} ({codes_str})",
                {'action': 'change_category', 'suggested_signet': suggested, 'reason': reason})

    # Deduplicate by issue text.
    seen_issues = set()
    unique_findings = []
    for finding in findings:
        if finding['issue'] not in seen_issues:
            seen_issues.add(finding['issue'])
            unique_findings.append(finding)
    return unique_findings


def _check_vegan_signet(dish, allergene_set, add_finding):
    """VEGAN-signet specific allergen/keyword checks."""
    for kind, codes, suggested in _allergen_conflicts(allergene_set):
        label = _ALLERGEN_LABELS[kind]
        codes_str = ', '.join(sorted(codes))
        if kind == 'marine':
            issue = f"VEGAN-Signet + {label} ({codes_str})"
            reason = f"{label} ({codes_str}) deklariert → weder vegan noch vegetarisch"
        else:
            issue = f"VEGAN-Signet + {label} ({codes_str})"
            reason = f"{label} ({codes_str}) deklariert → nicht vegan"
        add_finding('signet_allergen_conflict', 'high', issue,
            {'action': 'change_signet', 'suggested_signet': suggested, 'reason': reason})

    # Dairy/egg allergen + conflicting keyword in description.
    if allergene_set & (DAIRY_ALLERGENS | EGG_ALLERGENS):
        conflict_keyword = _has_keyword_without_vegan_prefix(dish, VEGAN_CONFLICTS)
        if conflict_keyword:
            add_finding('signet_allergen_conflict', 'high',
                f"VEGAN-Signet + '{conflict_keyword}' in Beschreibung (+ Tierprodukt-Allergen)",
                {'action': 'change_signet', 'suggested_signet': 'VEGETARISCH',
                 'reason': f"'{conflict_keyword}' + Tierprodukt-Allergen → nicht vegan"})

    # Meat/fish keyword in an allegedly vegan dish.
    meat_keyword = _has_keyword_without_vegan_prefix(dish, ALL_MEAT_FISH_KEYWORDS)
    if meat_keyword:
        add_finding('signet_keyword_conflict', 'medium',
            f"VEGAN-Signet + '{meat_keyword}' (Fleisch/Fisch) in Beschreibung",
            {'action': 'verify_signet',
             'reason': f"'{meat_keyword}' in Beschreibung → Signet prüfen"})
