# Fehlerbilder und Troubleshooting

## 1. Integration erscheint nach HACS-Installation nicht

Prüfen:

1. HACS hat das Repository als **Integration** installiert.
2. Home Assistant wurde vollständig neu gestartet.
3. Verzeichnis vorhanden:
   `<config>/custom_components/water_leak_detection`
4. Home-Assistant-Logs nach `water_leak_detection` durchsuchen.

---

# 2. Alte Vorabversion war als Helfer sichtbar

Eine frühe Vorabversion war fälschlich als Helper klassifiziert.

Dadurch konnte ein alter Config Entry unter **Helfer** statt unter **Integrationen** erscheinen und die neue Einrichtung derselben Domain blockieren.

Saubere Bereinigung:

1. alten Wasserwächter-/Water-Leak-Eintrag unter Helfer löschen
2. dadurch verschwinden auch alle zu diesem Config Entry gehörenden Entitäten
3. Home Assistant neu starten
4. aktuelle Integration neu einrichten

Dass mehrere zugehörige „Helfer“ gemeinsam verschwinden, ist in diesem Sonderfall korrekt: Sie gehörten alle zum selben alten Config Entry.

Nicht eigenständig `.storage/core.config_entries` editieren, solange eine normale Entfernung über Home Assistant möglich ist.

---

# 3. Durchflusssensor wird abgelehnt

Der Sensor muss eine unterstützte Durchflusseinheit besitzen.

Typische Einheiten:

- L/h
- L/min
- L/s
- m³/h
- m³/min
- m³/s

Ein Sensor ohne interpretierbare Einheit wird nicht geraten.

---

# 4. Kein Gesamtverbrauchssensor vorhanden

Der Gesamtverbrauch ist optional.

Die Erkennung funktioniert weiterhin.

Das Ereignisvolumen kann dann aus Durchfluss und Zeit abgeschätzt werden.

---

# 5. Keine Benachrichtigungsempfänger auswählbar

Prüfen:

- Home Assistant Companion App ist eingerichtet
- ein `notify.mobile_app_*`-Dienst existiert
- ein passender `device_tracker.*` existiert

Empfänger können sowohl:

- bei der Ersteinrichtung als auch
- später unter **Konfigurieren → Benachrichtigungsempfänger**

verwaltet werden.

---

# 6. „Für alle quittieren“ fehlt

Der Button wird nur angezeigt, wenn:

- der Empfänger globale Quittierung erlaubt und
- sein Tracker aktuell `home` ist

Das Backend prüft dies beim Klick erneut.

---

# 7. Globale Quittierung wird abgelehnt

Prüfen:

- richtiger Tracker ausgewählt
- Trackerzustand exakt `home`
- Empfänger darf global quittieren
- Event ist noch aktiv
- Empfänger wurde nicht zwischenzeitlich aus der Integration entfernt

Ein Gerät außerhalb der Home-Zone kann weiterhin nur für sich selbst stummschalten.

---

# 8. Alarm ist quittiert, aber weiterhin rot/aktiv

Das ist beabsichtigt.

Quittierung beendet nur weitere Benachrichtigungen für den jeweiligen Scope.

Der Detektor bleibt aktiv, bis seine physische Resetbedingung erfüllt ist.

Siehe:

- [Leckageklassen und Erkennungslogik](Leckageklassen-und-Erkennungslogik)
- [Alarmstufen und Quittierung](Alarmstufen-und-Quittierung)

---

# 9. High-Flow-Bypass unterdrückt einen Alarm nicht

Der Bypass unterdrückt ausschließlich **High Flow**.

Nicht unterdrückt werden:

- Slow Leak
- Low Flow
- Burst Leak

Das ist eine Sicherheitsentscheidung und kein Fehler.

---

# 10. Burst wird trotz Bypass ausgelöst

Das ist ausdrücklich beabsichtigt.

Ein geplatzter Schlauch während einer Poolbefüllung soll weiterhin erkannt werden.

---

# 11. Gelernter Maximaldurchfluss wirkt unplausibel

Prüfen:

- Gelernter Maximaldurchfluss
- Lernzuverlässigkeit
- Lernabdeckung
- Effektive High-Grenze
- Effektive Burst-Grenze
- manuell bekanntes Maximum
- Rohrdurchmesser / Druck

Bei Bedarf kann das Lernmodell über:

`water_leak_detection.reset_learning`

zurückgesetzt werden.

---

# 12. Sensor wird unavailable

Unavailable wird **nicht** als 0 interpretiert.

Folge:

- Monitoring kann verworfen werden
- aktive Lecks bleiben bestehen
- Resetzeit läuft nicht auf unbekannter Evidenz weiter
- laufende Lern-Episode wird verworfen

---

# 13. Water Shut Off bleibt trotz Quittierung aktiv

Das ist korrekt.

Die Absperranforderung hängt von:

- aktiven Detektoren und
- deren Shut-Off-Zuordnung

ab.

Quittierung gehört zur Alarmierungsschicht und ändert diese Entscheidung nicht.

---

# 14. Debug-Logging

Temporär:

```yaml
logger:
  default: info
  logs:
    custom_components.water_leak_detection: debug
```

Nach der Fehlersuche Debug-Logging wieder entfernen.

---

# 15. Issue melden

Repository:

`https://github.com/BeGiBue/home-assistant-water-leak-guard/issues`

Hilfreiche Angaben:

- Home-Assistant-Version
- Wasserwächter-Version
- Quell-Entity-IDs und Einheiten
- relevante Einstellungen
- Logauszug
- reproduzierbare Schritte

Keine Zugangstokens oder Geheimnisse posten.

## Reparatur „MQTT-Nullmeldungen werden möglicherweise unterdrückt“ nach wmbusmeters 3.1.0

Beobachtet mit dem Home-Assistant-Add-on von wmbusmeters 3.1.0. Das Add-on erzeugt
die MQTT-Discovery jetzt automatisch aus dem Treiber. Der Flow-Sensor wird **ohne
`force_update`** veröffentlicht, und das Add-on veröffentlicht ihn bei jedem Start
neu. Eine selbst veröffentlichte Discovery mit `force_update: true` wird dabei
überschrieben. Wasserwächter zeigt dann die Reparatur „MQTT-Nullmeldungen werden
möglicherweise unterdrückt“ und kann einen Low-Flow-Alarm nicht sicher
zurücksetzen. Entität, `unique_id`, Einheit und das JSON-Feld `timestamp` bleiben
gleich, die Messherkunft ist davon nicht betroffen.

Lösung, geprüft mit einem Diehl-Hydrus (Treiber `hydrus`):

1. In der Add-on-Konfiguration **Enable mqtt discovery** abschalten, speichern und
   das Add-on neu starten.
2. Die Discovery des Flow-Sensors noch einmal mit `"force_update": true`
   veröffentlichen (*Einstellungen → Geräte & Dienste → MQTT → Konfigurieren → Ein
   Paket veröffentlichen*): konkretes Topic, zum Beispiel
   `homeassistant/sensor/wmbusmeters/<Zähler-ID>_flow_m3h/config` (ohne `#`),
   **Retain** an, Payload wie bisher plus `"force_update": true`. Das Payload-Feld
   wertet Templates aus: den gesamten JSON-Text in `{% raw %}` und `{% endraw %}`
   einschließen, sonst wird das `value_template` ausgewertet.
3. Das Add-on erneut starten und prüfen, dass die retained Nachricht
   `force_update: true` behält und die Reparatur nicht zurückkehrt.

Bei abgeschalteter Discovery legt das Add-on neue oder geänderte Sensoren nicht
mehr automatisch an; vorhandene retained Discovery-Nachrichten bleiben gültig.
Nach jedem Update von wmbusmeters oder des Add-ons die Reparaturen erneut prüfen.

## Hydraulische Überwachung: Warten oder Gesperrt

1. Installierte Version nach Download und HA-Neustart prüfen; ein Release allein
   installiert nichts. Die neue Entität am Integrationsgerät auswählen.
2. Bei **Warte auf Messung** Flow-Quelle prüfen und einen echten frischen gültigen
   Report abwarten. Eine explizite Ablehnung/Unverfügbarkeit muss Gesperrt ergeben.
3. Bei **Gesperrt** Zustand, `reason`, `source_entity_id`, `source_available`,
   `mqtt_provenance_status`, `last_valid_measurement` und `observation_age_seconds`
   sichern. Der Zeitstempel ist der letzte gültige HA-Report; Alter ist monoton.
   Nullwerte sind keine Ersatzmessung. Der Sensor bleibt bei Sperre verfügbar.
4. Im Gesamtstatus `measurement_diagnostics` lesen: tatsächlicher Timeout,
   `mqtt_measurement_provenance.admission_since`, MQTT force_update/expire_after und
   Low-Resetfortschritt. Fehlende Telegramme bedeuten nie Nullverbrauch.
5. MQTT-Flow-Payload und originalen aware `timestamp` prüfen. `force_update: true`
   erlaubt neue gleichbleibende Reports, macht aber alte Wiederholungen nicht neu.
   Total-Attribute allein ersetzen Flow-Herkunft nicht.

`original_measurement_missing` kann auch Entity-/Topic-/Adapter-Auflösung oder
ungültiges JSON bedeuten; die allgemeine Repair-Meldung beweist keine einzelne
Ursache. `pre_startup_measurement` verlangt Vergleich mit Startup-/Outage-Grenze,
Replay/Retained-Gründe verlangen Prüfung originaler Nachrichten. Zukunft/Alter
verlangen Prüfung der Zeitbasis. `provenance_persistence_failed` verlangt Logs und
sichere Storage-Recovery, keinen Bypass. Auch bei `verified_original_measurement`
aktuelle Anzeige und reason prüfen: ein späterer Ausfall kann die Quelle sperren.

Ein blockierter oder quittierter Alarm ist keine physische Entwarnung. ACTIVE und
Shutoff bleiben nach ihren eigenen Regeln bestehen. Event-IDs für Dauer und
Benachrichtigungen getrennt prüfen. Bei Repair wegen beschädigter Daten Datei
bewahren und geprüftes Backup nutzen; nicht löschen. [Vollständiger Diagnosepfad](https://github.com/BeGiBue/home-assistant-water-leak-guard/blob/main/docs/TROUBLESHOOTING.md#hydraulic-monitoring-waiting-or-blocked).
## Bestätigter Neustartbefund und Einordnung

Am 14. Oktober 2026 bestätigte der Benutzer nach HA-Neustart mit installierter
Beta.3 und realem Hydrus: kein Fehlalarm, keine Reparaturmeldung, zunächst
11 Sekunden „Gesperrt“, dann automatisch „Aktiv“ und
`verified_original_measurement`. Dieser konkrete Neustarttest ist bestanden;
Codex hat den Hardwaretest nicht selbst durchgeführt.

Die kurze Sperre ist mit der konservativen Quellenfreigabe vereinbar und
allein kein Fehlalarm. Sie liefert keinen unbekannten technischen reason nach;
es wurden keine zusätzlichen Logs oder Messwerte übergeben. 11 Sekunden sind
keine garantierte Dauer, kein konfigurierter Timeout und kein Maßstab, nach dem
jede Installation freigegeben sein muss. Nicht sämtliche MQTT-/Neustart- oder
Ausfallszenarien sind damit geprüft. [Vollständiger Befund](Persistenz-und-Betrieb#vom-benutzer-bestätigter-hydrus-neustarttest).
