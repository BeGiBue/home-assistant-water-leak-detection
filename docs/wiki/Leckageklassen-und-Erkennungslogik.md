# Leckageklassen und Erkennungslogik

Diese Seite dokumentiert zwei Dinge gemeinsam:

1. **fachliche Definition** – was bedeutet Slow Leak, Low Flow, High Flow bzw. Burst Leak?
2. **technische Entscheidung** – wie und warum wird genau diese Klasse erkannt?

Die vier Klassen sind **keine vier Stufen eines einzigen Schwellwertalarms**. Jede Klasse besitzt einen eigenen Zustandsautomaten.

---

# 1. Slow Leak

## Definition

Ein **Slow Leak** ist ein sehr kleiner, aber dauerhaft vorhandener Wasserverlust.

Typische Beispiele:

- undichter WC-Spülkasten
- kleines dauerhaftes Rohrleck
- tropfende oder leicht undichte Armatur
- kleine Undichtigkeit an einem Anschluss

Entscheidend ist nicht die Menge pro Minute, sondern die **Kontinuität**.

## Standardwerte

| Parameter | Standard |
|---|---:|
| Startgrenze | 3 L/h |
| oberes Slow-Band | unter 150 L/h |
| Erkennungszeit | 60 Minuten |
| Resetgrenze | unter 3 L/h |
| Resetzeit | 10 Minuten |

## Erkennungsentscheidung

Ein Slow-Leak-Kandidat startet nur bei:

`3 L/h <= Durchfluss < 150 L/h`

und wird erst nach **60 Minuten kontinuierlich in diesem Band** aktiv.

### Warum ein eigenes Band?

Ein großer normaler Verbrauch – Dusche, Waschmaschine, Badewanne – soll nicht als Beweis für einen kleinen Dauerverlust zählen.

Darum wird eine noch unbestätigte Slow-Leak-Messphase verworfen, wenn:

- der Durchfluss unter 3 L/h sinkt oder
- der Durchfluss auf 150 L/h oder mehr steigt

## Warum bleibt ein bestätigter Slow Leak bei höherem Verbrauch stehen?

Weil ein zusätzlicher großer Verbrauch den kleinen Verlust nicht beweisbar beendet.

Beispiel:

- WC-Spülkasten verliert dauerhaft 7 L/h
- Slow Leak wird bestätigt
- anschließend duscht jemand mit 500 L/h

Der Duschverbrauch macht den WC-Verlust nicht dicht.

Darum gilt für einen **aktiven** Slow Leak:

> Nur mindestens 10 Minuten unter 3 L/h beenden den Alarm.

Ein höherer Verbrauch löscht ihn nicht.

## Ein-/Ausschaltbarkeit

Slow Leak besitzt einen eigenen Home-Assistant-Schalter.

Wird die Erkennung deaktiviert, wird nur dieser Detektor zurückgesetzt. Burst und die übrigen Detektoren bleiben unabhängig.

---

# 2. Low Flow

## Definition

**Low Flow** steht für einen moderaten, grundsätzlich plausiblen Wasserverbrauch, der **ungewöhnlich lange** anhält.

Leitbeispiel:

> Ein Wasserhahn wurde vergessen.

Low Flow ist ausdrücklich **nicht** dasselbe wie Slow Leak.

## Standardwerte

| Parameter | Standard |
|---|---:|
| Startgrenze | 150 L/h |
| oberes Low-Band | unter statischer High-Basis von 600 L/h |
| Erkennungszeit | 60 Minuten |
| Ruhegrenze | unter 20 L/h |
| Resetzeit | 3 Minuten |

## Erkennungsentscheidung

Ein Low-Flow-Kandidat beginnt im Bereich:

`150 L/h <= Durchfluss < 600 L/h`

Er wird aktiv, wenn dieser Nutzungskontext **60 Minuten** bestehen bleibt.

Kurze Schwankungen unterhalb der Startgrenze löschen die Beobachtung nicht sofort.

Stattdessen wird eine Ruhephase benötigt:

`Durchfluss < 20 L/h für 3 Minuten`

## Warum nicht bei jedem kurzen Abfall zurücksetzen?

Haushaltsverbrauch ist nicht perfekt konstant.

Mehrere aufeinanderfolgende Duschen oder kurze Unterbrechungen an einem Wasserhahn sollen den Zeitkontext nicht ständig auf Null setzen.

Die 3-minütige Ruhephase bedeutet sinngemäß:

> Der relevante Verbrauch ist tatsächlich beendet.

## Stabilitätserkennung (F08)

Low Flow hat zwei Aktivierungswege im Band **150 L/h ≤ Durchfluss < statische High-Schwelle** (standardmäßig 600 L/h):

- **Lang anhaltender Low Flow:** Der normale 60-Minuten-Pfad bleibt das Sicherheitsnetz, auch bei wechselndem Verbrauch.
- **Besonders gleichmäßiger Low Flow:** Standardmäßig aktiviert; Früherkennung nach 30 Minuten zusammenhängender bestätigter Low-Evidenz, wenn das letzte 15-Minuten-Fenster stabil ist.

Gleichmäßigkeit ist ein zusätzlicher Hinweis auf einen offenen Wasserhahn, aber **keine Voraussetzung für Low-Flow-Erkennung**. Referenz ist der zeitgewichtete Median M. Die Toleranz beträgt `max(20 L/h, 0,10 × M)`. Mindestens 90 % der bestätigten Fensterzeit müssen innerhalb `M ± Toleranz` liegen. Median und Anteil werden nach bestätigter Intervalldauer gewichtet, nicht nach Anzahl der Reports. Das älteste Intervall wird an der Fenstergrenze anteilig gekürzt. Wie in F05 gehört die bestätigte Intervallzeit zum aktuellen gültigen Report; der erste Report einer neuen Kette liefert null Sekunden. Häufigere Reports erhalten kein zusätzliches Gewicht; die Abtastrate begrenzt weiterhin, welche tatsächlichen Schwankungen sichtbar sind.

Jede echte Messung unter der Low-Schwelle löscht die Stabilitätsserie sofort, auch im Bereich 20–149 L/h und bei kurzen Ruhepausen. 15 Minuten stabil, 30 Sekunden Pause und weitere 15 Minuten stabil ergeben daher keinen Frühalarm. Der normale Low-Fortschritt folgt weiter seinen bestehenden Regeln. Erst **3 Minuten bestätigte Ruhe unter 20 L/h** setzen Low vollständig zurück: bei 179 Sekunden noch nicht, bei 180 Sekunden schon. Explizit gespeicherte Resetzeiten, etwa 7 Minuten, bleiben erhalten.

High verwirft die Low-Stabilität; die bestehende Low/High-Übernahme bleibt erhalten. Unknown, unavailable und ungültige Werte unterbrechen die Stabilität. Der erste Report nach Rückkehr liefert null Sekunden Evidenz. Round7 erhält den normalen bestätigten Low-Fortschritt beim Ausfall derselben Quelle. Interne Ticks liefern keine Evidenz. Ungleichmäßigkeit beendet kein bereits ACTIVE Low; dafür gilt weiterhin die physische Ruhe-/Resetbedingung. Die Stabilitätshistorie ist flüchtig und wird nach Neustart neu aufgebaut; aktive Ereignisse werden unverändert wiederhergestellt.

## Warum verwendet Low Flow die statische High-Basis?

High Flow darf durch das Lernmodell nach oben angepasst werden.

Low Flow darf dadurch nicht plötzlich bis zu sehr hohen Durchflüssen wachsen. Sonst könnte ein normaler hoher Spitzenverbrauch als „Low Flow“ einsortiert werden.

Darum bleibt die obere Low-Grenze an der **statischen High-Basis** orientiert.

## Warum bleibt ein aktiver Low Flow bei höherem Verbrauch stehen?

Auch hier gilt:

> Ein zusätzlicher höherer Verbrauch beweist nicht, dass der vorherige lang anhaltende Verbrauch beendet wurde.

Ein aktiver Low Flow endet deshalb nur nach der konfigurierten Ruhebedingung:

**3 Minuten unter 20 L/h.**

## Ein-/Ausschaltbarkeit

Low Flow besitzt ebenfalls einen eigenen Home-Assistant-Schalter.

---

# 3. High Flow

## Definition

**High Flow** bedeutet:

> Ein ungewöhnlich hoher und/oder mengenmäßig auffälliger Wasserverbrauch, der noch legitim sein kann.

Typische legitime Ursachen:

- Badewanne füllen
- Gartenbewässerung
- Pool befüllen
- mehrere gleichzeitige Verbraucher

High Flow ist deshalb bewusst **kein sofortiger Leckalarm nur aufgrund einer hohen Zahl**.

## Standardwerte

| Parameter | Standard |
|---|---:|
| statische Startschwelle | 600 L/h |
| Erkennungszeit | 45 Minuten |
| Mengengrenze | 500 L |
| Ruhegrenze | unter 100 L/h |
| Resetzeit | 5 Minuten |

## Statische High-Flow-Schwelle

Die konfigurierte Experten-Schwelle beträgt standardmäßig 600 L/h.
Lernen, manuelles Maximum und Hydraulik erhöhen sie nicht.
Low endet exakt darunter; High beginnt exakt an der Schwelle.

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



Details: [Adaptives Lernen und Hydraulik](Adaptives-Lernen-und-Hydraulik)

## Erkennungsentscheidung

Sobald der Durchfluss die **effektive High-Grenze** erreicht, startet `monitoring`.

High Flow wird aktiv, wenn **eine** der beiden Bedingungen erfüllt ist:

- Dauer >= 45 Minuten **oder**
- Ereignisvolumen >= 500 L

## Warum Dauer ODER Volumen?

Ein sehr hoher Verbrauch kann bereits in relativ kurzer Zeit eine auffällige Menge erzeugen.

Umgekehrt kann ein etwas niedrigerer High-Flow-Verbrauch vor allem durch seine lange Dauer verdächtig werden.

Die Kombination verhindert, dass nur ein einzelner Aspekt bewertet wird.

## High-Flow-Bypass

High Flow ist die einzige Klasse mit bewusst vorgesehenem Bypass.

Ein aktiver Bypass setzt High Flow auf `idle` und unterdrückt ihn für die Bypassdauer.

Grund:

> Es gibt geplante hohe Verbräuche, die dem Benutzer bekannt sind.

Der Bypass hat eine automatische Ablaufzeit.

**Burst Leak wird davon niemals unterdrückt.**

## Warum bleibt High Flow sonst stehen?

Ein aktiver High Flow endet regulär erst, wenn:

**5 Minuten unter 100 L/h**

gemessen wurden.

Ein bloßes Unterschreiten der statischen High-Grenze reicht nicht. Der Verbrauch soll eindeutig in einen ruhigen Bereich zurückgekehrt sein.

---

# 4. Burst Leak

## Definition

**Burst Leak** steht für einen massiven oder sehr schnell einsetzenden Wasserverlust.

Typische Beispiele:

- Rohrbruch
- geplatzter Flexschlauch
- abgerissene Leitung
- große offene Leckstelle

Burst Leak ist die höchste Gefahrenklasse.

## Standardwerte

| Parameter | Standard |
|---|---:|
| absolute Basisgrenze | 3500 L/h (neue/nicht gesetzte Konfiguration) |
| absolute Bestätigung | 30 Sekunden |
| schneller Anstieg | +1000 L/h normiert auf 10 s |
| Rapid-Rise-Bestätigung | 10 Sekunden |
| Resetgrenze | unter 500 L/h |
| Resetzeit | 60 Sekunden |
| adaptiver Faktor | 1,80 × Normalreferenz |

## Zwei Erkennungswege

### Absolute Burst-Erkennung

Wenn der Durchfluss die effektive Burst-Grenze überschreitet, startet ein Kandidat.

Bleibt der Wert für **30 Sekunden** ausreichend hoch, wird Burst Leak aktiv.

### Dynamische Burst-Erkennung

Ein Rohrbruch kann besonders dadurch auffallen, dass der Durchfluss sehr schnell ansteigt.

Die Engine berechnet den positiven Durchflussanstieg normiert auf 10 Sekunden.

Standard:

`Anstieg >= 1000 L/h je 10 s`

Zusätzlich muss der aktuelle Durchfluss mindestens die **effektive Burst-Grenze**
erreichen. Rapid Rise beschleunigt nur diesen Burst-Kandidaten und beginnt seine
10 Sekunden bestätigter Evidenz erst am qualifizierenden Report. Die frühere
gültige Frist gewinnt; keine Rückdatierung oder Verlängerung der normalen Frist.
Echte Evidenzlücken und relevante Optionsänderungen verwerfen unbestätigtes
Monitoring. Bereits ACTIVE bleibt an den bestehenden physischen Reset gekoppelt.

## Warum absolute UND dynamische Erkennung?

Ein Burst kann zwei unterschiedliche Signaturen haben:

- sofort extrem hoher Durchfluss
- sehr schneller, ungewöhnlicher Sprung, der noch unter der absoluten Grenze liegt

Nur die absolute Grenze würde die zweite Klasse unnötig spät erkennen.

## Warum ignoriert Burst den High-Flow-Bypass?

Der Bypass ist für **bekannten legitimen hohen Verbrauch** gedacht.

Ein Rohrbruch muss auch während Poolbefüllung oder Bewässerung erkannt werden können.

Deshalb existiert in der Burst-Auswertung kein High-Flow-Bypass.

## Warum bleibt Burst stehen?

Burst endet erst bei:

**60 Sekunden unter 500 L/h.**

Ein kurzer Einbruch reicht nicht.

Bei dieser Gefahrenklasse soll das System erst dann Entwarnung geben, wenn über eine zusammenhängende Zeit ein deutlich niedriger Durchfluss vorliegt.

---

# 5. Gemeinsame Zustandslogik

Jeder Detektor besitzt:

- `idle`
- `monitoring`
- `active`

Erst `active` erzeugt ein Leckereignis mit Event-ID.

## Priorität

Wenn mehrere Detektoren aktiv sind:

`Slow Leak < Low Flow < High Flow < Burst Leak`

Die höchste aktive Klasse bestimmt den Gesamtstatus.

Niedrigere aktive Klassen können intern weiterlaufen.

---

# 6. Resetbedingungen im direkten Vergleich

| Klasse | Wird aktiv durch | Bleibt aktiv bis |
|---|---|---|
| Slow Leak | 3–<150 L/h für 60 min | <3 L/h für 10 min |
| Low Flow | 150–<600 L/h, Zeitkontext 60 min | <20 L/h für 3 min |
| High Flow | effektive High-Grenze + 45 min **oder** 500 L | <100 L/h für 5 min oder bewusster High-Bypass |
| Burst Leak | absolute Grenze 30 s **oder** Rapid Rise 10 s | <500 L/h für 60 s |

Diese Resetbedingungen sind der zentrale Grund, warum ein quittierter Alarm weiterhin als aktiv angezeigt werden kann.
