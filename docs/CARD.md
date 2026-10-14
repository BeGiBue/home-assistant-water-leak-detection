# Dashboard-Karte (Lovelace)

**Status:** Karte 0.6.0 (unveröffentlicht: Abschnitte standardmäßig offen, Option `collapsed`, Wanddisplay-Empfänger); zuletzt veröffentlicht Karte 0.5.0 mit Water Leak Guard **2.0.0-beta.2**. Die Karte ist eine Ansicht auf die vorhandenen
Entitäten, Dienste und Kartenbefehle und **keine Vertrauensgrenze**: Sie enthält weder Empfänger-Token noch
Reset-Nonce, und Berechtigung, Anwesenheit und erlaubte Alarmaktionen prüft ausschließlich das
Backend. Die Integration bleibt ohne Karte voll funktionsfähig (SPEC §1051).

**Nicht nachgewiesen:** Die Karte ist bisher nur mit simuliertem Home Assistant im Browser getestet
(Chromium, Desktop- und Handybreite, hell/dunkel). Ein Test in einer echten HA-Installation steht aus.

Datei: `custom_components/water_leak_detection/frontend/water-leak-guard-card.js`
– eine einzelne JS-Datei ohne Build-Schritt und ohne externe Abhängigkeiten. Sie wird mit der
Integration installiert und automatisch geladen (siehe Installation).

![Karte im Normalzustand und bei Burst-Leak-Alarm mit Geräteaktionen](https://raw.githubusercontent.com/BeGiBue/homeassistant-water-leak-detection/main/docs/assets/card-preview.png)

## Inhalt der Karte

| Bereich | Quelle | Bedienung |
|---|---|---|
| Kopf: Alarmstatus, Leckalarm, Absperranforderung | `sensor.*_status` (Attribute `aggregate_alarm_active`, `aggregate_shutoff_request`, `active_detector`) | Tippen öffnet Details |
| **Hydraulische Überwachung** | `sensor.*_hydraulic_monitoring_status` (ab 1.2.0-beta.3) mit `reason`, `source_entity_id`, `mqtt_provenance_status`, `last_valid_measurement`, `observation_age_seconds` | Grund und Messherkunft aufklappbar |
| Hinweis Laufzeitspeicher | Attribut `storage_recovery_required` | – |
| Alarmkasten (aktive Ereignisse, hydraulisch und extern) – steht bei Alarm direkt unter dem Kopf | Attribute `hydraulic_detectors`, `external_sources`, `notification_events`; Dauer-/Volumensensor; Befehl `session` | Stummschalten, global quittieren, externes Leck zurücksetzen, bei Slow Leak/Low Flow „Erkennung abschalten“, bei High Flow „Bypass starten“ – nur was dieses Gerät gerade darf (siehe unten) |
| Durchfluss mit High-/Burst-Marke | `current_flow`, `effective_high_threshold`, `effective_burst_threshold` | – |
| Erkennung: 2×2-Statusraster Slow/Low/High/Burst | Attribut `detectors`, Schalter Slow/Low (nur gelesen), Bypass-Schalter | keine – reine Anzeige; Erklärung im Tooltip |
| High-Flow-Bypass (einklappbar) | Bypass-Schalter, Restzeit, Standarddauer | Zusammenfassung „Aus – High Flow wird überwacht“ bzw. „Aktiv – noch 1 h 30 min (bis 21:00)“; aufgeklappt Start mit Voreinstellung oder Standarddauer; „Beenden“ steht bei aktivem Bypass direkt in der Zusammenfassung |
| Externe Lecksensoren (wenn konfiguriert) | Attribut `external_sources` (ohne Tombstones), Live-Zustand des Sensors | Tippen öffnet den Sensor |
| Lernmodell (einklappbar) | Lernzuverlässigkeit, Abdeckung, Normalspitze, Langzeitmaximum, Lernwerte | Zusammenfassung „Zuverlässig · 30/30 Tage“; aufgeklappt vier Werte in einer Zeile und Zurücksetzen (nur Admins, mit Rückfrage) |

Alle Bedienelemente rufen nur vorhandene, im Backend geprüfte Schalter, Dienste und Kartenbefehle auf
(`switch.turn_off`, `start_high_flow_bypass`, `cancel_high_flow_bypass`, `reset_learning`,
`water_leak_detection/mute`, `/acknowledge`, `/external_reset`).

## Layout und unterstützte Bildschirme (ab Karte 0.5.0)

**Wie breit die Karte wird, bestimmt Home Assistant.** Spalten im Masonry-Layout und Abschnitte
(Sections) sind höchstens ca. 500 px breit. Dort ist die Karte deshalb **immer einspaltig**, auch auf
einem Tablet oder dem Raspberry-Pi-Display. Zwei Spalten gibt es nur, wenn die Karte selbst mindestens
ca. 600 px breit ist: in der **Panel-Ansicht** oder in einer Sections-Ansicht mit einem Abschnitt über
mehrere Spalten (`column_span` ≥ 2) und `grid_options: columns: full` an der Karte.

Höhe der ruhigen Karte (Überwachung aktiv, kein Alarm), gemessen in Chromium mit simuliertem Home
Assistant. Je nach Schrift weichen echte Geräte um **ca. ±15 px** ab. Ab 0.6.0 starten die Abschnitte
„High-Flow-Bypass“ und „Lernmodell“ **aufgeklappt**; mit `collapsed: true` starten sie zu (Höhe wie 0.5.0).

| Gerät / Ansicht | Kartenbreite | Spalten | 0.4.1 | 0.6.0 Standard (offen) | 0.6.0 `collapsed: true` |
|---|---|---|---|---|---|
| schmales Telefon | 320 px | 1 | ca. 930 px | ca. 615 px | ca. 335 px |
| iPhone 17 Pro (402×874) | ca. 386 px | 1 | ca. 884 px | ca. 550 px | ca. 335 px |
| iPad / Raspberry Pi 7″ quer (800×480) in Masonry oder Sections | ca. 490–500 px | 1 | ca. 827 px | ca. 550 px | ca. 335 px |
| Raspberry Pi 7″ hochkant (480×800), Kiosk ohne Seitenleiste | ca. 448–464 px | 1 | – | ca. 550 px | ca. 335 px |
| Panel-Ansicht oder Abschnitt über ganze Breite (Tablet, Pi im Panel) | ≥ ca. 600 px (z. B. 744/768 px) | 2 | ca. 810 px | ca. 465 px | ca. 190 px |

Mit einem externen Sensor kommen ca. 80 px hinzu (ca. 415 px), mit aktivem Bypass bei schmaler Karte
ca. 12 px (zweizeilige Zusammenfassung).

**Raspberry Pi 7″ (altes offizielles Display):**

- **Hochkant (480×800,** ca. 744 px unter der HA-Leiste von 56 px): Die Karte ist ca. 448–464 px breit
  und passt mit dem **Standard (Abschnitte offen)** ohne Scrollen: ruhig ca. 550 px, Unterkante bei ca.
  613 px (gemessen bei 448 und 464 px, DE/EN, ±15 px). Ein Alarm braucht mehr Platz (Display-Sitzung:
  Burst ca. 850–880 px, Low Flow ca. 870–900 px); der Alarmkasten steht oben, der Rest wird gescrollt.
  `collapsed: true` ist hier nicht nötig.
- **Quer (800×480,** ca. 420 px unter der Leiste): Nur mit `collapsed: true` (ca. 335 px) passt die ruhige
  Karte ohne Scrollen. `collapsed: true` braucht man also nur quer oder auf anderen niedrigen Bildschirmen.

Für ein Wanddisplay oder den Pi eignet sich eine eigene Ansicht im Panel-Modus (zwei Spalten):

```yaml
views:
  - title: Wasser
    path: wasser
    type: panel
    cards:
      - type: custom:water-leak-guard-card
        entity: sensor.wasserwachter_status
```

- **Einklappbar:** „High-Flow-Bypass“ und „Lernmodell“ zeigen eine Zusammenfassungszeile. Sie ist ein
  echter Button mit `aria-expanded` und Pfeil (mindestens 44 px hoch), bedienbar per Klick, Enter und
  Leertaste. Beide Abschnitte sind anfangs zu. Der Auf/Zu-Zustand gilt pro Karte und bleibt bei jeder
  Aktualisierung von Home Assistant erhalten (nicht über ein Neuladen der Seite hinweg).
- **Überwachung kompakt:** Ist die hydraulische Überwachung bestätigt aktiv, sind Status- und
  Überwachungs-Entität verfügbar, ist weder die Messquelle gestört (`source_unavailable`,
  `source_available: false`) noch der Laufzeitspeicher beschädigt und ist kein externer Sensor
  unerreichbar, ersetzt ein grüner Hinweis „Hydraulik aktiv“ in der Durchflusszeile die eigene Zeile (ohne
  Durchflussabschnitt steht er im Kopf). In jedem anderen Zustand erscheint die volle Zeile
  „Hydraulische Überwachung“ mit Grund und Details wie bisher. Grün bleibt bestätigt aktiver
  Überwachung vorbehalten.
- **Immer sichtbar:** flacher Kopf (ca. 76 px, kleines Schild rechts; Titel, Überschrift und Kennzeichen
  laufen nie unter das Schild, Kennzeichen dürfen umbrechen), Alarmkasten bei Alarm, Durchfluss, das
  2×2-Raster der Detektoren, die beiden Zusammenfassungszeilen und – wenn konfiguriert – die externen
  Sensoren.
- **Zwei Spalten** ab ca. 600 px Kartenbreite (CSS Container Query auf der Karte, nicht auf dem Fenster):
  links Kopf, Alarmkasten, Überwachung, Durchfluss; rechts Erkennung, Bypass, externe Sensoren, Lernmodell.
- **Mindestbreite 280 px:** Die Container Query macht die Breite der Karte unabhängig von ihrem Inhalt; in
  einem Container, der sich nach dem Inhalt richtet, würde sie sonst auf 0 px zusammenfallen.
- **Bedienflächen:** Jedes Bedienelement hat mindestens 44 px Trefferfläche. Buttons (auch im
  Alarmkasten und „Beenden“), Zusammenfassungszeilen, „Grund und Messherkunft“ und das Status-Symbol sind
  tatsächlich mindestens 44 px hoch; kleine Textlinks (Durchflusswert, Sensornamen) haben eine
  unsichtbare Trefferfläche von 44 px.
- `getGridOptions()` bleibt `{ columns: 12, min_columns: 6, rows: "auto" }`: Bestehende Dashboards im
  Abschnitte-Layout behalten Breite und Platz, die Höhe folgt dem Inhalt. `getCardSize()` (nur für das
  Masonry-Layout zum Verteilen der Spalten, Einheit 50 px) liefert 7 ohne und 14 mit Alarm.
- Hell/dunkel über die Theme-Variablen von Home Assistant; bei `prefers-reduced-motion` keine Animationen.

## Keine Schalter in der Karte (ab 0.5.0)

Die Karte hat **keine Ein/Aus-Schalter** mehr (Entscheidung des Maintainers). Das Raster „Erkennung“ zeigt
nur den Zustand: „Bereit“, „Prüft“, „Alarm“, „Aus“ (Detektor abgeschaltet), „Bypass“, „Pausiert“ oder
neutral „unbekannt“. Die Kacheln sind nicht anklickbar und öffnen keinen Detaildialog.

- Slow Leak oder Low Flow lassen sich in der Karte nur noch **im Alarmkasten** abschalten, und nur solange
  der Alarm **dieses** Detektors aktiv ist: „Erkennung abschalten“, mit derselben Rückfrage wie bisher und
  demselben Dienstaufruf (`switch.turn_off` auf den Detektorschalter). Wieder einschalten und das
  Abschalten außerhalb eines Alarms gehen über die Geräteseite der Integration bzw. die Entitäten.
- Die Karte verlinkt die Detektorschalter nirgends; ein Detaildialog dieser Schalter wird auch bei einem
  manipulierten Link nicht geöffnet. Bypass-Schalter und Bypass-Dauer öffnet sie während eines
  High-Flow-Alarms ebenfalls nicht.

### Alarm beenden nur zuhause

Es gilt dieselbe Regel wie für alle anderen Aktionen: **quittieren von überall, Alarm beenden nur von
zuhause.** Zwei Kartenaktionen beenden einen laufenden Alarm:

- „Erkennung abschalten“ bei einem aktiven Slow-Leak- oder Low-Flow-Alarm,
- „Bypass starten“ während eines aktiven High-Flow-Alarms (im Alarmkasten oder aufgeklappt im
  Bypass-Abschnitt).

Beide bietet die Karte nur einem **gekoppelten Gerät, das zuhause ist** an – dieselbe Bedingung wie für
„Externes Leck zurücksetzen“ (`paired` und `home` aus der Session-Antwort, zusätzlich sofort gesperrt,
wenn der sichtbare Tracker nicht `home` ist). Unterwegs erscheinen sie gesperrt mit „Nur zuhause
möglich“, ein nicht gekoppeltes Gerät sieht sie nicht. Der Klick prüft die Bedingung erneut. Ohne Alarm
sind die Bypass-Voreinstellungen wie bisher für alle verfügbar; „Beenden“ des Bypass beendet keinen Alarm
und ist immer erlaubt.

**Wichtig:** Das ist eine Regel der Karte, keine Sicherheitsgrenze. Die Entitäten (`switch.*_detection`,
`switch.*_high_flow_bypass`) und Dienste (`start_high_flow_bypass`) der Integration bleiben in Home
Assistant **unbeschränkt**: Jeder HA-Benutzer kann sie über die Geräteseite, Automationen oder Skripte
bedienen. Eine Backend-Prüfung nur für den Kartenweg würde daran nichts ändern und wurde deshalb nicht
eingebaut.

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
  statt „Bereit“; ein ACTIVE-Detektor bleibt „Alarm“. Meldet die Überwachung „aktiv“, ist aber der
  Speicher beschädigt oder die Messquelle gestört (`source_unavailable`, `source_available: false`), ist
  die Karte ohne Alarm gelb mit „Überwachung eingeschränkt“ statt grün „Alles ruhig“. Die Zeile
  „Hydraulische Überwachung“ zeigt dann gelb „Eingeschränkt“ statt grün „Aktiv“, und die Detektoren zeigen
  „Pausiert“ statt „Bereit“ – dasselbe wie ohne gültige Messung, denn es wird nicht verlässlich
  ausgewertet; der Tooltip nennt den Grund. Ein ACTIVE-Detektor bleibt „Alarm“. Ist der Alarm aktiv, ohne dass eine Alarmart
  bekannt ist, lautet die Überschrift „Leckalarm“.
- Ein **ACTIVE**-Alarm bleibt in jedem Betriebszustand sichtbar: Kopf rot, Detektor „Alarm“,
  Ereignis im Alarmkasten. Das Backend meldet als Status bei Quellenausfall `source_unavailable`,
  auch während eines Alarms. Die Karte liest die Alarmart deshalb aus `active_detector`.
- Liefert die Status-Entität selbst nichts (`unavailable`), zeigt die Karte nur „Status nicht
  verfügbar“ und keine veralteten Werte.
- Externe Sensoren, deren Entität fehlt oder nicht verfügbar ist, zeigen „Nicht verfügbar“ statt
  „Trocken“. Ein aktives externes Leck bleibt sichtbar.

Bedeutung der Zustände, Attribute und Zeitbasis:
[Hydraulische Überwachung](CONFIGURATION.md#hydraulische-überwachung) ·
[Diagnose bei „Warte auf Messung“ oder „Gesperrt“](TROUBLESHOOTING.md#hydraulic-monitoring-waiting-or-blocked).

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
| Für *Name* stummschalten | stoppt Benachrichtigungen nur für den gekoppelten Empfänger (*Name* aus der Session-Antwort `recipient_name`; ohne Namen „Für dieses Gerät stummschalten“). Wichtig bei Benutzer-Kopplung: Ein Laptop desselben Benutzers schaltet damit den Empfänger (z. B. das Telefon) stumm | gekoppelt, Ereignis nicht global quittiert, Empfänger noch nicht stumm (sonst: „Bei *Name* stummgeschaltet“) | nie (auch unterwegs erlaubt) |
| Global quittieren | stoppt Benachrichtigungen für alle | gekoppelt, Berechtigung „globale Quittierung“, nicht global quittiert | nicht zuhause: „Nur zuhause möglich“ |
| Externes Leck zurücksetzen | beendet den Alarm des externen Sensors und seinen Beitrag zur Absperranforderung; der Sensor wird erst wieder scharf, wenn er „trocken“ meldet. Rückfrage vor dem Senden | nur bei aktivem externem Ereignis ohne Identitätskonflikt, gekoppelt, Berechtigung „externer Reset“ | nicht zuhause: „Nur zuhause möglich“ |
| Erkennung abschalten (Slow Leak/Low Flow) | schaltet den Detektor aus (`switch.turn_off`) und beendet damit seinen aktiven Alarm samt Beitrag zur Absperranforderung; die Ursache bleibt. Rückfrage vor dem Senden | aktiver Alarm dieses Detektors, gekoppelt, Detektor eingeschaltet | nicht zuhause: „Nur zuhause möglich“ |
| Bypass starten (High Flow) | startet den High-Flow-Bypass mit Standarddauer und beendet damit den aktiven High-Flow-Alarm; die Ursache bleibt. Rückfrage vor dem Senden | aktiver High-Flow-Alarm, gekoppelt | nicht zuhause: „Nur zuhause möglich“ |
| Hydraulischen Alarm sonst beenden | kein Kartenbefehl. Der Alarm endet, sobald der Durchfluss die Ruhe-/Rücksetzbedingung erfüllt. Burst Leak endet nur physisch | – | – |

Jeder Button trägt die genaue `event_id`, der Reset zusätzlich `source_id` und `source_generation` aus
`external_sources`. Die Karte schickt die `config_entry_id` mit, sobald sie bekannt ist. Ein Button ist
während seiner Anfrage gesperrt (kein Doppelversand). Nach Erfolg kommt eine kurze Bestätigung, und die
Session wird neu abgefragt.

**Nicht gekoppelt:** Keine Aktionsbuttons, sondern der Hinweis „Dieses Gerät ist nicht gekoppelt – nur
Anzeige.“ Admins sehen zusätzlich, wo gekoppelt wird (**Konfigurieren → Benachrichtigungsempfänger →
Empfänger bearbeiten → Kopplung für die Dashboard-Karte**) und den Link zur Integration. Ein älteres Backend ohne
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
Die Karte öffnet keinen Detaildialog der Detektorschalter und – während eines High-Flow-Alarms – keinen
des Bypass-Schalters, damit dort nichts ohne Rückfrage einen Alarm beendet.

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
collapsed: false                      # true: Bypass und Lernmodell starten eingeklappt (z. B. 800×480 quer)
```

`collapsed` (Editor: „Abschnitte eingeklappt starten“) bestimmt nur den Anfangszustand. Auf- und
Zuklappen in der Karte bleibt pro Karte im Speicher, auch bei Aktualisierungen; eine Änderung der Option
im Editor setzt beide Abschnitte auf den neuen Standard zurück.

Das Hintergrundmotiv übernimmt die Kartenfarbe (grün, grau, gelb, rot). Im Alarm schwappt das Wasser
an die rechte Wand. Bei `prefers-reduced-motion` steht es still.

## Backend-Vertrag für Kartenaktionen (Etappe B)

Im Backend umgesetzt und getestet. Die Karte nutzt ihn seit Version 0.4.0 (Etappe C, siehe
„Alarmbedienung in der Karte“).

### Identität: Benutzer oder einzelne Anmeldung

Jede Anmeldung (Companion App oder Browser) hat in Home Assistant eine eigene Login-ID (Refresh-Token-ID)
und gehört zu einem Benutzer. Beides führt die WebSocket-Verbindung serverseitig mit; das Gerät kann es
nicht fälschen.

Die Kopplung ist **Teil des Empfänger-Eintrags**: Unter **Konfigurieren → Benachrichtigungsempfänger →
Empfänger hinzufügen / bearbeiten** gibt es das optionale Feld **Kopplung für die Dashboard-Karte**. Zur
Wahl stehen:

- „—“: nicht gekoppelt,
- **„👤 Name“** (Benutzer; Standard, steht oben): jede normale App-/Browser-Anmeldung dieses HA-Benutzers.
  Passt zum Modell „ein Gerät = immer ein Benutzer“ und übersteht Ab-/Anmelden, Neuinstallation der App
  und einen neuen Browser,
- **„🔑 Benutzer – App/Browser · zuletzt genutzt · IP“** (einzelne Anmeldung): genau eine Anmeldung, wie bisher.
  Die Symbole sind sprachneutral, weil das Optionsformular die Sprache des Betrachters nicht kennt.

Gespeichert wird entweder `session_user_id` oder `session_token_id` am Empfänger, nie beides. Beide sind
keine Geheimnisse und erlauben allein keine Anmeldung. Bestehende Kopplungen an eine Anmeldung
(`session_token_id`) gelten unverändert weiter; eine Migration ist nicht nötig.

**Auflösung je Verbindung** (`session_recipient`):

1. Nur eine normale App-/Browser-Anmeldung (keine Long-Lived-Tokens/Skripte) eines aktiven, nicht
   systemeigenen Benutzers, die zum Benutzer der Verbindung gehört, wird überhaupt betrachtet.
2. Ist genau diese Anmeldung mit einem Empfänger gekoppelt, gilt dieser Empfänger (Anmeldung schlägt
   Benutzer).
3. Sonst gilt der Empfänger, der mit dem Benutzer der Verbindung gekoppelt ist.
4. Sonst ist die Sitzung nicht gekoppelt (nur Anzeige). Mehrdeutige Kopplungen berechtigen nie.

**Folge der Benutzer-Kopplung:** *Jede* Anmeldung dieses Benutzers – auch ein Laptop-Browser – erhält die
Rechte des gekoppelten Empfängers. „Zuhause“ kommt aber immer vom Device Tracker **dieses Empfängers**
(z. B. dem Telefon), nicht vom Laptop. Wer einem Benutzer auf mehreren Geräten verschiedene Rechte geben
will (iPad zuhause darf global quittieren, Telefon unterwegs nur stummschalten), koppelt diese Geräte
einzeln über „🔑 …“; eine solche Kopplung hat Vorrang vor der Benutzer-Kopplung.

- Das Feld ändert **keine** Alarmeinstellung: Benachrichtigungsdienst, Device Tracker, kritische
  Burst-Alarme, Berechtigungen und Action-Token bleiben genau wie konfiguriert. Speichern ohne Änderung des
  Felds behält die bisherige Kopplung, auch wenn die Anmeldung inzwischen gelöscht ist (sie steht dann mit
  „⚠“ in der Liste und wirkt nicht).
- Ein Benutzer kann nur mit **einem** Empfänger gekoppelt sein, eine Anmeldung ebenso
  (`session_user_already_paired`, `session_already_paired`). Ein inzwischen gelöschter oder deaktivierter
  Benutzer wird abgelehnt (`session_user_not_found`), eine gelöschte Anmeldung ebenso (`session_not_found`).
- Wird die Anmeldung gelöscht oder der Benutzer deaktiviert, verliert die Kopplung sofort ihre Wirkung.
- Die Kopplung wird bei jeder Aktion **innerhalb** der Schreibsperre des Managers erneut aufgelöst. Wird
  sie geändert, während ein Befehl wartet, wird der Befehl abgelehnt (`not_paired`).
- Stummschalten, Quittieren, Zuhause-Prüfung und externes Zurücksetzen arbeiten wie bisher pro
  **Empfänger**; nur die Zuordnung Verbindung → Empfänger ist neu. Stummschalten gilt also nur für den
  aufgelösten Empfänger.
- `trusted_stationary` ersetzt die Anwesenheitsprüfung **nicht**: Auch ein stationäres iPad braucht
  einen Device Tracker mit Zustand `home`.
- Nicht gekoppelte Sitzungen können nur anzeigen.

### Befehle

Alle Befehle nehmen optional `config_entry_id` (nötig bei mehreren Instanzen). Kein Befehl nimmt oder
liefert ein Empfänger-Token oder eine Reset-Nonce. Diese liest das Backend selbst und übergibt sie an die
vorhandenen Prüffunktionen.

| Befehl | Felder | Wirkung | Prüfung im Backend beim Ausführen |
|---|---|---|---|
| `water_leak_detection/session` | – | Auskunft: `paired`, `recipient_id`, `recipient_name`, `kind` (`mobile`/`display`), `home`, `tracker_entity` (bei einem Display `null`), `trusted_stationary`, `can_mute`, `can_global_ack`, `can_external_reset` | nur Anzeige; jede Aktion prüft erneut |
| `water_leak_detection/mute` | `event_id` | stummschalten **nur für dieses Gerät** | gekoppelt, Ereignis aktiv, kein Wanddisplay (`mute_not_applicable`); überall erlaubt |
| `water_leak_detection/acknowledge` | `event_id` | globale Quittierung | über `async_acknowledge_event`: Berechtigung, Device Tracker `home`, Ereignis aktiv, dauerhaft gespeichert vor Bestätigung |
| `water_leak_detection/external_reset` | `event_id`, `source_id`, `source_generation` | externes Leck zurücksetzen | über `async_external_reset`: Berechtigung, `home`, exakte Ereignisbindung, dauerhaft gespeichert |

Für hydraulische Alarme gibt es keinen WebSocket-Befehl. Sie enden, sobald der Durchfluss die
Ruhe-/Rücksetzbedingung erfüllt, oder über die vorhandenen Schalter und Dienste (siehe „Keine Schalter in der Karte“);
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
| `mute_not_applicable` | Ein Wanddisplay bekommt keine Benachrichtigungen; Stummschalten entfällt |

### Wanddisplay (Empfängertyp `display`)

Ein fest montiertes Display (TouchKio, Kiosk-Browser) wird unter *Konfigurieren →
Benachrichtigungsempfänger → Wanddisplay hinzufügen* angelegt. Es hat keinen Benachrichtigungsdienst und
keinen Device Tracker, bekommt nie Benachrichtigungen und gilt bei **jeder** Zuhause-Prüfung als
zuhause (globale Quittierung, externer Reset, die alarmbeendenden Kartenaktionen). Es braucht eine
Kopplung, und zwar **nur an eine einzelne Anmeldung** (🔑): die Anmeldung des Kiosk-Geräts. Eine
Benutzer-Kopplung ist für ein Display nicht erlaubt (Formularfehler `display_requires_login`); in einem
von Hand bearbeiteten Eintrag wird sie ignoriert und im Log gemeldet. Sonst wäre jede Anmeldung dieses
Benutzers – Laptop im Büro, Handy nach einer Neuanmeldung – über den Benutzer-Rückfall „zuhause“.
Eindeutigkeit und „nur normale Anmeldungen“ gelten wie oben. Die Rechte sind die üblichen Häkchen des
Empfängers; „Globales Quittieren“ ist bei einem Display ohne gespeicherten Wert aus. Die Karte blendet
dort „Stummschalten“ aus und zeigt nie „Nur zuhause möglich“. **Abwägung:** Wer diese Kiosk-Anmeldung
nutzt – am Display oder aus der Ferne mit derselben Browser-Sitzung –, hat diese Rechte. Empfohlen ist
ein eigener HA-Benutzer ohne Adminrechte für das Kiosk-Gerät. Meldet sich das Kiosk-Gerät neu an, muss die
Kopplung erneuert werden. Empfänger mit unbekannter oder leerer Art (`kind`) werden ignoriert und im Log
gemeldet; sie bekommen keine Benachrichtigungen und dürfen nichts. Beispiel-Automation zum
Einschalten des Displays bei Alarm: Wiki-Seite *Dashboard-Karte*, Abschnitt „Wanddisplay / TouchKio“.

## Entwicklungsstand

Alle Etappen der Kartenübergabe sind umgesetzt: A (Überwachungszustand, ehrliche Anzeige), B (Backend-Vertrag
mit Gerätekopplung), C (Alarmaktionen in der Karte) und D (Auslieferung mit der Integration). Danach: kompaktes,
einklappbares Layout mit zwei Spalten und Kopplung an einen Benutzer (Karte 0.5.0, unveröffentlicht). Jede Etappe
wurde von einer unabhängigen Review-Instanz anhand des Codes geprüft. Getestet ist die Karte mit simuliertem
Home Assistant und der vollständigen Python-Testsuite in der CI; ein Test in einer echten Installation steht
aus.

Bewusst offen (geringe Auswirkung, Entscheidung des Maintainers):

- Stummschalten genau während eines Neuladens der Integration kann verloren gehen und trotzdem Erfolg melden;
  das Gerät erhält dann weiter Meldungen.
- Wird nur die Kopplung eines Empfängers geändert, während gerade eine Meldung an ihn übergeben wird, kann
  diese eine Meldung entfallen.
- Ist der Device Tracker für einen Benutzer nicht sichtbar, sperrt die Karte Zuhause-Knöpfe erst mit der
  nächsten Berechtigungsabfrage; das Backend lehnt bis dahin mit `not_home` ab.
- Schlägt beim externen Zurücksetzen das Speichern fehl, meldet die Karte „abgelehnt“ statt „nicht
  gespeichert“; Alarm und Absperranforderung bleiben korrekt aktiv.
