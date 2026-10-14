# Persistenz und Neustartverhalten

> **Standhinweis:** Veröffentlichte Basis ist **1.0.3**. Aussagen zur statischen High-Flow-Schwelle (F02) beschreiben den Branch `feature/f02-static-high-flow` und sind noch **nicht Bestandteil von 1.0.3**.


## Ziel

Ein Home-Assistant-Neustart darf einen aktiven Wasserfehler nicht stillschweigend in einen unkritischen Ausgangszustand verwandeln.

Gleichzeitig dürfen unsichere, unvollständige Beobachtungen nicht nach einem Neustart als sichere Evidenz weitergerechnet werden.

---

# 1. Persistenter Store

Jeder Config Entry verwendet einen eigenen Home-Assistant-Store.

Schlüssel sinngemäß:

`water_leak_detection.runtime.<entry_id>`

Gespeichert werden unter anderem:

- Detection-Engine-Runtime
- High-Flow-Bypass-Endzeit
- Quittierungszustände
- zugelassene Lernwerte

---

# 2. Aktive Detektoren

Bestätigte `active`-Zustände werden persistiert.

Dazu gehören unter anderem:

- Phase
- Startzeit
- Erkennungszeit
- Event-ID
- Volumenbezug
- Reset-/Quiet-Kontext
- Burst-Grund

Damit bleibt ein ernstes Ereignis über einen Neustart erhalten.

---

# 3. Monitoring-Zustände

Die Engine kann Runtime-Zustände speichern, behandelt fehlende Messwerte aber konservativ.

Wenn die Quelle nicht verfügbar ist:

- noch unbestätigte Monitoring-Evidenz wird verworfen
- laufende Quiet-/Resetintervalle werden verworfen

Warum?

> Zeit ohne Messwert darf weder als Leck-Beweis noch als Null-Durchfluss-Beweis zählen.

---

# 4. Aktive Alarme bei Quellenverlust

Bereits bestätigte aktive Ereignisse bleiben aktiv.

Ein unbekannter Sensorzustand darf kein aktives Ereignis zurücksetzen.

Das ist die Konsequenz des Grundsatzes:

**unknown != 0 L/h**

---

# 5. High-Flow-Bypass

Gespeichert wird der absolute Endzeitpunkt.

Nach einem Neustart:

- liegt der Zeitpunkt noch in der Zukunft → Bypass wird wiederhergestellt
- ist er bereits abgelaufen → Bypass bleibt aus

Dadurch kann ein Neustart einen Bypass nicht unbegrenzt verlängern.

---

# 6. Quittierungen

Der Quittierungszustand wird pro Event-ID gespeichert.

Gespeichert werden:

- globale Quittierung
- welches Gerät global quittiert hat
- Zeitpunkt
- persönliche Mutes

Beim physischen Event-Ende wird der Quittierungszustand dieser Event-ID entfernt.

---

# 7. Lernmodell

Persistiert werden ausschließlich bereits zugelassene, abgeschlossene normale Episoden.

Nicht gespeichert wird:

- eine gerade laufende, noch nicht abgeschlossene Lern-Episode

## Warum?

Eine Episode, die direkt vor einem Neustart oder Sensorausfall abbricht, kann nicht zuverlässig als normal bewertet werden.

Darum wird sie verworfen statt nachträglich „fertiggedacht“.

---

# 8. Volumen nach Ausfallzeiten

Wenn kein Gesamtverbrauchssensor zur Verfügung steht, wird Volumen aus Durchfluss und Zeit integriert.

Nach einer großen Zeitlücke wird die rückwirkende Integration begrenzt.

Damit wird nicht angenommen, dass der letzte bekannte Durchfluss während einer beliebig langen HA-Ausfallzeit unverändert weiterlief.

---

# 9. Betriebszustand nach Reload

Bei einem Konfigurations-Reload:

1. alter Manager wird sauber entladen
2. aktueller Store wird gespeichert
3. neuer Manager lädt den Zustand
4. Quellenlistener und 10-Sekunden-Tick werden neu registriert
5. aktuelle Quellen werden sofort neu ausgewertet

---

# 10. Sicherheitsfolgen

Persistenz soll zwei gegensätzliche Fehler vermeiden:

### Falsch negative Entwarnung

Ein aktiver Burst darf nach Neustart nicht einfach verschwinden.

### Falsch positive Evidenz

Ein unvollständig beobachteter Messzeitraum darf nicht als vollständiger Leak- oder Lernbeweis gelten.

Darum sind aktive Events langlebig, unbestätigte Zeitfenster bei fehlender Evidenz dagegen konservativ.

## Korrekturrunde 1 (in 1.0.3 veröffentlicht)

Sicherheitsübergänge werden mit einer festen Frist von 1 s gespeichert; Mess-/Lernupdates
mit 10 s ab dem ersten vorgemerkten Update. Weitere Samples verschieben die Frist nicht.
Event-Loop-Blockaden und Speicherfehler können diese Fristen überschreiten.
Pro Event und Empfänger wird die erfolgreiche Annahme durch den Notify-Service persistiert.
Nicht verfügbare/fehlgeschlagene Dienste werden erneut versucht; Quittierungen bleiben wirksam.
Ein Absturz zwischen Versand und Speicherung kann eine doppelte Meldung verursachen.

Negative, nicht endliche und überalterte Messungen sind keine Ruhe-Evidenz.
`last_reported` unterscheidet neue identische Meldungen von eingefrorenen Zuständen;
der Standard ist jetzt automatische Meldekadenz (Option 0, Details im README). Laufzeitintervalle
verwenden eine monotone Uhr; Neustarts setzen unbestätigte Intervalle zurück.
Zählerreset, unplausibler Sprung und Quellenwechsel lösen den alten Volumenbezug.
Aktive Leckage und Absperranforderung bleiben dabei erhalten. Eingefrorene oder fehlende
Totalwerte werden durch Durchflussintegration ersetzt. Die fachlichen Findings
Auf dem Branch `feature/f02-static-high-flow` ist F02 fachlich geschlossen; diese Änderung ist noch nicht Bestandteil von 1.0.3. F04/F08 und die Rapid-Rise-Definition bleiben für eine separate Spezifikation offen.

## Korrekturrunde 2 (in 1.0.3 veröffentlicht)

Interne Ticks bestätigen weder Detektions- noch Quiet-Intervalle. Neue Meldungen
werden unabhängig von UTC-Rückstellungen nach State-Identität/Meldung erkannt.
Einzelne eingefrorene Werte können deshalb keinen Timer allein bestätigen.
Der historische Kadenz-Anlauf aus Runde 2 wurde in Runde 6 entfernt;
der aktuelle Mess-Evidenz-Vertrag steht unten. Die Engine-Zeitachse und laufende Bypass-Dauer sind monoton.
Beim Speichern wird die UTC-Bypassfrist aus der verbleibenden Laufzeit neu projiziert.
Persistierte aktive Laufzeit zählt Offline-Zeit nicht als bestätigte Laufzeit.

Zählerfortschritt nutzt einen gemeinsamen Referenzzeitraum über mehrere Flow-Reports;
keine feste 1-Liter-Auflösung wird angenommen. Noch nicht unterstützte positive
Sprünge bleiben vorgemerkt; eingefrorene Totals blockieren Flow-Integration nicht.

Notify-Aufgaben sind pro Event/Empfänger isoliert. Ein normaler Service-Return bedeutet
HA-Annahme, keine bestätigte Telefonzustellung. Laufende Calls werden nicht nach
5 Sekunden als fehlgeschlagen abgebrochen und erneut gesendet. Beim Unload unterbrochene
bereits laufende Übergaben sind unklar und werden nicht automatisch wiederholt.
Beschädigte Runtime-Felder löschen ein anhand verbleibender Bestätigungsdaten
klar erkennbares aktives Ereignis nicht. Unbestätigtes Monitoring bleibt verwerfbar.


## Korrekturrunde 3 (in 1.0.3 veröffentlicht)

Die historische Kadenzqualifikation aus Runde 3 wurde in Runde 6 entfernt.
Interne Ticks zählen weiterhin weder Leak- noch Ruhezeit.

Steuerungsänderungen werden vor der Frischeprüfung angewendet. Deaktivieren von
Slow/Low und Einschalten des High-Flow-Bypass greifen sofort nach den bestehenden
Regeln; Burst bleibt unabhängig. Bypass-Ende erzeugt aus einem alten State kein Event.

Ein verworfener Totalwert braucht für erneute Akzeptanz einen neuen Totalreport
oder echten Wertfortschritt. Bloßes Flow-Aufholen bestätigt einen eingefrorenen
Zählersprung nicht. Quantisierte Fortschritte behalten ungenutzte Flow-Evidenz.
Der Mengenvergleich enthält keinen pauschalen Faktor 1,5 mehr.

Notify-Status und laufende Aufgaben beziehen sich auf Event, Empfänger-ID und den
konkret verwendeten Notify-Service. Ein unterbrochener alter Service sperrt keinen
neu konfigurierten Versandweg. Event-Ende cancelt und erwartet nur dessen lokale
Aufgaben. Bereits an HA übergebene Calls können weiterhin nicht zurückgerufen werden.

Alle vier Klassen restaurieren bestätigte Sicherheitsereignisse nach derselben
Regel. `reason` ist optional. Neue Stores enthalten redundant `confirmed_active`;
Altdaten bleiben lesbar. Aktionsunsichere Event-IDs werden ersetzt, ohne eine alte
Quittierung zu übernehmen. Fehlen in Altdaten sämtliche Bestätigungsinformationen,
kann daraus kein bestätigtes Ereignis erfunden werden.

Lern-Episoden messen Laufzeit monoton. Persistierte Lern-Samples erhalten dagegen
die echte UTC des Abschlusses; das Rolling Window arbeitet ebenfalls mit realer UTC.
Wiki-Dateien dieser Runde werden nur lokal gepflegt, nicht veröffentlicht.


## Korrekturrunde 6: deterministische Mess-Evidenz (in 1.0.3 veröffentlicht)

Die Integration bewertet frische gültige Messmeldungen. Sie versucht im
Automatikbetrieb nicht mehr, die Meldekadenz statistisch zu erraten. Erst der
zweite Report bestätigt das abgeschlossene Intervall; während des Wartens erzeugen
Ticks immer null Sekunden Evidenz. Bestätigte Monitoring-Zeit wird akkumuliert.

„Maximal anrechenbarer Abstand zwischen zwei Messwertmeldungen“ ist optional:
0 bedeutet keine künstliche Grenze. Bei einer positiven Grenze zählt Gleichheit;
eine größere Lücke fügt null Sekunden hinzu und löscht keinen bisherigen Fortschritt.
Weitere normale Intervalle zählen sofort wieder. Fachliche Resetregeln bleiben erhalten.

Beobachtetes unknown/unavailable oder ein ungültiger Flow unterbricht die Messkette
und erzeugt weder Leak- noch Ruhe-Evidenz. Unbestätigte Monitoring-/Quiet-Fenster
werden nach den bestehenden Ausfallregeln verworfen; aktive Leaks bleiben aktiv.
Der erste gültige Report danach startet mit null Evidenz eine neue Messkette.

Ohne explizite Max-Gap-Einstellung lassen sich eine legitime langsame Meldekadenz
und ein stiller Kommunikationsausfall zwischen zwei gültigen Reports nicht
unterscheiden. Ein späterer gültiger Report kann daher ein langes Intervall bestätigen.
Die Grenze wird niemals automatisch aus Reportmustern abgeleitet.

## F04 V3 Upgrade

Der aktuelle Feature-Stand verwendet HA-Store-/Learning-Schema 2 mit atomarer
Legacy-Learning-Quarantäne. ACTIVE, ACK und Shutoff bleiben erhalten. Externe
Lifecycles, generationsgebundene Nonces und getrennte Lernkanäle sind beschrieben
in [F04 V3](F04-V3.md). Ein fehlgeschlagener Reset-Schreibvorgang gibt keinen
Sicherheitsbeitrag frei. Die frühere F04-Roadmap bleibt historischer Kontext.
