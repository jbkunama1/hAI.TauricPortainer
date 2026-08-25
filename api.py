"""
TradingAgents API-Wrapper.

Stellt TradingAgents als internen HTTP-Dienst bereit. Kein Endpoint
fuehrt jemals eine Order aus - die API liefert ausschliesslich ein
normalisiertes, konservatives Analyse-Signal zurueck.

Sicherheitsprinzipien:
- API-Key-Pflicht fuer jeden Request (X-API-Key Header).
- Striktes Input-Schema (Ticker-Whitelist-Pattern, Datumsvalidierung).
- Ticker-Allowlist optional per ENV erzwingbar.
- Kein Shell-Zugriff, kein Dateisystem-Zugriff ueber die API.
- Timeouts / Concurrency-Begrenzung ueber Semaphore.
- Kein Debug-Modus, keine Stacktraces nach aussen.
- Strukturiertes Logging jeder Anfrage (Audit-Trail).
"""

import logging
import os
import re
import threading
import time
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("tradingagents-api")

API_KEY = os.environ.get("TRADINGAGENTS_API_KEY", "")
TICKER_ALLOWLIST_RAW = os.environ.get("TRADINGAGENTS_TICKER_ALLOWLIST", "")
TICKER_ALLOWLIST = {
    t.strip().upper() for t in TICKER_ALLOWLIST_RAW.split(",") if t.strip()
}
MAX_CONCURRENT_ANALYSES = int(os.environ.get("TRADINGAGENTS_MAX_CONCURRENCY", "1"))
TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,15}$")

if not API_KEY:
    logger.warning(
        "TRADINGAGENTS_API_KEY ist nicht gesetzt - die API laeuft ungeschuetzt! "
        "Nur fuer lokale Tests akzeptabel."
    )

_analysis_semaphore = threading.Semaphore(MAX_CONCURRENT_ANALYSES)

app = FastAPI(
    title="TradingAgents API",
    description="Interner Analyse-Wrapper. Kein Order-Execution-Endpoint.",
    version="1.0.0",
    docs_url=os.environ.get("TRADINGAGENTS_API_DOCS_URL") or None,
    redoc_url=None,
)

_config = DEFAULT_CONFIG.copy()
_graph_lock = threading.Lock()
_graph: Optional[TradingAgentsGraph] = None


def get_graph() -> TradingAgentsGraph:
    global _graph
    if _graph is None:
        with _graph_lock:
            if _graph is None:
                _graph = TradingAgentsGraph(debug=False, config=_config)
    return _graph


class AnalyzeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=15)
    analysis_date: date

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not TICKER_PATTERN.match(normalized):
            raise ValueError(
                "Ticker enthaelt ungueltige Zeichen. Erlaubt: A-Z, 0-9, Punkt, Minus."
            )
        if TICKER_ALLOWLIST and normalized not in TICKER_ALLOWLIST:
            raise ValueError(
                f"Ticker '{normalized}' ist nicht in der Allowlist freigegeben."
            )
        return normalized

    @field_validator("analysis_date")
    @classmethod
    def validate_date_not_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("analysis_date darf nicht in der Zukunft liegen.")
        return value


class AnalyzeResponse(BaseModel):
    schema_version: str = "1.0"
    source: str = "tradingagents"
    created_at: str
    ticker: str
    analysis_date: str
    action: str
    execution_allowed: bool = False
    risk_approved: bool = False
    reason: str
    raw_signal: Any
    final_trade_decision: Any


ALLOWED_ACTIONS = {"BUY", "SELL", "HOLD"}


def normalize_action(raw_signal: Any, raw_decision: Any) -> str:
    text = f"{raw_signal or ''} {raw_decision or ''}".upper()
    negations = ("NOT A BUY", "NOT A SELL", "NO BUY", "NO SELL", "AVOID")
    for neg in negations:
        text = text.replace(neg, "")

    found = [action for action in ALLOWED_ACTIONS if re.search(rf"\b{action}\b", text)]
    if len(found) == 1:
        return found[0]
    return "HOLD"


def verify_api_key(x_api_key: Optional[str]) -> None:
    if not API_KEY:
        return
    if not x_api_key or x_api_key != API_KEY:
        logger.warning("Abgelehnter Request: ungueltiger oder fehlender API-Key.")
        raise HTTPException(status_code=401, detail="Ungueltiger oder fehlender API-Key.")


@app.middleware("http")
async def audit_log_middleware(request: Request, call_next):
    start = time.time()
    client_host = request.client.host if request.client else "unknown"
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 1)
    logger.info(
        "%s %s status=%s client=%s duration_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        client_host,
        duration_ms,
    )
    return response


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(
    request: AnalyzeRequest,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
):
    verify_api_key(x_api_key)

    acquired = _analysis_semaphore.acquire(timeout=5)
    if not acquired:
        raise HTTPException(
            status_code=429,
            detail="Zu viele gleichzeitige Analysen. Bitte spaeter erneut versuchen.",
        )

    try:
        graph = get_graph()
        state, raw_signal = graph.propagate(
            request.ticker,
            request.analysis_date.isoformat(),
        )
        final_decision = state.get("final_trade_decision") if isinstance(state, dict) else None
        action = normalize_action(raw_signal, final_decision)

        return AnalyzeResponse(
            created_at=datetime.now(timezone.utc).isoformat(),
            ticker=request.ticker,
            analysis_date=request.analysis_date.isoformat(),
            action=action,
            execution_allowed=False,
            risk_approved=False,
            reason="Nur Analyseergebnis. Ausfuehrung erfordert separate Risikofreigabe.",
            raw_signal=str(raw_signal) if raw_signal is not None else None,
            final_trade_decision=final_decision,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Analyse fehlgeschlagen fuer Ticker=%s", request.ticker)
        raise HTTPException(
            status_code=500,
            detail="Analyse fehlgeschlagen. Details siehe Server-Log.",
        ) from None
    finally:
        _analysis_semaphore.release()
