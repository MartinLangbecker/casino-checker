# DB Casino Speisekarten-Checker

Automatisierte Konsistenzprüfung der DB Casino Speisekarten-PDFs. Erkennt fehlerhafte Signets (Vegan/Vegetarisch/Fleisch/Fisch) anhand von Allergenkennzeichnungen und Gerichtbeschreibungen.

## Funktionsweise

1. **PDF-Download**: Alle ~80 Casino-Speisekarten werden von `casino-net.app.db.de` heruntergeladen
2. **Grid-Extraktion**: Tabellenstruktur (Spalten = Wochentage, Zeilen = Gerichtkategorien) wird per `pdfplumber` erkannt
3. **Signet-Klassifikation**: Eingebettete Icons werden per Pixel-Analyse (Aspect Ratio + Farbverteilung) klassifiziert
4. **Konsistenzprüfung**: Signets werden gegen Allergene und Gerichtbeschreibungen validiert

## Prüfregeln (Konfidenz-Stufen)

### Hohe Konfidenz (`signet_allergen_conflict`, `category_allergen_conflict`)
- VEGAN-Signet + Milch-Allergen (g/g1) → Signet falsch
- VEGAN-Signet + Ei-Allergen (c) → Signet falsch
- Kategorie "Veganes Gericht" + tierisches Allergen → Kategorie-Text falsch
- Vegetarische/Vegane Kategorie + Fleisch-Signet → Signet oder Kategorie falsch

### Mittlere Konfidenz (`signet_keyword_conflict`, `signet_category_conflict`)
- SCHWEIN-Signet auf Geflügelgericht
- GEFLÜGEL-Signet auf Fischgericht
- VEGETARISCH-Signet auf Fleischgericht

### Niedrige Konfidenz (`missing_signet`)
- Gericht mit erkannter Kategorie aber ohne Signet

### Ausschlüsse
- "vegane Bratwurst", "Veganes Fischfilet" etc. → vegane Produkte, kein Conflict
- "Joghurt" ohne Milch-Allergen → pflanzlicher Joghurt
- Gerichte mit "oder" (mehrere Optionen) → kein Keyword-Conflict

## Usage

```bash
# Einzelnes Casino analysieren
python casino_analyzer.py <pdf_path>

# Batch über alle Casinos (Download + Archiv + Analyse + Findings)
python casino_batch.py

# Analyse & Trends (liest findings/-Daten)
python analyze.py [--mode MODE] [--casino CODE] [--top N] [-q]

# Findings aus dem Archiv neu berechnen (nach Regeländerung)
python reanalyze_archive.py [--dry-run] [--week 2026_kw34] [--verbose]
```

## Verzeichnisstruktur

```
casino-checker/
├── casino_analyzer.py      # Extraktion + Konsistenzprüfung (einzelnes PDF)
├── casino_core.py          # Geteilte Analyse-/Aggregationslogik (analyze_pdfs, build_findings_data, Statistik)
├── casino_batch.py         # Batch: Download + Archiv + Analyse + Findings
├── reanalyze_archive.py    # Findings aus archivierten PDFs neu berechnen (I/O-frei via casino_core)
├── analyze.py              # Trend-Analyse, Scorecards, Anomalien, Repeat Offenders
├── README.md
├── cron.log                # Cron-Ausgabe (nur auf Pi)
├── venv/                   # Python-Virtualenv (nur auf Pi)
├── archive/                # Archivierte PDFs pro Woche
│   ├── 2026_kw33_dec_Erfurt_Bahnhofstraße.pdf
│   ├── 2026_kw34_dec_Erfurt_Bahnhofstraße.pdf
│   └── ...
└── findings/               # JSON-Ergebnisse pro Woche
    ├── 2026_kw33_findings.json
    ├── 2026_kw34_findings.json
    └── ...
```

## Output

Findings werden als JSON gespeichert (`findings/<year>_kw<nn>_findings.json`) mit:
- **meta**: Lauf-Metadaten (Zeitstempel, Anzahl Casinos, Gerichte, Findings)
- **statistics**: Gesamt-Statistik (Signet-Verteilung, Preise min/max/median/avg, Vegan-Anteil)
- **casinos**: Pro-Casino-Statistik (gleiche Struktur wie Gesamt)
- **findings**: Strukturierte Findings mit Konfidenz, Issue-Type und Recommendation

Konsolenausgabe zeigt Fortschritt und Zusammenfassung.

## Voraussetzungen

```
pip install -r requirements.txt
```

## Casino-Kürzel

Dreistellige Codes nach dem Muster `<Region><Ort><Standort>`:

| Prefix | Region |
|--------|--------|
| a | Nord (Hamburg, Bremen, Hannover, Neumünster, Seelze, Maschen) |
| b | Ost (Berlin, Magdeburg, Cottbus, Wittenberge, Neuseddin) |
| c | West/NRW (Köln, Duisburg, Düsseldorf, Dortmund, Hamm, Kassel, Krefeld, Minden, Paderborn, Wuppertal, Witten) |
| d | Mitte (Frankfurt, Erfurt, Fulda, Mainz, Würzburg) |
| e | Südost (Dresden, Leipzig, Dessau) |
| f | Südwest (Stuttgart, Karlsruhe, Mannheim, Ludwigshafen, Basel, Saarbrücken, Trier, Offenburg, Plochingen, Tübingen) |
| g | Süd/Bayern (München, Nürnberg) |

E-Mail-Schema: `casino.<kürzel>@deutschebahn.com` (z.B. `casino.dec@deutschebahn.com` für Erfurt).

Zentraler Kontakt (aus Casino-App Impressum): `DB.Gastro.Kundenbetreuung@deutschebahn.com` — vermutlich besserer Anlaufpunkt für systematische Findings als einzelne Casinos.

App: [Android](https://play.google.com/store/apps/details?id=de.wiebel_partner.dbcasino) | [iOS](https://apps.apple.com/de/app/db-casino/id1078193759)

## Signet-Erkennung

Alle Signets gemäß DB Casino Signet-Dokumentation:

| Signet | Bedeutung |
|--------|-----------|
| Vegan | Gericht ist vegan |
| Vegetarisch | Gericht ist vegetarisch |
| Nachhaltig | Gericht enthält Bestandteile aus nachhaltiger Produktion |
| Schwein | Gericht enthält Schweinefleisch |
| Schwein+Rind | Gericht enthält Schweine- und Rindfleisch |
| Rind | Gericht enthält Rindfleisch |
| Geflügel | Gericht enthält Geflügelfleisch |
| Fisch | Gericht enthält Fisch oder Fischprodukte |

Weitere Signets (selten, aktuell nicht im Classifier):
- Schwein+Geflügel, Rind+Geflügel, Wildfleisch, Lamm/Schaf, Kaninchen/Hase, Krebs-/Weichtiere, Fisch+Krebs-/Weichtiere, DGE-Zertifizierung (JOB&FIT)

### Pixel-basierte Klassifikation

| Signet | Aspect Ratio | Rot-Anteil | Grün-Anteil | Höhe (cropped) |
|--------|-------------|-----------|------------|----------------|
| Vegan | 1.55–2.0 | 0% | 1–4% | 35–48 px |
| Vegetarisch | 1.35–1.6 | 0% | 5–20% | 38–55 px |
| Schwein | 1.2–1.5 | 2–8% | 0% | 45–60 px |
| Schwein+Rind | 1.0–1.25 | 8–25% | 0% | 55–72 px |
| Rind | 1.1–1.3 | 0.8–5% | 0% | 55+ px |
| Geflügel | 0.7–0.95 | 0.3–2% | 0% | 65–90 px |
| Fisch | 0.8–1.05 | 1.8–5% | 0% | 70–90 px |
| Nachhaltig | 0.8–1.1 | 0% | 30–60% | 150–300 px |

## Allergene

Gesetzlich vorgeschriebene Kennzeichnung (EU-LMIV). Codes wie in den Casino-PDFs verwendet:

| Code | Allergen |
|------|----------|
| a | Glutenhaltiges Getreide |
| a1 | Weizen |
| a2 | Roggen |
| a3 | Gerste (Dinkel) |
| b | Krebstiere |
| c | Eier |
| d | Fisch |
| e | Erdnüsse |
| f | Schalenfrüchte (Nüsse) |
| g | Milch (einschl. Laktose) |
| g1 | Laktose |
| h | Schalenfrüchte (spezifisch) |
| h1 | Mandeln |
| h2 | Haselnüsse |
| h3 | Walnüsse |
| h4 | Cashewnüsse |
| i | Sellerie |
| j | Senf |
| k | Sesam |
| l | Schwefeldioxid/Sulfite |
| m | Lupine |
| n | Weichtiere |

Für die Konsistenzprüfung relevant:
- **g, g1** (Milch/Laktose) → widerspricht VEGAN (→ VEGETARISCH)
- **c** (Eier) → widerspricht VEGAN (→ VEGETARISCH)
- **b** (Krebstiere) → widerspricht VEGAN und VEGETARISCH (→ FISCH)
- **d** (Fisch) → widerspricht VEGAN und VEGETARISCH, bestätigt FISCH-Signet
- **n** (Weichtiere) → widerspricht VEGAN und VEGETARISCH (→ FISCH)

## Preisgestaltung (KBV Gastronomie, §7)

Grundlage: Konzernbetriebsvereinbarung über die Gestaltung der Betriebsgastronomie (12.03.2008, in Kraft seit 01.04.2008).

| Gerichttyp | Preisregel |
|-----------|-----------|
| Stammessen | Kaufmännisch gerundeter steuerlicher Sachbezugswert (2026: 4,60 €) |
| Wahlessen | Warenaufwand + 100% Aufschlag + MwSt |
| Sonstige Produkte (Anlage 2) | Vereinbarter Festpreis, dynamisiert an Lebenshaltungskostenindex |
| Zwischenverpflegung, Getränke, Non-Food | Frei kalkuliert |

### Stammessen (§5)

- Hauptkomponente (z.B. Fleisch/Fisch/Geflügel, aber auch Falafel, vegane Produkte etc.) mind. 150g Rohgewicht
- Zwei Beilagen (Kartoffeln/Reis/Teigwaren + Gemüse oder Salat)
- Alternativ: Eintopf mit Brötchen, oder Gericht mit nur 2 Komponenten (z.B. Süßspeisen)
- Freie Komponentenwahl soweit möglich

### Add-on-Erkennung

Einträge mit Preis unter dem Sachbezugswert (4,60 €) sind keine eigenständigen Gerichte, sondern Zusatzkomponenten (Upgrades, Extras, Beilagen). Sie werden aus der Statistik ausgeschlossen.

Zusätzlich: Kategorie "Add-on" (explizit im PDF so benannt).

## Bekannte Einschränkungen

- **Geschlossene Casinos** (z.B. Düsseldorf/cnb: generisches Template-PDF mit QR-Codes zu den Apps statt Speiseplan) werden als Parse-Fehler gemeldet
- **Gerichte mit Auswahl** (z.B. "Salat mit Räucherlachs oder Schinken") — Signet zeigt nur eine Variante. Diese Gerichte werden bewusst nicht als Finding gemeldet, da unklar ist welches Signet korrekt wäre.
- **Signet-Classifier** kann bei stark komprimierten JPEGs unsicher sein
- **Multi-Page-PDFs** (München, Berlin, Hamburg): Seite 2+ enthält Add-ons für dieselben Wochentage

## Analyse (analyze.py)

Liest die wöchentlichen Findings-JSONs und generiert Trend-Reports, Casino-Rankings und Anomalie-Erkennung.

### Modi

| Modus | Beschreibung |
|-------|-------------|
| `overview` | Wochenübersicht: Signets, Preise, Vegan-Steuerung, Casinos ohne Vegan (default) |
| `trend` | Multi-Wochen-Trend: Signet-Entwicklung, Vegan-Anteil, Preise nach Signet |
| `scorecard` | Casino-Ranking nach Vegan-Score (gewichteter Composite aus 4 Metriken) |
| `anomaly` | Woche-über-Woche-Änderungen: Vegan gewonnen/verloren, Preisänderungen, neue Findings |
| `findings` | Aggregierte Findings mit Repeat-Offender-Erkennung und häufigsten Issues |
| `all` | Alle Modi nacheinander |

### Optionen

| Option | Beschreibung |
|--------|-------------|
| `--mode MODE` | Analyse-Modus (default: overview) |
| `--casino CODE` | Filter auf einzelnes Casino (z.B. `cma`, `dmk`) |
| `--top N` | Anzahl Einträge in Rankings (default: 20) |
| `-q` | Kompakte Ausgabe (weniger Details) |

### Vegan-Score (Scorecard)

Gewichteter Composite-Score (0–100) aus vier Metriken:

| Metrik | Gewicht | Beschreibung |
|--------|---------|-------------|
| Vegan-Anteil | 30% | Anteil veganer Gerichte am Gesamtangebot |
| Platzierung (Row 0) | 25% | Veganes Gericht als erstes in der Spalte |
| Stammessen-Preis | 25% | Vegan zum Sachbezugswert (4,60 €) |
| Neutraler Name | 20% | Kategorie ohne "vegan" im Titel |

### Beispiele

```bash
# Aktuelle Woche: Übersicht
python analyze.py

# Alle Modi
python analyze.py --mode all

# Trend über alle verfügbaren Wochen
python analyze.py --mode trend

# Casino-Details für Krefeld
python analyze.py --mode findings --casino cma

# Top 10 Scorecards
python analyze.py --mode scorecard --top 10
```

## Geplante Features

- [x] Trend-Analyse über Wochen (Vegan-Anteil, Preisentwicklung) → `analyze.py`
- [ ] E-Mail-Benachrichtigung bei Findings an Casinos (braucht besseres Konzept)

## Steuerung veganer Nachfrage

### Hebel und Messkriterien

| Hebel | Messgröße | Ziel | KW33 Ist |
|-------|-----------|------|----------|
| **Platzierung** | Anteil veganer Gerichte an Row 0 | 100% | 44% |
| **Preis** | Anteil veganer Gerichte zum Stammessenpreis | ≥50% | 24% |
| **Auswahl** | Casino-Tage mit >1 veganem Gericht | ≥50% | 12% |
| **Benennung** | Kategorie-Label neutral (z.B. "Stammessen") | ≥50% | 20% |
| **Eigenständigkeit** | Tage ohne vegan/nicht-vegan-Doublette | 100% | (noch nicht gemessen) |

### Erläuterung

**Platzierung:** Veganes Gericht immer als erstes in der Spalte. Was oben steht, wird als Standard wahrgenommen.

**Preis:** Vegan zum Stammessenpreis (Sachbezugswert) anbieten. Aktuell sind 76% der veganen Gerichte Wahlessen (>4,60 €), bei Fleisch nur 55%. Preisparität senkt die Hürde. Lücke: zwischen 4,60 € und 6,00 € gibt es kein einziges veganes Gericht.

**Auswahl:** Mindestens 2 vegane Optionen pro Tag. Aktuell bieten nur 3 Casinos (alle Frankfurt) regelmäßig Auswahl. Ein Gericht = kein Ausweichen bei Nicht-Gefallen.

**Benennung:** "Stammessen" als Kategorie statt "Veganes Gericht" — normalisiert, keine Abgrenzung. "Veganes Stammessen" oder "Vegetarisches Stammessen" ist wieder ausgrenzend. Der Inhalt und das Signet kommunizieren vegan, der Titel muss es nicht betonen.

**Eigenständigkeit:** Nicht am gleichen Tag das gleiche Gericht in vegan und nicht-vegan anbieten (z.B. Spaghetti Bolognese + Linsenbolognese). Wer Lust auf Bolognese hat und sich nicht strikt vegan ernährt, greift zum Original. Vegane Gerichte sollen eigenständige Identität haben, nicht als Kopie positioniert sein.

**Weitere (nicht aus Daten messbar):**
- Ansprechende Namen; "vegan" als Label kann abschrecken
- Nicht nur Gesundheitsaspekt; auch comfort food (vegane Currywurst + Pommes)
- Proteingehalt kommunizieren (Bohnen, Tofu, Linsen)
- Ausreichende Portionsgrößen (oder Nachschlag-Option)
- Nicht am gleichen Tag vegan und nicht-vegan als Variante des gleichen Gerichts anbieten (z.B. Spaghetti Bolognese + Linsenbolognese) — wer Lust auf das Gericht hat, greift zum Original

### Kontext: Erwartungshaltung der Belegschaft

Studierendenwerke bieten seit 2020+ täglich vegane Gerichte zum günstigsten Preis an. Absolvent:innen die seit 3–5 Jahren im Beruf sind, kennen pflanzliche Optionen als Standard — nicht als Sonderangebot. 20 DB Casinos ohne ein einziges veganes Gericht bedienen eine Belegschaft, deren jüngere Mitglieder das aus der Mensa anders gewohnt sind. Die Erwartungshaltung ist bereits da; das Angebot hinkt hinterher.

### Argument: Universalität

Veganes Essen schließt die wenigsten aus — alle können es essen (abgesehen von spezifischen Allergien/Unverträglichkeiten). Vegetarisch schließt bereits mehr aus (Laktoseintoleranz, Milcheiweißallergie). Fleisch noch mehr (religiöse Gründe, ethische Entscheidung). Die Zielgruppe wird mit steigendem Tierproduktanteil immer kleiner.

Zudem: Kein Fleischgericht besteht nur aus Fleisch. Kartoffeln, Gemüse, Reis, Nudeln — der größte Bestandteil ist meist ohnehin pflanzlich. Der Schritt zum komplett veganen Gericht ist kleiner als wahrgenommen. Die Anreize (Preis, Platzierung, Auswahl) müssen stimmen, der Rest passiert intrinsisch.

Klimaaspekte (Landverbrauch, Wasserverbrauch, CO₂) sind ein weiteres Argument, aber für die meisten weniger greifbar und als alleiniger Motivator unzureichend.

### Vorbilder / Best Practices

- **Studierendenwerk Thüringen**: Seit 2020 täglich ein veganes Gericht. Preisgestaltung als Steuerung: günstigstes Gericht (1,95 €) ist täglich pflanzlich, Fleischgerichte kosten mindestens 2,70 € — expliziter Preisanreiz. Anteil Fleischgerichte sinkt bewusst. Aktionswochen mit komplett vegetarisch/veganem Speiseplan (4 Gerichte/Tag, davon 2 vegan, 1 vegetarisch; Mittwoch komplett fleischfrei). ([Preise](https://www.stw-thueringen.de/aktuelles/neue-preise-in-den-mensen.html), [Vegane Woche](https://www.stw-thueringen.de/aktuelles/vegane-und-vegetarische-woche-in-der-mensa-philosophenweg.html), [Tägliches Angebot](https://www.stw-thueringen.de/aktuelles/taeglich-ein-vegetarisches-und-veganes-gericht-auf-dem-mensa-speiseplan.html))
- **Mensa Rempartstraße, Freiburg (SWFR)**: Nachschlag-Konzept — wer nach der Portion noch Hunger hat, kann kostenlos eine weitere Portion abholen. Reduziert Lebensmittelverschwendung und garantiert Sättigung.
- **Allgemein Mensen**: Veganes Gericht immer in günstigster Preiskategorie → Preisanreiz für Flexitarier

### Prüfung

Die messbaren Kriterien (Platzierung, Preis, Auswahl, Benennung) werden im wöchentlichen Batch-Lauf mit ausgewertet und in `findings/<year>_kw<nn>_findings.json` unter `statistics` gespeichert.

## Wartung

### Seltene Signets ergänzen

Folgende Signets existieren laut Signet-Dokumentation, treten aber aktuell in keinem PDF auf. Sobald sie auftreten, müssen sie im Classifier (`classify_signet()`) anhand eines Beispiel-PDFs profiliert werden:

- Schwein+Geflügel
- Rind+Geflügel
- Wildfleisch
- Lamm/Schaf
- Kaninchen/Hase
- Krebs-/Weichtiere
- Fisch+Krebs-/Weichtiere
- DGE-Zertifizierung (JOB&FIT)

Vorgehen: PDF mit neuem Signet im Archiv identifizieren → Pixel-Profil extrahieren (Aspect Ratio, Rot/Grün/Schwarz-Anteil) → Classifier-Regel ergänzen.

### Sachbezugswert aktualisieren

Der Sachbezugswert (`SACHBEZUGSWERT` in `casino_analyzer.py`) wird jährlich vom BMF angepasst. Aktueller Wert: 4,60 € (2026). Bei Änderung im Folgejahr die Konstante aktualisieren.
