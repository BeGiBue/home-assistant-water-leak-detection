# Dashboard-Karte (Lovelace)

**Status:** Version 0.2.0, Etappe A. Die Karte ist eine reine Ansicht auf die vorhandenen
Entitäten und Dienste und **keine Vertrauensgrenze**: Sie enthält weder Empfänger-Token noch
Reset-Nonce, und Berechtigung, Anwesenheit und erlaubte Alarmaktionen prüft ausschließlich das
Backend. Die Integration bleibt ohne Karte voll funktionsfähig (SPEC §1051).

**Nicht nachgewiesen:** Die Karte ist bisher nur mit simuliertem Home Assistant im Browser getestet
(Chromium, Desktop- und Handybreite, hell/dunkel). Ein Test in einer echten HA-Installation steht aus.

Datei: `custom_components/water_leak_detection/frontend/water-leak-guard-card.js`
– eine einzelne JS-Datei ohne Build-Schritt und ohne externe Abhängigkeiten.

## Inhalt der Karte

| Bereich | Quelle | Bedienung |
|---|---|---|
| Kopf: Alarmstatus, Leckalarm, Absperranforderung | `sensor.*_status` (Attribute `aggregate_alarm_active`, `aggregate_shutoff_request`, `active_detector`) | Tippen öffnet Details |
| **Hydraulische Überwachung** | `sensor.*_hydraulic_monitoring_status` (ab 1.2.0-beta.3) mit `reason`, `source_entity_id`, `mqtt_provenance_status`, `last_valid_measurement`, `observation_age_seconds` | Grund und Messherkunft aufklappbar |
| Hinweis Laufzeitspeicher | Attribut `storage_recovery_required` | – |
| Aktive Ereignisse (hydraulisch und extern) | Attribute `hydraulic_detectors`, `external_sources`, `notification_events`; Dauer-/Volumensensor | nur Anzeige und Erklärung (siehe unten) |
| Durchfluss mit High-/Burst-Marke | `current_flow`, `effective_high_threshold`, `effective_burst_threshold` | – |
| Erkennung Slow/Low/High/Burst | Attribut `detectors`, Schalter Slow/Low, Bypass-Schalter | Slow/Low ein/aus |
| High-Flow-Bypass | Bypass-Schalter, Restzeit, Standarddauer | Start mit Voreinstellung oder Standarddauer, Beenden |
| Externe Lecksensoren | Attribut `external_sources` (ohne Tombstones), Live-Zustand des Sensors | Tippen öffnet den Sensor |
| Lernmodell | Lernzuverlässigkeit, Abdeckung, Normalspitze, Langzeitmaximum | Zurücksetzen (nur Admins, mit Rückfrage) |

Alle Bedienelemente rufen nur vorhandene, im Backend geprüfte Schalter und Dienste auf
(`switch.turn_on/off`, `start_high_flow_bypass`, `cancel_high_flow_bypass`, `reset_learning`).

Die Karte findet alle Entitäten automatisch über das Gerät der gewählten Status-Entität
(`translation_key` im Entity-Registry). Umbenannte Entity-IDs funktionieren weiterhin. Bei mehreren
Instanzen ermittelt sie die `config_entry_id` und schickt sie an die Dienste mit.

**Titel:** Ohne `title` zeigt die Karte den Gerätenamen aus Home Assistant, inklusive einer
Umbenennung durch den Nutzer. Der Standardname kommt aus der Übersetzung der Integration
(derzeit „Wasserwächter“ / „Water Leak Guard“).

## Alarmstatus und Betriebszustand

Beides wird getrennt angezeigt. Die Überschrift zeigt **nur den Alarmstatus**. Der Betriebszustand
steht immer in der eigenen Zeile **Hydraulische Überwachung**.

| Überwachung | Zeile | Farbe der Karte ohne Alarm | Detektoren |
|---|---|---|---|
| Aktiv | „Aktiv“ | grün, Überschrift „Alles ruhig“ | normal |
| Warte auf Messung | Hinweis, Grund aufklappbar | grau, „Kein Alarm“ | „Pausiert“ |
| Gesperrt | Grund und Messherkunft aufgeklappt | gelb, „Kein Alarm“ | „Pausiert“ |
| Entität nicht verfügbar | „Nicht verfügbar“ | grau | „Pausiert“ |
| Entität fehlt (vor 1.2.0-beta.3) | „Unbekannt“ mit Versionshinweis | grau | neutral, nie grün |

- Grün erscheint nur bei bestätigt aktiver Überwachung. Auch das Wasser im Hintergrundschild wird
  ohne aktive Überwachung grau bzw. gelb.
- Ein **ACTIVE**-Alarm bleibt in jedem Betriebszustand sichtbar: Kopf rot, Detektor „Alarm“,
  Ereignis im Alarmkasten. Das Backend meldet als Status bei Quellenausfall `source_unavailable`,
  auch während eines Alarms. Die Karte liest die Alarmart deshalb aus `active_detector`.
- Liefert die Status-Entität selbst nichts (`unavailable`), zeigt die Karte nur „Status nicht
  verfügbar“ und keine veralteten Werte.
- Externe Sensoren, deren Entität fehlt oder nicht verfügbar ist, zeigen „Nicht verfügbar“ statt
  „Trocken“. Ein aktives externes Leck bleibt sichtbar.

## Alarmbedienung heute

Die Karte bietet **keine** Buttons zum Quittieren oder Löschen an, weil das Backend dafür noch
keinen sicheren Vertrag hat. Zu jedem Ereignis erklärt sie stattdessen, was heute möglich ist:

| Aktion | Wirkung | Wo | Weg heute |
|---|---|---|---|
| Stummschalten | stoppt Benachrichtigungen nur für das eigene Gerät | überall | Benachrichtigung auf dem eigenen Gerät |
| Global quittieren | stoppt Benachrichtigungen für alle | nur zuhause (Backend-Prüfung) | Benachrichtigung oder **Konfigurieren → Quittierung** (Admin) |
| Externes Leck zurücksetzen | beendet den externen Alarm; der Sensor wird erst wieder scharf, wenn er „trocken“ meldet | nur zuhause, berechtigtes Gerät | Benachrichtigung |
| Hydraulischer Alarm | – | – | endet nur physisch nach den Rücksetzregeln |

Quittieren beendet **weder** Erkennung noch Alarm noch Absperranforderung. Die Karte zeigt pro
Ereignis, ob global quittiert ist und auf wie vielen Geräten stummgeschaltet wurde. Admins erhalten
bei offenen Ereignissen einen Link zur Integrationsseite.

## Installation (manuell, bis zur automatischen Registrierung)

HACS installiert die Datei mit dem Integrationsordner, registriert sie aber **nicht** als
Dashboard-Ressource. Bis Etappe D:

1. `water-leak-guard-card.js` nach `<config>/www/` kopieren.
2. **Einstellungen → Dashboards → ⋮ → Ressourcen → Ressource hinzufügen**:
   URL `/local/water-leak-guard-card.js?v=0.2.0`, Typ **JavaScript-Modul**.
3. Browser neu laden und im Dashboard die Karte **Water Leak Guard** hinzufügen.

Bei einem Kartenupdate die Datei ersetzen und in der bestehenden Ressource nur `?v=` anpassen.
So lädt der Browser die neue Version, und es entsteht keine zweite Ressource.

```yaml
type: custom:water-leak-guard-card
entity: sensor.wasserwachter_status   # optional; ohne Angabe wird die erste Instanz genommen
title: Wasserwächter                  # optional; ohne Angabe der Gerätename
show_flow: true
show_detectors: true
show_bypass: true
show_external: true
show_learning: true
show_background: true                 # Schutzschild mit Wasser im Kopf der Karte
bypass_presets: [60, 120, 240]        # Minuten, 1–1440
```

Das Hintergrundmotiv übernimmt die Kartenfarbe (grün, grau, gelb, rot). Im Alarm schwappt das Wasser
an die rechte Wand. Bei `prefers-reduced-motion` steht es still.

## Backend-Vertrag für Kartenaktionen (Etappe B)

Im Backend umgesetzt und getestet. Die Karte nutzt ihn erst ab Etappe C (`INTERFACE.enabled` bleibt
bis dahin `false`).

### Identität: das Gerät, nicht der Benutzer

Ein Gerät ist fest mit seinem HA-Benutzer angemeldet. Jede Anmeldung (Companion App oder Browser) hat
in Home Assistant eine eigene Login-ID (Refresh-Token-ID), die die WebSocket-Verbindung serverseitig
mitführt und die das Gerät nicht fälschen kann.

Die Kopplung ist **Teil des Empfänger-Eintrags**: Unter **Konfigurieren → Benachrichtigungsempfänger →
Empfänger hinzufügen / bearbeiten** gibt es das optionale Feld **Gekoppelte Anmeldung für die
Dashboard-Karte** (Auswahl aus der Liste: Benutzer · App/Browser · zuletzt genutzt · IP). Ein Empfänger
ist damit zugleich Alarmempfänger und, über seine Berechtigungen, Quittierberechtigter. Es gibt keinen
zweiten Eintrag.

- Das Feld ändert **keine** Alarmeinstellung: Benachrichtigungsdienst, Device Tracker, kritische
  Burst-Alarme, Berechtigungen und Action-Token bleiben genau wie konfiguriert. Bestehende Empfänger
  ohne Kopplung bleiben unverändert, bis jemand eine Anmeldung auswählt.

- Gespeichert wird nur die Login-ID (`session_token_id` am Empfänger). Sie ist kein Geheimnis und
  erlaubt allein keine Anmeldung.
- Eine Anmeldung kann nur mit **einem** Empfänger gekoppelt sein.
- Akzeptiert werden nur normale App-/Browser-Anmeldungen aktiver, nicht systemeigener Benutzer, die zum
  Benutzer der Verbindung gehören. Long-Lived-Tokens (Skripte) zählen nie als gekoppeltes Gerät.
- Wird die Anmeldung in HA gelöscht oder meldet sich das Gerät neu an, verliert die Kopplung sofort
  ihre Wirkung. Das Gerät muss dann neu gekoppelt werden.
- Nicht gekoppelte Sitzungen, etwa ein Desktop-Browser, können nur anzeigen.

Damit hat zum Beispiel ein iPad zuhause (stationär, globale Quittierung erlaubt) mehr Rechte als das
Telefon desselben Benutzers unterwegs.

### Befehle

Alle Befehle nehmen optional `config_entry_id` (nötig bei mehreren Instanzen). Kein Befehl nimmt oder
liefert ein Empfänger-Token oder eine Reset-Nonce. Diese liest das Backend selbst und übergibt sie an die
vorhandenen Prüffunktionen.

| Befehl | Felder | Wirkung | Prüfung im Backend beim Ausführen |
|---|---|---|---|
| `water_leak_detection/session` | – | Auskunft: `paired`, `recipient_id`, `recipient_name`, `home`, `trusted_stationary`, `can_global_ack`, `can_external_reset` | nur Anzeige; jede Aktion prüft erneut |
| `water_leak_detection/mute` | `event_id` | stummschalten **nur für dieses Gerät** | gekoppelt, Ereignis aktiv; überall erlaubt |
| `water_leak_detection/acknowledge` | `event_id` | globale Quittierung | über `async_acknowledge_event`: Berechtigung, Device Tracker `home`, Ereignis aktiv, dauerhaft gespeichert vor Bestätigung |
| `water_leak_detection/external_reset` | `event_id`, `source_id`, `source_generation` | externes Leck zurücksetzen | über `async_external_reset`: Berechtigung, `home`, exakte Ereignisbindung, dauerhaft gespeichert |

Für hydraulische Alarme gibt es keinen Befehl: Sie enden nur physisch. Quittieren und Stummschalten
beenden weder Erkennung noch Alarm noch Absperranforderung.

### Fehlercodes

| Code | Bedeutung für die Karte |
|---|---|
| `not_paired` | Dieses Gerät ist nicht gekoppelt (oder die Kopplung ist ungültig geworden) |
| `not_home` | Dieses Gerät ist laut Device Tracker nicht zuhause |
| `not_allowed` | Dem Empfänger fehlt die Berechtigung (globale Quittierung bzw. externer Reset) |
| `event_not_active` | Ereignis ist nicht mehr aktiv oder gehört nicht zu dieser Quelle/Generation |
| `not_committed` | Konnte nicht dauerhaft gespeichert werden; nichts wurde veröffentlicht |
| `rejected` | Sonstige Ablehnung durch die Prüffunktion |
| `instance_not_found` | Instanz unbekannt oder mehrdeutig (`config_entry_id` angeben) |

## Nächste Etappen

**Etappe C – Frontend-Anbindung:** Die Karte fragt `session` ab und zeigt nur die Aktionen, die dieses
Gerät gerade darf. Abgelehnte Aktionen erscheinen mit verständlichem Text zum Fehlercode. Tests für
mehrere Ereignisse und zuhause/unterwegs.

**Etappe D – Automatische Registrierung** (z. B. `StaticPathConfig` und
`frontend.add_extra_js_url`) mit Versionsparameter, Migrationsanleitung für manuell eingetragene
Ressourcen und Tests mit mehreren Konfigurationseinträgen.
