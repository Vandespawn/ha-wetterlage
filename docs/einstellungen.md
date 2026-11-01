# Einstellungen

Alles wird im Bereich **Wetterlage** in der Seitenleiste eingestellt, ohne YAML.
Die Karte hat zusätzlich ihren eigenen Editor im Dashboard.
Einstellungen lassen sich als JSON exportieren und importieren.

Fest sind nur zwei Dinge, weil die Lizenz es verlangt: der Quellenvermerk des DWD und der Wortlaut amtlicher Warnungen.

| Bereich | Einstellungen |
|---|---|
| **Ort** | Anzeigename, Koordinaten (Standard: Zone `home`), Höhe über NN, Rundung der Koordinaten für DWD-Abfragen |
| **Datenquellen** | Vorhersage-Station (automatisch oder Auswahl), Warngebiet (automatisch oder Warncell-ID), Pollenregion, Radar an/aus, Abrufintervalle je Quelle |
| **Wetterstation** | Sensor je Messgröße (Temperatur, Feuchte, Wind, Böen, Strahlung, UV, Regenrate, Regen der Woche, Bodentemperatur, Luftdruck, gefühlte Temperatur) oder DWD-Wert; Vorrang Station oder DWD |
| **Gefühlte Temperatur** | Modell (automatisch, Windchill, Hitzeindex, Steadman, Wert der Station, keine Korrektur), Wind und Sonne an/aus, Stärke des Sonneneffekts, Grenzwerte für Windchill und Schwüle, eigene Wörter je Temperaturbereich |
| **Regen** | Zeitraum 30 min bis 2 h, Schwelle in mm/h |
| **Eigene Hinweise** | Frost, Gewitter, Hitze, Sturm, Starkregen: jeweils an/aus, Vorausschau und Schwellen je Stufe; Bodenfrost, Glätte und Tropennacht einzeln |
| **Amtliche Warnungen** | anzeigen, Mindeststufe, Beschreibung und Verhaltenshinweise an/aus |
| **Pollen** | Pollenarten, Tag (heute, morgen, übermorgen), ab welcher Stufe es als Belastung gilt |
| **Tagesbericht** | Bausteine (Warnung, heute, Nacht, Wind, morgen, Pollen) an/aus und in eigener Reihenfolge, Stil kurz oder ausführlich, Uhrzeiten für „heute“ und „Nacht“ |
| **Karte** | Abschnitte an/aus und in eigener Reihenfolge, Anzahl Tage, Nachkommastellen, Design, Symbole oder Text, Farben je Stufe und für Regen, Eckenradius |
| **Entitäten** | Präfix der Entitäts-IDs, jede Entität einzeln an/aus |
| **Ereignisse** | Ereignis bei amtlicher Warnung, Ereignis bei eigenem Hinweis |

## Standardwerte

```json
{
  "quellen": { "mosmix_station": "auto", "warngebiet": "auto", "radar": true,
               "intervall_vorhersage_min": 60, "intervall_warnungen_min": 5,
               "intervall_radar_min": 5, "intervall_pollen_min": 360 },
  "gefuehlt": { "modell": "auto", "wind": true, "sonne": true, "sonnen_faktor": 0.1,
                "windchill_bis_c": 10, "schwuele_ab_c": 27, "schwuele_ab_feuchte": 40 },
  "regen": { "zeitraum_min": 60, "schwelle_mmh": 0.1 },
  "hinweise": {
    "frost": { "vorlauf_h": 24, "frost_ab_c": 0, "streng_ab_c": -10, "frostgefahr_ab_c": 3 },
    "gewitter": { "vorlauf_h": 12, "gering_ab": 10, "mittel_ab": 25, "hoch_ab": 50 },
    "hitze": { "tage": 3, "warm_ab": 27, "heiss_ab": 30, "extrem_ab": 35, "tropennacht_ab": 20 },
    "sturm": { "vorlauf_h": 24, "boeen_ab_kmh": 60, "orkan_ab_kmh": 100 },
    "starkregen": { "vorlauf_h": 24, "ab_mm_pro_h": 10 }
  },
  "warnungen": { "anzeigen": true, "mindeststufe": 1 }
}
```
