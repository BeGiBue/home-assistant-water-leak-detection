# Adaptives Lernen und Hydraulik

> **Standhinweis:** Veröffentlichte Basis ist **1.0.3**. Aussagen zur statischen High-Flow-Schwelle (F02) beschreiben den Branch `feature/f02-static-high-flow` und sind noch **nicht Bestandteil von 1.0.3**.


## Ziel

Haushalte unterscheiden sich stark.

High Flow beginnt immer an der konfigurierten statischen Schwelle
(Standard 600 L/h). Dauer und Volumen bestätigen den Alarm.

Für Burst kombiniert der Wasserwächter feste Basisgrenzen, kontinuierliches
Lernen, ein optional manuell bekanntes Maximum und hydraulische
Plausibilitätsgrenzen. Das Lernmodell beeinflusst **Burst Leak**, nicht die
High-Flow-Startschwelle. Slow Leak und Low Flow bleiben fachlich statisch.

---

# 1. Was wird gelernt?

Es werden nicht einzelne Sekundenwerte als „normal“ gespeichert.

Stattdessen lernt das System **abgeschlossene normale Wasserverbrauchsepisoden**.

Eine Episode:

- beginnt ab etwa 1 L/h
- verfolgt ihren maximalen Durchfluss
- gilt erst nach 120 Sekunden sehr niedrigen Durchflusses als abgeschlossen

Erst dann kann ihr Peak als Lernwert aufgenommen werden.

---

# 2. Was wird nicht gelernt?

Eine Episode wird ausgeschlossen, sobald sie als verdächtig gilt.

Insbesondere ausgeschlossen:

- aktiver Leckalarm
- High-Flow-Monitoring im allgemeinen Lernpfad
- Burst-Leak-Monitoring
- Zeit mit aktivem High-Flow-Bypass

## Warum auch High/Burst-Monitoring im allgemeinen Lernpfad?

Das Lernmodell darf nicht warten, bis ein außergewöhnlicher Wert schon zum bestätigten Alarm geworden ist.

Sonst könnte bereits ein einzelnes knapp vor der Bestätigung endendes gefährliches Ereignis als „normal“ gespeichert werden. Nur der separate Mehrfachbestätigungspfad darf saubere High-Episoden nachträglich zulassen.

## Wiederholt bestätigte normale High-Episoden

High bleibt **statisch**: standardmäßig 600 L/h, ACTIVE nach 45 Minuten **oder** 500 Litern, Reset nach 5 Minuten strikt unter 100 L/h. Lernen verändert keine dieser Grenzen. Es kann ausschließlich die bestehende adaptive Normalreferenz für Burst beeinflussen.

Der allgemeine Lernpfad schließt High-MONITORING weiterhin aus. Ein separater Bestätigungspfad verfolgt den Peak ab High IDLE → MONITORING und speichert erst beim normalen physischen MONITORING → IDLE einen abgeschlossenen Kandidaten. Eine einzelne Episode, etwa 750 L/h für 12 Minuten, reicht nicht. Auch zwei Episoden beeinflussen die normale Lernreferenz noch nicht.

Mindestens **drei** ähnliche saubere Episoden müssen innerhalb des bestehenden `learning_window_days` liegen, standardmäßig **30 Tage**. Für jeden bestätigenden Cluster gilt exakt und symmetrisch: `max_peak <= min_peak × 1,15`. Die 15-%-Grenze zählt mit. 750/780/800 sowie 700/800/805 passen zusammen; 650/850/1400 nicht. Sortierte, gegebenenfalls überlappende gültige Bänder werden deterministisch bewertet, ohne reihenfolgeabhängiges Aufbrauchen von Kandidaten.

Beim dritten passenden Kandidaten werden bisher unbestätigte Mitglieder höchstens einmal als normale LearningSamples aufgenommen. Ihre **ursprünglichen Abschlusszeitpunkte** bleiben erhalten. Bereits bestätigte High-Episoden können einen vierten Kandidaten sofort bestätigen, wenn weiterhin mindestens drei passende Episoden einschließlich des neuen Kandidaten im Fenster liegen. Gelernt wird nur der Peak, keine Dauer, Litergrenze oder Resetzeit. P95, kurze/lange Referenz, saisonale Gewichtung und bestehende Confidence bleiben unverändert. Drei High-Episoden umgehen INSUFFICIENT nicht. Bei ausreichender Confidence wirken bestätigte Peaks über Normalreferenz, Burst-Multiplikator und hydraulische Obergrenze auf Burst; High bleibt statisch.

Bypass-Episoden werden niemals gelernt. High ACTIVE, jeder andere aktive Leckagealarm sowie Burst MONITORING/ACTIVE einschließlich eines später verworfenen Rapid-Rise-Kandidaten schließen die Episode dauerhaft aus. Dasselbe gilt für unknown/unavailable, ungültige Werte, echte ausgeschlossene Evidenzlücken, Source-Rebind und Neustart. Die bestehende Engine-Entscheidung einschließlich der absoluten 2-µs-Rundungstoleranz wird wiederverwendet; explizite Null-Evidenz bleibt null. Das Abbrechen eines Bypass während fortgesetzten hohen Verbrauchs macht diesen nicht lernfähig. Nach Ablehnung muss die konfigurierte physische High-Ruhebedingung erfüllt werden. Nach jedem Startup oder Restore bleibt High-Lernen bis zur vollständig durch gültige Reports bestätigten, konfigurierten High-Ruhebedingung gesperrt. Ein kurzer Nullfluss oder ein Report unter High hebt die Sperre nicht auf; Ausfälle und echte Evidenzlücken unterbrechen den Ruhefortschritt.

Laufende Kandidaten und Ablehnungs-/Ruhetracking werden nicht persistiert. Abgeschlossene Pending-Kandidaten und bestätigte High-Historie werden getrennt mit Timestamp und Peak gespeichert. Optionale Felder benötigen keine neue Storage-Version. Beide Listen verwenden denselben F15-Kontext mit begrenzten, exakt gebundenen Rücksprungberechtigungen; Promotion verschiebt keine Zeitstempel und erzeugt keine Duplikate. Alte Stores liefern leere High-Historien. Ungültige Einträge werden ignoriert; die Bestätigungshistorie ist auf die neuesten 4096 gültigen, deduplizierten Einträge im Lernfenster begrenzt. Die chronologische Auswahl erfolgt erst nach vollständiger Validierung und Sample-Konsistenzprüfung. Unsortierte Eingaben sowie abgelaufene oder ungültige Präfixe verdrängen keine aktuellen Einträge.

Normale Samples und beide High-Historien altern gemeinsam im konfigurierten Fenster aus, auch nach Verkleinerung und Restore. Alte Winterwerte verlieren so automatisch ihre Bestätigungswirkung, ohne Monats- oder Saisonregeln. `reset_learning` löscht alle drei Historien, laufendes Tracking und zugehörigen Rollback-Kontext. Quellenwechsel neutralisieren Lernen wie bisher. Es entstehen keine neuen Optionen oder Entities; drei Bestätigungen und 15 % bleiben interne Konstanten.


## Warum Bypass-Zeiten nicht lernen?

Poolbefüllung ist ein gutes Beispiel.

Der Benutzer sagt mit dem Bypass:

> Dieser hohe Verbrauch ist gerade bewusst erlaubt.

Er sagt nicht:

> Dieser Verbrauch soll künftig die normale Haushaltsgrenze definieren.

Darum ist Bypass-Verbrauch kein Lernmaterial.

---

# 3. Rolling Window

Standard:

**30 Tage**

Zulässiger Expertenbereich:

typischerweise 7–90 Tage.

Alte Lernwerte außerhalb des Fensters werden entfernt.

Dadurch passt sich das Modell kontinuierlich an saisonale oder dauerhafte Verhaltensänderungen an.

---

# 4. Kurz- und Langzeitreferenz

Aus den zugelassenen Episoden werden robuste 95%-Referenzen berechnet.

### Langzeit

95. Perzentil des gesamten aktuellen Lernfensters.

### Kurzzeit

95. Perzentil der letzten bis zu 7 Tage.

### Kombinierte Lernreferenz

Wenn beide vorhanden sind:

`0,65 × Kurzzeit + 0,35 × Langzeit`

Zusätzlich darf die kombinierte Referenz nicht unter:

`0,85 × Langzeit`

fallen.

## Begründung

Die Kurzzeitreferenz sorgt für Anpassungsfähigkeit.

Die Langzeitreferenz verhindert, dass wenige ruhige Tage die Erwartung zu schnell absenken.

---

# 5. Confidence

Das Lernmodell zeigt offen, wie vertrauenswürdig seine Datenbasis ist.

## Insufficient

Wenn:

- weniger als 5 Lernwerte oder
- weniger als 3 abgedeckte Tage

Dann darf das gelernte Maximum die Schutzgrenzen **nicht nach oben anheben**.

## Learning

Ab ausreichender Mindestdatenbasis, aber noch nicht zuverlässig.

Voraussetzung für Reliable ist noch nicht erfüllt.

In dieser Phase fließt nur:

`85 % des gelernten Maximums`

in die Normalreferenz ein.

## Reliable

Bei mindestens:

- 20 Lernwerten und
- ausreichend abgedeckten Tagen

Die erforderlichen Tage entsprechen:

`min(14; max(7; Lernfenster / 2))`

Dann darf die vollständige gelernte Referenz verwendet werden.

---

# 6. Manuell bekanntes Maximum

Optional kann ein manuell bekanntes normales Maximum angegeben werden.

Ist es > 0, wird es unabhängig vom Lernstatus als Referenz berücksichtigt.

Die Normalreferenz ist dann das Maximum aus:

- manuellem Wert
- confidence-gewichteter Lernreferenz

---

# 7. Statische High-Grenze

Standard: **600 L/h**, in Expertenoptionen konfigurierbar.
High beginnt exakt hier mit MONITORING; Low endet strikt darunter.
Lernen, manuelles Maximum und Hydraulik erhöhen High nicht.
Dauer, Volumen, Quiet/Reset und Bypass bleiben unverändert.
High-MONITORING bleibt im allgemeinen Lernpfad ausgeschlossen. Der separate
Bestätigungspfad für normale High-Episoden verändert F02 nicht. Bypass und
Alarmepisoden bleiben stets vom Lernen ausgeschlossen.

---

# 8. Adaptive Burst-Grenze

Basis:

**2000 L/h**

Kandidat:

`max(Basis; Normalreferenz × 1,80)`

Zusätzlich gilt:

- hydraulische Obergrenze
- Burst soll nach Möglichkeit mindestens 10 % oberhalb der effektiven High-Grenze liegen

---

# 9. Hydraulisches Plausibilitätsmodell

Eingaben:

- Nennweite / Rohrdurchmesser
- statischer Druck

Referenzstandard:

- DN25
- 3,5 bar

Das Modell berechnet aus Querschnitt und einer druckskalierten praxisnahen Fließgeschwindigkeit einen Referenzdurchfluss.

Die Geschwindigkeit wird bewusst begrenzt.

## Ganz wichtig

Diese Berechnung ist **kein exaktes physikalisches Maximum**.

Der tatsächliche Durchfluss hängt zusätzlich ab von:

- Wasserzähler
- Druckminderer
- dynamischem Druck
- Rohrlänge
- Bögen und Armaturen
- Hausnetz
- vorgelagertem Versorgungsnetz

Deshalb heißt die Funktion bewusst **Plausibilitätsmodell**.

---

# 10. Warum eine hydraulische Obergrenze?

Ein rein selbstlernendes System könnte sich theoretisch durch wiederholt hohe Verbräuche immer unempfindlicher machen.

Die hydraulische Hülle verhindert:

> „Sehr hoch wurde oft gesehen, also muss noch viel höher erst gefährlich sein.“

Die statische High-Grenze dient als High-Referenz für den Dynamic Burst Floor.

---

# 11. Sensoren für Transparenz

Home Assistant zeigt unter anderem:

- Gelernter Maximaldurchfluss
- Lernzuverlässigkeit
- Lernabdeckung
- Hydraulischer Referenzdurchfluss
- High-Flow-Schwelle
- Effektive Burst-Leak-Grenze

Das adaptive Verhalten soll dadurch nachvollziehbar bleiben und keine Blackbox sein.

---

# 12. Lernmodell zurücksetzen

Aktion:

`water_leak_detection.reset_learning`

Sie löscht zugelassene Lernwerte.

Nicht zurückgesetzt werden dadurch:

- aktive Leckereignisse
- Detector-Einstellungen
- aktuelle physische Alarmbedingungen

Ein Reset des Lernmodells ist keine Alarmquittierung.
