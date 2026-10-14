# Wasserwächter – Projekt-Wiki

**Wasserwächter** (englisch: **Water Leak Guard**) ist eine Home-Assistant-Custom-Integration zur Erkennung auffälliger Wasserverbräuche und möglicher Leckagen.

Diese Repository-Wiki-Quellen dokumentieren den veröffentlichten Stand **1.2.0-beta.3** vom 14. Oktober 2026. Die Aktualisierung der Quellen veröffentlicht das GitHub-Wiki nicht automatisch. F02, F08 und F04 V3 sind implementiert; der eingeschränkte Beta-Einsatz und vom Benutzer bestätigte Neustarttest sind unter [Entwicklung und Release](Entwicklung-und-Release) beschrieben.

> **Wichtig:** Die technische Domain bleibt `water_leak_detection`. Der sichtbare Name ist auf Deutsch **Wasserwächter**.

## Ziel des Projekts

Der Wasserwächter soll aus einem vorhandenen Durchflusssensor erkennen, ob ein Wasserverbrauch noch zu normalem Haushaltsverhalten passt oder ob ein mögliches Leck bzw. ein gefährlicher Wasserverlust vorliegt.

Dabei werden vier unterschiedliche Situationen bewusst getrennt behandelt:

1. **Slow Leak** – sehr kleiner, kontinuierlicher Verlust
2. **Low Flow** – moderater Durchfluss, der ungewöhnlich lange anhält
3. **High Flow** – ungewöhnlich hoher, aber möglicherweise legitimer Verbrauch
4. **Burst Leak** – massiver bzw. sehr plötzlich einsetzender Wasserverlust

Die Integration trennt außerdem strikt zwischen:

- **Erkennung** – was ist physisch noch aktiv?
- **Alarmierung** – wer soll informiert werden?
- **Quittierung** – wer hat den Alarm gesehen bzw. für wen soll er verstummen?
- **Water Shut Off** – soll eine externe Absperrung angefordert werden?

Diese Trennung ist eine der wichtigsten Sicherheitsentscheidungen des Projekts.

## Wiki-Navigation

### Einstieg und Architektur

- [Projektüberblick](Projektueberblick)
- [Architektur und Datenfluss](Architektur)
- [Installation und Konfiguration](Installation-und-Konfiguration)

### Erkennung und Sicherheitslogik

- [Leckageklassen und Erkennungslogik](Leckageklassen-und-Erkennungslogik)
- [Alarmstufen und Quittierung](Alarmstufen-und-Quittierung)
- [Water Shut Off](Water-Shut-Off)
- [Adaptives Lernen und Hydraulik](Adaptives-Lernen-und-Hydraulik)
- [Designentscheidungen und Sicherheitsinvarianten](Designentscheidungen)

### Home Assistant

- [Entitäten, Aktionen und Events – einschließlich hydraulischer Überwachung](Home-Assistant-Schnittstellen)
- [Persistenz und Neustartverhalten](Persistenz-und-Betrieb)
- [Fehlerbilder und Troubleshooting – Warten/Gesperrt](Troubleshooting)

### Entwicklung

- [Entwicklung, Tests und Release](Entwicklung-und-Release)

## Die fünf zentralen fachlichen Fragen

Dieses Wiki beantwortet insbesondere:

### A) Was bedeutet welche Leckageklasse?

Die fachliche Definition der vier Klassen ist unter [Leckageklassen und Erkennungslogik](Leckageklassen-und-Erkennungslogik) dokumentiert.

### B) Wie wird entschieden, wie eine Leckage erkannt wird?

Für jede Klasse sind Messbereich, Zeitbedingungen, Resetbedingungen und die Begründung der gewählten Logik dokumentiert.

### C) Welche Alarmstufen gibt es und wie funktionieren Quittierungen?

Siehe [Alarmstufen und Quittierung](Alarmstufen-und-Quittierung). Dort werden persönliche Stummschaltung, globale Quittierung, Home-Zone-Prüfung und Rückkehr-nach-Hause-Verhalten erklärt.

### D) Wie funktioniert Water Shut Off?

Siehe [Water Shut Off](Water-Shut-Off). Der Shut-Off-Request ist bewusst **nicht** mit einer Quittierung gekoppelt.

### E) Warum bleibt welcher Alarm stehen?

Jede aktive Erkennung endet nur durch ihre **physische Resetbedingung**. Eine Quittierung beendet niemals die Erkennung. Die konkreten Gründe und Resetbedingungen stehen sowohl bei den einzelnen Leckageklassen als auch unter [Designentscheidungen](Designentscheidungen).

## Sicherheitsgrundsatz

Der Wasserwächter ist ein Erkennungs- und Entscheidungsbackend. Er kann das Risiko eines unbemerkten Wasserverlusts reduzieren, garantiert aber keine Schadensvermeidung.

Automatische physische Ventilsteuerung erfolgt derzeit nicht direkt durch die Integration. Stattdessen stellt sie eine unabhängige **Absperranforderung** bereit, die in Home Assistant gezielt mit einer bestehenden Ventil- oder Schaltentität automatisiert werden kann.

- [F04 V3: Burst, Langzeitlernen, Migration und externe Sensoren](F04-V3.md)

## Alarm und Überwachung getrennt beurteilen

**Hydraulische Überwachung** zeigt Aktiv, Warte auf Messung oder Gesperrt. „Kein
Alarm“ beweist keine funktionierende Messfreigabe; Gesperrt beendet keinen bereits
ACTIVE bestätigten Alarm. [Sensor und Attribute](Home-Assistant-Schnittstellen).
Die optionale [Lovelace-Karte 0.1.0](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/CARD.md) ist vorbereitet und manuell
zu registrieren; ihre vorgeschlagenen ACK-/Clear-WebSocket-Befehle fehlen im Backend.
Am 14. Oktober 2026 bestätigte der Benutzer einen erfolgreichen Hydrus-Neustart
mit installierter Beta.3: kein Fehlalarm/Repair, 11 Sekunden Gesperrt, anschließend
automatisch Aktiv und `verified_original_measurement`. Kein Codex-Hardwaretest
und keine garantierte Startdauer. [Befund und Grenzen](Persistenz-und-Betrieb#vom-benutzer-bestätigter-hydrus-neustarttest).
