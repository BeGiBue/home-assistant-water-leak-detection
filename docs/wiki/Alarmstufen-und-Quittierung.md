# Alarmstufen und Quittierung

## Grundsatz

Der Wasserwächter trennt **physische Erkennung** und **menschliche Reaktion**.

Eine Quittierung bedeutet ausschließlich:

> Jemand hat den Alarm gesehen und die weitere Benachrichtigung für diesen Ereigniskontext beeinflusst.

Sie bedeutet **nicht**:

> Die Leckage ist beendet.

Deshalb kann eine Leckage nach einer Quittierung weiterhin aktiv angezeigt werden.

---

# 1. Fachliche Alarmstufen

Die Leckageklassen besitzen folgende fachliche Dringlichkeit:

| Detektor | fachliche Stufe | Charakter |
|---|---|---|
| Slow Leak | Hinweis / Notice | klein, aber dauerhaft |
| Low Flow | Hinweis / Notice | moderat, ungewöhnlich lange |
| High Flow | Warnung / Warning | hoher, möglicherweise legitimer Verbrauch |
| Burst Leak | Kritisch / Critical | akute schwere Leckage |

## Companion-Transportpriorität

Aktuell erhält insbesondere **Burst Leak** bei entsprechend aktiviertem Empfänger einen Critical-Payload:

- iOS: Critical Interruption
- Android: hohe Priorität / Alarm-Stream
- TTL 0
- Priority high

Die fachlichen Stufen sind wichtiger als ein einzelnes plattformspezifisches Notification-Feld.

---

# 2. Ereignisbezogene Quittierung

Jedes bestätigte Leck erhält eine eigene Event-ID.

Quittierungen gehören immer genau zu dieser Event-ID.

Folge:

- Ereignis A wird quittiert.
- Die physische Situation endet.
- Später beginnt ein neues Ereignis B.
- B ist **nicht** automatisch quittiert.

Damit kann eine frühere Quittierung niemals zukünftige Leckagen dauerhaft stummschalten.

---

# 3. Persönliche Stummschaltung

Jeder konfigurierte Benachrichtigungsempfänger kann den aktuellen Alarm für **sein eigenes Gerät** stummschalten.

Wirkung:

- dieses Gerät erhält für die aktuelle Event-ID keine normalen Folgebenachrichtigungen
- andere Geräte bleiben unbeeinflusst

Nicht beeinflusst werden:

- Detektorzustand
- Leckalarm-Entität
- Water-Shut-Off-Request
- andere Empfänger
- zukünftige Event-IDs

## Warum gerätebezogen?

Eine Person kann mehrere Geräte besitzen.

Außerdem kann ein gemeinsames Tablet von mehreren Personen verwendet werden.

Deshalb ist die Reaktion an den konfigurierten Companion-Empfänger gebunden und nicht pauschal an eine `person.*`-Entität.

---

# 4. Globale Quittierung

Eine globale Quittierung unterdrückt weitere normale Alarmbenachrichtigungen für die **aktuelle Event-ID über alle Empfänger**.

Sie beendet trotzdem nicht:

- den Detektor
- das Leckereignis
- den Water-Shut-Off-Request

## Autorisierungsregel

Globale Quittierung ist nur zulässig, wenn:

1. der Empfänger dafür konfiguriert wurde und
2. sein zugeordneter `device_tracker.*` aktuell exakt `home` meldet – oder der Empfänger ein
   **Wanddisplay** ist: Es hat keinen Tracker und gilt immer als zuhause (siehe
   [Dashboard-Karte](Dashboard-Karte#wanddisplay--touchkio)). Ein Wanddisplay bekommt keine
   Benachrichtigungen und kann deshalb auch nicht über eine Benachrichtigung quittieren.

## Zwei Sicherheitsstufen

Die Home-Bedingung wird zweimal berücksichtigt:

### Darstellung

Der Button „Für alle quittieren“ wird nur angeboten, wenn das Gerät aktuell zuhause ist.

### Backend

Beim Empfang der Aktion prüft das Backend den Tracker **erneut**.

Die Sichtbarkeit des Buttons gilt nicht als Autorisierung.

---

# 5. Gerät ist nicht zuhause

Ein Gerät außerhalb der Home-Zone darf:

- für sich selbst stummschalten

Es darf nicht:

- global quittieren

Ein trotzdem eintreffender globaler Quittierungsversuch wird abgelehnt und als eigenes Rejected-Event protokolliert.

## Begründung

Eine globale Quittierung soll sinngemäß ausdrücken:

> Vor Ort ist jemand in einer Position, die Lage zu prüfen bzw. Verantwortung für den aktiven Alarm zu übernehmen.

Ein entferntes Mobilgerät darf diesen Sicherheitsstatus nicht allein setzen.

---

# 6. Stationäres vertrauenswürdiges Home-Gerät

Beispiel:

Ein iPad bleibt dauerhaft im Haus und kann von mehreren Haushaltsmitgliedern verwendet werden.

Es kann als **trusted stationary home device** konfiguriert werden.

Voraussetzungen für globale Quittierung bleiben:

- Empfänger darf global quittieren
- zugehöriger Tracker ist `home`

Der Status dokumentiert, dass dieses Gerät bewusst als gemeinsames Home-Terminal betrachtet wird.

Die Integration versucht nicht zu erraten, welche Person das Tablet gerade hält.

---

# 7. Rückkehr nach Hause

Ein wichtiges Sonderverhalten ist:

`not_home -> home`

Wenn ein konfiguriertes Gerät nach Hause zurückkehrt und:

- das Leckereignis noch aktiv ist
- das Ereignis nicht global quittiert wurde

dann wird das Gerät erneut benachrichtigt.

Dabei wird ein persönlicher Mute dieses Geräts für die aktuelle Event-ID entfernt.

## Warum?

Eine Heimkehr verändert den Sicherheitskontext.

Ein Benutzer kann unterwegs bewusst stummgeschaltet haben. Sobald er zuhause ist, ist die aktive Leckage wieder unmittelbar relevant.

Darum gilt:

> Heimkehr ist ein neuer Aufmerksamkeitspunkt.

---

# 8. Warum bleibt der Alarm trotz Quittierung sichtbar?

Weil „Alarm sichtbar“ aus dem **Detektorzustand** abgeleitet wird.

Quittierung verändert nur den **Benachrichtigungszustand**.

Beispiel Slow Leak:

1. 7 L/h liegen 60 Minuten an.
2. Slow Leak wird aktiv.
3. Benutzer quittiert global.
4. Pushmeldungen verstummen.
5. 7 L/h liegen weiterhin an.
6. Slow Leak bleibt aktiv.
7. Erst 10 Minuten unter 3 L/h beenden ihn.

Das gleiche Prinzip gilt für alle vier Klassen mit jeweils eigener Resetbedingung.

---

# 9. Ereignisende

Wenn der Detektor seine physische Resetbedingung erfüllt:

- wechselt er auf `idle`
- das Event-Ende wird ausgelöst
- der gespeicherte Quittierungszustand für diese Event-ID wird entfernt

Beim nächsten Ereignis startet die Quittierungslogik frisch.

---

# 10. Zusammenfassung

| Aktion | Detektor | Push dieses Geräts | Push andere Geräte | Globaler Push | Shut Off |
|---|---|---|---|---|---|
| Persönlich stummschalten | bleibt aktiv | aus | bleibt | bleibt | unverändert |
| Global quittieren | bleibt aktiv | aus | aus | aus | unverändert |
| Physische Resetbedingung erfüllt | endet | Ereignis endet | Ereignis endet | Ereignis endet | wird neu berechnet |

## F04 V3: externe Alarme und separater Reset

Mehrere externe binary_sensor-Quellen erhalten jeweils eine eigene Event-ID und
eigene Quittierungen. Normales ACK und persönliches Mute beenden weder hydraulische
noch externe ACTIVE-Alarme und geben keinen Shutoff-Beitrag frei. Der gesonderte
External Reset verlangt die unabhängige Berechtigung allow_external_reset (false
als Standard), einen aktuellen Home-Tracker und sämtliche aktuellen Event-,
Quellen-, Empfänger- und Nonce-Bindungen. trusted_stationary allein reicht nicht.
Erst erfolgreiches HA-Store-Schreiben setzt genau diese Quelle auf WAITING; sie
bleibt bis echtem OFF dort, auch nach Neustart. Andere Alarme bleiben erhalten.
Details und frische Actions nach Restart: [F04 V3](F04-V3.md).

## Quittierung und hydraulische Überwachung

Persönlicher Mute und globales ACK ändern weder die Quellenfreigabe noch
`hydraulic_monitoring_status`. Aktiv/Warten/Gesperrt ist unabhängig davon, ob
Benachrichtigungen quittiert sind. Persönlicher Mute unterwegs ist kein globales
ACK; letzteres verlangt weiterhin aktuelle Recipient-Berechtigung und Home-Zone,
serverseitig geprüft. Ein UI-Button ist keine Autorisierung.
Hydraulische Alarme haben keinen Lösch- oder Reset-Befehl. Sie enden nach ihren physischen
Resetregeln; Slow/Low zusätzlich, wenn der Detektor abgeschaltet wird, High Flow, wenn der Bypass
startet. Burst endet nur physisch. Der gesonderte berechtigte External Reset betrifft ausschließlich
seine externe Quelle. [Sensor und Kartenbefehle](Home-Assistant-Schnittstellen).

## Quittierung in der Dashboard-Karte

Seit 2.0.0-beta.1 bietet die [Dashboard-Karte](Dashboard-Karte) einem **gekoppelten Gerät** genau die
Aktionen an, die das Backend gerade erlaubt: persönliches Stummschalten für dieses Gerät (auch
unterwegs), globale Quittierung (Berechtigung und Device Tracker `home`) und externen Reset
(Berechtigung und `home`, mit Rückfrage). Die Rechte hängen am Gerät: Ein iPad zuhause kann global
quittieren, das Telefon desselben Benutzers unterwegs nur sich selbst stummschalten. Nicht gekoppelte
Geräte sehen nur die Anzeige. Ein gekoppeltes **Wanddisplay** gilt immer als zuhause: Es darf, was seine
Häkchen erlauben, hat aber kein Stummschalten. Jede Sitzung, die als das Display erkannt wird (bei
einer Kiosk-Benutzer-Kopplung jede Anmeldung dieses Benutzers), hat diese Rechte. Auch in der
Karte gilt: Quittierung beendet weder Erkennung noch Alarm noch Absperranforderung.
