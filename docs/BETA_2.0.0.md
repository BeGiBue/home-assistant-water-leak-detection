# Beta 2.0.0: Dashboard-Karte, Gerätekopplung und Kartenaktionen

**2.0.0-beta.3** ist eine Vorabversion (GitHub-Pre-release). Der zuletzt veröffentlichte stabile Stand bleibt
1.1.0. Eine Veröffentlichung aktualisiert kein laufendes HA: Backup, Download über HACS mit aktivierten
Beta-Versionen und Neustart sind erforderlich. [Upgrade-Schritte](INSTALLATION.md#upgrading-to-200-beta1).

## Neu in 2.0.0-beta.3

| Bereich | Neu in 2.0.0-beta.3 |
|---|---|
| Karte | Karte 0.6.1: Bypass und Lernmodell standardmäßig offen; Option `collapsed: true` für niedrige Bildschirme (z. B. 800×480 quer). |
| Wanddisplay | Neuer Empfängertyp für Wanddisplays (z. B. TouchKio): ohne Push und Tracker, gilt immer als zuhause, kein Stummschalten, Rechte über die Häkchen. Kopplung nur mit eigenem Kiosk-Benutzer (kein Admin/Besitzer, nirgends sonst gekoppelt) oder mit der Kiosk-Anmeldung; Anmeldungen der Companion-App sind ausgeschlossen. |
| Sicherheit | Externer Reset eines Displays nur über die Karte, nicht über Benachrichtigungsaktion oder Dienst; unbekannter Empfängertyp wird gewarnt und nie berechtigt. |
| Symbole | Absperranforderung: `mdi:valve-open` ohne, `mdi:valve-closed` mit Anforderung. |

## Neu in 2.0.0-beta.2

| Bereich | Neu in 2.0.0-beta.2 |
|---|---|
| Layout | Karte 0.5.0: ruhig einspaltig ca. 335 px hoch (iPhone, iPad-Spalte, Raspberry Pi 7″ 800×480); Bypass und Lernmodell einklappbar; Erkennung als 2×2-Raster; zweispaltig ab ca. 600 px Kartenbreite (Panel-Ansicht). |
| Bedienung | Keine Ein/Aus-Schalter mehr auf der Karte. Slow/Low abschalten nur im Alarmkasten während des eigenen Alarms; das und Bypass-Start im High-Flow-Alarm nur für ein gekoppeltes Gerät zuhause. |
| Anzeige | Bei gestörter Messquelle oder beschädigtem Speicher nichts Grünes mehr: „Überwachung eingeschränkt“, Zeile „Eingeschränkt“, Kacheln „Pausiert“. „Unzureichend“ beim Lernmodell nicht mehr grün. Stummschalten nennt den Empfänger. |
| Gerätekopplung | Empfänger koppelbar mit einem HA-**Benutzer** (Standard, übersteht Neuanmeldungen) oder wie bisher mit einer einzelnen **Anmeldung** (hat Vorrang). Bestehende Kopplungen bleiben ohne Migration. |
| Tests | Logiktests der Karte (Node, ohne npm) im Validate-Workflow; weitere Backend-Tests zur Kopplung. |

## Was neu ist in 2.0.0-beta.1

| Bereich | Neu in 2.0.0-beta.1 |
|---|---|
| Auslieferung | Karte 0.4.1 wird mit der Integration installiert und automatisch geladen; keine Ressource, kein Kopieren. |
| Anzeige | Alarmstatus und **Hydraulische Überwachung** getrennt; grün nur bei bestätigt aktiver Überwachung ohne ausgefallenen externen Sensor; ACTIVE-Alarme bleiben immer sichtbar. |
| Bedienung | Rückfrage mit Warnung, bevor Slow/Low-Abschalten oder High-Flow-Bypass einen laufenden Alarm beendet. Burst ist nicht abschaltbar. |
| Gerätekopplung | Empfänger können mit genau einer HA-Anmeldung gekoppelt werden (Feld im Empfängereintrag). Rechte hängen am Gerät, nicht am Benutzer. |
| Kartenaktionen | Stummschalten für dieses Gerät (überall), globale Quittierung (Berechtigung und zuhause), externer Reset (Berechtigung und zuhause, mit Rückfrage). Kein Löschknopf für hydraulische Alarme. Nicht gekoppelte Geräte: nur Anzeige. |
| Backend | WebSocket-Befehle `session`, `mute`, `acknowledge`, `external_reset`; Identität ausschließlich über die gekoppelte Anmeldung; Token und Nonce verlassen nie den Server; Prüfung beim Ausführen durch die bestehenden Validatoren. |

Unverändert: Erkennung, Alarm- und Absperrlogik, Quittierungssemantik (Quittieren und Stummschalten
beenden weder Erkennung noch Alarm noch Absperranforderung), Persistenz, MQTT-Messherkunft,
Entitäts-IDs, Dienste und Events.

## Voraussetzung: weiterhin ohne externe Sensoren

Der Beta-Umfang bleibt wie bei 1.2.0: hydraulische Erkennung mit Benachrichtigung, **ohne
konfigurierte externe Lecksensoren und ohne gespeicherte externe Alarmdatensätze**. F04-FSR-H01
(beschädigte gespeicherte Alarmdaten externer Melder) ist weiterhin offen. Die Reset-Funktion der
Karte für externe Lecks ist daher nur außerhalb dieses Beta-Umfangs relevant.
[Voraussetzungen im Detail](BETA_1.2.0.md#voraussetzung-hydraulischer-einsatz-ohne-externe-sensoren).

## Nachweise

- Vollständige Testsuite des Repositorys, Ruff, JSON-Prüfung, JS-Syntaxprüfung, Hassfest und HACS
  erfolgreich (GitHub Actions).
- Jede Etappe wurde von einer unabhängigen Review-Instanz anhand des Codes geprüft, der Code selbst von
  GitHub geladen, die HA-API gegen den Quellcode von Home Assistant 2026.9.4 und das passende Frontend
  verifiziert. Befunde wurden korrigiert und erneut geprüft.
- Die Karte wurde in Chromium mit simuliertem Home Assistant getestet (Desktop- und Handybreite,
  hell/dunkel, reduzierte Animation).
- **Nicht nachgewiesen:** Betrieb in einer echten HA-Installation, insbesondere Laden der Karte in der
  Companion App auf iOS/iPadOS und Kopplung mit echten Anmeldungen und Device Trackern.

Empfohlene erste Prüfungen nach dem Upgrade:

1. Karte erscheint unter *Karte hinzufügen*; Status und Hydraulische Überwachung stimmen mit den Entitäten.
2. Ein Gerät zuhause koppeln (z. B. iPad) und eines unterwegs (Telefon); im Alarm zeigen beide die
   erwarteten Knöpfe, unterwegs ist „Global quittieren“ gesperrt.
3. Stummschalten über die Karte wirkt nur auf das eigene Gerät; Alarm und Absperranforderung bleiben.

## Bewusst offene Punkte (geringe Auswirkung)

- Stummschalten genau während eines Neuladens kann verloren gehen und trotzdem Erfolg melden.
- Eine Kopplungsänderung während der Übergabe einer Meldung an diesen Empfänger kann diese eine Meldung
  entfallen lassen.
- Ohne sichtbaren Device Tracker sperrt die Karte Zuhause-Knöpfe erst mit der nächsten
  Berechtigungsabfrage; das Backend lehnt bis dahin mit `not_home` ab.
- Ein Speicherfehler beim externen Reset erscheint als „abgelehnt“ statt „nicht gespeichert“.

## Chronologie

| Version | Stand |
|---|---|
| 1.2.0-beta.1 bis beta.3 | Siehe [Beta 1.2.0](BETA_1.2.0.md). |
| 2.0.0-beta.1 | Karte 0.4.1 mit der Integration, Überwachungsanzeige, Gerätekopplung und Kartenaktionen. |
| 2.0.0-beta.2 | Karte 0.5.0: kompaktes Layout ohne Schalter, Alarm beenden nur zuhause, Benutzerkopplung. |
| 2.0.0-beta.3 | Karte 0.6.1 mit offenen Abschnitten, Wanddisplay-Empfänger, Ventil-Symbole. |
