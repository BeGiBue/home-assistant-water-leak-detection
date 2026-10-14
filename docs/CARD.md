# Dashboard-Karte (Lovelace)

**Status:** Version 0.4.1 (Etappen A, B, C und D umgesetzt). Die Karte ist eine Ansicht auf die vorhandenen
Entitäten, Dienste und Kartenbefehle und **keine Vertrauensgrenze**: Sie enthält weder Empfänger-Token noch
Reset-Nonce, und Berechtigung, Anwesenheit und erlaubte Alarmaktionen prüft ausschließlich das
Backend. Die Integration bleibt ohne Karte voll funktionsfähig (SPEC §1051).

**Nicht nachgewiesen:** Die Karte ist bisher nur mit simuliertem Home Assistant im Browser getestet
(Chromium, Desktop- und Handybreite, hell/dunkel). Ein Test in einer echten HA-Installation steht aus.

Datei: `custom_components/water_leak_detection/frontend/water-leak-guard-card.js`
– eine einzelne JS-Datei ohne Build-Schritt und ohne externe Abhängigkeiten. Sie wird mit der
Integration installiert und automatisch geladen (siehe Installation).

## Inhalt der Karte

| Bereich | Quelle | Bedienung |
|---|---|---|
| Kopf: Alarmstatus, Leckalarm, Absperranforderung | `sensor.*_status` (Attribute `aggregate_alarm_active`, `aggregate_shutoff_request`, `active_detector`) | Tippen öffnet Details |
| **Hydraulische Überwachung** | `sensor.*_hydraulic_monitoring_status` (ab 1.2.0-beta.3) mit `reason`, `source_entity_id`, `mqtt_provenance_status`, `last_valid_measurement`, `observation_age_seconds` | Grund und Messherkunft aufklappbar |
| Hinweis Laufzeitspeicher | Attribut `storage_recovery_required` | – |
| Aktive Ereignisse (hydraulisch und extern) | Attribute `hydraulic_detectors`, `external_sources`, `notification_events`; Dauer-/Volumensensor; Befehl `session` | Stummschalten, global quittieren, externes Leck zurücksetzen – nur was dieses Gerät gerade darf (siehe unten) |
| Durchfluss mit High-/Burst-Marke | `current_flow`, `effective_high_threshold`, `effective_burst_threshold` | – |
| Erkennung Slow/Low/High/Burst | Attribut `detectors`, Schalter Slow/Low, Bypass-Schalter | Slow/Low ein/aus |
| High-Flow-Bypass | Bypass-Schalter, Restzeit, Standarddauer | Start mit Voreinstellung oder Standarddauer, Beenden |
| Externe Lecksensoren | Attribut `external_sources` (ohne Tombstones), Live-Zustand des Sensors | Tippen öffnet den Sensor |
| Lernmodell | Lernzuverlässigkeit, Abdeckung, Normalspitze, Langzeitmaximum | Zurücksetzen (nur Admins, mit Rückfrage) |

Alle Bedienelemente rufen nur vorhandene, im Backend geprüfte Schalter, Dienste und Kartenbefehle auf
(`switch.turn_on/off`, `start_high_flow_bypass`, `cancel_high_flow_bypass`, `reset_learning`,
`water_leak_detection/mute`, `/acknowledge`, `/external_reset`).

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
- Ist ein konfigurierter externer Lecksensor nicht erreichbar (Entität fehlt, `unavailable`/`unknown`)
  und meldet kein Leck, ist die Karte gelb mit „Kein Alarm“ statt grün „Alles ruhig“.
- Ist der Laufzeitspeicher beschädigt (`storage_recovery_required`), zeigen die Detektoren „Pausiert“
  statt „Bereit“; ein ACTIVE-Detektor bleibt „Alarm“. Ist der Alarm aktiv, ohne dass eine Alarmart
  bekannt ist, lautet die Überschrift „Leckalarm“.
- Ein **ACTIVE**-Alarm bleibt in jedem Betriebszustand sichtbar: Kopf rot, Detektor „Alarm“,
  Ereignis im Alarmkasten. Das Backend meldet als Status bei Quellenausfall `source_unavailable`,
  auch während eines Alarms. Die Karte liest die Alarmart deshalb aus `active_detector`.
- Liefert die Status-Entität selbst nichts (`unavailable`), zeigt die Karte nur „Status nicht
  verfügbar“ und keine veralteten Werte.
- Externe Sensoren, deren Entität fehlt oder nicht verfügbar ist, zeigen „Nicht verfügbar“ statt
  „Trocken“. Ein aktives externes Leck bleibt sichtbar.

## Alarmbedienung in der Karte (Etappe C)

Die Karte fragt den Befehl `water_leak_detection/session` nur in diesen Fällen ab:

- beim Verbinden der Karte und wenn die konfigurierte Entität (Instanz) wechselt,
- wenn die Seite wieder sichtbar wird (`visibilitychange`),
- beim Übergang „kein Alarm → Alarm“,
- nach jeder Aktion der Karte,
- wenn sich der Zustand des Device Trackers des gekoppelten Empfängers ändert (`tracker_entity` aus
  der Session-Antwort),
- alle 60 s, solange ein Alarm aktiv ist. Ohne Alarm fragt sie nicht regelmäßig.

Normale Zustandsänderungen (Durchfluss, Dauer, Status) lösen keine Abfrage aus. Höchstens eine Abfrage
je 5 s; nur die Antwort der neuesten Anfrage zählt. Eine abgehängte Karte fragt nichts ab und hält keine
Timer. Sie zeigt pro aktivem Ereignis nur die Aktionen, die **dieses Gerät** gerade
darf. „Zuhause“ kommt ausschließlich aus der Session-Antwort (Device Tracker des gekoppelten
Empfängers), nicht aus einer Person-Entität im Browser. Den Tracker selbst nutzt die Karte nur als
Anlass für eine neue Abfrage und als Anzeigehinweis: Ist sein Zustand sichtbar und nicht `home`, sperrt
sie die nur-zuhause-Buttons sofort („Nur zuhause möglich“), auch wenn die letzte Session-Antwort noch
„zuhause“ sagte. Freigeben kann nur eine neue Session-Antwort. Das Backend prüft jede Aktion beim
Ausführen erneut; die Karte entscheidet nichts.

| Aktion | Wirkung | Angezeigt, wenn | Gesperrt (mit Grund) |
|---|---|---|---|
| Für dieses Gerät stummschalten | stoppt Benachrichtigungen nur für dieses Gerät | gekoppelt, Ereignis nicht global quittiert, dieses Gerät noch nicht stumm (sonst: „Auf diesem Gerät stummgeschaltet“) | nie (auch unterwegs erlaubt) |
| Global quittieren | stoppt Benachrichtigungen für alle | gekoppelt, Berechtigung „globale Quittierung“, nicht global quittiert | nicht zuhause: „Nur zuhause möglich“ |
| Externes Leck zurücksetzen | beendet den Alarm des externen Sensors und seinen Beitrag zur Absperranforderung; der Sensor wird erst wieder scharf, wenn er „trocken“ meldet. Rückfrage vor dem Senden | nur bei aktivem externem Ereignis ohne Identitätskonflikt, gekoppelt, Berechtigung „externer Reset“ | nicht zuhause: „Nur zuhause möglich“ |
| Hydraulischen Alarm beenden | kein Kartenbefehl. Der Alarm endet, sobald der Durchfluss die Ruhe-/Rücksetzbedingung erfüllt. Slow Leak/Low Flow enden auch beim Ausschalten des Detektors, High Flow beim Start des Bypass – jeweils mit Rückfrage; die Ursache bleibt. Burst Leak endet nur physisch | – | – |

Jeder Button trägt die genaue `event_id`, der Reset zusätzlich `source_id` und `source_generation` aus
`external_sources`. Die Karte schickt die `config_entry_id` mit, sobald sie bekannt ist. Ein Button ist
während seiner Anfrage gesperrt (kein Doppelversand). Nach Erfolg kommt eine kurze Bestätigung, und die
Session wird neu abgefragt.

**Nicht gekoppelt:** Keine Aktionsbuttons, sondern der Hinweis „Dieses Gerät ist nicht gekoppelt – nur
Anzeige.“ Admins sehen zusätzlich, wo gekoppelt wird (**Konfigurieren → Benachrichtigungsempfänger →
Empfänger bearbeiten → Gekoppelte Anmeldung**) und den Link zur Integration. Ein älteres Backend ohne
Kartenbefehle (`unknown_command`) oder ein Fehler der Session-Abfrage gilt ebenfalls als „nicht
gekoppelt“, mit kurzem Hinweis.

**Meldungen bei Ablehnung** (Benachrichtigung in HA):

| Code | Meldung der Karte |
|---|---|
| `not_paired` | Dieses Gerät ist nicht (mehr) gekoppelt. |
| `not_home` | Nur zuhause möglich: Dieses Gerät ist laut Device Tracker nicht zuhause. |
| `not_allowed` | Diese Aktion ist für dieses Gerät nicht freigegeben. |
| `event_not_active` | Das Ereignis ist nicht mehr aktiv. |
| `not_committed` | Konnte nicht dauerhaft gespeichert werden. Es wurde nichts geändert. |
| `rejected` | Vom Backend abgelehnt. |
| `instance_not_found` | Instanz nicht gefunden oder mehrdeutig. Bitte die Status-Entität der Karte prüfen. |
| `unknown_command` | Dieses Backend bietet keine Kartenaktionen an. |
| anderer Fehler | Aktion fehlgeschlagen: (Diagnosetext) |

Die Rückfrage liest die Phase immer aus dem Status-Sensor, den die Karte anzeigt (über das Gerät der
gewählten Entität aufgelöst), auch wenn im Editor eine andere Entität der Integration gewählt wurde.
Während eines laufenden High-Flow-Alarms öffnet der Kopf des Bypass-Abschnitts keinen Detaildialog
des Bypass-Schalters, damit der Bypass dort nicht ohne Rückfrage gestartet werden kann.

Ohne Eingriff endet ein hydraulischer Alarm, sobald der Durchfluss die Ruhe-/Rücksetzbedingung
erfüllt. Burst Leak endet nur physisch. Der Hinweis im Alarmkasten nennt den Weg passend zur Alarmart.

Quittieren und Stummschalten beenden **weder** Erkennung noch Alarm noch Absperranforderung. Die Karte
zeigt pro Ereignis, ob global quittiert ist und auf wie vielen Geräten stummgeschaltet wurde. Admins
erhalten bei offenen Ereignissen einen Link zur Integrationsseite. Quittieren ist außerdem weiterhin
über die Benachrichtigung und **Konfigurieren → Aktive Meldungen quittieren** möglich.

## Installation

Die Karte kommt **mit der Integration**. Es ist nichts zu kopieren und keine Ressource einzutragen:

1. Integration über HACS installieren oder aktualisieren und Home Assistant neu starten.
2. Browser bzw. Companion App neu laden.
3. Im Dashboard **Karte hinzufügen → Water Leak Guard** wählen.

So funktioniert es:

- Beim Start stellt die Integration die Datei unter `/water_leak_detection/water-leak-guard-card.js`
  bereit und lädt sie als zusätzliches Frontend-Modul (`frontend.add_extra_js_url`). Das gilt für alle
  Dashboards, im UI- wie im YAML-Modus, ohne Eintrag unter *Ressourcen*.
- Die Adresse enthält einen Prüfwert aus dem Dateiinhalt (`?v=…`). Nach jedem Update lädt der Browser die
  neue Version, ohne dass ein alter Stand im Cache hängen bleibt.
- `frontend` und `http` sind nur als **Lade-Reihenfolge** eingetragen (`after_dependencies`), nicht als
  Pflicht. Ohne Frontend oder bei einem Fehler beim Registrieren startet die Leckerkennung trotzdem.
  Nur die Karte fehlt dann, und im Log steht eine Warnung.
- Mehrere Instanzen der Integration teilen sich dieselbe Karte. Pro Karte wählt man die Instanz über
  die Status-Entität.

### Umstieg von der manuellen Installation (Karte 0.1.0/0.2.0)

Wer die Karte vorher von Hand eingebunden hat:

1. Unter **Einstellungen → Dashboards → ⋮ → Ressourcen** den Eintrag
   `/local/water-leak-guard-card.js…` löschen.
2. Die Datei `<config>/www/water-leak-guard-card.js` löschen.
3. Browser neu laden. Bestehende Karten (`type: custom:water-leak-guard-card`) bleiben unverändert.

Bleibt die alte Ressource stehen, lädt der Browser zwei Kopien. Ein Custom Element kann nur einmal
definiert werden, also gewinnt die zuerst geladene. Normalerweise ist das die Kopie der Integration.
Die Karte schreibt dann einen Hinweis in die Browser-Konsole, welche Version aktiv ist.

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

Im Backend umgesetzt und getestet. Die Karte nutzt ihn seit Version 0.4.0 (Etappe C, siehe
„Alarmbedienung in der Karte“).

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
  ihre Wirkung. Das Gerät muss dann neu gekoppelt werden. Im Empfängerformular steht das Feld in dem
  Fall auf „—“; wer den Empfänger speichert, entfernt damit die ungültige Kopplung. Alle anderen
  Einstellungen bleiben unverändert.
- Die Kopplung wird bei jeder Aktion **innerhalb** der Schreibsperre des Managers erneut geprüft. Wird
  sie geändert, während ein Befehl wartet, wird der Befehl abgelehnt (`not_paired`).
- `trusted_stationary` ersetzt die Anwesenheitsprüfung **nicht**: Auch ein stationäres iPad braucht
  einen Device Tracker mit Zustand `home`.
- Nicht gekoppelte Sitzungen, etwa ein Desktop-Browser, können nur anzeigen.

Damit hat zum Beispiel ein iPad zuhause (stationär, globale Quittierung erlaubt) mehr Rechte als das
Telefon desselben Benutzers unterwegs.

### Befehle

Alle Befehle nehmen optional `config_entry_id` (nötig bei mehreren Instanzen). Kein Befehl nimmt oder
liefert ein Empfänger-Token oder eine Reset-Nonce. Diese liest das Backend selbst und übergibt sie an die
vorhandenen Prüffunktionen.

| Befehl | Felder | Wirkung | Prüfung im Backend beim Ausführen |
|---|---|---|---|
| `water_leak_detection/session` | – | Auskunft: `paired`, `recipient_id`, `recipient_name`, `home`, `tracker_entity`, `trusted_stationary`, `can_global_ack`, `can_external_reset` | nur Anzeige; jede Aktion prüft erneut |
| `water_leak_detection/mute` | `event_id` | stummschalten **nur für dieses Gerät** | gekoppelt, Ereignis aktiv; überall erlaubt |
| `water_leak_detection/acknowledge` | `event_id` | globale Quittierung | über `async_acknowledge_event`: Berechtigung, Device Tracker `home`, Ereignis aktiv, dauerhaft gespeichert vor Bestätigung |
| `water_leak_detection/external_reset` | `event_id`, `source_id`, `source_generation` | externes Leck zurücksetzen | über `async_external_reset`: Berechtigung, `home`, exakte Ereignisbindung, dauerhaft gespeichert |

Für hydraulische Alarme gibt es keinen WebSocket-Befehl. Sie enden, sobald der Durchfluss die
Ruhe-/Rücksetzbedingung erfüllt, oder über die vorhandenen Bedienelemente (siehe „Alarmbedienung heute“);
Burst Leak endet nur physisch. Quittieren und Stummschalten
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

**Etappe C – Frontend-Anbindung:** umgesetzt in 0.4.0 (siehe „Alarmbedienung in der Karte“). Getestet
mit simuliertem Home Assistant; ein Test in einer echten Installation steht aus.

**Etappe D – Automatische Registrierung:** umgesetzt (siehe Installation).
