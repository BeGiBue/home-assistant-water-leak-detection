# Projektüberblick

> **Stand: 15. Oktober 2026 – stabiler Release 2.0.0.** Historische Versions-/Korrekturrunden bleiben als solche bezeichnet. F02, F08 und F04 V3 sind implementiert; externe Lecksensoren werden unterstützt (F04-FSR-H01 in 2.0.0 behoben, siehe [F04 V3](F04-V3)).


## Identität

| Eigenschaft | Wert |
|---|---|
| Deutscher Name | **Wasserwächter** |
| Englischer Name | **Water Leak Guard** |
| Technische Domain | `water_leak_detection` |
| Plattform | Home Assistant |
| Integrationstyp | Service-Integration |
| Aktueller Release | 2.0.0 (stabil) |
| Repository | `BeGiBue/homeassistant-water-leak-detection` |
| Fokus | Backend-Integration |
| Sprache | folgt der in Home Assistant eingestellten Sprache; Deutsch und Englisch enthalten |

## Problemstellung

Ein einzelner Grenzwert reicht für eine brauchbare Wasserleck-Erkennung nicht aus.

Ein Durchfluss von 7 L/h ist in einem Haushalt klein, kann über Stunden aber eindeutig auf einen dauerhaften Verlust hindeuten. Ein Durchfluss von 600 L/h kann beim Duschen oder Befüllen einer Badewanne normal sein, über lange Zeit aber auffällig werden. Ein plötzlicher Sprung auf mehrere Tausend Liter pro Stunde ist wiederum eine völlig andere Gefahrenklasse.

Der Wasserwächter behandelt diese Fälle daher **nicht als einen Alarm mit vier Schwellen**, sondern als vier unabhängige Zustandsautomaten mit eigenen Regeln.

## Primäre Messquellen

### Erforderlich: Durchfluss

Es wird ein Durchflusssensor benötigt.

Intern wird jeder unterstützte Wert auf **Liter pro Stunde (L/h)** normiert.

Unterstützte typische Einheiten sind unter anderem:

- L/h
- L/min
- L/s
- m³/h
- m³/min
- m³/s

### Optional: kumulierter Gesamtverbrauch

Ein Gesamtverbrauchssensor ist optional, aber empfohlen.

Intern wird dieser Wert auf **Liter** normiert.

Er verbessert insbesondere:

- Ereignisvolumen
- High-Flow-Mengenbewertung
- Ereignisstatistik

Ist kein Gesamtverbrauch verfügbar, kann die Integration Volumen aus Durchfluss und Zeit abschätzen.

## Referenzinstallation

Die Entwicklung wurde unter anderem für eine typische Hausinstallation mit folgenden Referenzwerten ausgelegt:

- Hausanschluss etwa **DN25 / 1"**
- statischer Druck etwa **3,5 bar**
- Durchflusssensor mit effektiver Auflösung etwa **1 L/h**

Diese Werte sind **keine Voraussetzung**. Rohrdurchmesser und Druck können in den Experteneinstellungen angepasst werden.

## Funktionsblöcke

Der Wasserwächter besteht funktional aus sechs Schichten:

1. **Messwerterfassung und Normalisierung**
2. **Leckage-Zustandsautomaten**
3. **Adaptives Lernmodell**
4. **Hydraulische Plausibilisierung**
5. **Alarmierung und Quittierung**
6. **Water-Shut-Off-Anforderung**

## Leitprinzipien

### Erkennung ist nicht Quittierung

Wenn ein Benutzer einen Alarm gesehen hat, ist das physische Wasserproblem nicht automatisch verschwunden.

Darum beeinflusst eine Quittierung nicht den Detektor.

### Water Shut Off ist nicht Alarmstatus

Eine Absperranforderung ist eine eigene Sicherheitsentscheidung.

Sie kann aktiv bleiben, obwohl eine Benachrichtigung quittiert wurde.

### Burst hat Vorrang

Ein Burst Leak darf nicht durch den High-Flow-Bypass unterdrückt werden.

### Lernen darf Gefahren nicht normalisieren

Verdächtige High-/Burst-Situationen und High-Flow-Bypass-Zeiten werden nicht als normales Nutzungsverhalten in das Lernmodell aufgenommen.

### Unbekannt ist nicht Null

Ein nicht verfügbarer Durchflusssensor wird niemals als 0 L/h interpretiert.

Dadurch kann ein Sensorausfall keinen aktiven Alarm künstlich „wegresetten“.

## Detektorpriorität

Wenn mehrere Detektoren gleichzeitig aktiv sind, bestimmt die höchste aktive Klasse den sichtbaren Gesamtstatus:

`Slow Leak < Low Flow < High Flow < Burst Leak`

Die niedrigeren Detektoren dürfen intern weiter aktiv bleiben. Das ist wichtig, weil ihre physische Ursache durch einen höher priorisierten Wasserverbrauch nicht zwingend verschwunden ist.

## Versionsentwicklung

### 0.1 – Kern

- Messquellen
- Slow / Low / High / Burst
- Entitäten und Events
- High-Flow-Bypass
- Water-Shut-Off-Request
- Persistenz

### 0.2 – Benachrichtigungen

- mehrere Companion-Empfänger
- persönliche Stummschaltung
- globale Quittierung
- Home-Zone-Autorisierung
- stationäre Home-Geräte
- erneute Alarmierung bei Heimkehr

### 0.3 – Adaptives Modell

- kontinuierliches Lernmodell
- Confidence-Stufen
- Kurz-/Langzeitreferenzen
- hydraulische Plausibilisierung
- statische High- und adaptive Burst-Grenzen
- Burst-Erkennung über schnellen Durchflussanstieg

## Betriebsstand 2.0.0

**2.0.0** (15. Oktober 2026) ist der stabile Stand: hydraulische Erkennung (Slow, Low, High, Burst),
Benachrichtigungen, die mitgelieferte [Dashboard-Karte](Dashboard-Karte) 0.6.2 mit Gerätekopplung und
Wanddisplay sowie **externe Lecksensoren**. Die frühere Beta-Einschränkung auf Installationen ohne
externe Sensoren entfällt, weil F04-FSR-H01 in 2.0.0 behoben ist ([Details](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/F04_FSR_H01.md)).
Die Integration betätigt selbst kein Ventil. Nicht auf jeder echten Hardware geprüft.
[Release Notes](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/RELEASE_NOTES_2.0.0.md).

Die folgenden Abschnitte „Betriebsstand Beta.3“ und „Betriebsstand 2.0.0-beta.1“ sind historisch.

## Betriebsstand Beta.3 (historisch)

PR #15 liefert Logo/Bildmaterial und eine vorbereitete manuelle Lovelace-Karte
0.1.0; PR #16 behebt die verzögerte erste MQTT-Messung; PR #17 ergänzt
**Hydraulische Überwachung**. Die Zustände Aktiv / Warte auf Messung / Gesperrt
sind von Alarmen unabhängig. Gesperrt bleibt als nutzbarer Sensorzustand sichtbar;
bestehende ACTIVE-Ereignisse und Shutoff-Beiträge bleiben erhalten.
[Entitäten](Home-Assistant-Schnittstellen) · [Diagnose](Troubleshooting).

Die Beta war auf hydraulische Erkennung/Benachrichtigungen ohne konfigurierte
externe Sensoren oder gespeicherte externe Alarmdatensätze beschränkt. F04-FSR-H01
(beschädigte gespeicherte Daten konfigurierter externer Melder) ist in 2.0.0 behoben ([Details](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/F04_FSR_H01.md)). Softwaretests und der am 14. Oktober 2026
vom Benutzer bestätigte erfolgreiche Hydrus-Neustart mit Beta.3 sind getrennte
Nachweise; der Einzeltest belegt nicht sämtliche Ausfall-/Neustartszenarien. [Beta-Chronologie](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/BETA_1.2.0.md).
[Kartendokumentation](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/CARD.md).

## Betriebsstand 2.0.0-beta.1 (historisch)

Die [Dashboard-Karte](Dashboard-Karte) wird seit 2.0.0-beta.1 mit der Integration geladen. Sie zeigt Alarm und
hydraulische Überwachung getrennt und bietet gekoppelten Geräten Stummschalten, globale Quittierung und
externen Reset an, jeweils nur wenn das Backend es erlaubt. Erkennung, Alarm- und Absperrlogik sind
unverändert. Der Beta-Umfang blieb damals ohne externe Lecksensoren.
