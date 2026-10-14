# Architektur und Datenfluss

## Überblick

Der Wasserwächter ist bewusst als Backend-Integration aufgebaut. Die eigentliche Sicherheitslogik liegt nicht in einer Lovelace-Karte, sondern vollständig in Home Assistant.

Vereinfachter Datenfluss:

```text
Durchflusssensor ─┐
                  ├─> Normalisierung ─> Manager ─> Detection Engine
Gesamtverbrauch ──┘                       │              │
                                         │              ├─> Leck-Events
                                         │              ├─> Alarmstatus
                                         │              └─> Shut-Off-Request
                                         │
                                         ├─> Adaptive Learner
                                         ├─> Hydraulikmodell
                                         ├─> Notification Controller
                                         ├─> HA-Entitäten
                                         └─> Persistenter Store
```

## 1. Manager

Der `WaterLeakManager` ist die Laufzeitkoordination einer eingerichteten Instanz.

Er übernimmt:

- Lesen der Home-Assistant-Quellzustände
- Normalisierung der Messwerte
- Ausführung der Detektoren
- Berechnung statischer High- und adaptiver Burst-Grenzen
- Übergabe sicherer Episoden an das Lernmodell
- Erzeugen von Home-Assistant-Events
- Verwaltung des High-Flow-Bypass
- Speichern und Wiederherstellen des Laufzeitzustands
- Aktualisierung der bereitgestellten Entitäten

### Ausführungszeitpunkte

Die Auswertung erfolgt:

- bei Zustandsänderung eines konfigurierten Quellsensors
- zusätzlich zyklisch alle **10 Sekunden**

Die internen Ticks prüfen Steuerungen und Quellenstatus, liefern aber **keine Mess-Evidenz**. Nur echte frische gültige Reports bestätigen Detektions- oder Quiet-Intervalle.

## 2. Detection Engine

Die Detection Engine ist weitgehend Home-Assistant-unabhängig und bildet vier getrennte Zustandsautomaten ab:

- Slow Leak
- Low Flow
- High Flow
- Burst Leak

Jeder Automat kennt die Phasen:

- `idle`
- `monitoring`
- `active`

### Monitoring vs. Active

`monitoring` bedeutet:

> Es liegen verdächtige Messwerte vor, aber die zeitliche bzw. mengenmäßige Bestätigung ist noch nicht erfüllt.

`active` bedeutet:

> Der Detektor hat seine Erkennungsbedingung bestätigt und erzeugt ein Ereignis mit eigener Event-ID.

Diese Trennung verhindert, dass ein kurzer normaler Wasserverbrauch sofort als Leckage gemeldet wird.

## 3. Event-IDs

Beim Übergang auf `active` erzeugt jeder Detektor eine eindeutige Ereignis-ID.

Sinngemäß:

`slow_leak_20261006T123456_a1b2c3`

Quittierungen sind immer an genau diese Event-ID gebunden.

Endet die physische Situation und tritt später erneut auf, entsteht eine neue Event-ID und damit ein vollständig neuer Alarmzyklus.

## 4. Messwertnormalisierung

Der Kern arbeitet unabhängig von der Einheit des Quellsensors.

Intern:

- Durchfluss: **L/h**
- Volumen: **L**

Negative und nicht endliche Durchflusswerte sind ungültige Messungen. Sie werden niemals als 0-Durchfluss oder Ruhe-Evidenz ausgewertet. Bestätigte Leckagen bleiben erhalten.

## 5. Verhalten bei Sensorausfall

Wenn der Durchflusssensor `unknown`, `unavailable` oder nicht sinnvoll konvertierbar ist:

- wird die Quelle als nicht verfügbar markiert
- bestätigter normaler Slow/Low/High-Monitoring-Fortschritt derselben Quelle bleibt nach Round7 erhalten; unbestätigte Burst-Kandidaten und Low-Stabilität werden unterbrochen
- laufende Quiet-/Reset-Zeitfenster werden verworfen
- bereits bestätigte `active`-Ereignisse bleiben aus Sicherheitsgründen aktiv
- die aktuelle unvollständige Lern-Episode wird verworfen

Grund:

> Fehlende Messwerte sind kein Beweis für 0 L/h.

## 6. Volumenberechnung

Wenn ein kumulierter Gesamtverbrauchssensor vorhanden ist, wird das Ereignisvolumen bevorzugt aus dessen Differenz berechnet.

Falls nicht, integriert die Engine den Durchfluss über die Zeit.

Nach längeren HA-Ausfallzeiten wird nicht beliebig viel Volumen rückwirkend integriert; große Zeitlücken werden begrenzt.

## 7. Adaptive Grenzwerte

Slow und Low verwenden bewusst statische fachliche Bänder.

High verwendet eine statische Grenze; Burst kann adaptive Grenzwerte verwenden.

Dadurch wird vermieden, dass ein gelerntes hohes Haushaltsmaximum den Low-Flow-Bereich ungewollt nach oben verschiebt.

## 8. Notification Controller

Der Notification Controller ist von der Detection Engine getrennt.

Er verwaltet:

- konfigurierbare Companion-Empfänger
- pro Ereignis persönliche Mutes
- globale Quittierung
- Home-Zone-Prüfung
- Re-Notification beim Heimkommen
- Critical-Payload für Burst

Er kann einen Detektor nicht zurücksetzen.

## 9. Water-Shut-Off-Schicht

Die Engine berechnet aus allen **aktiven** Detektoren und deren konfigurierter Zuordnung eine unabhängige boolesche Absperranforderung.

Diese wird als Home-Assistant-Binary-Sensor bereitgestellt.

Die physische Ventilsteuerung erfolgt in der aktuellen Version bewusst außerhalb der Integration über eine Home-Assistant-Automation.

## 10. Persistenz

Persistiert werden unter anderem:

- Detector-Runtime
- Event-ID und Startzeit
- Quittierungszustände
- High-Flow-Bypass-Endzeit
- zugelassene Lernwerte

Nicht persistiert wird eine noch unvollständige Lern-Episode. Eine vor einem Neustart nur teilweise beobachtete Episode ist keine vertrauenswürdige Grundlage für „normales Verhalten“.

## Betriebszustand ohne zweiten Detektor

`WaterLeakManager.hydraulic_monitoring_status` spiegelt vorhandene Annahme-,
Ausschluss- und Rebind-Entscheidungen. Der flüchtige Diagnosegrund beginnt mit
`waiting_for_measurement`, wird bei akzeptierter Messung `verified_measurement`
und bei `_suspend_source()` zum konkreten Ausschlussgrund. Aktiv erfordert zugleich
`source_available`. Die Anzeige steuert weder Evidenz noch Detektor und wird nicht
als eigener Sicherheitszustand persistiert. Sensorupdates verwenden dieselben
Manager-Listener, ohne neue Polling-Schleife oder MQTT-Subscription.

Nach Store-Restore wird MQTT einmal an den vor Store-I/O erfassten Setupbeginn
gebunden; `max(gespeicherte Grenze, Setupbeginn)` erhält strengere Grenzen.
Die erste gültige Messung liefert null Sekunden. [Betrieb](Persistenz-und-Betrieb)
und [Sensorattribute](Home-Assistant-Schnittstellen).
