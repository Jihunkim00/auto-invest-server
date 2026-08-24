from __future__ import annotations

from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService
from app.services.profile_aware_dry_run_auto_buy_factory import (
    build_profile_aware_dry_run_auto_buy_service,
)


def test_shared_builder_wires_kis_watchlist_preview_to_db_session(
    db_session,
    monkeypatch,
):
    class FakeKisClient:
        def __init__(self, settings, auth_manager):
            self.settings = settings
            self.auth_manager = auth_manager

    monkeypatch.setattr(
        "app.services.profile_aware_dry_run_auto_buy_factory.KisClient",
        FakeKisClient,
    )

    service = build_profile_aware_dry_run_auto_buy_service(db_session)

    assert isinstance(service.preview_service, KisWatchlistPreviewService)
    assert service.preview_service.db is db_session
    assert isinstance(service.preview_service.client, FakeKisClient)
    assert service.target_risk_service.budget_service.position_loader is not None
    assert service.target_risk_service.budget_service.balance_loader is not None
