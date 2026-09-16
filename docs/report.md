# Analyse & Wartung

## Report-Tool (`casino_report.py`)

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
python casino_report.py

# Alle Modi
python casino_report.py --mode all

# Trend über alle verfügbaren Wochen
python casino_report.py --mode trend

# Casino-Details für Krefeld
python casino_report.py --mode findings --casino cma

# Top 10 Scorecards
python casino_report.py --mode scorecard --top 10
```

## Output-Format

Findings werden als JSON gespeichert (`findings/<year>_kw<nn>_findings.json`) mit:
- **meta**: Lauf-Metadaten (Zeitstempel, Anzahl Casinos, Gerichte, Findings)
- **statistics**: Gesamt-Statistik (Signet-Verteilung, Preise min/max/median/avg, Vegan-Anteil)
- **casinos**: Pro-Casino-Statistik (gleiche Struktur wie Gesamt)
- **findings**: Strukturierte Findings mit Konfidenz, Issue-Type und Recommendation

Konsolenausgabe zeigt Fortschritt und Zusammenfassung.

## Wartung

### Seltene Signets ergänzen

Folgende Signets existieren laut Signet-Dokumentation, treten aber aktuell in keinem PDF auf. Sobald sie auftreten, müssen sie im Classifier (`classify_signet()` in `signet_classifier.py`) anhand eines Beispiel-PDFs profiliert werden:

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

Der Sachbezugswert (`SACHBEZUGSWERT` in `constants.py`) wird jährlich vom BMF angepasst. Aktueller Wert: 4,60 € (2026). Bei Änderung im Folgejahr die Konstante aktualisieren.
