# Dashboard-Karte

Seit **2.0.0-beta.1** gehört die Dashboard-Karte **Water Leak Guard** zur Integration; mit **2.0.0** ist es Karte **0.6.2** (offene Abschnitte, Wanddisplay-Empfänger, robuster Start). Sie ist
eine Ansicht und Bedienoberfläche, aber **keine Vertrauensgrenze**: Ob eine Aktion erlaubt ist,
entscheidet ausschließlich das Backend. Die Integration funktioniert unverändert auch ohne Karte.

![Karte im Normalzustand und bei Burst-Leak-Alarm mit Geräteaktionen](https://raw.githubusercontent.com/BeGiBue/water-leak-guard/main/docs/assets/card-preview.png)

## Installation

Es ist nichts zu kopieren und keine Ressource einzutragen.

1. Integration über HACS installieren oder aktualisieren, Home Assistant neu starten.
2. Browser bzw. Companion App neu laden.
3. Im Dashboard **Karte hinzufügen → Water Leak Guard** wählen.

Die Integration stellt die Datei beim Start unter `/water_leak_detection/water-leak-guard-card.js`
bereit und lädt sie in jedes Dashboard (UI- und YAML-Modus). Die Adresse enthält einen Prüfwert aus
dem Dateiinhalt, damit nach Updates keine alte Version im Browser-Cache bleibt. Frontend und http sind
nur Lade-Reihenfolge: Schlägt das Registrieren fehl, startet die Leckerkennung trotzdem, nur die Karte
fehlt und im Log steht eine Warnung.

Im UI-Ressourcenmodus legt die Integration zusätzlich **einen** Eintrag unter *Ressourcen* an:
„water-leak-guard-card loader“ (`data:text/javascript…`). Er lädt die Karte auch auf einer Seite, die
während des HA-Starts geöffnet wurde, und verhindert so den „Konfigurationsfehler“ bis zum Neuladen.
Nicht löschen; er wird mit dem letzten Eintrag der Integration entfernt. Beim Deinstallieren daher
zuerst die Einträge der Integration entfernen, dann HACS.

**Umstieg von Karte 0.1.0/0.2.0:** die manuell eingetragene Ressource `/local/water-leak-guard-card.js`
unter *Einstellungen → Dashboards → ⋮ → Ressourcen* löschen und die Datei in `<config>/www/` entfernen.
Bestehende Karten (`type: custom:water-leak-guard-card`) bleiben unverändert.

```yaml
type: custom:water-leak-guard-card
entity: sensor.wasserwachter_status   # optional; Editor bietet nur Status-Sensoren an
title: Wasserwächter                  # optional; sonst Gerätename aus Home Assistant
show_flow: true
show_detectors: true
show_bypass: true
show_external: true
show_learning: true
show_background: true                 # Schutzschild mit Wasser im Kopf
bypass_presets: [60, 120, 240]        # Minuten, 1–1440
```

## Was die Karte zeigt

- **Kopf:** nur den Alarmstatus, dazu „Leckalarm“ und „Absperrung angefordert“. Ein ACTIVE-Alarm bleibt
  immer sichtbar, auch wenn die Messquelle ausfällt.
- **Hydraulische Überwachung:** eigene Zeile mit Aktiv / Warte auf Messung / Gesperrt, bei „Gesperrt“
  mit Grund und Messherkunft. Grün und „Alles ruhig“ erscheinen nur bei bestätigt aktiver Überwachung
  und ohne ausgefallenen externen Sensor; sonst grau oder gelb mit „Kein Alarm“.
- Bei Alarm steht der **Alarmkasten** direkt unter dem Kopf.
- Durchfluss mit High- und Burst-Grenze und ein kompaktes 2×2-Raster der Detektoren Slow/Low/High/Burst
  (nur Anzeige, keine Schalter).
- **High-Flow-Bypass** und **Lernmodell** sind einklappbar (anfangs zu): Die Zusammenfassung zeigt
  „Aus – High Flow wird überwacht“ bzw. „Aktiv – noch 1 h 30 min (bis 21:00)“ mit „Beenden“, und
  „Zuverlässig · 30/30 Tage“. Nur ein zuverlässiges Lernmodell ist grün.
- Externe Lecksensoren, wenn konfiguriert.

## Layout

Ab Karte 0.5.0 ist die ruhige Karte einspaltig nur noch ca. 335 px hoch (gemessen, je nach Schrift
ca. ±15 px). Spalten im Masonry-Layout und Abschnitte sind in Home Assistant höchstens ca. 500 px breit;
dort – auch auf iPad und dem alten 7″-Display des Raspberry Pi – ist die Karte einspaltig. Zwei Spalten (links Kopf, Alarm, Überwachung, Durchfluss; rechts Erkennung,
Bypass, externe Sensoren, Lernmodell) zeigt sie nur, wenn sie selbst mindestens ca. 600 px breit ist: in
der Panel-Ansicht oder in einem Abschnitt über mehrere Spalten (`column_span` ≥ 2) mit
`grid_options: columns: full`. Beispiel für ein Wanddisplay:

```yaml
views:
  - title: Wasser
    type: panel
    cards:
      - type: custom:water-leak-guard-card
```

Ist die hydraulische Überwachung bestätigt aktiv und nichts gestört (auch kein externer Sensor
unerreichbar), zeigt ein grüner Hinweis „Hydraulik aktiv“ in der Durchflusszeile das an; in jedem anderen
Zustand erscheint die volle Zeile mit Grund. Sind Speicher oder Messquelle gestört, heißt es gelb
„Überwachung eingeschränkt“ statt „Alles ruhig“. Der Stummschalt-Knopf nennt den
gekoppelten Empfänger („Für Bea stummschalten“). Hell/dunkel und „Bewegung reduzieren“ werden beachtet.

## Abschnitte auf- oder zugeklappt

Ab Karte 0.6.0 starten „High-Flow-Bypass“ und „Lernmodell“ **aufgeklappt** (ruhige Karte einspaltig ca.
550 px hoch, bei 320 px ca. 615 px). Mit `collapsed: true` (Editor: „Abschnitte eingeklappt starten“)
starten sie zu; dann ist die ruhige Karte einspaltig ca. 335 px hoch (alle Werte gemessen, ±15 px).

Altes Raspberry-Pi-Display 7″:

- **hochkant (480×800):** Der Standard (offen) passt: ruhig ca. 550 px bei 448–464 px Kartenbreite,
  Unterkante bei ca. 613 px unter einer 56-px-Leiste (Platz ca. 744 px). `collapsed` ist nicht nötig.
  Ein Alarm braucht mehr Platz (ca. 850–900 px); der Alarmkasten steht oben.
- **quer (800×480):** Nur eingeklappt passt die ruhige Karte unter die Leiste (ca. 420 px Platz):

```yaml
type: custom:water-leak-guard-card
collapsed: true   # nur für 800×480 quer oder andere niedrige Bildschirme
```

Auf- und Zuklappen in der Karte bleibt bis zum Neuladen der Seite erhalten; eine Änderung der Option
im Editor setzt auf den neuen Standard zurück.

## Wanddisplay / TouchKio

> **Vollständige Anleitung (Kiosk-Benutzer, Formular, Karte, Automation, Fehlerbehebung):
> [Wanddisplay mit TouchKio](Wanddisplay-TouchKio).**

![Karte auf dem Raspberry Pi 7″: hochkant ruhig und bei Burst-Alarm, quer eingeklappt](https://raw.githubusercontent.com/BeGiBue/water-leak-guard/main/docs/assets/card-wall-display.png)

Ein fest montiertes Display – etwa [TouchKio](https://github.com/leukipp/touchkio) auf einem Raspberry Pi
oder ein anderer HA-Kiosk-Browser – hat weder Companion-Benachrichtigungen noch einen Device Tracker.
Dafür gibt es den Empfängertyp **Wanddisplay** (*Konfigurieren → Benachrichtigungsempfänger →
Wanddisplay hinzufügen*): keine Benachrichtigungen, kein Stummschalten, gilt immer als zuhause, braucht
eine Kopplung (eigener Kiosk-Benutzer ohne Adminrechte oder die einzelne Anmeldung des Kiosks).
**Jede Sitzung, die als das Display erkannt wird, hat seine Rechte** – bei einer Kopplung an den Benutzer
auch eine Anmeldung aus der Ferne; deshalb ein eigenes, starkes Passwort. Alles Weitere steht auf der
[Anleitungsseite](Wanddisplay-TouchKio).

Auf dem 7″-Display hochkant (480×800) reicht der Standard; quer (800×480) `collapsed: true` setzen (siehe oben).

**Empfohlene Automation:** Das Dashboard mit der Karte ist die Startseite des Kiosks (TouchKio `web_url`);
bei einem Leck genügt es, das Display einzuschalten. Die Entity-IDs sind **Platzhalter** – die echten
stehen unter *Einstellungen → Geräte & Dienste → Geräte → TouchKio*.

```yaml
alias: Wasserwächter – Display bei Leck einschalten
triggers:
  - trigger: event
    event_type: water_leak_detection_event_started
  - trigger: state
    entity_id: binary_sensor.wasserwachter_leckalarm   # Platzhalter: Leckalarm der Integration
    to: "on"
actions:
  - action: light.turn_on
    target:
      entity_id: light.touchkio_flur_display          # Platzhalter: Display-Licht von TouchKio
    data:
      brightness_pct: 100
mode: single
```

Zeigt der Kiosk sonst eine andere Seite, kann zusätzlich die Seiten-URL gesetzt werden – mit **exakt
derselben Basis-URL** (Schema, Host, Port) wie TouchKios `web_url`, sonst fehlt die gespeicherte
Anmeldung. Beispiel und Warnung: [Anleitung, Schritt 4](Wanddisplay-TouchKio#schritt-4-automation-die-das-display-aufweckt).

## Bedienung mit Rückfrage

Die Karte hat **keine Ein/Aus-Schalter** mehr. Slow Leak und Low Flow lassen sich in der Karte nur im
Alarmkasten abschalten, solange ihr Alarm läuft („Erkennung abschalten“); bei High Flow bietet der
Alarmkasten „Bypass starten“. **Beides beendet den laufenden Alarm sofort** samt seinem Beitrag zur
Absperranforderung, ohne die Ursache zu beheben. Die Karte fragt mit Warnung nach und bietet beides –
wie das Zurücksetzen eines externen Lecks – **nur einem gekoppelten Gerät zuhause** an („quittieren von
überall, Alarm beenden nur von zuhause“). Burst ist nicht abschaltbar und nicht per Bypass zu
unterdrücken. Ein-/Ausschalten außerhalb eines Alarms geht über die Geräteseite der Integration; die
Entitäten und Dienste selbst bleiben in Home Assistant unbeschränkt.

## Alarmaktionen pro Gerät

Rechte hängen am **Empfänger**. Gekoppelt wird beim passenden Benachrichtigungsempfänger:
*Konfigurieren → Benachrichtigungsempfänger → Empfänger bearbeiten → Kopplung für die Dashboard-Karte*.

- **„👤 Name“** (Benutzer, Standard): jede App-/Browser-Anmeldung dieses HA-Benutzers. Bleibt bei
  Ab-/Anmelden und Neuinstallation erhalten. Auch ein Laptop-Browser dieses Benutzers bekommt dann die
  Rechte des Empfängers; „zuhause“ kommt aber immer vom Device Tracker des Empfängers.
- **„🔑 Name – App/Browser“**: genau eine Anmeldung, z. B. wenn ein Benutzer auf iPad und Telefon verschiedene
  Rechte haben soll. Eine gekoppelte Anmeldung hat Vorrang vor der Benutzer-Kopplung.

Ein Benutzer und eine Anmeldung gehören jeweils zu höchstens einem Empfänger; die übrigen Einstellungen
des Empfängers ändern sich dadurch nicht. Bestehende Kopplungen an eine Anmeldung gelten weiter.

| Gerät | Angebotene Aktionen |
|---|---|
| nicht gekoppelt (z. B. Desktop-Browser) | keine, Hinweis „nur Anzeige“ |
| gekoppelt, unterwegs | Für *Empfänger* stummschalten (z. B. „Für Bea stummschalten“); „Global quittieren“ gesperrt („Nur zuhause möglich“) |
| gekoppelt, unterwegs, Alarm Slow/Low/High | zusätzlich „Erkennung abschalten“ bzw. „Bypass starten“ gesperrt („Nur zuhause möglich“) |
| Wanddisplay (gekoppelt, gilt immer als zuhause) | kein Stummschalten; Global quittieren und externes „Zurücksetzen“ je nach Berechtigung, „Erkennung abschalten“/„Bypass starten“ im Alarm – nie „Nur zuhause möglich“ |
| gekoppelt, zuhause, mit Berechtigung | Stummschalten, Global quittieren, bei externem Leck „Zurücksetzen“, bei Slow/Low „Erkennung abschalten“, bei High „Bypass starten“ – jeweils mit Rückfrage, wo ein Alarm endet |

- Stummschalten wirkt nur auf das eigene Gerät; Quittieren stoppt Benachrichtigungen für alle. Beides
  beendet weder Erkennung noch Alarm noch Absperranforderung.
- Für hydraulische Alarme gibt es keinen Lösch- oder Reset-Knopf.
- „Zuhause“ bestimmt der Device Tracker des gekoppelten Empfängers, geprüft im Backend beim Ausführen.
  Ein stationäres iPad braucht ebenfalls einen Tracker auf `home`.
- Bei Kopplung an eine einzelne Anmeldung: Meldet sich das Gerät neu an oder wird die Anmeldung
  gelöscht, endet die Kopplung; dann die neue Anmeldung wählen oder auf „Benutzer“ umstellen.

Abgelehnte Aktionen erscheinen als verständliche Meldung, zum Beispiel „Dieses Gerät ist laut Device
Tracker nicht zuhause“. Technische Einzelheiten zu Befehlen und Fehlercodes:
[Entitäten, Aktionen und Events](Home-Assistant-Schnittstellen#dashboard-karte-und-kartenbefehle).

## Stand und Grenzen

Getestet mit der vollständigen Testsuite in der CI und mit simuliertem Home Assistant im Browser; jede
Etappe wurde unabhängig anhand des Codes geprüft. Ein Test in einer echten Installation steht aus.
Bewusst offene Punkte mit geringer Auswirkung und alle Details:
[Kartendokumentation](https://github.com/BeGiBue/water-leak-guard/blob/main/docs/CARD.md) · [Beta 2.0.0](https://github.com/BeGiBue/water-leak-guard/blob/main/docs/BETA_2.0.0.md).
