# Dashboard-Karte

Seit **2.0.0-beta.1** gehört die Dashboard-Karte **Water Leak Guard** zur Integration (veröffentlicht: Karte 0.4.1; in Arbeit: Karte 0.5.0 mit kompaktem Layout). Sie ist
eine Ansicht und Bedienoberfläche, aber **keine Vertrauensgrenze**: Ob eine Aktion erlaubt ist,
entscheidet ausschließlich das Backend. Die Integration funktioniert unverändert auch ohne Karte.

![Karte im Normalzustand und bei Burst-Leak-Alarm mit Geräteaktionen](https://raw.githubusercontent.com/BeGiBue/homeassistant-water-leak-detection/main/docs/assets/card-preview.png)

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
dort – auch auf iPad und dem alten 7″-Display des Raspberry Pi (800×480) – ist die Karte einspaltig und
passt unter die HA-Leiste. Zwei Spalten (links Kopf, Alarm, Überwachung, Durchfluss; rechts Erkennung,
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
[Kartendokumentation](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/CARD.md) · [Beta 2.0.0](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/BETA_2.0.0.md).
