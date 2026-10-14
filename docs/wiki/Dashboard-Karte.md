# Dashboard-Karte

Seit **2.0.0-beta.1** gehört die Dashboard-Karte **Water Leak Guard** (Karte 0.4.1) zur Integration. Sie ist
eine Ansicht und Bedienoberfläche, aber **keine Vertrauensgrenze**: Ob eine Aktion erlaubt ist,
entscheidet ausschließlich das Backend. Die Integration funktioniert unverändert auch ohne Karte.

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
- Durchfluss mit High- und Burst-Grenze, Detektoren Slow/Low/High/Burst, High-Flow-Bypass, externe
  Lecksensoren und Lernmodell.

## Bedienung mit Rückfrage

Slow und Low lassen sich abschalten, der High-Flow-Bypass lässt sich starten. **Beides beendet einen
laufenden Alarm dieser Art sofort** samt seinem Beitrag zur Absperranforderung, ohne die Ursache zu
beheben. Die Karte fragt in diesem Fall mit Warnung nach. Burst ist nicht abschaltbar und nicht per
Bypass zu unterdrücken.

## Alarmaktionen pro Gerät

Rechte hängen am **Gerät**, nicht am Benutzer. Ein Gerät wird gekoppelt, indem beim passenden
Benachrichtigungsempfänger seine Anmeldung ausgewählt wird:
*Konfigurieren → Benachrichtigungsempfänger → Empfänger bearbeiten → Gekoppelte Anmeldung für die
Dashboard-Karte*. Eine Anmeldung gehört zu höchstens einem Empfänger; die übrigen Einstellungen des
Empfängers ändern sich dadurch nicht.

| Gerät | Angebotene Aktionen |
|---|---|
| nicht gekoppelt (z. B. Desktop-Browser) | keine, Hinweis „nur Anzeige“ |
| gekoppelt, unterwegs | Für dieses Gerät stummschalten; „Global quittieren“ gesperrt („Nur zuhause möglich“) |
| gekoppelt, zuhause, mit Berechtigung | Stummschalten, Global quittieren, bei externem Leck „Zurücksetzen“ mit Rückfrage |

- Stummschalten wirkt nur auf das eigene Gerät; Quittieren stoppt Benachrichtigungen für alle. Beides
  beendet weder Erkennung noch Alarm noch Absperranforderung.
- Für hydraulische Alarme gibt es keinen Lösch- oder Reset-Knopf.
- „Zuhause“ bestimmt der Device Tracker des gekoppelten Empfängers, geprüft im Backend beim Ausführen.
  Ein stationäres iPad braucht ebenfalls einen Tracker auf `home`.
- Meldet sich ein Gerät neu an oder wird die Anmeldung gelöscht, endet die Kopplung; dann die neue
  Anmeldung auswählen.

Abgelehnte Aktionen erscheinen als verständliche Meldung, zum Beispiel „Dieses Gerät ist laut Device
Tracker nicht zuhause“. Technische Einzelheiten zu Befehlen und Fehlercodes:
[Entitäten, Aktionen und Events](Home-Assistant-Schnittstellen#dashboard-karte-und-kartenbefehle).

## Stand und Grenzen

Getestet mit der vollständigen Testsuite in der CI und mit simuliertem Home Assistant im Browser; jede
Etappe wurde unabhängig anhand des Codes geprüft. Ein Test in einer echten Installation steht aus.
Bewusst offene Punkte mit geringer Auswirkung und alle Details:
[Kartendokumentation](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/CARD.md) · [Beta 2.0.0](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/BETA_2.0.0.md).
