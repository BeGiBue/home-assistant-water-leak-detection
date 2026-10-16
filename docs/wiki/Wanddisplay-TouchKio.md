# Wanddisplay mit TouchKio

Schritt-für-Schritt-Anleitung für ein fest montiertes Display (zum Beispiel ein Raspberry Pi mit
[TouchKio](https://github.com/leukipp/touchkio)), das die Karte **Water Leak Guard** zeigt, bei
einem Alarm aufwacht und dort quittieren darf. Voraussetzung: Wasserwächter ab **2.0.0** (Karte 0.6.2).

![Karte auf dem Raspberry Pi 7″: hochkant ruhig und bei Burst-Alarm, quer mit eingeklappten Abschnitten](https://raw.githubusercontent.com/BeGiBue/home-assistant-water-leak-detection/main/docs/assets/card-wall-display.png)

*Die Bilder zeigen die ausgelieferte Karte 0.6.2 in Chromium mit simuliertem Home Assistant (Pi 7″
hochkant 480×800 und quer 800×480, 56-px-Leiste, Wanddisplay-Sitzung). Kein Test auf echter Hardware.*

## Was ist ein Wanddisplay und warum ein eigener Empfängertyp?

Ein Wanddisplay ist ein **Empfänger der Art „Wanddisplay“**. Im Unterschied zu einem Handy:

- Es hat **keinen Benachrichtigungsdienst** und bekommt nie Benachrichtigungen.
- Es hat **keinen Device Tracker** und gilt bei jeder Zuhause-Prüfung **immer als zuhause**.
- Es kann **nicht stummschalten** (die Karte zeigt den Knopf dort nicht), denn es gibt nichts
  stummzuschalten.

**Rechtemodell, einfach gesagt:** Wer vor dem Display steht, hat die Rechte des Displays. Das Display
wird nicht daran erkannt, *wer* davor steht, sondern daran, *mit welcher Anmeldung* die Karte geladen
wurde (siehe Schritt 1 und 2). Gib dem Display deshalb nur Rechte, die für jeden im Haushalt und für
Besuch in Ordnung sind. Die Karte selbst ist keine Vertrauensgrenze: Das Backend prüft jede Aktion
erneut.

## Voraussetzungen und Hardware

- Ein Raspberry Pi mit einem Display und **TouchKio**. Laut TouchKio-README liefert TouchKio
  Display an/aus und Helligkeit als `light`-Entität, kann die Seiten-URL setzen (Navigation) und hat
  **keine** Benachrichtigungsentität und keine Töne. Genaueres und die Einrichtung (MQTT) stehen im
  [TouchKio-README](https://github.com/leukipp/touchkio).
- TouchKio öffnet als Startseite (`web_url`) das Home-Assistant-Dashboard mit der Karte.
- Die **Entity-IDs von TouchKio werden hier nicht vorgegeben**: Du findest sie unter *Einstellungen →
  Geräte & Dienste → Geräte → TouchKio (Gerät des Displays)*. Alle Namen in den Beispielen sind
  **Platzhalter**.

## Schritt 1: Kiosk-Benutzer anlegen

1. *Einstellungen → Personen → Benutzer* (Erweiterter Modus nötig): einen **eigenen Benutzer** anlegen,
   zum Beispiel „Wanddisplay“.
2. **Kein Administrator**, **nicht der Besitzer**, ein **lokales Konto** mit Benutzername und eigenem,
   **starkem Passwort**, das du nirgends sonst verwendest. Falls deine Home-Assistant-Version die Option
   „Nur im lokalen Netzwerk anmelden“ anbietet, aktiviere sie: Das begrenzt den Fernzugriff, ersetzt
   aber kein starkes Passwort.
3. Das Kiosk-Gerät (TouchKio) mit **diesem Benutzer** anmelden und das Dashboard mit der Karte
   als Startseite einstellen.

> **Wichtig:** Koppelst du das Display mit dem **Benutzer** („👤“), zählt **jede Anmeldung dieses
> Benutzers** als das Display und damit als zuhause, **auch eine Anmeldung aus der Ferne** mit seinem
> Passwort. Deshalb: starkes, einmaliges Passwort und keine Adminrechte.

## Schritt 2: Wanddisplay hinzufügen

*Einstellungen → Geräte & Dienste → Wasserwächter → Konfigurieren → Benachrichtigungsempfänger →
„Wanddisplay hinzufügen (ohne Push, immer zuhause)“*

| Feld | Bedeutung |
|---|---|
| **Anzeigename** | Name des Displays, zum Beispiel „Wanddisplay Flur“. |
| **Kopplung des Displays (erforderlich)** | Pflicht, sonst erkennt die Karte das Display nicht. Auswahl siehe unten. |
| **Globales Quittieren erlauben** | Darf die Karte auf diesem Display Alarme für alle quittieren? Standardmäßig aus. |
| **Externen Reset erlauben** | Darf die Karte auf diesem Display externe Lecks zurücksetzen (beendet den Alarm des Sensors)? Standardmäßig aus. |
| **Zurück ohne Speichern** | Verlässt das Formular ohne Änderung. |

**Kopplung, zwei Möglichkeiten:**

- **„👤 Kiosk-Benutzer“** (einfacher): der Benutzer aus Schritt 1. Die Rechte gelten für jede
  Anmeldung dieses Benutzers; sie bleiben bei Neuanmeldung des Kiosk-Geräts erhalten.
- **„🔑 Anmeldung“** (strenger): genau die **eine Anmeldung** des Kiosk-Geräts. Die Rechte hängen nur an
  dieser Sitzung. Meldet sich das Kiosk-Gerät neu an, muss die Kopplung **erneuert** werden.
  Long-Lived-Tokens zählen nie.

Eine gekoppelte Anmeldung hat Vorrang vor einer Benutzer-Kopplung. Gezählt werden die Kopplungen
**aller Instanzen** der Integration.

**Was das Formular ablehnt, und warum:**

| Meldung (sinngemäß) | Grund |
|---|---|
| Wanddisplay braucht eine Kopplung | Ohne Kopplung kann die Karte das Display nicht erkennen. |
| Besitzer oder Administrator nicht erlaubt | Ein Display gilt immer als zuhause; ein Administrator-Konto auf einer Wand wäre zu mächtig. Eigenen Kiosk-Benutzer anlegen oder die einzelne Anmeldung („🔑“) wählen. |
| Benutzer oder eine seiner Anmeldungen schon mit einem anderen Empfänger gekoppelt | Ein Display braucht einen Benutzer, den sonst niemand nutzt. |
| Anmeldung kann kein Wanddisplay sein | Anmeldungen der **Companion-App** (Handy/Tablet) und Anmeldungen eines Benutzers, den ein Handy-Empfänger nutzt, werden nicht angeboten; sonst wäre dieses Handy überall „zuhause“. Die Anmeldung des Kiosk-Browsers wählen. |

Umgekehrt kann **kein anderer Empfänger** den Kiosk-Benutzer oder eine seiner Anmeldungen wählen
(„einem Wanddisplay zugeordnet“).

**Die Art lässt sich nach dem Anlegen nicht ändern.** Zum Umstellen den Eintrag entfernen und neu
anlegen. Bearbeiten (Name, Kopplung, Häkchen) ist jederzeit möglich; Kennung und Token bleiben erhalten.

## Schritt 3: Karte auf dem Kiosk-Dashboard

Hochkant (**480×800**, Standard, Abschnitte offen):

```yaml
type: custom:water-leak-guard-card
```

Quer (**800×480**): ruhig passt die Karte nur eingeklappt unter die Leiste:

```yaml
type: custom:water-leak-guard-card
collapsed: true
```

Ansicht im Panel-Modus (zwei Spalten, wenn die Karte mindestens ca. 600 px breit ist):

```yaml
views:
  - title: Wasser
    path: wasser
    type: panel
    cards:
      - type: custom:water-leak-guard-card
```

Höhen der **ruhigen** Karte (je nach Schrift ±15 px; gemessen mit simuliertem Home Assistant):
eingeklappt (`collapsed: true`) ca. **335 px**; offen etwa **500–550 px**. Hochkant (ca. 744 px
unter der 56-px-Leiste) passt die offene Karte; quer (ca. 420 px) nur die eingeklappte. Ein Alarm
braucht mehr Platz (ca. 750–900 px); der Alarmkasten steht oben, der Rest wird gescrollt.

Layout: Spalten im Masonry-Layout und Abschnitte sind in Home Assistant höchstens **ca. 500 px**
breit, die Karte ist dort einspaltig. Mehr dazu: [Dashboard-Karte](Dashboard-Karte#layout).

## Schritt 4: Automation, die das Display aufweckt

Das Dashboard mit der Karte ist schon die Startseite des Kiosks. Dann genügt es, das Display bei einem
Alarm **einzuschalten**. **Empfohlen:**

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

**Optional**, nur wenn der Kiosk sonst eine andere Seite zeigt: zusätzlich die Seiten-URL setzen.

```yaml
  - action: text.set_value
    target:
      entity_id: text.touchkio_flur_page_url          # Platzhalter: Seiten-URL von TouchKio
    data:
      # Platzhalter: gleiche Basis-URL wie TouchKios web_url, nur der Pfad deines Dashboards
      value: "http://192.168.1.20:8123/wasser"
```

> **Gleicher Ursprung:** Verwende **dasselbe Schema, denselben Host und denselben Port** wie die
> Start-URL von TouchKio (`web_url`); nur der Pfad darf abweichen. Ein anderer Host (IP statt Hostname
> oder umgekehrt) ist für den Browser ein anderer Ursprung **ohne gespeicherte Anmeldung**; dann lädt
> das Dashboard bzw. die Karte nicht.

## Was das Display im Alarm kann

| Aktion | Wanddisplay |
|---|---|
| Stummschalten | **nie** (Knopf fehlt, es gibt keine Benachrichtigung) |
| Global quittieren | wenn „Globales Quittieren erlauben“ gesetzt ist; nie „Nur zuhause möglich“ |
| Externes Leck zurücksetzen | wenn „Externen Reset erlauben“ gesetzt ist; nur über die Karte, nicht über Benachrichtigungsaktion oder Dienst |
| Erkennung abschalten (Slow Leak, Low Flow) und Bypass starten (High Flow) im Alarm | **immer angeboten**, weil das Display als gekoppelt und zuhause gilt; mit Rückfrage; beendet den laufenden Alarm samt Absperranforderung |
| Burst Leak | **nicht** abschaltbar und nicht per Bypass zu unterdrücken |

Quittieren stoppt nur Benachrichtigungen; es beendet weder Erkennung noch Alarm noch
Absperranforderung ([Alarmstufen und Quittierung](Alarmstufen-und-Quittierung)).

## Fehlerbehebung

- **Karte zeigt „Konfigurationsfehler“:** Meist hat die Seite das Kartenmodul nicht rechtzeitig
  bekommen (Start von Home Assistant). Seite neu laden. Die Integration legt dafür unter *Einstellungen →
  Dashboards → ⋮ → Ressourcen* den Eintrag „water-leak-guard-card loader“ an; **nicht löschen**. Details:
  [Troubleshooting der Karte](https://github.com/BeGiBue/home-assistant-water-leak-detection/blob/main/docs/TROUBLESHOOTING.md).
- **Karte fehlt nach dem Update:** Home Assistant neu starten, auf dem Kiosk **hart neu laden** bzw.
  den Browser-Cache leeren; in der Companion App den Frontend-Cache zurücksetzen. Prüfe, ob der Eintrag
  „water-leak-guard-card loader“ vorhanden ist (nicht im YAML-Ressourcenmodus).
- **Display reagiert nicht auf die Automation:** Entity-ID des Display-Lichts unter *Geräte → TouchKio*
  prüfen (die Beispiele sind Platzhalter), TouchKio-MQTT-Verbindung prüfen, die Automation im Verlauf
  ansehen. Bei der Seiten-URL: gleiche Basis-URL wie `web_url` (siehe oben).
- **Karte zeigt „nur Anzeige“ oder keine Aktionen (Kopplung „🔑 Anmeldung“):** Das Kiosk-Gerät hat sich
  neu angemeldet. Die Kopplung erneuern: *Wanddisplay bearbeiten → Kopplung des Displays* neu wählen.
- **Reparaturhinweis „Sicherheitszustand muss wiederhergestellt werden“ (`.corrupt`):** Der
  Laufzeitspeicher war beschädigt; Alarme bleiben konservativ erhalten, Quittieren und Reset sind
  gesperrt. Vorgehen: [Persistenz und Betrieb](Persistenz-und-Betrieb) und die Beschreibung der
  Reparatur in Home Assistant.

## Sicherheit und Grenzen

- Bei Kopplung an den **Benutzer** zählt jede Anmeldung dieses Benutzers als das Display, auch aus der
  Ferne mit dem Passwort. Deshalb ein **starkes, einmaliges Passwort**, **kein Admin**, kein
  Besitzer.
- **Physischer Zugriff:** Wer am Display steht, hat dessen Rechte (Quittieren, je nach Häkchen Reset,
  im Alarm Erkennung abschalten oder Bypass). Nur freigeben, was für alle im Haus in Ordnung ist.
- Das Backend begrenzt die **Karte**, nicht Home Assistant: **Entitäten und Dienste** bleiben dort
  unbeschränkt; der Kiosk-Benutzer kann in Home Assistant tun, was seine Benutzerrechte erlauben
  (nicht-Admin schränkt das ein, ersetzt aber keine Dashboard-Absicherung).
- Nicht getestet: echte Raspberry-Pi-/TouchKio-Hardware, Browser Mod, Töne auf dem Display.

Weiter: [Dashboard-Karte](Dashboard-Karte) · [Installation und Konfiguration](Installation-und-Konfiguration) ·
[Alarmstufen und Quittierung](Alarmstufen-und-Quittierung).
