# hAI.TauricPortainer

Interner **FastAPI-Wrapper** für [TradingAgents](https://github.com/TauricResearch/TradingAgents), fertig gehärtet für den Betrieb als **Portainer-Stack**. Dieses Repo enthält keine eigenständige Trading-Logik, keine Order-Ausführung und keinen eToro-Zugriff — es liefert ausschließlich ein normalisiertes Analyse-Signal über einen internen HTTP-Endpoint.

> ⚠️ **Kein Financial-Advice-Tool.** TradingAgents ist ein LLM-basiertes Research-Framework (siehe [Upstream-README](https://github.com/TauricResearch/TradingAgents)). Dieser Wrapper macht daraus einen kontrollierten internen Dienst, aber die inhaltliche Unsicherheit von LLM-Ausgaben bleibt bestehen.

## Architekturüberblick

```text
MCP / eToro-Bot / Scheduler
        |
        | POST /analyze  (X-API-Key)
        v
tradingagents-api (dieser Stack)
        |
        v
TradingAgentsGraph.propagate(ticker, date)
        |
        v
normalisiertes JSON-Signal (execution_allowed: false)
```

Der Container führt **niemals** eine Order aus. `execution_allowed` ist im Response-Schema fest auf `false` gesetzt — die Ausführung bleibt vollständig in eurem separaten eToro-MCP, nach eigenem Risiko-Gate.

## Repository-Inhalt

| Datei | Zweck |
|---|---|
| `api.py` | FastAPI-Wrapper um `TradingAgentsGraph`. API-Key-Pflicht, Ticker-Allowlist, Concurrency-Limit, Audit-Logging. |
| `Dockerfile.api` | Mehrstufiger Build. Klont einen gepinnten TradingAgents-Tag, installiert als non-root, read-only-fähig. |
| `portainer-stack.yml` | Fertiger Compose-Stack für Portainer. Internes Docker-Netz, kein Port-Publishing, gehärtete Runtime-Optionen. |
| `stack.env.example.txt` | Vorlage für die Stack-Umgebungsvariablen (Secrets, LLM-Provider, Allowlist). |
| `SECURITY.md` | Ausführliche Sicherheitsprüfung: identifizierte Risiken, Gegenmaßnahmen, bewusst offene Punkte. |
| `TESTPLAN.md` | Schritt-für-Schritt-Testfälle für Health, Auth, Allowlist, Concurrency, Persistenz, Restart. |

## Voraussetzungen

- Docker-Host mit Portainer (z. B. dein Debian/DietPi-Setup).
- Ein API-Key für mindestens einen LLM-Provider (OpenAI, Anthropic, Google, ...).
- Optional: eigenes GitHub-Repo als Build-Quelle für Portainer (Repository-Methode), alternativ manuelles Kopieren der Build-Dateien auf den Host (Web-Editor-Methode).

## Schnellstart

### 1. Repository auf den Docker-Host holen (falls nicht über Portainer-Repository-Build)

```bash
git clone https://github.com/jbkunama1/hAI.TauricPortainer.git
cd hAI.TauricPortainer
```

### 2. API-Key generieren

```bash
openssl rand -hex 32
```

### 3. Stack in Portainer anlegen

1. **Stacks → Add stack**
2. Name: `tradingagents-api`
3. Build-Methode:
   - **Repository** (empfohlen): URL dieses Repos eintragen, Compose-Pfad `portainer-stack.yml`.
   - **Web editor**: Inhalt von `portainer-stack.yml` einfügen. In diesem Fall müssen `api.py` und `Dockerfile.api` zusätzlich manuell in das Build-Context-Verzeichnis auf dem Host kopiert werden.
4. Unter **Environment variables** die Werte aus `stack.env.example.txt` eintragen:
   - `TRADINGAGENTS_API_KEY` (der generierte Wert aus Schritt 2)
   - `OPENAI_API_KEY` bzw. der Key des gewünschten Providers
   - `TRADINGAGENTS_TICKER_ALLOWLIST` nach Bedarf anpassen (Standard: `AAPL,MSFT,NVDA,BTC-USD,ETH-USD`)
5. **Deploy the stack**

### 4. Healthcheck

```bash
docker logs -f tradingagents-api
docker inspect tradingagents-api --format '{{.State.Health.Status}}'
```

### 5. Ersten Testaufruf ausführen

Da der Container **keinen Port nach außen veröffentlicht**, erfolgt der Test über einen Wegwerf-Container im selben Docker-Netz:

```bash
docker run --rm --network tradingagents_internal curlimages/curl:latest \
  curl -s -X POST http://tradingagents-api:8000/analyze \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: DEIN_GENERIERTER_KEY' \
  -d '{"ticker":"AAPL","analysis_date":"2025-01-15"}'
```

Der erste Lauf kann je nach `TRADINGAGENTS_MAX_DEBATE_ROUNDS` mehrere Minuten dauern — das ist normales LLM-Verhalten, kein Fehler.

Vollständige Testfälle inklusive Negativtests (fehlender Key, Ticker außerhalb der Allowlist, Zukunftsdatum, Concurrency-Limit) stehen in [`TESTPLAN.md`](./TESTPLAN.md).

## Konfiguration

Alle Variablen werden über die Stack-Umgebung gesetzt, siehe [`stack.env.example.txt`](./stack.env.example.txt):

| Variable | Beschreibung | Default |
|---|---|---|
| `TRADINGAGENTS_API_KEY` | Pflicht-Header `X-API-Key` für jeden Request | — |
| `TRADINGAGENTS_TICKER_ALLOWLIST` | Kommagetrennte erlaubte Ticker | `AAPL,MSFT,NVDA,BTC-USD,ETH-USD` |
| `TRADINGAGENTS_MAX_CONCURRENCY` | Max. gleichzeitige LLM-Analysen | `1` |
| `TRADINGAGENTS_LLM_PROVIDER` | LLM-Provider (`openai`, `anthropic`, `google`, ...) | `openai` |
| `TRADINGAGENTS_DEEP_THINK_LLM` | Modell für komplexe Reasoning-Schritte | `gpt-5.5` |
| `TRADINGAGENTS_QUICK_THINK_LLM` | Modell für schnelle Teilschritte | `gpt-5.4-mini` |
| `TRADINGAGENTS_MAX_DEBATE_ROUNDS` | Anzahl Bull/Bear-Debattenrunden | `1` |
| `TRADINGAGENTS_MAX_RISK_ROUNDS` | Anzahl Risk-Management-Runden | `1` |
| `TRADINGAGENTS_TEMPERATURE` | Sampling-Temperatur | `0` |
| `TRADINGAGENTS_CHECKPOINT_ENABLED` | LangGraph-Checkpoint-Resume aktivieren | `true` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `ALPHA_VANTAGE_API_KEY` | Provider-Zugangsdaten, nur den genutzten Key befüllen | — |
| `LOG_LEVEL` | Log-Level der API | `INFO` |

## API-Endpunkte

### `GET /health`

```json
{"status": "ok", "time": "2026-08-25T00:02:00+00:00"}
```

### `POST /analyze`

Request:

```json
{
  "ticker": "AAPL",
  "analysis_date": "2025-01-15"
}
```

Header: `X-API-Key: <dein-key>`

Response:

```json
{
  "schema_version": "1.0",
  "source": "tradingagents",
  "created_at": "2026-08-25T00:05:00+00:00",
  "ticker": "AAPL",
  "analysis_date": "2025-01-15",
  "action": "HOLD",
  "execution_allowed": false,
  "risk_approved": false,
  "reason": "Nur Analyseergebnis. Ausfuehrung erfordert separate Risikofreigabe.",
  "raw_signal": "...",
  "final_trade_decision": "..."
}
```

`action` ist immer eines von `BUY`, `SELL`, `HOLD`. `execution_allowed` ist strukturell immer `false` — es gibt in diesem Service keinen Weg, eine echte Order auszulösen.

## Integration mit eigenem MCP / eToro-Bot

1. MCP-Container demselben Docker-Netz `tradingagents_internal` hinzufügen.
2. Im MCP-Tool `http://tradingagents-api:8000/analyze` mit `X-API-Key`-Header aufrufen.
3. `action` und `execution_allowed` an den eigenen Risiko-Gate-Schritt weiterreichen.
4. Order-Ausführung bleibt vollständig im separaten eToro-MCP.

## Sicherheit

Eine vollständige Risikoanalyse mit Bewertungstabelle steht in [`SECURITY.md`](./SECURITY.md), unter anderem zu:

- Authentifizierung und Ticker-Allowlist
- Netzwerk-Isolation (kein Port-Publishing, `internal: true`)
- Non-root, read-only Filesystem, `cap_drop: ALL`
- Gepinnte Upstream-Version statt `main`
- Bewusst offene Punkte (TLS im internen Netz, Secrets-Rotation, Rate-Limiting pro Tag)

## Lizenz

Dieser Wrapper steht unter der [MIT-Lizenz](./LICENSE). Das zugrunde liegende [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) steht unter Apache-2.0 — dessen Lizenzbedingungen gelten für den geklonten Code im Build-Prozess unverändert weiter.

## Haftungsausschluss

Dieses Repository ist ein reines Infrastruktur- und Sicherheitswrapper. Es stellt keine Finanz-, Anlage- oder Handelsberatung dar. Trading-Entscheidungen basieren auf nicht-deterministischen LLM-Ausgaben und werden ausdrücklich ohne Garantie auf Richtigkeit oder Profitabilität bereitgestellt.
