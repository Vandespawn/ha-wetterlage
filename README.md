# Wetterlage für Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Custom-orange)](https://hacs.xyz)
[![Lizenz: MIT](https://img.shields.io/badge/Lizenz-MIT-blue)](LICENSE)

> **Status: in Entwicklung.** Die Integration ist noch nicht installierbar. Dieses Repo enthält derzeit das Konzept.

Wetterlage holt Vorhersage, amtliche Warnungen, Pollenflug und Regenradar vom Deutschen Wetterdienst,
verbindet sie mit deiner eigenen Wetterstation und rechnet aus, was das für dich heißt:
gefühlte Temperatur, Regen in der nächsten Stunde, Frost, Gewitter, Hitze und ein Tagesbericht auf Deutsch.
Das Ergebnis steht als Entitäten für Automationen bereit und auf einer mitgelieferten Dashboard-Karte.

**Alles ist einstellbar:** Quellen, Sensoren, Rechenmodelle, Schwellenwerte, Texte und jeder Teil der Karte.

## Geplanter Umfang

| Bereich | Inhalt |
|---|---|
| Vorhersage | DWD MOSMIX-L der nächstgelegenen Station, stündlich und täglich bis 10 Tage, als `weather`-Entität |
| Amtliche Warnungen | DWD-Warnungen für deine Gemeinde und deinen Landkreis, unverändert, mit Stufe 1 bis 4 |
| Pollenflug | DWD-Pollenflug-Gefahrenindex für 8 Pollenarten, heute bis übermorgen |
| Regen nächste Stunde | DWD-Radar-Nowcast (RV) in 5-Minuten-Schritten bis 2 Stunden voraus |
| Gefühlte Temperatur | Windchill, Hitzeindex oder Steadman, mit Sonne; mit Begründung im Attribut `grund` |
| Eigene Hinweise | Frost, Bodenfrost, Glätte, Gewitter, Hitze, Tropennacht, Sturm, Starkregen |
| Tagesbericht | Fließtext auf Deutsch, Bausteine und Reihenfolge wählbar |
| Wetterstation | optional, z. B. Ecowitt; jeder Messwert frei zuordenbar |
| Dashboard-Karte | wird mit der Integration ausgeliefert, kein zweites HACS-Paket |
| Automationen | Ereignisse bei Warnungen und Hinweisen, Blueprints |

Jede Entität nennt im Attribut `grund`, warum sie diesen Wert hat, und im Attribut `quelle`, woher er stammt.

Alle Einstellungen: [docs/einstellungen.md](docs/einstellungen.md)

## Installation (sobald verfügbar)

1. HACS → ⋮ → **Benutzerdefinierte Repositories** → `https://github.com/Vandespawn/ha-wetterlage`, Kategorie **Integration**.
2. **Wetterlage** installieren und Home Assistant neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Wetterlage.**

Voraussetzung: Home Assistant 2026.7 oder neuer.

## Datenquellen und Lizenz

**Datenbasis: Deutscher Wetterdienst**, lizenziert unter [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.de).
Einzelne Werte werden von der Integration aus diesen Daten berechnet.

Die Integration lädt die Daten erst zur Laufzeit direkt vom DWD. Dieses Repo enthält keine DWD-Daten.
Der Code steht unter der [MIT-Lizenz](LICENSE).

Dieses Projekt ist **kein Angebot des Deutschen Wetterdienstes** und wird von ihm weder betrieben noch unterstützt.

Details: [docs/rechtliches.md](docs/rechtliches.md)

## Wichtiger Hinweis

Die gefühlte Temperatur und die eigenen Hinweise sind Schätzungen, keine amtlichen Warnungen.
Sie ersetzen weder die Warnungen des DWD noch die Anweisungen von Behörden. Keine Gewähr für Richtigkeit und Verfügbarkeit.

## Inspiration

Die Idee, Vorhersage, Station und Warnungen zusammenzuführen und zu erklären, stammt von
[Hestia Weather](https://github.com/hestiaFB/hestia-weather-integration) für Frankreich.
Wetterlage ist eine eigenständige Neuentwicklung für Deutschland und übernimmt keinen Code daraus.
