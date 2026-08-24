from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService
from app.services.profile_aware_dry_run_auto_buy_service import (
    ProfileAwareDryRunAutoBuyService,
)
from app.services.strategy_risk_budget_service import StrategyRiskBudgetService
from app.services.target_aware_risk_service import TargetAwareRiskService


def build_profile_aware_dry_run_auto_buy_service(
    db: Session,
    *,
    client_factory: Callable[[Session], KisClient] | None = None,
) -> ProfileAwareDryRunAutoBuyService:
    """Build the shared KIS preview and target-risk dependency graph.

    Manual dry-run routes, HTTP scheduler calls, and the background scheduler
    must use the same read-only preview path.  The KIS client is cached for the
    lifetime of this service instance, while the database session remains the
    caller's session.
    """

    cache: dict[str, object] = {}

    def client(session: Session) -> KisClient:
        if "client" not in cache:
            if client_factory is not None:
                cache["client"] = client_factory(session)
            else:
                settings = get_settings()
                cache["client"] = KisClient(
                    settings,
                    KisAuthManager(settings, session),
                )
        return cache["client"]  # type: ignore[return-value]

    def positions(session: Session, provider: str, market: str):
        if "positions" not in cache:
            cache["positions"] = (
                client(session).list_positions()
                if provider == "kis" and market == "KR"
                else []
            )
        return cache["positions"]  # type: ignore[return-value]

    def balance(session: Session, provider: str, market: str):
        if "balance" not in cache:
            cache["balance"] = (
                client(session).get_account_balance()
                if provider == "kis" and market == "KR"
                else {}
            )
        return cache["balance"]  # type: ignore[return-value]

    risk_service = TargetAwareRiskService(
        budget_service=StrategyRiskBudgetService(
            position_loader=positions,
            balance_loader=balance,
        )
    )
    return ProfileAwareDryRunAutoBuyService(
        preview_service=KisWatchlistPreviewService(client(db), db=db),
        target_risk_service=risk_service,
    )
