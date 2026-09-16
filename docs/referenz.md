# Referenz

Nachschlage-Referenz zu Prüfregeln, Casino-Kürzeln, Signets, Allergenen und Zusatzstoffen.

## Prüfregeln (Konfidenz-Stufen)

### Hohe Konfidenz (`signet_allergen_conflict`, `category_allergen_conflict`, `signet_additive_conflict`, `category_additive_conflict`)
- VEGAN-Signet + Milch-Allergen (g/g1) → Signet falsch
- VEGAN-Signet + Ei-Allergen (c) → Signet falsch
- VEGAN-Signet/-Kategorie + Molkerei-Zusatzstoff (18/18.1–18.5) → nicht vegan (auch ohne Milch-Allergen)
- Kategorie "Veganes Gericht" + tierisches Allergen → Kategorie-Text falsch
- Vegetarische/Vegane Kategorie + Fleisch-Signet → Signet oder Kategorie falsch

### Mittlere Konfidenz (`signet_keyword_conflict`, `signet_category_conflict`, `signet_additive_conflict`)
- SCHWEIN-Signet auf Geflügelgericht
- GEFLÜGEL-Signet auf Fischgericht
- VEGETARISCH-Signet auf Fleischgericht
- VEGAN-Signet + Zusatzstoff 7 (gewachst) → Wachs kann tierisch sein, Prüfhinweis

### Niedrige Konfidenz (`missing_signet`)
- Gericht mit erkannter Kategorie aber ohne Signet

### Ausschlüsse
- "vegane Bratwurst", "Veganes Fischfilet" etc. → vegane Produkte, kein Conflict
- "Joghurt" ohne Milch-Allergen → pflanzlicher Joghurt
- Gerichte mit "oder" (mehrere Optionen) → kein Keyword-Conflict

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

Die konkreten Schwellwerte sind als benannte Konstanten am Kopf von `signet_classifier.py` gebündelt (`VEGAN_MIN_ASPECT`, `FISCH_MIN_BLACK_PCT` etc.). Bei Layout-Änderungen der PDFs dort rekalibrieren.

## Allergene

Gesetzlich vorgeschriebene Kennzeichnung (EU-LMIV). Codes wie in den Casino-PDFs verwendet:

| Code | Allergen |
|------|----------|
| a | Glutenhaltiges Getreide |
| a1 | Weizen |
| a2 | Roggen |
| a3 | Gerste |
| a4 | Hafer |
| a5 | Dinkel |
| a6 | Kamut |
| a7 | Hybridstämme davon |
| b | Krebstiere |
| c | Eier |
| d | Fisch |
| e | Erdnüsse |
| f | Soja |
| g | Milch und Milcherzeugnisse (inkl. Laktose) |
| g1 | Laktose |
| h | Schalenfrüchte und Nüsse |
| h1 | Mandeln |
| h2 | Haselnüsse |
| h3 | Walnüsse |
| h4 | Cashewnüsse |
| h5 | Pekannüsse |
| h6 | Paranüsse |
| h7 | Pistazien |
| h8 | Macadamia-/Queenslandnüsse |
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

## Zusatzstoffe

Kennzeichnungspflichtige Zusatzstoffe, in den PDFs als `Zusatzstoffe: 2, 3, 18.1` (komma-separierte Codes) deklariert. Für die Konsistenzprüfung sind nur zwei Codes relevant, beide als Nicht-Vegan-Indikator:

| Code | Zusatzstoff | Konfidenz | Bedeutung für Prüfung |
|------|-------------|-----------|-----------------------|
| 7 | gewachst | mittel | Wachs kann tierisch (Bienenwachs, Schellack) oder pflanzlich (Carnauba) sein → Prüfhinweis bei VEGAN-Signet |
| 18 | mit Molkereiprodukt/-en | hoch | eindeutig nicht vegan |
| 18.1 | mit Milcheiweiß | hoch | eindeutig nicht vegan |
| 18.2 | mit Milchpulver | hoch | eindeutig nicht vegan |
| 18.3 | mit Molkenpulver | hoch | eindeutig nicht vegan |
| 18.4 | unter Verwendung von Milch | hoch | eindeutig nicht vegan |
| 18.5 | unter Verwendung von Sahne | hoch | eindeutig nicht vegan |

Molkerei-Zusatzstoffe (18.x) fangen Fälle, in denen Milch enthalten ist, aber **kein** Milch-Allergen (g/g1) deklariert wurde. Alle übrigen Zusatzstoff-Codes (Farbstoff, Konservierung, Süßungsmittel etc.) sind für die Vegan-Prüfung nicht relevant.
