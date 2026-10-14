# Vorbereitung von 1.2.0-beta.1

Diese Vorabversion ist für einen begrenzten privaten Test der hydraulischen
Erkennung gedacht: Slow, Low, High und Burst sowie Benachrichtigung, Mute und ACK.
Sie ist noch nicht veröffentlicht. Die aktuelle Produktversion bleibt 1.1.0.

## Voraussetzung: hydraulischer Einsatz ohne externe Sensoren

F04-FSR-H01 bleibt ein offenes Sicherheitsfinding bei beschädigten gespeicherten
Alarmdaten aktuell eingebundener externer Wassermelder. Externe Sensoren sind
deshalb nicht uneingeschränkt für diese Beta freigegeben.

Vor Installation die bestehende vollständige HA-Konfiguration und Runtime-Datei
sichern. Prüfen, dass keine externen Sensoren konfiguriert sind und die gespeicherten
Listen `external_sources` und `external_alarm_ledger` leer sind. Nicht nur den
angezeigten Hauptalarm prüfen. Vorhandene Datensätze nicht löschen, um diese
Voraussetzung künstlich herzustellen. Bei vorhandenen Zuständen ist dieser
eingeschränkte Beta-Einsatz nicht abgenommen. Gültige Alarme zunächst über ihren
vorgesehenen physischen beziehungsweise autorisierten Weg bearbeiten.

Shutoff ist ein optionales Anforderungssignal; die Integration betätigt kein
Ventil. Für den ersten Haushaltsversuch keine neue Absperrautomation einrichten.
ACK und persönliches Mute wirken ausschließlich auf Benachrichtigungen, nie auf
physische Alarme oder Shutoff. Globales ACK erfordert die aktuelle Berechtigung
und Home-Zone; die vorhandene HA-Quittieroberfläche verwendet dieselben Prüfungen.

## Hydrus, wmbusmeters und MQTT

Geprüft wurde die gelieferte Discovery für `flow_m3h` in m³/h und `total_m3` in m³
vom selben Topic, mit originalem UTC-`timestamp` und `force_update: true` für Flow.
Die Discovery enthält kein `expire_after`. Zwei Originalnullmeldungen mit
116 Sekunden Abstand und eine identische Wiederzustellung wurden über einen
echten TCP-Broker und HA geprüft. Das belegt Strukturkompatibilität, nicht die
vollständige Funk-/Firmwarekampagne.

`force_update: true` ist für die getestete Konfiguration empfohlen und stellt
sicher, dass wiederholte gleiche Flowwerte neue HA-Auswertungen auslösen.
Der Wert muss bei erneuter Veröffentlichung der Add-on-Discovery erhalten bleiben.
Die Integration verändert die wmbusmeters-Konfiguration nicht automatisch.
Ein identischer alter Payload wird dadurch nicht zu neuer physischer Evidenz.

Die Originalmesszeit liefert das bestätigte physische Intervall. Empfangszeit
bleibt für Timeout und Diagnose zuständig. Steigende oder fallende Zustelllatenz
verwirft daher keine Burst-/Quiet-Evidenz mehr. Die 2-µs-Rundungstoleranz bleibt
unverändert. Unknown/unavailable, Replay, Restart und ausdrücklich ausgeschlossene
Intervalle erzeugen weiterhin keine Messzeit. Auch eine ausgeschlossene Lücke der
Originalmesszeiten wird bei konfiguriertem `source_max_age_seconds` verworfen.

Der Default von `source_max_age_seconds` ist 0: keine automatische Cadence-Schätzung.
Ein fehlendes Telegramm ist niemals eine Nullmeldung. Ohne Timeout oder explizite
Unverfügbarkeit kann die Integration eine stille Funkunterbrechung nicht sicher
von einem langen regulären Meldeintervall unterscheiden. Einen passenden Timeout
anhand der tatsächlich beobachteten Intervalle einschließlich Empfangsschwankungen
konfigurieren; nicht unter die normale Cadence setzen. Keine Werte auf Verdacht
aus nur zwei Telegrammen ableiten. Der reale Hydrus-Status
`TEMPORARY_ERROR UNKNOWN_E0` wird hier nicht als unbedenklich oder ungültig erklärt.

## Nach ausdrücklicher Freigabe

1. Beta-Abnahmebericht und den konkreten geprüften Commit bestätigen.
2. Vorbereiteten Versionspatch separat prüfen und anwenden; Manifest, const.py,
   pyproject.toml und Release-Metadaten konsistent auf 1.2.0-beta.1 setzen.
3. Erneut Validate/Hassfest/HACS auf dem endgültigen Versionscommit ausführen.
4. Merge und Veröffentlichung nur mit gesonderter ausdrücklicher Freigabe.
5. GitHub-Release als **prerelease**, **nicht latest** veröffentlichen. Die vorhandene
   Release-Automation setzt diese Kennzeichen bisher nicht automatisch; den
   vorbereiteten Patch zuerst freigeben. Nicht unverändert starten.
6. Im Haushalt Mobilzustellung, Mute/ACK, HA-/Add-on-Restart, echte Ruhe über
   mindestens 180 Sekunden, Empfangslücke und frische Rückkehr protokollieren.

Die Beobachtung der Nullmeldungen 08:31:02/08:32:45 und Alarmende 08:34:57 ist ein
Nutzerbefund. Sie wird nicht als hier selbst ausgeführter Hardwaretest ausgegeben.
