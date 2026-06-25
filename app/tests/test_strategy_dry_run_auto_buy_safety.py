from __future__ import annotations

import json

import pytest

from app.db.models import KisOrderValidationLog, OrderLog, RuntimeSetting
from app.tests.test_strategy_dry_run_auto_buy_service import (
    candidate,
    preview,
    request,
    service,
)


def test_dry_run_does_not_submit_validate_or_mutate_settings(
    monkeypatch,
    db_session,
):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_order",
        lambda *args, **kwargs: pytest.fail("submit must not run"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("cash submit must not run"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("manual submit must not run"),
    )
    before_settings = db_session.query(RuntimeSetting).count()

    result = service().run_once(
        db_session,
        request(),
        preview_override=preview(candidate()),
    )

    assert result["safety"]["real_order_submitted"] is False
    assert result["safety"]["validation_called"] is False
    assert result["safety"]["broker_submit_called"] is False
    assert result["safety"]["manual_submit_called"] is False
    assert result["safety"]["setting_changed"] is False
    assert result["safety"]["scheduler_changed"] is False
    assert db_session.query(KisOrderValidationLog).count() == 0
    assert db_session.query(RuntimeSetting).count() == before_settings
    order = db_session.query(OrderLog).one()
    response = json.loads(order.response_payload)
    assert response["real_order_submitted"] is False
    assert response["validation_called"] is False
