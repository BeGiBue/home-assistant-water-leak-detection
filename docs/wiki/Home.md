# Wasserwächter – Projekt-Wiki

**Wasserwächter** (englisch: **Water Leak Guard**) ist eine Home-Assistant-Custom-Integration zur Erkennung auffälliger Wasserverbräuche und möglicher Leckagen.

Dieses Wiki basiert auf dem veröffentlichten Stand **1.0.3**. Änderungen zu **F02 (statische High-Flow-Schwelle)** sind auf dem Branch `feature/f02-static-high-flow` fachlich umgesetzt, aber noch **nicht Bestandteil von 1.0.3**. Das Wiki dokumentiert sowohl die Bedienung als auch die technischen und fachlichen Entscheidungen hinter der Erkennung.

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

- [Entitäten, Aktionen und Events](Home-Assistant-Schnittstellen)
- [Persistenz und Neustartverhalten](Persistenz-und-Betrieb)
- [Fehlerbilder und Troubleshooting](Troubleshooting)

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
