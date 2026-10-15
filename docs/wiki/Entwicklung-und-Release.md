# Entwicklung, Tests und Release

## Repository

`BeGiBue/homeassistant-water-leak-detection`

Technische Domain:

`water_leak_detection`

Der sichtbare Name darf geändert bzw. übersetzt werden, die Domain sollte nach Veröffentlichung stabil bleiben.

---

# 1. Entwicklungsmodell

Änderungen werden auf Feature-/Fix-Branches entwickelt.

Vor Merge nach `main` werden je nach Änderung geprüft:

- JSON
- Python Compile
- Ruff
- Pytest
- Hassfest
- HACS-Validator

---

# 2. Tests

Die Tests sind bewusst deterministisch und decken unter anderem ab:

- Detektor-Zustandsautomaten
- Resetverhalten
- High-Flow-Bypass
- Burst-Unabhängigkeit vom Bypass
- Rapid-Rise-Burst
- Lernmodell
- Confidence
- saisonale Anpassung
- hydraulische Grenzen
- Config Flow
- Benachrichtigungen
- Home-/Away-Quittierung
- Rückkehr-nach-Hause
- Übersetzungs-/UI-Metadaten

Der Stand vor dem ersten 0.3.0-Release wurde mit **94 Tests** erfolgreich geprüft. Die Release-Metadaten werden zusätzlich darauf geprüft, dass die Integration **nicht** als Home-Assistant-Helfer klassifiziert ist.

---

# 3. Hassfest

Hassfest prüft Home-Assistant-spezifische Metadaten und Strukturen.

Der dokumentierte Stand wurde mit:

`Invalid integrations: 0`

validiert.

---

# 4. GitHub Actions

Die Projekt-Workflows sind absichtlich **manual-only** über `workflow_dispatch`.

Grund:

Automatische Checks auf jeden Push/PR erzeugten unnötig viele Benachrichtigungen.

Automatische Trigger sollen nicht ohne bewusste Entscheidung wieder aktiviert werden.

Workflows:

- Validate
- Hassfest
- HACS
- Publish 1.0.2

---

# 5. HACS

Für HACS wichtig:

- öffentliches Repository
- `hacs.json`
- gültiges `manifest.json`
- README
- Topics
- lokale Brand-Assets
- veröffentlichter GitHub Release für Release-Versionierung

Der HACS-Anzeigename ist:

**Water Leak Guard**

Deutsch wird erst innerhalb Home Assistant zu:

**Wasserwächter**

---

# 6. Release 1.0.2

Das Repository enthält:

- `CHANGELOG.md`
- `RELEASE_NOTES_1.0.2.md`
- manuellen Publish-Workflow

Der Release-Workflow prüft die Manifest-Version **und** `integration_type: "service"` und erzeugt den GitHub Release `1.0.2`.

Der veröffentlichte 0.3.0-Tag enthielt noch `integration_type: "helper"`. Das wurde erst nach dem Tag auf `main` korrigiert. 1.0.0 war deshalb der erste stabile Release, der von Home Assistant als normale Integration und nicht als Helfer einsortiert wird.

---

# 7. Versionsphilosophie

## 0.1

Kern-Detektion und HA-Backend.

## 0.2

Companion-Benachrichtigungen und gerätebasierte Quittierung.

## 0.3

Adaptives Lernen, Confidence, Hydraulik und Rapid-Rise-Burst.

---

# 8. Nicht verhandelbare Regressionen

Änderungen dürfen insbesondere nicht dazu führen, dass:

- High-Flow-Bypass Burst deaktiviert
- Quittierung einen Detektor beendet
- Quittierung Shut Off löscht
- `unknown` als 0 gewertet wird
- verdächtige Episoden das Lernmodell erhöhen
- ein Away-Gerät global quittieren kann
- Slow und Low nur noch gemeinsam abschaltbar sind
- die Integration im Manifest wieder als `helper` statt als normale `service`-Integration klassifiziert wird

Diese Punkte sollten bei Änderungen an Engine, Manager oder Notifications immer als Regressionstests erhalten bleiben.


## 1.0.1

Version 1.0.1 verbessert die Verwaltung mehrerer Benachrichtigungsempfänger: Bereits eingerichtete Geräte werden während Einrichtung, Hinzufügen, Bearbeiten und Entfernen gemeinsam angezeigt. Sichtbar sind Anzeigename, Companion-Benachrichtigungsdienst und Device Tracker; interne IDs und Action-Tokens bleiben verborgen.


## 1.0.2

Version 1.0.2 behebt die Navigation im Home-Assistant-Konfigurator. Speichern beendet den Options-Flow nicht mehr, sondern führt zurück zum passenden Menü. Das Empfänger-Untermenü besitzt zusätzlich **Zurück zur Konfiguration**. Außerdem wurden sichtbare `\n\n`-Escape-Sequenzen in der Empfängerübersicht korrigiert und die Übersicht auf kompakte Anzeigenamen reduziert.


# 9. Lizenz

Das Projekt steht unter der **GNU Affero General Public License v3.0 only (AGPL-3.0-only)**.

Die vollständigen Lizenzbedingungen stehen in der Datei `LICENSE` im Repository. Änderungen und Weitergabe bleiben unter den Bedingungen der AGPLv3; bei einer modifizierten netzwerkbasierten Bereitstellung muss der entsprechende Quellcode den Nutzern zugänglich gemacht werden.

## Unveröffentlichte Korrekturrunde 1

Die Paketversion bleibt 1.0.2; Korrekturen stehen unter `Unreleased` im Changelog.
Release-Workflows validieren denselben unveränderlichen Commit, den sie als Release-Ziel
verwenden. Vorhandene Tags müssen ebenfalls auf diesen Commit zeigen.
Eine Freigabe/Veröffentlichung gehört nicht zu dieser Korrekturrunde. Das öffentliche Wiki
bleibt bis zu einer gesondert autorisierten Synchronisation auf seinem bisherigen Stand.
Aktuelle Testanzahl und lokale Validierungsergebnisse stehen im Abschlussbericht.

## Veröffentlichte Beta.2 und Beta.3 – 14. Oktober 2026

Beta.2 ist als `v1.2.0-beta.2` veröffentlicht: PR #15 (Bildmaterial/Karte 0.1.0)
und PR #16 (MQTT-Setupgrenze). Beta.3 ist als `1.2.0-beta.3` veröffentlicht:
PR #17 (separate hydraulische Überwachungsentität und konsistente Paketversion).
Die damaligen Beta.2-Paketfelder standen noch auf Beta.1; Tags/Release-Namen und
tatsächlich installierter Code sind zu unterscheiden.

Beta.3-Feature-SHA: `2564843c2724970b3692714ed18dca5e92ce1f16`;
Merge-/Release-SHA: `7e1e4e786710f060bc982ba461940da2dbc42697`, identischer Dateibaum.
Je 1476 Softwaretests unter HA 2026.9.0/2026.9.4, 16 Statusfälle separat und
Validate/Hassfest/HACS bestanden. Diese Ergebnisse sind keine physischen Tests.
Am 14. Oktober 2026 bestätigte der Benutzer den erfolgreichen Neustart mit
installierter Beta.3 und realem Hydrus: kein Fehlalarm oder Repair, 11 Sekunden
Gesperrt, anschließend automatisch Aktiv, `verified_original_measurement`. Das
ist kein von Codex selbst ausgeführter Hardwaretest und kein Nachweis aller
Neustart-/MQTT-Ausfallfälle. Die Dauer ist kein garantierter Startwert.
[Chronologie und Haushaltsprüfung](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/BETA_1.2.0.md).

Diese Runde aktualisiert nur Repository-Dokumentation/Wiki-Quellen; ein neuer
Release ist nicht nötig. Der manuelle Workflow **Publish Wiki** synchronisiert
`docs/wiki/` aus main. Die tatsächliche Veröffentlichung muss separat bestätigt
werden; allein ein Merge aktualisiert das öffentliche Wiki nicht.
Die früheren Release-/Korrekturrunden auf dieser Seite sind historischer Kontext.

## 2.0.0-beta.3 – 15. Oktober 2026

Karte 0.6.1 mit standardmäßig offenen Abschnitten (Option `collapsed`), neuer Empfängertyp Wanddisplay
(z. B. TouchKio) mit Kiosk-Benutzer- oder Anmelde-Kopplung, zustandsabhängige Ventil-Symbole der
Absperranforderung. Zusammengeführt aus `feature/display-recipient`; mehrere Runden unabhängiger Review
anhand des Codes, Validate, Hassfest und HACS bestanden. Kein Test in einer echten Installation.
[Release Notes](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/RELEASE_NOTES_2.0.0-beta.3.md).

## 2.0.0-beta.2 – 14. Oktober 2026

Karte 0.5.0: kompaktes, einklappbares Layout (ruhig einspaltig ca. 335 px, passt auf iPhone, iPad-Spalte
und Raspberry Pi 7″ 800×480; zweispaltig ab ca. 600 px Kartenbreite), keine Ein/Aus-Schalter mehr,
alarmbeendende Aktionen nur für ein gekoppeltes Gerät zuhause, nichts Grünes bei eingeschränkter
Überwachung. Empfänger lassen sich mit einem HA-Benutzer oder einer einzelnen Anmeldung koppeln.
Zusammengeführt aus `feature/card-compact` und `docs/readme-hacs-card-preview` (README mit HACS-tauglichem
Logo und Kartenvorschau). Mehrere Runden unabhängiger Review anhand des Codes; Validate, Hassfest und
HACS bestanden. Kein Test in einer echten Installation.
[Release Notes](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/RELEASE_NOTES_2.0.0-beta.2.md).

## 2.0.0-beta.1 – 14. Oktober 2026

Erste Version mit Dashboard-Karte als Bestandteil der Integration (Karte 0.4.1): getrennte Anzeige von
Alarm und hydraulischer Überwachung, Rückfragen vor dem Beenden von Alarmen durch Bedienung,
Gerätekopplung im Empfängereintrag und Kartenaktionen über WebSocket-Befehle mit Prüfung im Backend.
Zusammengeführt aus PR #18 (Überwachungsanzeige), #19 (Backend-Vertrag und Kopplung), #22 (Auslieferung
mit der Integration) und #23 (Kartenaktionen). Jede Etappe wurde von einer unabhängigen Review-Instanz
anhand des Codes geprüft; Validate, Hassfest und HACS bestanden. Kein Test in einer echten Installation.
Beta-Umfang weiterhin ohne externe Lecksensoren (H01 damals offen; inzwischen im Branch
`fix/f04-fsr-h01` behoben, noch nicht veröffentlicht: [F04-FSR-H01](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/F04_FSR_H01.md)).
[Release Notes](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/RELEASE_NOTES_2.0.0-beta.1.md) ·
[Beta 2.0.0](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/BETA_2.0.0.md).
