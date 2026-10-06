"""Immutable, DB-only market regime telemetry for one decision/run.

Snapshots are produced by MarketRegimeService; this module never calculates
markets, fetches market data, or supplies inputs to execution gates.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from functools import wraps
from inspect import signature
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError

from app.db.models import MarketRegimeSnapshot

KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class MarketRegimeTradingContext:
    snapshot_id: int | None = None
    calculation_date: date | None = None
    calculated_at: datetime | None = None
    state_week_ending: date | None = None
    stage: int | None = None
    stage_key: str | None = None
    stage_label: str | None = None
    status: str = "insufficient_data"
    confirmed: bool = False
    combined_score: float | None = None
    kospi_score: float | None = None
    nasdaq_score: float | None = None
    score_change_3w: float | None = None
    new_bullish_reversal: bool = False
    new_bearish_reversal: bool = False
    bullish_confirmation_streak: int = 0
    bearish_confirmation_streak: int = 0

    def to_payload(self) -> dict:
        return {
            name: value.isoformat() if isinstance(value, (date, datetime)) else value
            for name, value in asdict(self).items()
        }


def _decision_utc(decision_at: datetime) -> datetime:
    return (
        decision_at.replace(tzinfo=KST) if decision_at.tzinfo is None else decision_at
    ).astimezone(UTC)


def get_market_regime_context(db, decision_at: datetime) -> MarketRegimeTradingContext:
    """Read the newest snapshot available at decision_at, without autoflush.

    MarketRegimeService writes UTC instants (SQLite drops their timezone). Legacy
    naive ABC decision timestamps use KST, matching the ABC exporter convention.
    No current snapshot is attached to historical observations as a fallback.
    """
    if db is None:
        return MarketRegimeTradingContext()
    decision_utc = _decision_utc(decision_at)
    try:
        with db.no_autoflush:
            row = (
                db.query(MarketRegimeSnapshot)
                .filter(MarketRegimeSnapshot.calculated_at <= decision_utc)
                .order_by(MarketRegimeSnapshot.calculated_at.desc(), MarketRegimeSnapshot.id.desc())
                .first()
            )
    except SQLAlchemyError:
        # Telemetry is optional, including on SQLite DBs awaiting migration.
        return MarketRegimeTradingContext()
    if row is None:
        return MarketRegimeTradingContext()
    calculated_at = row.calculated_at
    if calculated_at.tzinfo is None:
        calculated_at = calculated_at.replace(tzinfo=UTC)
    return MarketRegimeTradingContext(
        snapshot_id=row.id, calculation_date=row.calculation_date,
        calculated_at=calculated_at.astimezone(UTC), state_week_ending=row.state_week_ending,
        stage=row.stage, stage_key=row.stage_key, stage_label=row.stage_label,
        status=row.status, confirmed=bool(row.confirmed),
        combined_score=row.combined_score, kospi_score=row.kospi_score,
        nasdaq_score=row.nasdaq_score, score_change_3w=row.score_change_3w,
        new_bullish_reversal=bool(row.new_bullish_reversal),
        new_bearish_reversal=bool(row.new_bearish_reversal),
        bullish_confirmation_streak=row.bullish_confirmation_streak,
        bearish_confirmation_streak=row.bearish_confirmation_streak,
    )


# ContextVar scopes telemetry to the call, including nested previews/execution,
# while keeping parallel users/workers and subsequent runs independent.
_RUN_CONTEXT: ContextVar[tuple[object, MarketRegimeTradingContext] | None] = ContextVar(
    "market_regime_trading_run", default=None,
)


def get_run_market_regime_context(db, decision_at: datetime | None = None):
    current = _RUN_CONTEXT.get()
    if current is not None and current[0] is db:
        context = current[1]
        if (decision_at is not None and context.calculated_at is not None
                and context.calculated_at > _decision_utc(decision_at)):
            # A nested historical payload cannot borrow a future run snapshot.
            return MarketRegimeTradingContext()
        return context
    return get_market_regime_context(db, decision_at or datetime.now(UTC))


def begin_market_regime_run(db, decision_at: datetime):
    return _RUN_CONTEXT.set((db, get_run_market_regime_context(db, decision_at)))


def end_market_regime_run(token):
    _RUN_CONTEXT.reset(token)


def market_regime_run(method):
    """Capture once at entry and restore the outer scope even after failures."""
    parameters = signature(method)

    @wraps(method)
    def wrapped(*args, **kwargs):
        bound = parameters.bind(*args, **kwargs).arguments
        db = bound.get("db")
        if db is None:
            db = getattr(bound.get("self"), "db", None)
        decision_at = bound.get("decision_timestamp") or bound.get("now") or datetime.now(UTC)
        token = begin_market_regime_run(db, decision_at)
        try:
            return method(*args, **kwargs)
        finally:
            end_market_regime_run(token)

    return wrapped
