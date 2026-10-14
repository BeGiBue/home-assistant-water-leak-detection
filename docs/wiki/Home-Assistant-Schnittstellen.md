# Home-Assistant-Schnittstellen

Diese Seite beschreibt die sichtbaren und automatisierbaren Schnittstellen des Wasserwächters.

Die technische Domain lautet:

`water_leak_detection`

Die sichtbaren deutschen Namen folgen der in Home Assistant eingestellten Sprache.

---

# 1. Gerät

Jeder Config Entry erzeugt ein Home-Assistant-Gerät:

**Wasserwächter**

Hersteller:

**BeGiBue**

Das Gerät bündelt die Backend-Entitäten der jeweiligen Instanz.

---

# 2. Sensoren

## Status

Gesamtstatus der Detektion.

Mögliche fachliche Zustände:

- Bereit
- Messquelle nicht verfügbar
- Slow Leak wird geprüft
- Low Flow wird geprüft
- High Flow wird geprüft
- Burst Leak wird geprüft
- Slow Leak
- Low Flow
- High Flow
- Burst Leak

Wenn mehrere Detektoren gleichzeitig aktiv sind, zeigt der Status die höchste aktive Klasse.

Zusatzattribute enthalten unter anderem:

- Flow-Quelle
- Total-Quelle
- Quellenverfügbarkeit
- aktive Event-ID
- aktiven Detektor
- globale Quittierung
- stummgeschaltete Empfänger
- High-Flow-Bypass
- Slow-/Low-Aktivierung
- interne Detektorzustände

## Hydraulische Überwachung

Regulärer, auch bei Sperre verfügbarer Sensor `hydraulic_monitoring_status` am
bestehenden Integrationsgerät. Unique-ID:
`<config-entry-id>_hydraulic_monitoring_status`; Entity-ID kann umbenannt werden.

| Intern | Deutsch | Englisch | Bedeutung |
|---|---|---|---|
| `active` | Aktiv | Active | Messquelle ist vom Manager freigegeben. |
| `waiting_for_measurement` | Warte auf Messung | Waiting for measurement | Erste Messung nach Start/Quellenwechsel fehlt, ohne festgestellte Sperre. |
| `blocked` | Gesperrt | Blocked | Quelle/Auswertung ist ausgeschlossen; Grund steht in Attributen. |

„Kein Alarm“ und „Aktiv“ sind verschiedene Aussagen. `blocked` ist kein ACK und
beendet keinen ACTIVE-Alarm oder Shutoff-Beitrag. Die Entität selbst bleibt bei
Sperre verfügbar, sofern die Integration funktionsfähig ist.

| Attribut | Zeitbasis / Bedeutung |
|---|---|
| `reason` | Konkrete letzte Manager-Entscheidung. |
| `source_entity_id` | Konfigurierte Flow-Entität. |
| `source_available` | Vorhandener Manager-Freigabewert; bei Rebind kann er kurz die alte Quelle beschreiben, während die Anzeige korrekt wartet. |
| `mqtt_provenance_status` | Herkunftsprüfung; gemeinsam mit aktuellem Zustand und reason lesen. |
| `last_valid_measurement` | Zeitstempel des letzten gültigen **HA-Reports**, nicht der originale Funk-Timestamp. |
| `observation_age_seconds` | Monotones Beobachtungsalter; fehlende Werte bleiben null. |

Mehr Diagnosen liegen im Gesamtstatus unter `measurement_diagnostics`, darunter
`mqtt_measurement_provenance.admission_since` und Low-Resetfortschritt.
[Fehlersuche](Troubleshooting). Die Anzeige folgt nur der bestehenden Manager-
Logik und ist unabhängig von persönlichem Mute/globalem ACK.

## Aktueller Durchfluss

Normalisierter Durchfluss in:

**L/h**

Dieser Sensor ist diagnostisch.

## Dauer des aktiven Ereignisses

Dauer des aktuell höchst priorisierten aktiven Ereignisses in Sekunden.

## Volumen des aktiven Ereignisses

Wasserverbrauch seit Beginn des aktuell höchst priorisierten Ereignisses in Litern.

## Restzeit High-Flow-Bypass

Verbleibende Bypasszeit in Sekunden.

Attribute:

- aktiv ja/nein
- Endzeitpunkt

## Gelernter Maximaldurchfluss

Robuste aktuelle Normalreferenz des Lernmodells.

Attribute:

- Kurzzeitreferenz
- Langzeitreferenz
- Anzahl Lernwerte
- abgedeckte Tage
- Lernfenster
- Confidence

## Lernzuverlässigkeit

Zustände:

- Unzureichend gelernt
- Lernen aktiv
- Zuverlässig gelernt

## Lernabdeckung

Anzahl der Tage, die durch zugelassene Lernwerte repräsentiert werden.

## Hydraulischer Referenzdurchfluss

Diagnostische hydraulische Plausibilitätsreferenz.

Nicht als exaktes physikalisches Maximum interpretieren.

## High-Flow-Schwelle

Konfigurierter statischer High-Grenzwert.

## Effektive Burst-Leak-Grenze

Aktuell verwendete absolute Burst-Grenze.

Attribute zeigen zusätzlich:

- Normalreferenz
- hydraulische Referenz
- Hinweis, dass das Hydraulikmodell nur Plausibilitätskontext ist

---

# 3. Binary Sensoren

## Leckalarm

`on`, sobald mindestens ein Detektor `active` ist.

Wichtig:

> Quittieren ändert diesen Zustand nicht.

## Absperranforderung

`on`, sobald mindestens ein aktiver Detektor gemäß Konfiguration Water Shut Off anfordert.

Wichtig:

> Diese Entität ist bewusst von Alarmquittierung entkoppelt.

---

# 4. Schalter

## Slow-Leak-Erkennung

Aktiviert oder deaktiviert nur den Slow-Leak-Detektor.

## Low-Flow-Erkennung

Aktiviert oder deaktiviert nur den Low-Flow-Detektor.

## High-Flow-Bypass

Startet bzw. beendet den zeitbegrenzten High-Flow-Bypass.

Burst bleibt immer aktiv.

---

# 5. Number-Entität

## Dauer High-Flow-Bypass

Standarddauer, die verwendet wird, wenn der Bypass über den Schalter gestartet wird.

Bereich:

1 bis 1440 Minuten.

---

# 6. Aktionen

## High-Flow-Bypass starten

`water_leak_detection.start_high_flow_bypass`

Optional:

- `config_entry_id`
- `duration_minutes`

Wenn nur eine Instanz geladen ist, kann die Config-Entry-ID entfallen.

## High-Flow-Bypass beenden

`water_leak_detection.cancel_high_flow_bypass`

## Lernmodell zurücksetzen

`water_leak_detection.reset_learning`

Löscht nur die zugelassenen Lernwerte.

---

# 7. Events

## Leckage gestartet

`water_leak_detection_event_started`

Typischer Payload:

- Config-Entry-ID
- Typ
- Event-ID
- Phase
- Durchfluss
- Volumen
- Startzeit
- Erkennungszeit
- Grund

Bei Burst kann der Grund z. B. sein:

- `absolute_flow`
- `rapid_rise`

## Leckage beendet

`water_leak_detection_event_ended`

Wird ausgelöst, wenn die physische Resetbedingung des aktiven Detektors erfüllt wird.

## Absperranforderung gestartet

`water_leak_detection_shutoff_requested`

## Absperranforderung beendet

`water_leak_detection_shutoff_cleared`

## Quittierung akzeptiert

`water_leak_detection_acknowledged`

Scopes:

- `device`
- `global`

## Quittierung abgelehnt

`water_leak_detection_ack_rejected`

Mögliche Gründe umfassen beispielsweise:

- ungültiger Empfänger / Token
- Event nicht mehr aktiv
- globale Quittierung für Empfänger nicht erlaubt
- Gerät nicht zuhause

---

# 8. Companion-Aktions-IDs

Notification-Aktionen enthalten intern:

- Config-Entry-ID
- Event-ID
- Empfänger-ID
- zufälliges Token
- Aktionstyp

Damit wird die Antwort einem konkret konfigurierten Gerät und einem konkreten Ereignis zugeordnet.

Die interne Action-ID ist kein öffentliches API-Versprechen und sollte nicht manuell nachgebaut werden.

---

# 9. Konfiguration

Die Konfiguration ist vollständig über die Home-Assistant-UI erreichbar.

Unter **Konfigurieren**:

- Messquellen
- Benachrichtigungsempfänger
- Experteneinstellungen

Zusätzlich unterstützt die Integration Home Assistants **Neu konfigurieren** für die Messquellen.

---

# 10. Sprache

Die UI und Laufzeitbenachrichtigungen verwenden die Home-Assistant-Sprache.

Deutsch:

**Wasserwächter**

Englisch:

**Water Leak Guard**

Technische IDs bleiben sprachunabhängig.

## F04 V3 Schnittstellen

Configure → Externe Lecksensoren verwaltet mehrere binary_sensor ohne YAML,
einschließlich Bearbeiten, Entfernen und Shutoff-Beitrag. Empfänger erhalten die
getrennte Reset-Berechtigung. Die Dienste external_reset und
request_external_reset_action verwenden aktuelle Ereignisbindungen und Home-
Autorisierung. Letzterer fordert nur eine frische Action an und hebt ACK nicht auf.
Status/Alarm/Shutoff aggregieren alle Ereignisse; Attribute zeigen externe
ACTIVE/WAITING-Quellen, hydraulische Alarme, Beiträge und Migrationsstatus.
Ein diagnostischer Langzeitmaximum-Sensor zeigt den getrennt bestätigten Wert.
Alle Sicherheits- und Persistenzregeln: [F04 V3](F04-V3.md).

## Dashboard-Karte und Kartenbefehle

Seit 2.0.0-beta.1 stellt die Integration die Karte selbst bereit
(`/water_leak_detection/water-leak-guard-card.js`, als Frontend-Modul geladen). Bedienung und Kopplung:
[Dashboard-Karte](Dashboard-Karte).

Für die Karte registriert die Integration WebSocket-Befehle. Alle nehmen optional `config_entry_id`
(nötig bei mehreren Instanzen). Die Identität ist ausschließlich die Anmeldung der Verbindung und ihr
Benutzer: Ist genau diese Anmeldung bei einem Empfänger hinterlegt, gilt er; sonst der Empfänger, der mit
dem Benutzer gekoppelt ist (**Kopplung für die Dashboard-Karte**). Long-Lived-Tokens zählen nie. Empfänger-Token und
Reset-Nonce verlassen nie den Server.

| Befehl | Felder | Wirkung | Prüfung beim Ausführen |
|---|---|---|---|
| `water_leak_detection/session` | – | Auskunft: `paired`, `recipient_id`, `recipient_name`, `home`, `tracker_entity`, `trusted_stationary`, `can_global_ack`, `can_external_reset` | nur Anzeige |
| `water_leak_detection/mute` | `event_id` | stummschalten nur für dieses Gerät | gekoppelt, Ereignis aktiv; überall |
| `water_leak_detection/acknowledge` | `event_id` | globale Quittierung | Berechtigung, Device Tracker `home`, Ereignis aktiv, gespeichert vor Bestätigung |
| `water_leak_detection/external_reset` | `event_id`, `source_id`, `source_generation` | externes Leck zurücksetzen | Berechtigung, `home`, exakte Ereignisbindung, gespeichert |

Fehlercodes: `not_paired`, `not_home`, `not_allowed`, `event_not_active`, `not_committed`, `rejected`,
`instance_not_found`. Die Kopplung wird innerhalb der Schreibsperre des Managers erneut geprüft.

Für hydraulische Alarme gibt es keinen Befehl. Sie enden, wenn der Durchfluss die Ruhebedingung
erfüllt; Slow/Low außerdem beim Abschalten des Detektors und High Flow beim Start des Bypass (die Karte
fragt dann nach). Burst endet nur physisch.

Die bestehenden Dienste `water_leak_detection.acknowledge_event` und `water_leak_detection.external_reset`
bleiben unverändert; sie verlangen ihre Token- bzw. Nonce-Bindungen und werden von der Karte nicht
aufgerufen.
