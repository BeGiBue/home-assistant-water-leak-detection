# Wasserwächter-Karte (Lovelace)

**Status:** vorbereitet, Version 0.1.0. Die Karte ist eine reine Ansicht auf die vorhandenen
Entitäten und Dienste. Sie ändert kein Backend-Verhalten, und die Integration bleibt ohne Karte voll
funktionsfähig (SPEC §1051).

Datei: `custom_components/water_leak_detection/frontend/water-leak-guard-card.js`
– eine einzelne JS-Datei ohne Build-Schritt und ohne externe Abhängigkeiten.

## Inhalt der Karte

| Bereich | Quelle | Bedienung |
|---|---|---|
| Kopf: Status, Leckalarm, Absperranforderung | `sensor.*_status`, Attribute `aggregate_alarm_active`, `aggregate_shutoff_request` | Tippen öffnet Details |
| Hinweise: Messquelle, Laufzeitspeicher | Attribute `source_available`, `storage_recovery_required` | – |
| Aktive Ereignisse (hydraulisch und extern) | Attribute `hydraulic_detectors`, `external_sources`, `notification_events`; Dauer-/Volumensensor | Quittieren, Alarm löschen (siehe unten) |
| Durchfluss mit High-/Burst-Marke | `current_flow`, `effective_high_threshold`, `effective_burst_threshold` | – |
| Erkennung Slow/Low/High/Burst | Attribut `detectors`, Schalter Slow/Low, Bypass-Schalter | Slow/Low ein/aus |
| High-Flow-Bypass | Bypass-Schalter, Restzeit, Standarddauer | Start mit Voreinstellung oder Standarddauer, Beenden |
| Externe Lecksensoren | Attribut `external_sources` (ohne Tombstones) | Tippen öffnet den Sensor |
| Lernmodell | Lernzuverlässigkeit, Abdeckung, Normalspitze, Langzeitmaximum | Zurücksetzen (nur Admins, mit Rückfrage) |

Die Karte findet alle Entitäten automatisch über das Gerät der gewählten Status-Entität
(`translation_key` im Entity-Registry). Umbenannte Entity-IDs funktionieren weiterhin.
Bei mehreren Instanzen schickt sie `config_entry_id` an die Dienste mit.

Sprache: Deutsch oder Englisch, je nach HA-Sprache. Farben: HA-Theme-Variablen, also Hell und Dunkel.

Im Kopf der Karte steht als dekoratives Hintergrundmotiv ein Schutzschild, das mit sanft bewegtem
Wasser gefüllt ist. Es übernimmt die Statusfarbe (grün in Ruhe, blau beim Prüfen, gelb bei
fehlender Messquelle, rot bei Alarm). Im Alarm bewegen sich die Wellen schneller. Bei
`prefers-reduced-motion` stehen sie still. Mit `show_background: false` lässt sich das Motiv abschalten.

## Installation (bis zur automatischen Registrierung)

1. `water-leak-guard-card.js` nach `<config>/www/` kopieren.
2. **Einstellungen → Dashboards → ⋮ → Ressourcen → Ressource hinzufügen**:
   URL `/local/water-leak-guard-card.js`, Typ **JavaScript-Modul**.
3. Browser neu laden und im Dashboard die Karte **Water Leak Guard** hinzufügen.

```yaml
type: custom:water-leak-guard-card
entity: sensor.wasserwachter_status   # optional; ohne Angabe wird die erste Instanz genommen
title: Wasserwächter                  # optional
show_flow: true
show_detectors: true
show_bypass: true
show_external: true
show_learning: true
show_background: true          # Schutzschild mit Wasser im Kopf der Karte
bypass_presets: [60, 120, 240]        # Minuten, 1–1440
```

## Quittieren und Alarm löschen

Konzept: **Quittieren geht von überall, Alarm löschen nur von zuhause.**

| Aktion | Wirkung | Wer/wo | Karte |
|---|---|---|---|
| Quittieren | Stoppt Benachrichtigungen. Alarm und Absperranforderung bleiben. | überall | Button immer aktiv, solange nicht quittiert |
| Alarm löschen | Beendet den Alarm einer Quelle | nur zuhause | Button nur aktiv, wenn die Person des angemeldeten HA-Benutzers `home` ist |

Die Anwesenheitsprüfung in der Karte ist **nur ein UI-Hinweis**. Die verbindliche
Home-Prüfung muss im Backend passieren, so wie heute bei globaler Quittierung und externem Reset.

Hydraulische Alarme (Slow, Low, High, Burst) enden heute nur physisch. Die Karte bietet
„Alarm löschen“ deshalb nur für externe Lecksensoren an und zeigt bei hydraulischen Alarmen einen Hinweis.

Die Karte enthält **kein** Empfänger-Token und **keine** Reset-Nonce. Die vorhandenen Dienste
`acknowledge_event` und `external_reset` setzen beides voraus und werden deshalb nicht aufgerufen.

### Vorgeschlagene Backend-Schnittstelle

Beide Buttons rufen WebSocket-Befehle auf, die es im Backend **noch nicht gibt**. Antwortet das Backend
mit `unknown_command`, öffnet die Karte den vorhandenen, admin-geschützten Dialog
**Konfigurieren** der Integration (`/config/integrations/integration/water_leak_detection`).

Die Namen stehen in der Karte zentral im Objekt `INTERFACE`. Die spätere Schnittstellendoku kann
sie also ändern, ohne die übrige Karte anzufassen.

```jsonc
// Quittieren – von überall
{ "type": "water_leak_detection/acknowledge",
  "config_entry_id": "…",   // fehlt bei nur einer Instanz, wenn nicht ermittelbar
  "event_id": "…" }

// Alarm löschen – nur zuhause
{ "type": "water_leak_detection/clear_alarm",
  "config_entry_id": "…",
  "event_id": "…",
  "source_id": "…",          // bei externen Quellen
  "source_generation": "…" } // bei externen Quellen
```

Offene Punkte für die Schnittstellendoku:

- **Identität:** Das Backend sollte den aufrufenden HA-Benutzer (`connection.user`) einer Person
  bzw. einem Empfänger zuordnen, statt ein Token vom Frontend anzunehmen.
- **Home-Prüfung für `clear_alarm`:** dieselbe Regel wie beim externen Reset, ausgewertet im Backend
  zum Zeitpunkt des Commits.
- **Quittieren von unterwegs:** Heute ist von unterwegs nur die gerätebezogene Stummschaltung
  möglich, die globale Quittierung braucht Home. Für „Quittieren von überall“ muss festgelegt werden,
  ob das Stummschalten für den Benutzer oder eine globale Quittierung gemeint ist.
- **Fehlercodes:** Bei Ablehnung (`not_home`, `not_active`, `not_authorized`) zeigt die Karte die
  Fehlermeldung als Hinweis an.

## Automatische Registrierung (später)

Die Datei liegt bereits im Integrationsordner, damit HACS sie mitinstalliert. Ein späterer
Backend-Schritt kann sie über `StaticPathConfig` und `frontend.add_extra_js_url` selbst
registrieren. Dann entfallen die manuellen Installationsschritte oben.
