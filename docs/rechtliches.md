# Rechtliches

Stand: November 2026. Zusammenfassung nach bestem Wissen, keine Rechtsberatung.

## DWD-Daten

Vorhersage (MOSMIX), Warnungen, Pollenflug und Radar stammen vom Open-Data-Angebot des
Deutschen Wetterdienstes und stehen unter **CC BY 4.0**.

So erfüllt die Integration die Lizenz:

| Pflicht | Umsetzung |
|---|---|
| Quelle nennen | Jede Entität hat `attribution: "Datenbasis: Deutscher Wetterdienst"`. Die Karte zeigt den Vermerk immer an; er lässt sich nicht ausschalten. |
| Änderungen kenntlich machen | Berechnete Werte sind als berechnet markiert und nennen im Attribut `quelle` ihre Herkunft. |
| Lizenz verlinken | README und Karte verlinken auf CC BY 4.0. |
| Kein Anschein einer Billigung | Kein DWD-Logo, kein Bundesadler, „DWD“ nicht im Projektnamen. Das Projekt ist kein Angebot des DWD. |

**Amtliche Warnungen** werden im Wortlaut angezeigt und nie verändert. Sie lassen sich ausblenden.
Eigene Hinweise der Integration sind davon klar getrennt und heißen nie „Warnung des DWD“.

**Warngebiete:** Deren Geometrien tragen den Vermerk „© GeoBasis-DE / BKG“. Die Integration fragt
nur Punkte ab und zeigt keine Flächen an. Kommt eine Warnkarte hinzu, wird der BKG-Vermerk ergänzt.

## Umweltbundesamt (optional, geplant)

Luftqualitätsdaten stehen unter der Datenlizenz Deutschland – Namensnennung 2.0.
Quellenangabe: „Umweltbundesamt mit Daten der Messnetze der Länder und des Bundes“.
Die Nutzungsbedingungen der API werden vor dem Einbau noch einmal geprüft.

## Code

Der Code steht unter der MIT-Lizenz. Das Repo enthält keine Wetterdaten; sie werden zur Laufzeit geladen.
Abhängigkeiten werden nur mit freizügigen Lizenzen eingesetzt.

## Vorbild

[Hestia Weather](https://github.com/hestiaFB/hestia-weather-integration) (MIT) diente als Ideengeber.
Code, Texte, Bilder, Kartendesign und Name werden nicht übernommen.

## Datenschutz

- Vorhersage, Pollen und Radardateien werden ohne Standortangabe geladen.
- Für Warngebiet und Radar-Punktabfrage werden Koordinaten an den DWD gesendet, standardmäßig auf
  2 Nachkommastellen (ca. 1 km) gerundet. Die Rundung ist einstellbar.
- Die Integration sendet keine Daten an andere Dienste.

## Quellen

- [DWD: Nutzungsbedingungen Open Data](https://opendata.dwd.de/climate_environment/CDC/Nutzungsbedingungen_German.pdf)
- [DWD: Rechtliche Hinweise](https://www.dwd.de/DE/service/rechtliche_hinweise/rechtliche_hinweise_node.html)
- [DWD: Beschreibung Pollenflug-Gefahrenindex](https://opendata.dwd.de/climate_environment/health/alerts/Beschreibung_pollen_s31fg.pdf)
- [UBA: Schnittstellenbeschreibung Luftdaten-API](https://www.umweltbundesamt.de/sites/default/files/medien/358/dokumente/schnittstellenbeschreibung_luftdaten_api_v4.pdf)
- [Creative Commons BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.de)
