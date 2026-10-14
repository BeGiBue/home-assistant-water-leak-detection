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
| Externes Leck zurücksetzen | beendet den externen Alarm | nur zuhause, berechtigtes Gerät, Sensor wieder trocken | Benachrichtigung |
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

## Nächste Etappen

**Etappe B – Backend-Vertrag (offen, Entscheidungen nötig).** Vor jeder Implementierung festlegen:

- **Identität:** Zuordnung des angemeldeten HA-Benutzers (`connection.user`) zu Person und
  Empfänger(n) serverseitig. Kein Token aus dem Frontend.
- **Getrennte Aktionen:** persönliches Stummschalten (überall, nur eigene Empfänger), globale
  Quittierung (Home-Prüfung beim Ausführen) und externes Zurücksetzen (Home, Berechtigung, Sensor
  trocken). Hydraulische Alarme bleiben ausgeschlossen.
- **Ereignisbindung:** jede Aktion mit exakter `event_id` (bei extern zusätzlich `source_id` und
  `source_generation`), damit nie der falsche Alarm quittiert wird.
- **Fehlercodes** für verständliche Meldungen, z. B. `not_home`, `not_active`, `not_authorized`,
  `no_recipient`.
- Vorher prüfen, ob vorhandene Backend-Funktionen (`async_acknowledge_event`, Mute-Pfad,
  `async_external_reset`) wiederverwendet werden können.

Platzhalter in der Karte (`INTERFACE`, derzeit `enabled: false`):
`water_leak_detection/acknowledge` und `water_leak_detection/clear_alarm`. Namen und Felder
richten sich nach dem Vertrag aus Etappe B.

**Etappe C – Frontend-Anbindung** an den geprüften Vertrag, mit Tests für Berechtigung, mehrere
Ereignisse und zuhause/unterwegs.

**Etappe D – Automatische Registrierung** (z. B. `StaticPathConfig` und
`frontend.add_extra_js_url`) mit Versionsparameter, Migrationsanleitung für manuell eingetragene
Ressourcen und Tests mit mehreren Konfigurationseinträgen.
