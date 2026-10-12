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
