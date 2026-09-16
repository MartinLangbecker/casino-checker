"""
DB Casino Speisekarten-Analyzer
================================
Extracts dish grid from casino PDFs, classifies signets via pixel analysis,
checks consistency between signets, allergens and dish descriptions.
"""
import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')

import pdfplumber
from pypdf import PdfReader
from PIL import Image
import numpy as np
from io import BytesIO
from collections import defaultdict

# Sachbezugswert for meals (updated annually, see KBV Gastronomie §7)
SACHBEZUGSWERT = 4.60

# Canonical signet order, shared across analyzer / batch / analyze modules.
SIGNET_ORDER = ['VEGAN', 'VEGETARISCH', 'SCHWEIN', 'SCHWEIN+RIND', 'RIND', 'GEFLÜGEL', 'FISCH']

# Signets denoting meat or fish (used for category cross-checks).
MEAT_FISH_SIGNETS = frozenset({'SCHWEIN', 'SCHWEIN+RIND', 'RIND', 'GEFLÜGEL', 'FISCH'})

# Signets that carry no dietary conflict semantics and are skipped in checks/stats.
NON_DIET_SIGNETS = frozenset({'UNKNOWN', 'NACHHALTIG'})

# Console icons per finding confidence level.
CONFIDENCE_ICONS = {'high': '🔴', 'medium': '🟡', 'low': '⚪'}

# =============================================================================
# SIGNET CLASSIFIER
# =============================================================================

def crop_to_content(pixels, threshold=240):
    """Crop a HxWx3 pixel array to its non-white bounding box.

    Returns (cropped_pixels, content_width, content_height).
    """
    non_white = np.any(pixels < threshold, axis=2)
    if not non_white.any():
        return pixels, 0, 0
    rows = np.where(non_white.any(axis=1))[0]
    cols = np.where(non_white.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return pixels, 0, 0
    cropped = pixels[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    return cropped, cols[-1] - cols[0] + 1, rows[-1] - rows[0] + 1


def classify_signet(image_bytes):
    """Classify a signet image based on aspect ratio and color distribution."""
    try:
        image = Image.open(BytesIO(image_bytes)).convert('RGB')
    except Exception:
        return 'UNKNOWN'

    pixels = np.array(image)
    full_width, full_height = pixels.shape[1], pixels.shape[0]

    if full_width > 500 or full_height > 500:
        return 'LOGO'

    cropped, content_width, content_height = crop_to_content(pixels)
    if content_width < 3 or content_height < 3:
        return 'SPACER'

    pixel_count = content_height * content_width
    red = cropped[:, :, 0].astype(float)
    green = cropped[:, :, 1].astype(float)
    blue = cropped[:, :, 2].astype(float)

    red_pct = ((red > 120) & (red - green > 60) & (red - blue > 60)).sum() / pixel_count * 100
    green_pct = ((green > 60) & (green - red > 20) & (green - blue > 20)).sum() / pixel_count * 100
    black_pct = ((red < 80) & (green < 80) & (blue < 80)).sum() / pixel_count * 100
    aspect = content_width / content_height

    # Classification rules (ordered by specificity):
    # Large green+black = Nachhaltig badge
    if green_pct > 30 and full_width > 200:
        return 'NACHHALTIG'

    # VEGAN: tall narrow, tiny green, no red (two small leaves)
    if aspect > 1.55 and green_pct < 4 and red_pct < 0.5:
        return 'VEGAN'

    # VEGETARISCH: slightly less narrow, more green (broad sweeping leaf)
    if 1.35 <= aspect <= 1.6 and green_pct > 4 and red_pct < 0.5:
        return 'VEGETARISCH'

    # SCHWEIN+RIND: wide, lots of red (two animals)
    if aspect > 1.0 and red_pct > 8:
        return 'SCHWEIN+RIND'

    # RIND: medium aspect, moderate red, taller than schwein
    if 1.1 <= aspect <= 1.3 and red_pct > 0.8 and content_height > 55:
        return 'RIND'

    # SCHWEIN: wider than tall, some red
    if aspect > 1.2 and red_pct > 1.5:
        return 'SCHWEIN'

    # FISCH: roughly square, high black (detailed outline), red > 2%
    # Must come BEFORE Geflügel (overlapping aspect range)
    if 0.8 <= aspect <= 1.05 and black_pct > 14 and red_pct > 1.8:
        return 'FISCH'

    # GEFLÜGEL: taller than wide, moderate black outline, low red (<2%)
    if 0.7 <= aspect <= 0.95 and black_pct > 8 and red_pct < 2:
        return 'GEFLÜGEL'

    # Fallback: small Nachhaltig badge (12.8x12.8)
    if green_pct > 20:
        return 'NACHHALTIG'

    return f'UNKNOWN(a={aspect:.2f},r={red_pct:.1f},g={green_pct:.1f},b={black_pct:.1f})'


# =============================================================================
# PAGE EXTRACTION
# =============================================================================

def extract_page(page, image_data_dict):
    """Extract dishes and signets from a single page."""
    words = page.extract_words(keep_blank_chars=True, x_tolerance=2, y_tolerance=2)

    # Find weekday/weekend headers
    all_days = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
    day_positions = {}
    for word in words:
        if word['text'] in all_days:
            day_positions[word['text']] = word['x0']

    if len(day_positions) < 2:
        return [], "Too few day headers"

    sorted_days = sorted(day_positions.items(), key=lambda item: item[1])

    # Column boundaries at header starts
    col_boundaries = [0] + [x for _, x in sorted_days[1:]] + [page.width]
    col_names = [day for day, _ in sorted_days]

    def column_for_x(x):
        for index in range(len(col_names)):
            if col_boundaries[index] <= x < col_boundaries[index + 1]:
                return col_names[index]
        return None
    
    # Collect signets per column with their Y positions
    # Primary signets (17x61 or 17x17) define row boundaries
    # Secondary badges (12.8x12.8) are assigned to nearest row after boundaries are set
    col_signets = defaultdict(list)  # day -> [(y_center, img_name)]
    col_badges = defaultdict(list)   # day -> [(y_center, img_name)]
    for image in page.images:
        image_width = image['x1'] - image['x0']
        image_height = image['bottom'] - image['top']
        x_center = (image['x0'] + image['x1']) / 2
        y_center = (image['top'] + image['bottom']) / 2
        day = column_for_x(x_center)
        if not day:
            continue
        image_name = image.get('name', '')
        if (15 < image_width < 20 and 55 < image_height < 65) or (15 < image_width < 20 and 15 < image_height < 20):
            # Primary signet (defines rows)
            col_signets[day].append((y_center, image_name))
        elif 10 < image_width < 15 and 10 < image_height < 15:
            # Secondary badge (NACHHALTIG or spacer — assigned to row later)
            col_badges[day].append((y_center, image_name))
    
    # Sort signets per column by Y
    for day in col_signets:
        col_signets[day].sort()
    
    # Per-column row boundaries: each signet defines a row.
    # Text ABOVE a signet (between previous signet and this one) belongs to this signet's row.
    # Strategy: row boundaries are midpoints between consecutive signets within each column.
    def row_boundaries_for_column(day):
        """Return row boundaries for a specific column based on its signets."""
        signets = col_signets.get(day, [])
        if not signets:
            return [0, page.height], 0

        # Each signet marks the END of its row (signet sits at bottom-right of dish cell)
        # Row n starts after signet n-1 and ends at signet n
        boundaries = [0]
        for index in range(1, len(signets)):
            # Midpoint between signet index-1 and signet index
            midpoint = (signets[index - 1][0] + signets[index][0]) / 2
            boundaries.append(midpoint)
        boundaries.append(page.height)
        return boundaries, len(signets)

    def row_index_in_column(day, y):
        """Get row index for a Y position within a specific column."""
        boundaries, _ = row_boundaries_for_column(day)
        for index in range(len(boundaries) - 1):
            if boundaries[index] <= y < boundaries[index + 1]:
                return index
        return -1

    # Group text by (day, row)
    cell_text = defaultdict(list)
    # Skip footer zone (bottom 5% of page — contains legal text spanning full width)
    footer_y = page.height * 0.85

    for word in words:
        if word['top'] > footer_y:
            continue
        x_center = (word['x0'] + word['x1']) / 2
        day = column_for_x(x_center)
        if not day:
            continue
        row = row_index_in_column(day, word['top'])
        if row >= 0:
            cell_text[(day, row)].append((word['top'], word['x0'], word['text']))

    # Map signets to cells (each primary signet defines its row index)
    cell_signets = defaultdict(list)
    for day, signets in col_signets.items():
        for row_index, (_, image_name) in enumerate(signets):
            if image_name in image_data_dict:
                signet_type = classify_signet(image_data_dict[image_name])
                if signet_type not in ('SPACER', 'LOGO'):
                    cell_signets[(day, row_index)].append(signet_type)

    # Assign secondary badges to nearest row
    for day, badges in col_badges.items():
        signets = col_signets.get(day, [])
        if not signets:
            continue
        for badge_y, badge_name in badges:
            if badge_name not in image_data_dict:
                continue
            signet_type = classify_signet(image_data_dict[badge_name])
            if signet_type in ('SPACER', 'LOGO', 'UNKNOWN'):
                continue
            # Find nearest primary signet row
            nearest_row = 0
            nearest_dist = abs(badge_y - signets[0][0])
            for row_index, (signet_y, _) in enumerate(signets):
                dist = abs(badge_y - signet_y)
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_row = row_index
            cell_signets[(day, nearest_row)].append(signet_type)
    
    # Build dish records
    results = []
    for (day, row), text_parts in sorted(cell_text.items(),
            key=lambda cell: (all_days.index(cell[0][0]) if cell[0][0] in all_days else 99, cell[0][1])):
        text_parts.sort()  # by y, then x
        full_text = ' '.join(text for _, _, text in text_parts)
        
        # Skip header-only cells or very short text
        if len(full_text.strip()) < 10:
            continue
        # Skip if it's just the page header
        if 'Speisekarte vom' in full_text and 'Casino' in full_text:
            continue
        # Skip footer text
        if 'Zusatzstoffe und Allergene' in full_text:
            continue
        if 'Produktionsprozesse' in full_text:
            continue
        
        # Parse category
        category = ''
        text = full_text
        # Remove day name anywhere in beginning
        for day_name in all_days:
            if text.startswith(day_name):
                text = text[len(day_name):].strip()
                break
        # Remove casino/date header remnants (often bleeds into first/last column)
        text = re.sub(r'^.*?Casino\s+[\w\s\-äöüÄÖÜß]+?\s+(?=(Veganes|Vegetarisches|Stammessen|Menü|Tipp|Add-on|Pasta|Meer|Vital|Grill|zentrale|JOB))', '', text).strip()
        text = re.sub(r'Speisekarte vom.*?(?=\s[A-Z])', '', text).strip()
        # Remove any remaining day names at start
        for day_name in all_days:
            if text.startswith(day_name):
                text = text[len(day_name):].strip()

        for category_label in ['Veganes Gericht', 'Vegetarisches Gericht', 'Vital Gericht',
                               'Stammessen', 'Tipp des Tages', 'Menü', 'Add-on', 'Pasta',
                               'Meer', 'Vegetarisch', 'zentrale Aktion']:
            if text.startswith(category_label):
                category = category_label
                text = text[len(category_label):].strip()
                break
        
        # Remove leading numbers
        text = re.sub(r'^\d+\s*', '', text)
        
        # Extract allergens
        allergene = ''
        allerg_match = re.search(r'Allergene:\s*([\w,\s.]*?)(?:\s*Zusatzstoffe|$)', text)
        if allerg_match:
            allergene = allerg_match.group(1).strip().rstrip(',').strip()
        
        # Extract DB price
        price_db = None
        price_match = re.search(r'DB:\s*(\d+[.,]\d{2})', text)
        if price_match:
            price_db = float(price_match.group(1).replace(',', '.'))
        
        # Dish name = everything before "Allergene:" or price
        dish = re.split(r'\s*\|?\s*Allergene:', text)[0].strip().rstrip('|').strip()
        dish = re.split(r'\s*DB:\s*\d', dish)[0].strip()
        
        signets = cell_signets.get((day, row), [])
        
        # Add-on detection: anything priced below Stammessen (Sachbezugswert)
        # is not a standalone dish but a component/upgrade. "Upgrade gefällig?"
        # marks upgrades explicitly and is caught by text even when no price was
        # parsed on the line.
        results.append({
            'day': day,
            'row': row,
            'category': category,
            'dish': dish,
            'allergene': allergene,
            'price_db': price_db,
            'signets': signets,
            'is_addon': (category.lower().startswith('add-on')
                         or 'upgrade gefällig' in dish.lower()
                         or (price_db is not None and price_db < SACHBEZUGSWERT)),
        })
    
    return results, None


# =============================================================================
# FULL PDF EXTRACTION (multi-page)
# =============================================================================

def extract_menu(pdf_path):
    """Extract full menu from all pages of a casino PDF."""
    pdf = pdfplumber.open(pdf_path)
    reader = PdfReader(pdf_path)
    
    all_results = []
    casino_name = ''
    date_range = ''
    
    for page_idx in range(len(pdf.pages)):
        page = pdf.pages[page_idx]

        # Get image data for this page
        if page_idx < len(reader.pages):
            image_data = {image.name.split('.')[0]: image.data
                          for image in reader.pages[page_idx].images}
        else:
            image_data = {}

        results, error = extract_page(page, image_data)
        if error:
            continue

        all_results.extend(results)

        # Extract casino name from first page header
        if page_idx == 0:
            words = page.extract_words(keep_blank_chars=True, x_tolerance=2, y_tolerance=2)
            header = ' '.join(word['text'] for word in words if word['top'] < 75)
            name_match = re.search(r'Casino\s+([\w\s\-äöüÄÖÜß]+?)(?:\s+Montag|\s+Samstag)', header)
            casino_name = name_match.group(0).strip() if name_match else ''
            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})\s+bis\s+(\d{2}\.\d{2}\.\d{4})', header)
            date_range = f"{date_match.group(1)}–{date_match.group(2)}" if date_match else ''
    
    pdf.close()
    return all_results, casino_name, date_range


# =============================================================================
# CONSISTENCY CHECKER
# =============================================================================

SCHWEIN_KEYWORDS = ['schwein', 'speck', 'schinken', 'kasseler', 'bratwurst', 'bacon', 'pancetta',
              'leberkäs', 'wiener würstchen', 'bockwurst', 'jagdwurst', 'mettwurst']
RIND_KEYWORDS = ['rind', 'beef', 'gulasch vom rind', 'rindfleisch']
GEFLÜGEL_KEYWORDS = ['pute', 'turkey', 'huhn', 'hähnchen', 'chicken', 'geflügel', 'ente', 'nuggets']
FISCH_KEYWORDS = ['fisch', 'lachs', 'seelachs', 'pangasius', 'forelle', 'thunfisch', 'kabeljau',
            'dorsch', 'scholle', 'garnele', 'shrimp', 'matjes', 'hering', 'calamari', 'fischragout',
            'hoki', 'wels', 'rotbarsch', 'seehecht', 'kap-seehecht', 'saibling', 'zander',
            'barsch', 'heilbutt', 'dorade', 'wolfsbarsch', 'tono', 'tonno']
VEGAN_CONFLICTS = ['joghurt', 'yoghurt', 'käse', 'cheese', 'sahne', 'butter', 'quark',
                   'schmand', 'gouda', 'mozzarella', 'parmesan', 'frischkäse', 'hirtenkäse',
                   'feta', 'honig', 'honey', 'mayo', 'mascarpone', 'crème fraîche',
                   'hartkäse', 'blauschimmelkäse', 'ziegenkäse']

DAIRY_ALLERGENS = {'g', 'g1', 'g2', 'g3', 'g4', 'g5', 'g6', 'g7'}
EGG_ALLERGENS = {'c'}
# Fisch (d) und Krebstiere (b) sind tierische Allergene, die vegan UND vegetarisch
# ausschließen. Empfehlung daher FISCH-Signet, nicht VEGETARISCH.
MARINE_ALLERGENS = {'b', 'd', 'n'}

_VEGAN_PREFIX_RE = re.compile(r'\b(?:vegane?[rsn]?|vegetarisch(?:e[rsn]?)?)\b', re.IGNORECASE)

def _has_keyword_without_vegan_prefix(dish_lower, keywords):
    """Return first keyword found in dish that is NOT in a vegan/vegetarisch context.
    Returns None if all keyword occurrences have a vegan/vegetarisch qualifier nearby."""
    # Quick check: if 'vegan' appears anywhere in the dish, assume meat/fish keywords
    # refer to vegan variants (e.g. "Bratwurst Vegan vegane Bratwurst")
    if _VEGAN_PREFIX_RE.search(dish_lower):
        return None
    for keyword in keywords:
        if keyword in dish_lower:
            return keyword
    return None

def check_consistency(dish_record):
    """Check signet vs dish description/allergens. Returns list of structured findings."""
    findings = []
    dish = dish_record['dish'].lower()
    category = dish_record['category'].lower()
    allergene_set = set(allergen.strip() for allergen in dish_record['allergene'].split(',') if allergen.strip())

    # Add-ons (Upgrades, Extras, Beilagen unter Sachbezugswert) sind keine
    # eigenständigen Gerichte. Sie werden aus der Statistik ausgeschlossen und
    # ebenso von der Konsistenzprüfung, da ihre Allergenangaben in den PDFs
    # häufig zur benachbarten Hauptgericht-Zeile gehören.
    if dish_record.get('is_addon'):
        return findings

    # Multi-option dishes ("oder") — keyword conflicts are not meaningful
    is_multi_option = ' oder ' in dish

    def add_finding(issue_type, confidence, issue, recommendation):
        findings.append({
            'issue_type': issue_type,
            'confidence': confidence,
            'issue': issue,
            'recommendation': recommendation,
        })

    # Missing signet check: only for dishes with a recognized category
    if (not dish_record['signets'] and not dish_record.get('is_addon') and not is_multi_option
            and dish_record['dish'].strip() and dish_record['category']):
        add_finding('missing_signet', 'low',
            f"Kein Signet bei '{dish_record['category']}'",
            {'action': 'verify_signet',
             'reason': f"Kategorie '{dish_record['category']}' vorhanden, aber kein Signet erkannt"})

    for signet in dish_record['signets']:
        if 'UNKNOWN' in signet or signet == 'NACHHALTIG':
            continue

        # VEGAN checks
        if signet == 'VEGAN':
            dairy_conflict = allergene_set & DAIRY_ALLERGENS
            egg_conflict = allergene_set & EGG_ALLERGENS

            if dairy_conflict:
                add_finding('signet_allergen_conflict', 'high',
                    f"VEGAN-Signet + Milch-Allergen ({', '.join(sorted(dairy_conflict))})",
                    {'action': 'change_signet', 'suggested_signet': 'VEGETARISCH',
                     'reason': f"Milch-Allergen ({', '.join(sorted(dairy_conflict))}) deklariert → nicht vegan"})

            if egg_conflict:
                add_finding('signet_allergen_conflict', 'high',
                    f"VEGAN-Signet + Ei-Allergen (c)",
                    {'action': 'change_signet', 'suggested_signet': 'VEGETARISCH',
                     'reason': "Ei-Allergen (c) deklariert → nicht vegan"})

            marine_conflict = allergene_set & MARINE_ALLERGENS
            if marine_conflict:
                add_finding('signet_allergen_conflict', 'high',
                    f"VEGAN-Signet + Fisch/Krebstier/Weichtier-Allergen ({', '.join(sorted(marine_conflict))})",
                    {'action': 'change_signet', 'suggested_signet': 'FISCH',
                     'reason': f"Fisch/Krebstier/Weichtier-Allergen ({', '.join(sorted(marine_conflict))}) deklariert → weder vegan noch vegetarisch"})

            if allergene_set & (DAIRY_ALLERGENS | EGG_ALLERGENS):
                conflict_keyword = _has_keyword_without_vegan_prefix(dish, VEGAN_CONFLICTS)
                if conflict_keyword:
                    add_finding('signet_allergen_conflict', 'high',
                        f"VEGAN-Signet + '{conflict_keyword}' in Beschreibung (+ Tierprodukt-Allergen)",
                        {'action': 'change_signet', 'suggested_signet': 'VEGETARISCH',
                         'reason': f"'{conflict_keyword}' + Tierprodukt-Allergen → nicht vegan"})

            meat_keyword = _has_keyword_without_vegan_prefix(dish, SCHWEIN_KEYWORDS + RIND_KEYWORDS + GEFLÜGEL_KEYWORDS + FISCH_KEYWORDS)
            if meat_keyword:
                add_finding('signet_keyword_conflict', 'medium',
                    f"VEGAN-Signet + '{meat_keyword}' (Fleisch/Fisch) in Beschreibung",
                    {'action': 'verify_signet',
                     'reason': f"'{meat_keyword}' in Beschreibung → Signet prüfen"})

        # VEGETARISCH checks
        elif signet == 'VEGETARISCH':
            meat_keyword = _has_keyword_without_vegan_prefix(dish, SCHWEIN_KEYWORDS + RIND_KEYWORDS + GEFLÜGEL_KEYWORDS + FISCH_KEYWORDS)
            if meat_keyword and not is_multi_option:
                # Determine suggested signet from keyword
                if any(keyword in dish for keyword in SCHWEIN_KEYWORDS):
                    suggested = 'SCHWEIN'
                elif any(keyword in dish for keyword in GEFLÜGEL_KEYWORDS):
                    suggested = 'GEFLÜGEL'
                elif any(keyword in dish for keyword in FISCH_KEYWORDS):
                    suggested = 'FISCH'
                elif any(keyword in dish for keyword in RIND_KEYWORDS):
                    suggested = 'RIND'
                else:
                    suggested = None

                recommendation = {'action': 'change_signet', 'suggested_signet': suggested,
                       'reason': f"'{meat_keyword}' in Beschreibung → nicht vegetarisch"}
                add_finding('signet_keyword_conflict', 'medium',
                    f"VEGETARISCH-Signet + '{meat_keyword}' in Beschreibung", recommendation)

        # SCHWEIN checks
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

        # GEFLÜGEL checks
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
                        f"GEFLÜGEL-Signet, aber Fisch im Gericht",
                        {'action': 'change_signet', 'suggested_signet': 'FISCH',
                         'reason': "Fisch in Beschreibung → FISCH-Signet passender"})

        # FISCH checks
        elif signet == 'FISCH':
            if not any(keyword in dish for keyword in FISCH_KEYWORDS):
                add_finding('signet_keyword_conflict', 'low',
                    f"FISCH-Signet, aber kein Fisch in Beschreibung",
                    {'action': 'verify_signet',
                     'reason': "Kein Fisch-Keyword gefunden → Signet oder Beschreibung prüfen"})

        # RIND checks
        elif signet == 'RIND':
            if not any(keyword in dish for keyword in RIND_KEYWORDS):
                if 'vegetar' in category or 'vegan' in category:
                    add_finding('signet_category_conflict', 'medium',
                        f"RIND-Signet auf {dish_record['category']}",
                        {'action': 'verify_signet',
                         'reason': f"Kategorie '{dish_record['category']}' passt nicht zu RIND-Signet"})

        # Category vs Signet cross-check.
        # Eine vegane Kategorie erlaubt ausschließlich das VEGAN-Signet;
        # jedes andere Diät-Signet (auch VEGETARISCH) widerspricht der Überschrift.
        # (signet ist hier stets ein Diät-Signet, da UNKNOWN/NACHHALTIG oben übersprungen werden.)
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

    # Category vs Allergen checks (highest confidence)
    if 'vegan' in category:
        dairy_conflict = allergene_set & DAIRY_ALLERGENS
        egg_conflict = allergene_set & EGG_ALLERGENS
        if dairy_conflict:
            add_finding('category_allergen_conflict', 'high',
                f"Kategorie 'Veganes Gericht' + Milch-Allergen ({', '.join(sorted(dairy_conflict))})",
                {'action': 'change_category', 'suggested_signet': 'VEGETARISCH',
                 'reason': f"Milch-Allergen deklariert → Kategorie 'Vegetarisches Gericht' verwenden"})
        if egg_conflict:
            add_finding('category_allergen_conflict', 'high',
                f"Kategorie 'Veganes Gericht' + Ei-Allergen (c)",
                {'action': 'change_category', 'suggested_signet': 'VEGETARISCH',
                 'reason': "Ei-Allergen deklariert → Kategorie 'Vegetarisches Gericht' verwenden"})
        marine_conflict = allergene_set & MARINE_ALLERGENS
        if marine_conflict:
            add_finding('category_allergen_conflict', 'high',
                f"Kategorie 'Veganes Gericht' + Fisch/Krebstier/Weichtier-Allergen ({', '.join(sorted(marine_conflict))})",
                {'action': 'change_category', 'suggested_signet': 'FISCH',
                 'reason': "Fisch/Krebstier/Weichtier-Allergen deklariert → weder vegan noch vegetarisch"})

    # Deduplicate by issue text
    seen_issues = set()
    unique_findings = []
    for finding in findings:
        if finding['issue'] not in seen_issues:
            seen_issues.add(finding['issue'])
            unique_findings.append(finding)
    return unique_findings


# =============================================================================
# MAIN (standalone usage)
# =============================================================================

if __name__ == '__main__':
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
