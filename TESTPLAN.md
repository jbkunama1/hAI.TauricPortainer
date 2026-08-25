# Testplan: TradingAgents-API

Alle Tests laufen über einen Wegwerf-Container im selben Docker-Netz (`tradingagents_internal`), da der Service keinen Port nach außen veröffentlicht.

## 1. Healthcheck

```bash
docker run --rm --network tradingagents_internal curlimages/curl:latest \
  curl -s http://tradingagents-api:8000/health
```

Erwartung: `{"status": "ok", "time": "..."}`

## 2. Analyse ohne API-Key (muss fehlschlagen)

```bash
docker run --rm --network tradingagents_internal curlimages/curl:latest \
  curl -s -o /dev/null -w "%{http_code}\n" \
  -X POST http://tradingagents-api:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"AAPL","analysis_date":"2025-01-15"}'
```

Erwartung: `401`

## 3. Analyse mit gültigem API-Key

```bash
docker run --rm --network tradingagents_internal curlimages/curl:latest \
  curl -s -X POST http://tradingagents-api:8000/analyze \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: DEIN_GENERIERTER_KEY' \
  -d '{"ticker":"AAPL","analysis_date":"2025-01-15"}'
```

Erwartung: JSON mit `action`, `execution_allowed: false`, `raw_signal`, `final_trade_decision`. Der erste Lauf kann mehrere Minuten dauern.

## 4. Ticker außerhalb der Allowlist

```bash
docker run --rm --network tradingagents_internal curlimages/curl:latest \
  curl -s -X POST http://tradingagents-api:8000/analyze \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: DEIN_GENERIERTER_KEY' \
  -d '{"ticker":"TSLA","analysis_date":"2025-01-15"}'
```

Erwartung: `422`, sofern `TSLA` nicht in `TRADINGAGENTS_TICKER_ALLOWLIST` steht.

## 5. Zukunftsdatum

```bash
docker run --rm --network tradingagents_internal curlimages/curl:latest \
  curl -s -X POST http://tradingagents-api:8000/analyze \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: DEIN_GENERIERTER_KEY' \
  -d '{"ticker":"AAPL","analysis_date":"2099-01-01"}'
```

Erwartung: `422`

## 6. Parallelitätsbegrenzung

Bei `TRADINGAGENTS_MAX_CONCURRENCY=1` zwei Anfragen gleichzeitig senden (zweites Terminal parallel starten). Erwartung: Die zweite Anfrage wartet oder liefert `429`, statt beide LLM-Läufe gleichzeitig zu starten.

## 7. Persistenz

```bash
docker exec tradingagents-api sh -c \
  "find /home/appuser/.tradingagents -maxdepth 3 -type f"
```

Erwartung: Einträge unter `logs/`, `cache/`, ggf. `memory/trading_memory.md`.

## 8. Restart-Verhalten

```bash
docker restart tradingagents-api
docker logs --tail 50 tradingagents-api
```

Erwartung: Container startet ohne Fehler neu, `read_only`-Dateisystem verursacht keine Schreibfehler (nur `/tmp` und das Volume sind beschreibbar).
