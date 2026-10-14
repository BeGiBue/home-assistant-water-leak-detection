# Beta 1.2.0: veröffentlichter Stand und Praxistest

Diese Vorabversion ist für einen begrenzten privaten Test der hydraulischen
Erkennung gedacht: Slow, Low, High und Burst sowie Benachrichtigung, Mute und ACK.
Am 14. Oktober 2026 ist **1.2.0-beta.3 als GitHub-Pre-release veröffentlicht**.
Der zuletzt veröffentlichte stabile Stand bleibt 1.1.0. Eine Veröffentlichung
aktualisiert kein laufendes HA; Download/Installation und Neustart sind erforderlich.

Für die konkrete private Installation wurde bestätigt: ausschließlich Hydrus
eingerichtet; externe Lecksensoren wurden nie konfiguriert. H01 ist damit für
diese Installation nicht relevant. Für andere Installationen gelten weiterhin
die unten genannten Voraussetzungen; H01 ist nicht allgemein geschlossen.

## Voraussetzung: hydraulischer Einsatz ohne externe Sensoren

F04-FSR-H01 bleibt ein offenes Sicherheitsfinding bei beschädigten gespeicherten
Alarmdaten aktuell eingebundener externer Wassermelder. Externe Sensoren sind
deshalb nicht uneingeschränkt für diese Beta freigegeben.

Vor Installation die bestehende vollständige HA-Konfiguration und Runtime-Datei
sichern. Prüfen, dass keine externen Sensoren konfiguriert sind und die gespeicherten
Listen `external_sources` und `external_alarm_ledger` leer sind. Nicht nur den
angezeigten Hauptalarm prüfen. Vorhandene Datensätze nicht löschen, um diese
Voraussetzung künstlich herzustellen. Bei vorhandenen Zuständen ist dieser
eingeschränkte Beta-Einsatz nicht abgenommen. Gültige Alarme zunächst über ihren
vorgesehenen physischen beziehungsweise autorisierten Weg bearbeiten.

Shutoff ist ein optionales Anforderungssignal; die Integration betätigt kein
Ventil. Für den ersten Haushaltsversuch keine neue Absperrautomation einrichten.
ACK und persönliches Mute wirken ausschließlich auf Benachrichtigungen, nie auf
physische Alarme oder Shutoff. Globales ACK erfordert die aktuelle Berechtigung
und Home-Zone; die vorhandene HA-Quittieroberfläche verwendet dieselben Prüfungen.

## Hydrus, wmbusmeters und MQTT

Geprüft wurde die gelieferte Discovery für `flow_m3h` in m³/h und `total_m3` in m³
vom selben Topic, mit originalem UTC-`timestamp` und `force_update: true` für Flow.
Die Discovery enthält kein `expire_after`. Zwei Originalnullmeldungen mit
116 Sekunden Abstand und eine identische Wiederzustellung wurden über einen
echten TCP-Broker und HA geprüft. Das belegt Strukturkompatibilität, nicht die
vollständige Funk-/Firmwarekampagne.

`force_update: true` ist für die getestete Konfiguration empfohlen und stellt
sicher, dass wiederholte gleiche Flowwerte neue HA-Auswertungen auslösen.
Der Wert muss bei erneuter Veröffentlichung der Add-on-Discovery erhalten bleiben.
Die Integration verändert die wmbusmeters-Konfiguration nicht automatisch.
Ein identischer alter Payload wird dadurch nicht zu neuer physischer Evidenz.

Die Originalmesszeit liefert das bestätigte physische Intervall. Empfangszeit
bleibt für Timeout und Diagnose zuständig. Steigende oder fallende Zustelllatenz
verwirft daher keine Burst-/Quiet-Evidenz mehr. Die 2-µs-Rundungstoleranz bleibt
unverändert. Unknown/unavailable, Replay, Restart und ausdrücklich ausgeschlossene
Intervalle erzeugen weiterhin keine Messzeit. Auch eine ausgeschlossene Lücke der
Originalmesszeiten wird bei konfiguriertem `source_max_age_seconds` verworfen.

Der Default von `source_max_age_seconds` ist 0: keine automatische Cadence-Schätzung.
Ein fehlendes Telegramm ist niemals eine Nullmeldung. Ohne Timeout oder explizite
Unverfügbarkeit kann die Integration eine stille Funkunterbrechung nicht sicher
von einem langen regulären Meldeintervall unterscheiden. Einen passenden Timeout
anhand der tatsächlich beobachteten Intervalle einschließlich Empfangsschwankungen
konfigurieren; nicht unter die normale Cadence setzen. Keine Werte auf Verdacht
aus nur zwei Telegrammen ableiten. Der reale Hydrus-Status
`TEMPORARY_ERROR UNKNOWN_E0` wird hier nicht als unbedenklich oder ungültig erklärt.

## Chronologie und Nachweise

| Version | Veröffentlichter Stand |
|---|---|
| Beta.1 (`1.2.0-beta.1`) | F04-Hydraulik, Benachrichtigung/ACK, lesbare Dauer und Trennung von physischer MQTT-Zeit und Empfangszeit. |
| Beta.2 (`v1.2.0-beta.2`) | Stand nach PR #15 und #16: vorbereitete Karte 0.1.0 sowie Korrektur der ersten MQTT-Zulassungsgrenze. Die damaligen Paket-Versionsfelder standen noch auf Beta.1; Release-/Tagname allein belegt deshalb nicht die installierte Version. |
| Beta.3 (`1.2.0-beta.3`) | PR #17: regulärer Sensor `hydraulic_monitoring_status`, DE/EN und konsistente Paketversion Beta.3. |

Die tatsächliche Setupzeit wird vor Store-I/O erfasst. Nach Restore wird die
Zulassungsgrenze einmal an `max(gespeicherte Grenze, Setupbeginn)` gebunden.
Ein neues Hydrus-Telegramm darf nicht allein wegen normaler Zustelllatenz als
`pre_startup_measurement` abgewiesen werden. Strengere persistierte Grenzen,
Unterbrechungen, Retained/Replay/Out-of-Order, Zukunft, Alter und sichere Persistenz
bleiben wirksam. Erste gültige Messung: **0 Sekunden Evidenz**.

**Hydraulische Überwachung** ist unabhängig vom Alarm: `active` / Aktiv bedeutet
Freigabe, `waiting_for_measurement` / Warte auf Messung fehlende erste Messung ohne
festgestellte Sperre, `blocked` / Gesperrt eine Ausschlussentscheidung. Gesperrt
bleibt sichtbar und beendet keinen ACTIVE-Alarm oder Shutoff-Beitrag.
[Attribute und genaue Zeitbasis](CONFIGURATION.md#hydraulische-überwachung).

Softwareabnahme des Beta.3-Feature-Commits
`2564843c2724970b3692714ed18dca5e92ce1f16`: je **1476 Tests** unter HA 2026.9.0
und 2026.9.4, darunter 16 neue Statusfälle; Validate, Hassfest und HACS erfolgreich.
Release-/Merge-Commit `7e1e4e786710f060bc982ba461940da2dbc42697` hat denselben
getesteten Dateibaum. Die frühere Startup-Reproduktion mit echtem TCP-Broker bestand
bei 0/100 ms Latenz. Das sind Software-/Brokerbelege, keine physischen Funkbelege.

## Vom Benutzer bestätigter Hydrus-Neustarttest – 14. Oktober 2026

Der Benutzer hat Home Assistant mit **installierter 1.2.0-beta.3** und einem
**realen Hydrus-Wasserzähler** neu gestartet und folgende Beobachtungen bestätigt:

| Prüfung | Beobachtung |
|---|---|
| Fehlalarm beim Neustart | Keiner |
| Home-Assistant-Reparaturmeldung | Keine |
| Hydraulische Überwachung unmittelbar nach Neustart | Zunächst 11 Sekunden „Gesperrt“ |
| Anschließender Zustand | Automatisch „Aktiv“ |
| MQTT-Messherkunft | `verified_original_measurement` |

**Ergebnis: Dieser konkrete Neustarttest wurde erfolgreich bestanden.**
Dies ist ein vom Benutzer bestätigter Praxistest, kein von Codex selbst
durchgeführter Hardwaretest. Die vorübergehende Sperre ist mit der
sicherheitsgerichteten Freigabe der Messquelle vereinbar; anschließend wurde die
hydraulische Überwachung automatisch aktiviert. Aus dem Befund wird kein
bestimmter interner Ablehnungsgrund oder zusätzlicher Logeintrag abgeleitet.

Die **11 Sekunden sind nur die beobachtete Dauer dieses Neustarts**, keine
zugesicherte Startzeit, Wartefrist oder Timeout-Einstellung. Der Test bestätigt
nicht sämtliche Neustart-, Replay-, MQTT-Ausfall-, Funk- oder Recovery-Szenarien.
Software-/Brokerabnahme und dieser Benutzerbefund bleiben getrennte Nachweise.
Weitergehende Ausfallszenarien sind dadurch nicht pauschal abgenommen.

Die früheren Nullmeldungen 08:31:02/08:32:45 und Alarmende 08:34:57 bleiben
separate historische Nutzerbeobachtungen, keine zusätzliche Neustartmessung.
Für weitere gezielte Prüfungen installierte Version, reale Original-/Empfangszeit,
Zustandswechsel und Event-IDs protokollieren; keine Schutzprüfung abschalten und
fehlende Telegramme niemals als Nullverbrauch interpretieren.
[Diagnosepfad](TROUBLESHOOTING.md#hydraulic-monitoring-waiting-or-blocked).

## Karte und Upgrade

Karte 0.1.0 bleibt optional und manuell über `/local/water-leak-guard-card.js`
einzubinden. Sie zeigt den neuen Überwachungssensor noch nicht separat an;
verwende vorerst eine Standard-HA-Karte. Ihre ACK/Clear-WebSocket-Kommandos sind
nur vorgeschlagen, mit geschütztem Configure-Fallback. [Kartenanleitung](CARD.md).
[Upgrade und Backup](INSTALLATION.md#upgrading-to-the-published-120-beta3).

[Beta.3-Release](https://github.com/BeGiBue/homeassistant-water-leak-detection/releases/tag/1.2.0-beta.3).
Beta.1 und Beta.2 bleiben unverändert. Die Dokumentationsänderung darf nach Prüfung gemergt und das Wiki über seinen
Veröffentlichungsworkflow synchronisiert werden; ein neuer Release ist nicht nötig.
