# Designentscheidungen und Sicherheitsinvarianten

Diese Seite dokumentiert die wichtigsten Architekturentscheidungen des Wasserwächters und deren Begründung.

Sie ist bewusst nicht nur eine Beschreibung des aktuellen Codes, sondern ein **Entscheidungsprotokoll**.

Änderungen an diesen Punkten sollten als bewusste Produkt-/Sicherheitsentscheidung behandelt werden.

---

# 1. Vier getrennte Detektoren statt eines universellen Grenzwerts

## Entscheidung

Slow Leak, Low Flow, High Flow und Burst Leak besitzen getrennte Zustandsautomaten.

## Begründung

Die physikalischen Muster unterscheiden sich fundamental:

- klein + dauerhaft
- moderat + ungewöhnlich lange
- hoch + potenziell legitim
- extrem / sehr schnell ansteigend

Ein einziger Schwellwert mit verschiedenen Severity-Stufen würde diese Semantik nicht ausreichend abbilden.

---

# 2. Slow und Low besitzen statische fachliche Bänder

## Entscheidung

Das adaptive Lernmodell verändert nicht die grundlegenden Slow-/Low-Grenzen.

## Begründung

Ein gelerntes hohes Haushaltsmaximum darf nicht dazu führen, dass ein sehr hoher Verbrauch plötzlich als Low Flow interpretiert wird.

Adaptive Haushaltsnormalität ist vor allem für Burst relevant.

---

# 3. Ein bestätigter Slow Leak wird nicht durch höheren Verbrauch gelöscht

## Entscheidung

Nach Aktivierung endet Slow Leak nur durch ausreichend lange Unterschreitung seiner Resetgrenze.

## Begründung

Ein zusätzlicher Verbraucher beseitigt die kleine Leckage nicht.

Hoher Verbrauch ist kein Beweis für Reparatur.

---

# 4. Low Flow braucht echte Ruhe

## Entscheidung

Kurze Durchflussabfälle resetten Low Flow nicht sofort.

## Begründung

Normale Haushaltssituationen besitzen Unterbrechungen.

Erst eine zusammenhängende Ruhephase zeigt zuverlässig, dass die relevante Nutzung beendet ist.

---

# 5. High Flow ist verdächtig, aber nicht automatisch ein Leck

## Entscheidung

High Flow kombiniert Schwelle mit Dauer bzw. Volumen und besitzt einen Bypass.

## Begründung

Sehr hoher Wasserverbrauch kann geplant und legitim sein.

Ein sofortiger Alarm allein durch 600 L/h würde zu unnötigen Fehlalarmen führen.

---

# 6. Burst ist von High Flow unabhängig

## Entscheidung

Burst besitzt eine eigene absolute und dynamische Erkennung.

## Begründung

Ein Rohrbruch ist eine andere Risikoklasse als „lange viel Wasser“.

Er muss auch dann erkannt werden, wenn High Flow absichtlich unterdrückt ist.

---

# 7. High-Flow-Bypass darf Burst niemals unterdrücken

## Entscheidung

Burst kennt den High-Flow-Bypass nicht.

## Begründung

Beispiel Poolbefüllung:

Hoher Grundverbrauch ist erlaubt, aber ein gleichzeitig platzender Schlauch muss weiterhin erkannt werden.

Diese Regel ist eine Sicherheitsinvariante.

---

# 8. Bypass läuft automatisch ab

## Entscheidung

High-Flow-Bypass besitzt immer eine zeitliche Endbedingung.

## Begründung

Ein vergessener permanenter Bypass würde die Schutzwirkung dauerhaft reduzieren.

---

# 9. Detection, Alarmierung, Quittierung und Shut Off sind getrennt

## Entscheidung

Vier getrennte Konzepte:

1. physische Erkennung
2. Benachrichtigung
3. Quittierung
4. Absperranforderung

## Begründung

„Ich habe die Meldung gesehen“ ist nicht dasselbe wie „das Wasserproblem ist beendet“.

Diese Trennung verhindert, dass UI-Aktionen physische Sicherheitszustände versehentlich löschen.

---

# 10. Quittierung löscht keinen Detektor

## Entscheidung

Personal Mute und globale Quittierung verändern keine Detector-Phase.

## Begründung

Der Sensorzustand entscheidet, wann ein Ereignis beendet ist.

Der Benutzer entscheidet nur über Alarmkommunikation.

---

# 11. Quittierung löscht keinen Water-Shut-Off-Request

## Entscheidung

Shut Off wird ausschließlich aus aktiven Detektoren und ihrer Mapping-Konfiguration berechnet.

## Begründung

Eine Benachrichtigungsaktion darf keine sicherheitskritische Absperrentscheidung zurücknehmen.

---

# 12. Alarme bleiben bis zur physischen Resetbedingung stehen

## Entscheidung

Jeder Detektor besitzt eine eigene Resetbedingung.

| Detektor | Reset |
|---|---|
| Slow | <3 L/h für 10 min |
| Low | <20 L/h für 3 min |
| High | <100 L/h für 5 min |
| Burst | <500 L/h für 60 s |

High Flow kann zusätzlich bewusst per High-Flow-Bypass beendet/unterdrückt werden.

## Begründung

Ein einzelner kurzer Messwert unterhalb einer Schwelle ist keine ausreichende Entwarnung.

Je gefährlicher die Klasse, desto klarer muss die Entwarnung sein.

---

# 13. Unknown / unavailable ist niemals Null

## Entscheidung

Fehlende Sensorwerte werden nicht als 0 L/h behandelt.

## Begründung

Sonst könnte ein Sensorausfall:

- aktive Alarme resetten
- Quiet-Zeiten erfüllen
- falsche Lernwerte erzeugen

Unbekannte Evidenz bleibt unbekannt.

---

# 14. Monitoring darf bei Quellenverlust nicht weiterlaufen

## Entscheidung

Noch unbestätigte Monitoring-Zeit wird bei Quellenverlust verworfen.

## Begründung

Ohne Messwert darf keine Detektionszeit gesammelt werden.

Aktive Ereignisse bleiben dagegen bestehen.

---

# 15. Event-ID pro physischem Ereignis

## Entscheidung

Jede bestätigte Aktivierung erhält eine neue eindeutige Event-ID.

## Begründung

Quittierungen müssen an ein konkretes Ereignis gebunden sein.

Ein neuer Vorfall darf nicht wegen einer alten Quittierung stumm bleiben.

---

# 16. Quittierung ist gerätebezogen

## Entscheidung

Empfänger sind konkrete Companion-Geräte mit eigenem Token und Tracker.

## Begründung

Eine Person kann mehrere Geräte besitzen; ein gemeinsames Tablet kann von mehreren Personen verwendet werden.

Gerätekontext ist für die Reaktion zuverlässiger als nur `person.*`.

---

# 17. Globale Quittierung nur bei Home-Kontext

## Entscheidung

Ein globales Acknowledge wird im Backend nur akzeptiert, wenn der zugeordnete Tracker `home` meldet.

## Begründung

Globales Quittieren soll eine stärkere Aussage sein als „Push unterwegs gelesen“.

Die Berechtigung wird im Backend geprüft; der UI-Button allein reicht nicht.

---

# 18. Heimkehr erzeugt neue Aufmerksamkeit

## Entscheidung

Kehrt ein Empfänger bei aktivem, nicht global quittiertem Ereignis nach Hause zurück, wird er erneut benachrichtigt und ein persönlicher Mute wird gelöscht.

## Begründung

Die Relevanz eines Wasserproblems ändert sich deutlich, sobald der Benutzer wieder vor Ort ist.

---

# 19. Lernen ist kontinuierlich

## Entscheidung

Kein einmaliges Kalibrierungsfenster, sondern Rolling Window.

## Begründung

Haushaltsverhalten ist saisonal und verändert sich langfristig.

---

# 20. Verdächtige Ereignisse dürfen sich nicht selbst normalisieren

## Entscheidung

High-/Burst-Verdacht, aktive Alarme und Bypass-Episoden werden aus dem normalen Lernen ausgeschlossen.

## Begründung

Ein Schutzsystem darf seine Alarmgrenze nicht nach oben verschieben, weil es wiederholt gefährliche Zustände gesehen hat.

---

# 21. Niedrige Learning Confidence darf Schutz nicht verschlechtern

## Entscheidung

`insufficient` hebt High-/Burst-Grenzen nicht an.

`learning` wirkt nur gedämpft.

## Begründung

Wenige Daten dürfen kein starkes Vertrauen vortäuschen.

---

# 22. Hydraulik ist Plausibilitätsgrenze, keine Wahrheit

## Entscheidung

Rohrdurchmesser und statischer Druck begrenzen adaptive Schwellen, definieren aber kein exaktes physisches Maximum.

## Begründung

Reale Flüsse hängen von vielen nicht bekannten Installationsparametern ab.

---

# 23. Water Shut Off ist ein Backend-Request, keine harte Aktorkopplung

## Entscheidung

Die Integration gibt einen Request aus; die reale Ventilautomation ist extern.

## Begründung

- unterschiedliche Hardware
- explizites Opt-in
- testbare Trennung von Erkennung und Aktorik
- keine versteckte physische Aktion

---

# 24. Home-Assistant-native Mechanismen bevorzugen

## Entscheidung

Config Flow, Options Flow, Entitäten, Events, Aktionen und Companion-Mechanismen werden nativ verwendet.

## Begründung

Die Integration soll ohne spezielle Frontend-Karte vollständig funktionsfähig bleiben.

---

# 25. Deutsche UI folgt der HA-Sprache

## Entscheidung

Deutsch wird nicht hart als globale Sprache erzwungen.

Home Assistant entscheidet anhand seiner konfigurierten Sprache.

## Begründung

Das entspricht dem HA-Übersetzungsmodell und erlaubt gleichzeitig vollständige deutsche Nutzung und englischen Fallback.

---

# 26. Zusammenfassung der nicht verhandelbaren Regeln

1. Burst unabhängig von High.
2. High-Bypass unterdrückt Burst niemals.
3. Erkennung, Benachrichtigung, Quittierung und Shut Off bleiben getrennt.
4. Quittierung bedeutet nicht „Leck beendet“.
5. Shut Off ist unabhängig vom Acknowledge.
6. Slow und Low können optional Shut Off anfordern.
7. Globale Quittierung wird backendseitig autorisiert.
8. Away-Gerät kann nur sich selbst stummschalten.
9. Home-Gerät kann bei Berechtigung global quittieren.
10. Heimkehr kann erneut alarmieren.
11. Lernen ist kontinuierlich.
12. Verdächtige Ereignisse werden nicht automatisch normal.
13. Integration funktioniert vollständig ohne Custom Card.
14. Unknown wird niemals als Null interpretiert.

## F04 V3: ausdrücklich begrenzte Ergänzungen

Die oben beschriebenen physischen Resetbedingungen bleiben für hydraulische
Detektoren bindend. Externe Quellen ergänzen einen ausdrücklich autorisierten,
Home-gebundenen External Reset mit persistierendem WAITING bis OFF; normales ACK
ist weiterhin ausschließlich eine Benachrichtigungsaktion. Quellenersatz darf
keinen fremden Lifecycle, keine Event-ID und keinen Reset-Nonce übernehmen.
High-Peaks werden getrennt im Langzeitkanal bestätigt und wirken ausschließlich
über Faktor 1,20; das heuristische hydraulische Ceiling begrenzt diesen Kanal
nicht. Die konfigurierte Burst-Basis bleibt stets der feste Aufnahmeanker.
Seit 2.0.0 (erstmals in 1.2.0-beta.1) ersetzt F04 V3 frühere F04-Entwürfe;
[der aktuelle V3-Vertrag](F04-V3.md) hat Vorrang.
