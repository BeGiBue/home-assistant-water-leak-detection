# Installation und Konfiguration

## Voraussetzungen

- Home Assistant 2026.9.0 oder neuer
- HACS empfohlen
- mindestens ein kompatibler Durchflusssensor
- optional ein kumulierter Gesamtverbrauchssensor
- für Benachrichtigungen: Home Assistant Companion App mit registriertem `notify.mobile_app_*`-Dienst

## Installation über HACS

Repository:

`https://github.com/BeGiBue/homeassistant-water-leak-detection`

Kategorie:

**Integration**

Nach der Installation:

1. Home Assistant neu starten.
2. **Einstellungen → Geräte & Dienste → Integration hinzufügen** öffnen.
3. Nach **Wasserwächter** suchen.
4. Einrichtung starten.

## Ersteinrichtung

### 1. Messquellen

Es gibt zwei Wege:

- einzelne Entitäten direkt auswählen
- ein Home-Assistant-Gerät auswählen und kompatible Sensoren daraus erkennen lassen

Erforderlich:

- Durchflusssensor

Optional:

- Gesamtverbrauchssensor

### 2. Benachrichtigungsempfänger

Bereits während der Installation können ein oder mehrere Companion-Geräte hinzugefügt werden.

Pro Gerät werden konfiguriert:

- Anzeigename
- `notify.mobile_app_*`
- passender `device_tracker.*`
- Critical-Burst-Alarm ja/nein
- globale Quittierung zuhause erlaubt ja/nein
- stationäres vertrauenswürdiges Home-Gerät ja/nein

Die Einrichtung kann auch ohne Empfänger abgeschlossen werden.

## Konfiguration später wieder öffnen

Die Konfiguration ist **nicht** auf die Installation beschränkt.

Unter:

**Einstellungen → Geräte & Dienste → Integrationen → Wasserwächter → Konfigurieren**

stehen unter anderem folgende Bereiche zur Verfügung:

### Messquellen

- Durchflusssensor ändern
- optionalen Gesamtverbrauch ändern

### Benachrichtigungsempfänger

- hinzufügen
- bearbeiten
- entfernen
- **Zurück zur Konfiguration** führt wieder ins Hauptmenü

Beim Speichern bleibt der Konfigurator geöffnet:

- Hinzufügen, Bearbeiten und Entfernen führen zurück zur Empfängerübersicht.
- Messquellen und Experteneinstellungen führen zurück zur Hauptübersicht.
- Das X oben links beendet den Options-Flow vollständig.

Die Empfängerübersicht zeigt bewusst nur die vergebenen Anzeigenamen. Technische `notify.*`- und `device_tracker.*`-IDs werden dort nicht mehr ausgeschrieben.

### Experteneinstellungen

Hier liegen unter anderem:

- Detektorgrenzen
- Erkennungszeiten
- Resetzeiten
- High-Flow-Bypass
- Lernfenster
- manuell bekanntes Normalmaximum
- Rohrdurchmesser
- statischer Druck
- adaptive Multiplikatoren
- Zuordnung der Detektoren zur Absperranforderung

Home Assistants separate Funktion **Neu konfigurieren** für Messquellen wird zusätzlich unterstützt.

## High-Flow-Bypass

Der High-Flow-Bypass ist für geplante hohe Verbräuche gedacht, z. B.:

- Pool befüllen
- längere Gartenbewässerung
- andere bewusst hohe Wasserentnahme

Er unterdrückt nur **High Flow**.

Er unterdrückt **nicht**:

- Slow Leak
- Low Flow
- Burst Leak

Der Bypass hat immer eine Ablaufzeit und kann nicht versehentlich dauerhaft aktiv bleiben.

## Sprache

Die Integration folgt der Home-Assistant-Sprache.

Bei `de` werden unter anderem deutsch dargestellt:

- Integrationstitel **Wasserwächter**
- Gerätename
- Entitätsnamen
- Zustände
- Konfigurationsdialoge
- Aktionen
- Companion-Pushtexte

Englischer Fallback ist **Water Leak Guard**.

## Wichtiger Hinweis nach Änderungen

Konfigurationsbereiche verwenden die vorhandenen Update-/Reload-Pfade; reine Empfängeränderungen können live erfolgen, ohne laufende Detektionstimer zurückzusetzen.

Bei einer HACS-Aktualisierung sollte Home Assistant vollständig neu gestartet werden, wenn HACS dies anfordert.

## Low-Flow-Stabilität in den Expertenoptionen (F08)

Low Flow hat zwei Aktivierungswege im Band **150 L/h ≤ Durchfluss < statische High-Schwelle** (standardmäßig 600 L/h):

- **Lang anhaltender Low Flow:** Der normale 60-Minuten-Pfad bleibt das Sicherheitsnetz, auch bei wechselndem Verbrauch.
- **Besonders gleichmäßiger Low Flow:** Standardmäßig aktiviert; Früherkennung nach 30 Minuten zusammenhängender bestätigter Low-Evidenz, wenn das letzte 15-Minuten-Fenster stabil ist.

Gleichmäßigkeit ist ein zusätzlicher Hinweis auf einen offenen Wasserhahn, aber **keine Voraussetzung für Low-Flow-Erkennung**. Referenz ist der zeitgewichtete Median M. Die Toleranz beträgt `max(20 L/h, 0,10 × M)`. Mindestens 90 % der bestätigten Fensterzeit müssen innerhalb `M ± Toleranz` liegen. Median und Anteil werden nach bestätigter Intervalldauer gewichtet, nicht nach Anzahl der Reports. Das älteste Intervall wird an der Fenstergrenze anteilig gekürzt. Wie in F05 gehört die bestätigte Intervallzeit zum aktuellen gültigen Report; der erste Report einer neuen Kette liefert null Sekunden. Häufigere Reports erhalten kein zusätzliches Gewicht; die Abtastrate begrenzt weiterhin, welche tatsächlichen Schwankungen sichtbar sind.

Jede echte Messung unter der Low-Schwelle löscht die Stabilitätsserie sofort, auch im Bereich 20–149 L/h und bei kurzen Ruhepausen. 15 Minuten stabil, 30 Sekunden Pause und weitere 15 Minuten stabil ergeben daher keinen Frühalarm. Der normale Low-Fortschritt folgt weiter seinen bestehenden Regeln. Erst **3 Minuten bestätigte Ruhe unter 20 L/h** setzen Low vollständig zurück: bei 179 Sekunden noch nicht, bei 180 Sekunden schon. Explizit gespeicherte Resetzeiten, etwa 7 Minuten, bleiben erhalten.

High verwirft die Low-Stabilität; die bestehende Low/High-Übernahme bleibt erhalten. Unknown, unavailable und ungültige Werte unterbrechen die Stabilität. Der erste Report nach Rückkehr liefert null Sekunden Evidenz. Round7 erhält den normalen bestätigten Low-Fortschritt beim Ausfall derselben Quelle. Interne Ticks liefern keine Evidenz. Ungleichmäßigkeit beendet kein bereits ACTIVE Low; dafür gilt weiterhin die physische Ruhe-/Resetbedingung. Die Stabilitätshistorie ist flüchtig und wird nach Neustart neu aufgebaut; aktive Ereignisse werden unverändert wiederhergestellt.

| Option | Standard |
|---|---|
| `low_stability_enabled` | aktiviert |
| `low_stability_early_minutes` | 30 min |
| `low_stability_window_minutes` | 15 min |
| `low_stability_relative_percent` | 10 % |
| `low_stability_absolute_lph` | 20 L/h |
| `low_stability_required_percent` | 90 % |

Bei aktivierter Stabilität muss das Fenster positiv und höchstens so lang wie die Früherkennung sein; die Früherkennung muss kürzer als die normale Low-Erkennungszeit sein. Bei deaktivierter Stabilität blockiert diese Zeitrelation das Speichern nicht. Gespeicherte Zeiten bleiben erhalten und werden beim Wiedereinschalten wieder geprüft. Toleranzen müssen positiv sein; der Anteil muss größer als 0 und höchstens 100 % sein. Es entstehen keine zusätzlichen HA-Entities.

Nur fehlende Stabilitätszeiten werden für UI und Runtime gemeinsam abgeleitet: `Früherkennung = min(30, normale Low-Zeit / 2)` Minuten; `Fenster = min(15, resultierende Früherkennung / 2)` Minuten. Abgerundet wird auf die UI-Auflösung von 0,1 Minuten, mit einem Minimum von 0,1 Minuten. Eine explizite Früherkennungszeit wird bei einem fehlenden Fenster berücksichtigt; explizit gespeicherte Zeiten werden nie überschrieben. Bei der im UI zulässigen normalen Low-Zeit ab 1 Minute bleiben die abgeleiteten Zeiten gültig.

| Normale Low-Zeit | Fehlender Früherkennungs-Default | Fehlender Fenster-Default |
|---|---:|---:|
| 10 min | 5 min | 2,5 min |
| 20 min | 10 min | 5 min |
| 30 min | 15 min | 7,5 min |
| 60 min | 30 min | 15 min |

## F04 V3 Upgrade und externe Quellen

Wurden die Experteneinstellungen nie gespeichert, gilt jetzt eine Burst-Basis von
3.500 L/h. Ein gespeicherter Wert bleibt erhalten, auch 2.000 L/h, die 1.1.0 beim
Speichern der Optionen abgelegt hat. Bitte prüfen. Prüfe den Sicherheitsabstand zu normalem
Maximalverbrauch. Beim Upgrade werden alte gemeinsame Lerndaten quarantänisiert;
die effektive Burst-Schwelle kann sinken. Ein tatsächlicher Lern-Upgrade erzeugt
einen HA-Repair-Hinweis. ACTIVE-Alarme, ACK, Empfänger und Optionen bleiben erhalten.
Unter Configure können mehrere externe binary_sensor hinzugefügt und verwaltet
werden. Shutoff-Beitrag je Quelle ist standardmäßig true, External-Reset-Recht
je Empfänger false. Einzelheiten zu Migration, Home-Zone und defekten Sensoren:
[F04 V3](F04-V3.md).

## Upgrade auf 2.0.0

**2.0.0** ist der stabile Stand ([Release Notes](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/RELEASE_NOTES_2.0.0.md)). Vorher ein vollständiges HA-Backup inklusive
`.storage/` erstellen (Laufzeitspeicher `.storage/water_leak_detection.runtime.<entry_id>`), in HACS
auf 2.0.0 aktualisieren, HA neu starten und Browser bzw. Companion App neu laden.

- **Von 1.1.0:** Alte Lerndaten werden quarantänisiert (ein Reparaturhinweis erklärt es). Wurden die
  Experteneinstellungen nie gespeichert, gilt jetzt Burst 3.500 L/h. Ein gespeicherter Wert bleibt
  erhalten, auch 2.000 L/h, die 1.1.0 beim Speichern der Optionen abgelegt hat. Bitte prüfen. Die Karte über *Karte hinzufügen →
  Water Leak Guard* einfügen; eine alte manuelle Ressource `/local/water-leak-guard-card.js` entfernen.
- **Von einer 2.0.0-Beta:** Kopplungen, Empfänger und Wanddisplays bleiben erhalten. Externe
  Lecksensoren sind nicht mehr ausgeschlossen (F04-FSR-H01 behoben). Unter *Ressourcen* erscheint der
  Eintrag „water-leak-guard-card loader“; nicht löschen.

Danach `storage_recovery_required` (soll `false` sein) und die Hydraulische Überwachung prüfen.

Die folgenden Upgrade-Abschnitte zu Betas sind historisch.

## Upgrade auf Beta.3 und optionale Karte (historisch)

Die Veröffentlichung von 1.2.0-beta.3 installiert nichts in einem laufenden HA.
Konfiguration und Store sichern, in HACS Beta-/Pre-release-Versionen aktivieren,
Beta.3 herunterladen und HA neu starten. Danach installierte Version und neue
Entität **Hydraulische Überwachung** am Integrationsgerät prüfen. Config Entry und
Runtime-Datei nicht löschen, um eine Sperre zu umgehen.
[Beta-Voraussetzungen](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/BETA_1.2.0.md).

## Upgrade auf 2.0.0-beta.1 und Dashboard-Karte (historisch; Kopplung und Wanddisplay gelten weiter)

Konfiguration und Store sichern, in HACS Beta-Versionen aktivieren, 2.0.0-beta.1 herunterladen und HA
neu starten. Die Karte wird danach automatisch geladen: *Karte hinzufügen → Water Leak Guard*. Eine
früher manuell eingetragene Ressource `/local/water-leak-guard-card.js` und die Datei in `<config>/www/`
entfernen.

Für Alarmaktionen in der Karte beim Empfänger des jeweiligen Geräts die Kopplung wählen:
*Konfigurieren → Benachrichtigungsempfänger → Empfänger bearbeiten → Kopplung für die Dashboard-Karte*.
Standard ist **„👤 Name“** (Benutzer) (jede App-/Browser-Anmeldung dieses HA-Benutzers, übersteht eine
Neuanmeldung; auch ein Laptop-Browser dieses Benutzers erhält die Rechte, „zuhause“ kommt vom Tracker
des Empfängers). **„🔑 Name – App/Browser“** koppelt genau eine Anmeldung und hat Vorrang, z. B. für ein iPad mit
anderen Rechten als das Telefon desselben Benutzers. Das Feld ändert keine andere Einstellung des
Empfängers; bestehende Kopplungen an eine Anmeldung gelten weiter.

Ein fest montiertes **Wanddisplay** (z. B. TouchKio) ohne Companion-App wird unter *Konfigurieren →
Benachrichtigungsempfänger → Wanddisplay hinzufügen* angelegt: Name, Kopplung (Pflicht: ein eigener
Kiosk-Benutzer ohne Adminrechte, den sonst kein Empfänger nutzt, oder die einzelne Anmeldung des
Kiosk-Geräts) und die Häkchen „Globales Quittieren“ und „Externer Reset“. Es
bekommt keine Benachrichtigungen und gilt immer als zuhause. Details:
[Dashboard-Karte – Wanddisplay](Dashboard-Karte#wanddisplay--touchkio); vollständige Anleitung:
[Wanddisplay mit TouchKio](Wanddisplay-TouchKio).
Externe Lecksensoren werden seit 2.0.0 unterstützt (in den Betas ausgeschlossen).
[Dashboard-Karte](Dashboard-Karte) · [Beta 2.0.0](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/BETA_2.0.0.md).
