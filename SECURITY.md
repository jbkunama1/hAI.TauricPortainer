# Sicherheitsprüfung: TradingAgents-API-Wrapper

## Identifizierte Risiken und Gegenmaßnahmen

| Risiko | Bewertung | Gegenmaßnahme im Stack |
|---|---|---|
| Unauthentifizierter Zugriff auf `/analyze` | hoch | Pflicht-Header `X-API-Key`, Vergleich gegen `TRADINGAGENTS_API_KEY`; ohne gesetzten Key läuft die API offen und loggt eine Warnung |
| Beliebige Ticker als Kostentreiber/Missbrauch | mittel | Ticker-Whitelist-Pattern per Regex plus optionale `TRADINGAGENTS_TICKER_ALLOWLIST` |
| Ungültige/zukünftige Daten, Prompt-Injection über Freitext-Felder | mittel | Pydantic-Validierung, kein Freitextfeld im Request-Schema |
| Ressourcenerschöpfung durch parallele LLM-Läufe (Kosten, Rate-Limits) | mittel | Semaphore begrenzt gleichzeitige Analysen (`TRADINGAGENTS_MAX_CONCURRENCY`) |
| Informationsleck durch Stacktraces/Debug-Ausgaben | mittel | `docs_url`/`redoc_url` standardmäßig deaktiviert, generische 500-Antwort, Details nur ins Server-Log |
| Direkter Internetzugriff auf den Container | hoch | Docker-Netz `internal: true`, keine `ports:`-Direktive – nur erreichbar für Container im selben Netz |
| Kompromittierter Container erhält Root-Rechte / Host-Zugriff | hoch | `USER appuser` (UID 10001), `read_only: true`, `cap_drop: ALL`, `no-new-privileges:true` |
| Fehlkonfigurierte Order-Ausführung direkt aus der Analyse | kritisch | API liefert ausschließlich `execution_allowed: false`; es gibt keinen Order-Endpoint in diesem Service |
| Ungepinnte Upstream-Version, unerwartete Breaking Changes | mittel | `Dockerfile.api` klont einen festen Tag (`v0.3.1`) statt `main` |
| API-Keys im Klartext im Repo | hoch | `.env`/Stack-Variablen separat pflegen, `stack.env.example.txt` enthält nur Platzhalter |
| Übermäßige Log-Größe / Log-Flood als DoS-Vektor | niedrig | `json-file`-Logging mit `max-size`/`max-file` begrenzt |
| Kein Audit-Trail bei Fehlnutzung | niedrig | Middleware loggt jede Anfrage mit Pfad, Status, Client-IP, Dauer |

## Bewusst nicht gelöste Punkte

- **TLS/Verschlüsselung im internen Netz:** Der Traffic zwischen MCP-Container und `tradingagents-api` läuft aktuell unverschlüsselt im internen Docker-Netz. Für ein einzelnes Docker-Host-Setup meist akzeptabel; bei mehreren Hosts/Overlay-Netzen zusätzlich mTLS oder Service-Mesh erwägen.
- **Secrets-Rotation:** Der API-Key ist statisch. Für höhere Sicherheit ggf. auf Docker Secrets oder ein Vault-System wechseln statt reiner Environment-Variablen.
- **LLM-Provider-Kosten-Explosion:** Die Semaphore begrenzt Parallelität, aber nicht die Gesamtzahl an Aufrufen pro Tag. Bei Bedarf Rate-Limiting (z. B. `slowapi`) oder Tages-Budget-Zähler ergänzen.
- **Kein Endpoint-Level-RBAC:** Aktuell ein einziger API-Key für alle Aufrufer. Bei mehreren Konsumenten mehrere Keys mit Namens-Zuordnung im Log einführen.

## Ausbaustufen

- Rate-Limiting pro Tag/Nutzer.
- Mehrere API-Keys mit Zuordnung für Audit-Zwecke.
- Prometheus-Metriken-Endpoint für Portainer/Grafana-Monitoring.
- CI-Job, der auf neue TradingAgents-Tags prüft, statt `TRADINGAGENTS_REF` manuell zu pflegen.
