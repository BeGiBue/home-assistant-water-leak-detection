# Water Shut Off

## Ziel

Der Wasserwächter stellt eine unabhängige Entscheidung bereit:

> Soll aufgrund der aktuell aktiven Leckagezustände eine Wasserabsperrung angefordert werden?

Diese Entscheidung wird als Home-Assistant-Binary-Sensor **Absperranforderung / Water shutoff request** ausgegeben.

---

# 1. Bewusste Trennung

Water Shut Off ist unabhängig von:

- der Pushbenachrichtigung
- persönlicher Stummschaltung
- globaler Quittierung
- sichtbarer Bedienoberfläche

Das ist eine zentrale Sicherheitsentscheidung.

## Warum?

Eine Person kann bestätigen:

> Ich habe den Alarm gesehen.

Das bedeutet nicht automatisch:

> Wasser darf weiterlaufen.

Würde die Quittierung den Shut-Off-Request löschen, könnte das reine Drücken eines Notification-Buttons eine sicherheitsrelevante Absperrentscheidung aufheben.

---

# 2. Zuordnung je Detektor

Jeder Detektor kann unabhängig so konfiguriert werden, dass er eine Absperranforderung erzeugt.

Standard:

| Detektor | Water Shut Off standardmäßig |
|---|---|
| Slow Leak | aus |
| Low Flow | aus |
| High Flow | aus |
| Burst Leak | **ein** |

## Warum diese Defaults?

### Slow Leak

Ein kleiner Dauerverlust kann ärgerlich und teuer sein, rechtfertigt aber nicht in jedem Haushalt eine automatische Unterbrechung der Wasserversorgung.

### Low Flow

Ein vergessener Wasserhahn ist kritisch, kann aber viele legitime Langzeitnutzungen ähneln. Standardmäßig erfolgt daher keine automatische Shut-Off-Anforderung.

### High Flow

High Flow ist ausdrücklich auch für legitime Nutzung gedacht. Darum ist die Absperranforderung standardmäßig aus.

### Burst Leak

Burst Leak repräsentiert eine schwere akute Situation. Hier ist die Shut-Off-Anforderung standardmäßig aktiv.

---

# 3. Berechnung

Der Request ist aktiv, wenn mindestens ein Detektor:

1. im Zustand `active` ist und
2. für diesen Detektor Water Shut Off aktiviert ist

Sinngemäß:

```text
shutoff_request =
    (Slow aktiv  AND Slow->Shutoff)
 OR (Low aktiv   AND Low->Shutoff)
 OR (High aktiv  AND High->Shutoff)
 OR (Burst aktiv AND Burst->Shutoff)
```

Die Priorität des sichtbaren Gesamtstatus ist für diese OR-Logik nicht entscheidend.

---

# 4. Wann verschwindet der Request?

Der Request wird bei jeder Zustandsänderung neu aus den aktiven Detektoren berechnet.

Er verschwindet erst, wenn **kein** aktiver Detektor mit aktivierter Shut-Off-Zuordnung mehr vorhanden ist.

Beispiel:

- Slow Leak aktiv, Shut Off für Slow = an
- Burst Leak zusätzlich aktiv, Shut Off für Burst = an
- Burst endet
- Slow Leak bleibt aktiv

Ergebnis:

> Shut-Off-Request bleibt aktiv.

---

# 5. Quittierung verändert den Request nicht

Weder:

- persönlicher Mute
- globale Quittierung

ändern die Detektor-Runtime oder die Shut-Off-Zuordnung.

Daher bleibt die Absperranforderung bestehen, solange die physische Detektionslogik dies verlangt.

---

# 6. Aktuelle Ventilsteuerung

Auch 1.2.0-beta.3 steuert **nicht direkt** ein Ventil.

Stattdessen stellt die Integration einen stabilen Backend-Ausgang zur Verfügung.

Die physische Aktion wird bewusst über Home Assistant automatisiert.

Beispiel:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.water_leak_detection_water_shutoff_request
    to: "on"

actions:
  - action: valve.close_valve
    target:
      entity_id: valve.main_water
```

Die konkrete Entity-ID kann in jeder Installation anders sein.

---

# 7. Warum externe Automation statt harter Ventilkopplung?

Verschiedene Installationen besitzen unterschiedliche Aktoren:

- `valve.*`
- `switch.*`
- Relais
- herstellerspezifische Integrationen

Außerdem soll eine automatische physische Absperrung **explizit** eingerichtet und getestet werden.

Der Wasserwächter entscheidet:

> Absperrung angefordert: ja/nein.

Home Assistant entscheidet über eine benutzerdefinierte Automation:

> Welche reale Hardware soll wie reagieren?

Das reduziert Kopplung und vermeidet implizite gefährliche Aktorsteuerung.

---

# 8. Events

Bei einer Änderung der Absperranforderung werden Events erzeugt:

- `water_leak_detection_shutoff_requested`
- `water_leak_detection_shutoff_cleared`

Der Payload enthält je nach Situation unter anderem:

- Config-Entry-ID
- Status
- Detektortyp
- Event-ID
- aktuellen Durchfluss
- Ereignisvolumen
- Burst-Erkennungsgrund, falls vorhanden

Damit können externe Automationen zusätzlich zum Binary Sensor auf Übergänge reagieren.

---

# 9. Empfohlene Betriebsweise

Vor echter automatischer Ventilsteuerung:

1. zunächst nur Benachrichtigungen beobachten
2. Grenzwerte mit realen Haushaltsdaten prüfen
3. Shut-Off-Request in Dashboards/Automationen beobachten
4. Ventil separat manuell testen
5. erst danach die automatische Schließautomation aktivieren

Eine automatische Absperrung sollte nie ungeprüft allein aufgrund theoretischer Standardwerte produktiv geschaltet werden.

## F04 V3: unabhängige Beiträge und fehlgeschlagene Writes

Hydraulische und externe ACTIVE-Alarme tragen unabhängig zur Absperranforderung
bei. Pro externem Sensor ist contributes_to_shutoff konfigurierbar, standardmäßig
true. Die Alarmanzeige priorisiert gegebenenfalls einen Hauptalarm, verliert aber
keinen anderen Beitrag. Ein autorisierter External Reset entfernt erst nach
erfolgreicher atomischer Persistenz genau seinen Beitrag; während oder nach
einem fehlgeschlagenen Write bleibt ACTIVE mit Shutoff öffentlich bestehen. ACK
und Mute entfernen keine Beiträge. High-Bypass unterdrückt externe Sensoren nicht.
Die Integration öffnet oder schließt niemals selbst ein physisches Ventil.
Weitere Regeln: [F04 V3](F04-V3.md).

## Diagnose-Entität ohne Steuerwirkung

`hydraulic_monitoring_status` erzeugt und löscht keine Absperranforderung.
Gesperrt ist ein Diagnosezustand, keine Freigabe für Wasser: bereits bestätigte
ACTIVE-Alarme behalten ihre konfigurierten Shutoff-Beiträge. ACK/Mute ändern
weder Überwachungsfreigabe noch Beiträge. Die Integration öffnet niemals selbst
ein Ventil. [Betriebszustände](Home-Assistant-Schnittstellen).
