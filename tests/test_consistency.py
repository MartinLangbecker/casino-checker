"""Tests for the consistency checker rules.

check_consistency is a pure function (dish_record dict -> list of findings),
so every rule can be exercised without touching a PDF.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from consistency import (  # noqa: E402
    _allergen_conflicts,
    _has_keyword_without_vegan_prefix,
    check_consistency,
    signet_for_keyword,
)


def make_dish(dish='', category='', allergene='', signets=None, price_db=None,
              is_addon=False, zusatzstoffe=''):
    """Build a dish record with sensible defaults."""
    return {
        'day': 'Montag',
        'row': 0,
        'category': category,
        'dish': dish,
        'allergene': allergene,
        'zusatzstoffe': zusatzstoffe,
        'price_db': price_db,
        'signets': signets or [],
        'is_addon': is_addon,
    }


def issue_types(findings):
    return {f['issue_type'] for f in findings}


def confidences(findings):
    return {f['confidence'] for f in findings}


# --- Add-ons are skipped entirely -------------------------------------------

def test_addon_returns_no_findings():
    dish = make_dish(dish='Pommes', category='Add-on', signets=['VEGAN'],
                     allergene='g', is_addon=True)
    assert check_consistency(dish) == []


# --- VEGAN signet + allergens (high confidence) -----------------------------

def test_vegan_signet_with_dairy_allergen():
    dish = make_dish(dish='Käsespätzle', signets=['VEGAN'], allergene='g')
    findings = check_consistency(dish)
    assert 'signet_allergen_conflict' in issue_types(findings)
    assert 'high' in confidences(findings)
    conflict = next(f for f in findings if f['issue_type'] == 'signet_allergen_conflict')
    assert conflict['recommendation']['suggested_signet'] == 'VEGETARISCH'


def test_vegan_signet_with_egg_allergen():
    dish = make_dish(dish='Pfannkuchen', signets=['VEGAN'], allergene='c')
    findings = check_consistency(dish)
    assert any('Ei-Allergen' in f['issue'] for f in findings)


def test_vegan_signet_with_marine_allergen_suggests_fisch():
    dish = make_dish(dish='Reispfanne', signets=['VEGAN'], allergene='d')
    findings = check_consistency(dish)
    conflict = next(f for f in findings if f['issue_type'] == 'signet_allergen_conflict')
    assert conflict['recommendation']['suggested_signet'] == 'FISCH'


def test_vegan_signet_clean_dish_no_findings():
    dish = make_dish(dish='Gemüsecurry mit Reis', signets=['VEGAN'], allergene='a1')
    assert check_consistency(dish) == []


# --- VEGAN keyword conflicts ------------------------------------------------

def test_vegan_signet_with_meat_keyword():
    dish = make_dish(dish='Hähnchenbrust mit Reis', signets=['VEGAN'])
    findings = check_consistency(dish)
    assert 'signet_keyword_conflict' in issue_types(findings)


def test_vegan_prefix_suppresses_keyword_conflict():
    # "vegane Bratwurst" must NOT trigger a schwein keyword conflict.
    dish = make_dish(dish='Vegane Bratwurst mit Sauerkraut', signets=['VEGAN'])
    findings = check_consistency(dish)
    assert 'signet_keyword_conflict' not in issue_types(findings)


# --- VEGETARISCH signet -----------------------------------------------------

def test_vegetarisch_with_fish_suggests_fisch():
    dish = make_dish(dish='Lachsfilet', signets=['VEGETARISCH'])
    findings = check_consistency(dish)
    conflict = next(f for f in findings if f['issue_type'] == 'signet_keyword_conflict')
    assert conflict['recommendation']['suggested_signet'] == 'FISCH'


def test_vegetarisch_multi_option_no_keyword_conflict():
    dish = make_dish(dish='Schnitzel oder Gemüsepfanne', signets=['VEGETARISCH'])
    findings = check_consistency(dish)
    assert 'signet_keyword_conflict' not in issue_types(findings)


# --- SCHWEIN / GEFLÜGEL / FISCH / RIND signets ------------------------------

def test_schwein_signet_with_fish_keyword():
    dish = make_dish(dish='Seelachs paniert', signets=['SCHWEIN'])
    findings = check_consistency(dish)
    conflict = next(f for f in findings if f['issue_type'] == 'signet_keyword_conflict')
    assert conflict['recommendation']['suggested_signet'] == 'FISCH'


def test_geflügel_signet_with_fish_keyword():
    dish = make_dish(dish='Forelle Müllerin', signets=['GEFLÜGEL'])
    findings = check_consistency(dish)
    conflict = next(f for f in findings if f['issue_type'] == 'signet_keyword_conflict')
    assert conflict['recommendation']['suggested_signet'] == 'FISCH'


def test_fisch_signet_without_fish_keyword_low_confidence():
    dish = make_dish(dish='Rindergulasch', signets=['FISCH'])
    findings = check_consistency(dish)
    conflict = next(f for f in findings if f['issue_type'] == 'signet_keyword_conflict')
    assert conflict['confidence'] == 'low'


def test_fisch_signet_with_fish_keyword_no_conflict():
    dish = make_dish(dish='Kabeljau mit Kartoffeln', signets=['FISCH'])
    assert check_consistency(dish) == []


# --- Category vs signet cross-checks (high confidence) ----------------------

def test_vegan_category_with_non_vegan_signet():
    dish = make_dish(dish='Etwas', category='Veganes Gericht', signets=['VEGETARISCH'])
    findings = check_consistency(dish)
    conflict = next(f for f in findings if f['issue_type'] == 'signet_category_conflict')
    assert conflict['confidence'] == 'high'
    assert conflict['recommendation']['suggested_signet'] == 'VEGAN'


def test_vegetarisch_category_with_meat_signet():
    dish = make_dish(dish='Etwas', category='Vegetarisches Gericht', signets=['SCHWEIN'])
    findings = check_consistency(dish)
    conflict = next(f for f in findings
                    if f['issue_type'] == 'signet_category_conflict' and f['confidence'] == 'high')
    assert conflict['recommendation']['suggested_signet'] == 'VEGETARISCH'


# --- Category vs allergen checks --------------------------------------------

def test_vegan_category_with_dairy_allergen():
    dish = make_dish(dish='Auflauf', category='Veganes Gericht', allergene='g')
    findings = check_consistency(dish)
    assert 'category_allergen_conflict' in issue_types(findings)


# --- Zusatzstoffe (Molkerei 18.x / gewachst 7) ------------------------------

def test_vegan_signet_with_dairy_additive_18():
    # Molkerei-Zusatzstoff 18.1 ohne Milch-Allergen → trotzdem nicht vegan.
    dish = make_dish(dish='Auflauf', signets=['VEGAN'], zusatzstoffe='2, 18.1')
    findings = check_consistency(dish)
    conflict = next(f for f in findings if f['issue_type'] == 'signet_additive_conflict')
    assert conflict['confidence'] == 'high'
    assert conflict['recommendation']['suggested_signet'] == 'VEGETARISCH'


def test_vegan_signet_with_wax_additive_7():
    dish = make_dish(dish='Obstsalat', signets=['VEGAN'], zusatzstoffe='7')
    findings = check_consistency(dish)
    conflict = next(f for f in findings if f['issue_type'] == 'signet_additive_conflict')
    assert conflict['confidence'] == 'medium'


def test_vegan_category_with_dairy_additive():
    dish = make_dish(dish='Auflauf', category='Veganes Gericht', zusatzstoffe='18.2')
    findings = check_consistency(dish)
    assert 'category_additive_conflict' in issue_types(findings)


def test_vegan_signet_harmless_additives_no_finding():
    # Zusatzstoffe 2, 3 (Konservierung/Antioxidation) sind kein Vegan-Konflikt.
    dish = make_dish(dish='Gemüsecurry', signets=['VEGAN'], zusatzstoffe='2, 3')
    assert check_consistency(dish) == []


def test_non_vegan_signet_dairy_additive_ignored():
    # Zusatzstoff-Check greift nur bei VEGAN, nicht bei anderen Signets.
    dish = make_dish(dish='Käsespätzle', signets=['VEGETARISCH'], zusatzstoffe='18.1')
    findings = check_consistency(dish)
    assert 'signet_additive_conflict' not in issue_types(findings)


# --- Missing signet ---------------------------------------------------------

def test_missing_signet_with_category():
    dish = make_dish(dish='Irgendein Gericht', category='Stammessen', signets=[])
    findings = check_consistency(dish)
    assert 'missing_signet' in issue_types(findings)
    assert next(f for f in findings if f['issue_type'] == 'missing_signet')['confidence'] == 'low'


def test_missing_signet_not_flagged_without_category():
    dish = make_dish(dish='Irgendein Gericht', category='', signets=[])
    findings = check_consistency(dish)
    assert 'missing_signet' not in issue_types(findings)


# --- NACHHALTIG / UNKNOWN signets are ignored -------------------------------

def test_nachhaltig_signet_ignored():
    dish = make_dish(dish='Rindergulasch', signets=['NACHHALTIG'])
    assert check_consistency(dish) == []


# --- Deduplication ----------------------------------------------------------

def test_findings_are_deduplicated_by_issue_text():
    dish = make_dish(dish='Käse', category='Veganes Gericht', signets=['VEGAN'], allergene='g')
    findings = check_consistency(dish)
    issues = [f['issue'] for f in findings]
    assert len(issues) == len(set(issues))


# --- Helper functions -------------------------------------------------------

@pytest.mark.parametrize('dish,expected', [
    ('schweinebraten', 'SCHWEIN'),
    ('hähnchenschnitzel', 'GEFLÜGEL'),
    ('lachsfilet', 'FISCH'),
    ('rindergulasch', 'RIND'),
    ('gemüsecurry', None),
])
def test_signet_for_keyword(dish, expected):
    assert signet_for_keyword(dish) == expected


def test_has_keyword_without_vegan_prefix_suppressed():
    assert _has_keyword_without_vegan_prefix('vegane bratwurst', ['bratwurst']) is None


def test_has_keyword_without_vegan_prefix_found():
    assert _has_keyword_without_vegan_prefix('bratwurst mit senf', ['bratwurst']) == 'bratwurst'


def test_allergen_conflicts_detects_all_kinds():
    conflicts = _allergen_conflicts({'g', 'c', 'd'})
    kinds = {kind for kind, _, _ in conflicts}
    assert kinds == {'dairy', 'egg', 'marine'}
