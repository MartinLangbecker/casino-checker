"""
PDF extractor — dish grid extraction from casino menu PDFs.
===========================================================
Recognizes the weekday-column / dish-row table structure via pdfplumber,
maps embedded signet images to rows, and builds structured dish records.

Public API:
    extract_menu(pdf_path) -> (dish_records, casino_name, date_range)
    extract_page(page, image_data_dict) -> (dish_records, error)

extract_page delegates its two hard parts to:
    PageGrid           — column/row geometry (which cell does an (x, y) fall in)
    parse_dish_record  — turn a cell's raw text + signets into a dish dict
"""
import re
from collections import defaultdict

import pdfplumber
from pypdf import PdfReader

from constants import SACHBEZUGSWERT
from signet_classifier import classify_signet

WEEKDAYS = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']

CATEGORY_LABELS = ['Veganes Gericht', 'Vegetarisches Gericht', 'Vital Gericht',
                   'Stammessen', 'Tipp des Tages', 'Menü', 'Add-on', 'Pasta',
                   'Meer', 'Vegetarisch', 'zentrale Aktion']

# Footer zone: bottom 15% of the page holds legal text spanning all columns.
FOOTER_ZONE_RATIO = 0.85

# Primary signet dimensions (px): tall 17x61 or square 17x17 — these define rows.
PRIMARY_SIGNET_WIDTH = (15, 20)
PRIMARY_SIGNET_TALL_HEIGHT = (55, 65)
PRIMARY_SIGNET_SQUARE_HEIGHT = (15, 20)
# Secondary badge (~12.8x12.8): Nachhaltig / spacer, assigned to nearest row.
SECONDARY_BADGE_SIZE = (10, 15)


class PageGrid:
    """Column/row geometry for a single menu page.

    Columns are the weekday headers (sorted left→right). Rows are defined
    per column by the vertical positions of that column's primary signets:
    each signet sits at the bottom of its dish cell, so row boundaries are the
    midpoints between consecutive signets.
    """

    def __init__(self, page, words):
        self.page_width = page.width
        self.page_height = page.height

        day_positions = {word['text']: word['x0'] for word in words
                         if word['text'] in WEEKDAYS}
        sorted_days = sorted(day_positions.items(), key=lambda item: item[1])
        self.col_names = [day for day, _ in sorted_days]
        # Column boundaries: header start x-positions, bracketed by 0 and page width.
        self.col_boundaries = [0] + [x for _, x in sorted_days[1:]] + [page.width]

        # day -> sorted [(y_center, image_name)] of primary signets
        self.col_signets = defaultdict(list)

    @property
    def has_enough_columns(self):
        return len(self.col_names) >= 2

    def column_for_x(self, x):
        """Return the weekday column an x-position falls into, or None."""
        for index in range(len(self.col_names)):
            if self.col_boundaries[index] <= x < self.col_boundaries[index + 1]:
                return self.col_names[index]
        return None

    def add_primary_signet(self, day, y_center, image_name):
        self.col_signets[day].append((y_center, image_name))

    def finalize(self):
        """Sort each column's signets by vertical position (call after adding)."""
        for day in self.col_signets:
            self.col_signets[day].sort()

    def _row_boundaries(self, day):
        """Vertical row boundaries for one column, derived from its signets."""
        signets = self.col_signets.get(day, [])
        if not signets:
            return [0, self.page_height]
        boundaries = [0]
        for index in range(1, len(signets)):
            midpoint = (signets[index - 1][0] + signets[index][0]) / 2
            boundaries.append(midpoint)
        boundaries.append(self.page_height)
        return boundaries

    def row_index_in_column(self, day, y):
        """Row index for a y-position within a column, or -1 if outside."""
        boundaries = self._row_boundaries(day)
        for index in range(len(boundaries) - 1):
            if boundaries[index] <= y < boundaries[index + 1]:
                return index
        return -1

    def nearest_row(self, day, y):
        """Index of the primary signet closest to y (for secondary badges)."""
        signets = self.col_signets.get(day, [])
        if not signets:
            return None
        nearest_idx = 0
        nearest_dist = abs(y - signets[0][0])
        for row_index, (signet_y, _) in enumerate(signets):
            dist = abs(y - signet_y)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_idx = row_index
        return nearest_idx


def _is_primary_signet(width, height):
    tall = (PRIMARY_SIGNET_WIDTH[0] < width < PRIMARY_SIGNET_WIDTH[1]
            and PRIMARY_SIGNET_TALL_HEIGHT[0] < height < PRIMARY_SIGNET_TALL_HEIGHT[1])
    square = (PRIMARY_SIGNET_WIDTH[0] < width < PRIMARY_SIGNET_WIDTH[1]
              and PRIMARY_SIGNET_SQUARE_HEIGHT[0] < height < PRIMARY_SIGNET_SQUARE_HEIGHT[1])
    return tall or square


def _is_secondary_badge(width, height):
    return (SECONDARY_BADGE_SIZE[0] < width < SECONDARY_BADGE_SIZE[1]
            and SECONDARY_BADGE_SIZE[0] < height < SECONDARY_BADGE_SIZE[1])


def _collect_signets(page, grid, image_data_dict):
    """Populate grid with primary signets and return (cell_signets, badges).

    cell_signets: {(day, row): [signet_type, ...]} from primary signets
    badges:       {day: [(y_center, image_name), ...]} secondary badges
    """
    badges = defaultdict(list)
    for image in page.images:
        width = image['x1'] - image['x0']
        height = image['bottom'] - image['top']
        x_center = (image['x0'] + image['x1']) / 2
        y_center = (image['top'] + image['bottom']) / 2
        day = grid.column_for_x(x_center)
        if not day:
            continue
        image_name = image.get('name', '')
        if _is_primary_signet(width, height):
            grid.add_primary_signet(day, y_center, image_name)
        elif _is_secondary_badge(width, height):
            badges[day].append((y_center, image_name))

    grid.finalize()

    # Map each primary signet to its row index.
    cell_signets = defaultdict(list)
    for day, signets in grid.col_signets.items():
        for row_index, (_, image_name) in enumerate(signets):
            if image_name in image_data_dict:
                signet_type = classify_signet(image_data_dict[image_name])
                if signet_type not in ('SPACER', 'LOGO'):
                    cell_signets[(day, row_index)].append(signet_type)

    # Assign secondary badges to the nearest primary row.
    for day, day_badges in badges.items():
        for badge_y, badge_name in day_badges:
            if badge_name not in image_data_dict:
                continue
            signet_type = classify_signet(image_data_dict[badge_name])
            if signet_type in ('SPACER', 'LOGO', 'UNKNOWN'):
                continue
            row = grid.nearest_row(day, badge_y)
            if row is not None:
                cell_signets[(day, row)].append(signet_type)

    return cell_signets


def _collect_cell_text(page, grid, words):
    """Group non-footer words into {(day, row): [(y, x, text), ...]}."""
    cell_text = defaultdict(list)
    footer_y = page.height * FOOTER_ZONE_RATIO
    for word in words:
        if word['top'] > footer_y:
            continue
        x_center = (word['x0'] + word['x1']) / 2
        day = grid.column_for_x(x_center)
        if not day:
            continue
        row = grid.row_index_in_column(day, word['top'])
        if row >= 0:
            cell_text[(day, row)].append((word['top'], word['x0'], word['text']))
    return cell_text


def _strip_headers(text):
    """Remove leading day names and casino/date header remnants from cell text."""
    for day_name in WEEKDAYS:
        if text.startswith(day_name):
            text = text[len(day_name):].strip()
            break
    text = re.sub(
        r'^.*?Casino\s+[\w\s\-äöüÄÖÜß]+?\s+'
        r'(?=(Veganes|Vegetarisches|Stammessen|Menü|Tipp|Add-on|Pasta|Meer|Vital|Grill|zentrale|JOB))',
        '', text).strip()
    text = re.sub(r'Speisekarte vom.*?(?=\s[A-Z])', '', text).strip()
    for day_name in WEEKDAYS:
        if text.startswith(day_name):
            text = text[len(day_name):].strip()
    return text


def parse_dish_record(day, row, text_parts, signets):
    """Build a dish record dict from a cell's raw words and signets.

    Returns None for header/footer/too-short cells that are not real dishes.
    """
    text_parts.sort()  # by y, then x
    full_text = ' '.join(text for _, _, text in text_parts)

    if len(full_text.strip()) < 10:
        return None
    if 'Speisekarte vom' in full_text and 'Casino' in full_text:
        return None
    if 'Zusatzstoffe und Allergene' in full_text:
        return None
    if 'Produktionsprozesse' in full_text:
        return None

    text = _strip_headers(full_text)

    category = ''
    for category_label in CATEGORY_LABELS:
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

    # Extract Zusatzstoffe (comma-separated numeric codes, optional dot suffix,
    # e.g. "2, 3, 18.1"). Stops at the next non-code token (e.g. "DB:").
    zusatzstoffe = ''
    zusatz_match = re.search(r'Zusatzstoffe:\s*([\d.,\s]*?)(?:\s*DB:|\s*[A-Za-z]|$)', text)
    if zusatz_match:
        zusatzstoffe = zusatz_match.group(1).strip().rstrip(',').strip()

    # Extract DB price
    price_db = None
    price_match = re.search(r'DB:\s*(\d+[.,]\d{2})', text)
    if price_match:
        price_db = float(price_match.group(1).replace(',', '.'))

    # Dish name = everything before "Allergene:" or price
    dish = re.split(r'\s*\|?\s*Allergene:', text)[0].strip().rstrip('|').strip()
    dish = re.split(r'\s*DB:\s*\d', dish)[0].strip()

    # Add-on detection: components/upgrades priced below Sachbezugswert, or
    # explicitly marked "Upgrade gefällig?".
    is_addon = (category.lower().startswith('add-on')
                or 'upgrade gefällig' in dish.lower()
                or (price_db is not None and price_db < SACHBEZUGSWERT))

    return {
        'day': day,
        'row': row,
        'category': category,
        'dish': dish,
        'allergene': allergene,
        'zusatzstoffe': zusatzstoffe,
        'price_db': price_db,
        'signets': signets,
        'is_addon': is_addon,
    }


def extract_page(page, image_data_dict):
    """Extract dishes and signets from a single page.

    Returns (dish_records, error). error is a string on structural failure,
    None on success.
    """
    words = page.extract_words(keep_blank_chars=True, x_tolerance=2, y_tolerance=2)

    grid = PageGrid(page, words)
    if not grid.has_enough_columns:
        return [], "Too few day headers"

    cell_signets = _collect_signets(page, grid, image_data_dict)
    cell_text = _collect_cell_text(page, grid, words)

    def cell_sort_key(cell):
        (day, row), _ = cell
        day_order = WEEKDAYS.index(day) if day in WEEKDAYS else 99
        return (day_order, row)

    results = []
    for (day, row), text_parts in sorted(cell_text.items(), key=cell_sort_key):
        record = parse_dish_record(day, row, text_parts, cell_signets.get((day, row), []))
        if record is not None:
            results.append(record)

    return results, None


def extract_menu(pdf_path):
    """Extract full menu from all pages of a casino PDF.

    Returns (dish_records, casino_name, date_range).
    """
    pdf = pdfplumber.open(pdf_path)
    reader = PdfReader(pdf_path)

    all_results = []
    casino_name = ''
    date_range = ''

    for page_idx in range(len(pdf.pages)):
        page = pdf.pages[page_idx]

        if page_idx < len(reader.pages):
            image_data = {image.name.split('.')[0]: image.data
                          for image in reader.pages[page_idx].images}
        else:
            image_data = {}

        results, error = extract_page(page, image_data)
        if error:
            continue

        all_results.extend(results)

        # Extract casino name + date range from first-page header.
        if page_idx == 0:
            words = page.extract_words(keep_blank_chars=True, x_tolerance=2, y_tolerance=2)
            header = ' '.join(word['text'] for word in words if word['top'] < 75)
            name_match = re.search(r'Casino\s+([\w\s\-äöüÄÖÜß]+?)(?:\s+Montag|\s+Samstag)', header)
            casino_name = name_match.group(0).strip() if name_match else ''
            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})\s+bis\s+(\d{2}\.\d{2}\.\d{4})', header)
            date_range = f"{date_match.group(1)}–{date_match.group(2)}" if date_match else ''

    pdf.close()
    return all_results, casino_name, date_range
