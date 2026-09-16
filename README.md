# DB Casino Speisekarten-Checker

Automatisierte Konsistenzprüfung der DB Casino Speisekarten-PDFs. Erkennt fehlerhafte Signets (Vegan/Vegetarisch/Fleisch/Fisch) anhand von Allergenkennzeichnungen und Gerichtbeschreibungen.

## Funktionsweise

1. **PDF-Download**: Alle ~80 Casino-Speisekarten werden von `casino-net.app.db.de` heruntergeladen
2. **Grid-Extraktion**: Tabellenstruktur (Spalten = Wochentage, Zeilen = Gerichtkategorien) wird per `pdfplumber` erkannt
3. **Signet-Klassifikation**: Eingebettete Icons werden per Pixel-Analyse (Aspect Ratio + Farbverteilung) klassifiziert
4. **Konsistenzprüfung**: Signets werden gegen Allergene und Gerichtbeschreibungen validiert

Details zu den Prüfregeln, Signets und Allergen-Codes: siehe [docs/referenz.md](docs/referenz.md).

## Voraussetzungen

```
pip install -r requirements.txt
```

Für Entwicklung (Tests + Linting) zusätzlich:

```
pip install -r requirements-dev.txt
```

## Usage

```bash
# Einzelnes Casino analysieren
python casino_analyzer.py <pdf_path>

# Batch über alle Casinos (Download + Archiv + Analyse + Findings)
python casino_batch.py [--verbose]

# Analyse & Trends (liest findings/-Daten)
python casino_report.py [--mode MODE] [--casino CODE] [--top N] [-q]

# Findings aus dem Archiv neu berechnen (nach Regeländerung)
python reanalyze_archive.py [--dry-run] [--week 2026_kw34] [--verbose] [--debug]
```

`--verbose` bei `casino_batch.py` und `--debug` bei `reanalyze_archive.py` aktivieren
volle Tracebacks für Parse-Fehler (Logging auf DEBUG-Level).

Report-Modi, Optionen und Vegan-Score: siehe [docs/report.md](docs/report.md).

### Tests und Linting

```bash
pytest
ruff check .
```

## Verzeichnisstruktur

```
casino-checker/
├── casino_analyzer.py      # Facade + CLI (einzelnes PDF), re-exportiert die Module unten
├── constants.py            # Geteilte Konstanten: Signets, Keywords, Allergen-Sets
├── signet_classifier.py    # Pixel-basierte Signet-Klassifikation (classify_signet)
├── pdf_extractor.py        # PDF → Dish-Records (extract_menu, extract_page, PageGrid)
├── consistency.py          # Konsistenzregeln (check_consistency)
├── casino_core.py          # Geteilte Analyse-/Aggregationslogik (analyze_pdfs, build_findings_data, Statistik)
├── casino_batch.py         # Batch: Download + Archiv + Analyse + Findings
├── reanalyze_archive.py    # Findings aus archivierten PDFs neu berechnen (I/O-frei via casino_core)
├── casino_report.py        # Trend-Analyse, Scorecards, Anomalien, Repeat Offenders
├── tests/                  # pytest-Tests (test_consistency.py)
├── pyproject.toml          # ruff- + pytest-Konfiguration
├── requirements.txt        # Laufzeit-Abhängigkeiten (gepinnt)
├── requirements-dev.txt    # Zusätzlich: pytest, ruff
├── docs/                   # Referenz, Report-Doku, Vegan-Strategie
├── archive/                # Archivierte PDFs pro Woche
└── findings/               # JSON-Ergebnisse pro Woche
```

## Bekannte Einschränkungen

- **Geschlossene Casinos** (z.B. Düsseldorf/cnb: generisches Template-PDF mit QR-Codes zu den Apps statt Speiseplan) werden als Parse-Fehler gemeldet
- **Gerichte mit Auswahl** (z.B. "Salat mit Räucherlachs oder Schinken") — Signet zeigt nur eine Variante. Diese Gerichte werden bewusst nicht als Finding gemeldet, da unklar ist welches Signet korrekt wäre.
- **Signet-Classifier** kann bei stark komprimierten JPEGs unsicher sein
- **Multi-Page-PDFs** (München, Berlin, Hamburg): Seite 2+ enthält Add-ons für dieselben Wochentage

## Geplante Features

- [x] Trend-Analyse über Wochen (Vegan-Anteil, Preisentwicklung) → `casino_report.py`
- [ ] E-Mail-Benachrichtigung bei Findings an Casinos (braucht besseres Konzept)

## Dokumentation

- [docs/referenz.md](docs/referenz.md) — Prüfregeln, Casino-Kürzel, Signet-Erkennung, Allergene
- [docs/report.md](docs/report.md) — Report-Tool (Modi, Optionen, Vegan-Score), Output-Format, Wartung
- [docs/vegan-strategie.md](docs/vegan-strategie.md) — Preisgestaltung (KBV) und Steuerung veganer Nachfrage
