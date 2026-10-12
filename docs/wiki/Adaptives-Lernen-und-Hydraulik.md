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

F04 V3 führt einen getrennten Langzeitkanal ein. High bleibt statisch: 600 L/h,
45 Minuten ODER 500 Liter und fünf Minuten strikt unter 100 L/h als Standard.
Nur vollständig beobachtete, sauber beendete High-MONITORING-Episoden mit Peak
**unter der konfigurierten Burst-Basis** dürfen kandidieren. Drei unabhängige
Episoden mit `max_peak <= min_peak × 1,15` bestätigen das erste Maximum. Jede
spätere Erhöhung benötigt drei **neue** Episoden über dem bisherigen Maximum.
Alte Bestätigungen liefern diese neuen Stimmen nicht. High-Peaks gelangen niemals
in den Rolling-Sample-Pool und wirken nicht zusätzlich über dessen Faktor 1,8.

Pending- und Audit-Historie verfallen nicht zeitlich. Nach Validierung,
Identitätsprüfung, Deduplizierung und deterministischer Sortierung bleiben
höchstens die neuesten 4096 Datensätze insgesamt; das separate bestätigte Maximum
bleibt monoton erhalten. Originalzeitstempel und exakt gebundene F15-Berechtigungen
bleiben erhalten. Bypass, Alarme, Burst/Rapid Rise und Messlücken schließen die
Episode aus. Laufende Episoden bleiben flüchtig. Nach jedem Neustart ist zunächst
die vollständige konfigurierte physische High-Ruhe neu zu bestätigen.
Das Rolling-Modell mit 30-Tage-Fenster, P95 und Confidence bleibt für gewöhnliche
Samples erhalten. Einzelheiten: [F04 V3](F04-V3.md).

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

**3500 L/h**

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
