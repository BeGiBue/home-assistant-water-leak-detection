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
Der gezielte echte Hydrus-Test nach Beta.3-Installation/HA-Neustart bleibt offen.
[Chronologie und Haushaltsprüfung](https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/BETA_1.2.0.md).

Diese Runde aktualisiert nur Repository-Dokumentation/Wiki-Quellen; sie erstellt
keinen neuen Release und veröffentlicht das öffentliche GitHub-Wiki nicht.
Die früheren Release-/Korrekturrunden auf dieser Seite sind historischer Kontext.
