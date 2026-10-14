# Water Leak Guard 1.2.0-beta.1 – Entwurf

Noch nicht veröffentlicht; Versionsänderung und Veröffentlichung benötigen Freigabe.

- F04-V3 mit hydraulischer Slow-/Low-/High-/Burst-Erkennung, getrenntem Rolling-
  und Long-Term-Learning, verständlicher Ereignisdauer und HA-Quittierung.
- MQTT-Messzeit und Zustellzeit getrennt: normaler Transportjitter unterbricht
  weder Burst-Bestätigung noch Low-Flow-Rücksetzung. Replay, Timeout, Restart und
  echte ausgeschlossene Messlücken bleiben geschützt.
- Neue Burst-Basis für nicht explizit konfigurierte Werte: 3.500 L/h. Bestehende
  gespeicherte Werte bleiben erhalten. Low hat normalen 60-Minuten-Pfad und
  zusätzlichen Stabilitätspfad; gültige Ruhe setzt Low nach standardmäßig 3 Minuten zurück.
- Legacy-Lerndaten werden quarantänisiert; ein Repair weist auf die Migration und
  mögliche adaptive Schwellenabsenkung hin. Vor Upgrade vollständige Sicherung erstellen.

Abgenommen wird ausschließlich der hydraulische Haushaltsversuch **ohne externe
Sensoren und ohne gespeicherte externe Datensätze**. F04-FSR-H01 bleibt offen;
externe Sensoren sind nicht uneingeschränkt freigegeben. Vorhandene Alarmdaten
nicht löschen. Automatische Absperrung bleibt eine optionale externe Automation;
die Integration öffnet oder schließt selbst kein Ventil.

Hydrus-Discovery mit originalem UTC-timestamp und `force_update: true` wurde mit
echtem Broker und HA geprüft. Die dauerhafte Discovery-Einstellung sowie reale
Funk-/Smartphone-/Restart-Sequenzen bleiben im Haushalt zu prüfen. Die Integration
ersetzt weder mechanischen Wasserschutz noch menschliche Kontrolle.
