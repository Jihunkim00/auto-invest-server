from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import OrderLog, TradeRunLog
from app.main import app


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_empty_review_returns_safe_empty_summary(client, db_session):
    response = client.get("/kis/scheduler/dry-run-review")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "kis_scheduler_dry_run_review"
    assert body["review_only"] is True
    assert body["summary"]["total_runs"] == 0
    assert body["summary"]["no_submit_invariant_ok"] is True
    assert body["summary"]["sell_before_buy_ordering_ok"] is True
    assert body["recent_runs"] == []
    assert body["safety_violations"] == []
    assert db_session.query(OrderLog).count() == 0


def test_review_aggregates_completed_scheduler_dry_run_runs(client, db_session):
    _seed_run(
        db_session,
        slot_label="morning_check",
        result="completed",
        created_days_ago=1,
    )
    _seed_run(
        db_session,
        slot_label="midday_check",
        result="partial",
        created_days_ago=2,
    )

    body = client.get("/kis/scheduler/dry-run-review").json()

    assert body["summary"]["total_runs"] == 2
    assert body["summary"]["completed_count"] == 1
    assert body["summary"]["partial_count"] == 1
    assert body["summary"]["latest_slot_label"] == "morning_check"
    assert body["summary"]["latest_result"] == "completed"
    assert body["latest_recommended_operator_action"] == "review_buy_candidate"


def test_review_aggregates_child_limited_buy_and_sell_results(client, db_session):
    _seed_run(db_session)

    body = client.get("/kis/scheduler/dry-run-review").json()

    assert body["module_summary"]["limited_auto_sell"]["run_count"] == 1
    assert body["module_summary"]["limited_auto_buy"]["run_count"] == 1
    assert body["module_summary"]["scheduler_readiness"]["run_count"] == 1
    assert body["module_summary"]["portfolio_management"]["reviewed_count"] == 1
    modules = [child["module"] for child in body["recent_runs"][0]["child_runs"]]
    assert modules == [
        "scheduler_readiness",
        "portfolio_management",
        "limited_auto_sell",
        "limited_auto_buy",
    ]


def test_review_counts_sell_ready_and_buy_ready_candidates(client, db_session):
    _seed_run(db_session, child_runs=_sell_ready_buy_skipped_children())
    _seed_run(db_session, child_runs=_default_children())

    body = client.get("/kis/scheduler/dry-run-review").json()

    assert body["summary"]["sell_ready_count"] == 1
    assert body["summary"]["buy_ready_count"] == 1
    assert body["module_summary"]["limited_auto_sell"]["sell_ready_count"] == 1
    assert body["module_summary"]["limited_auto_buy"]["buy_ready_count"] == 1


def test_review_counts_buy_skipped_after_sell_review(client, db_session):
    _seed_run(db_session, child_runs=_sell_ready_buy_skipped_children())

    body = client.get("/kis/scheduler/dry-run-review").json()

    assert body["summary"]["buy_skipped_after_sell_review_count"] == 1
    buy = _child(body["recent_runs"][0], "limited_auto_buy")
    assert buy["result"] == "skipped"
    assert buy["primary_block_reason"] == "sell_review_required_before_buy"


def test_review_reports_top_block_reasons(client, db_session):
    _seed_run(
        db_session,
        block_reasons=["scheduler_real_orders_disabled", "dry_run_enabled"],
    )
    _seed_run(
        db_session,
        block_reasons=["scheduler_real_orders_disabled", "no_held_position"],
    )

    body = client.get("/kis/scheduler/dry-run-review").json()

    top = body["top_block_reasons"][0]
    assert top["reason"] == "scheduler_real_orders_disabled"
    assert top["label"] == "Scheduler Real Orders Disabled"
    assert top["count"] == 4


def test_review_detects_broker_submit_called_safety_violation(
    client,
    db_session,
):
    _seed_run(db_session, response_overrides={"broker_submit_called": True})

    body = client.get("/kis/scheduler/dry-run-review").json()

    assert body["summary"]["broker_submit_count"] == 0
    assert body["summary"]["no_submit_invariant_ok"] is False
    assert _violation_reasons(body) == ["broker_submit_called_true"]


def test_review_detects_manual_submit_called_safety_violation(
    client,
    db_session,
):
    _seed_run(db_session, response_overrides={"manual_submit_called": True})

    body = client.get("/kis/scheduler/dry-run-review").json()

    assert body["summary"]["no_submit_invariant_ok"] is False
    assert "manual_submit_called_true" in _violation_reasons(body)


def test_review_detects_child_order_id_safety_violation(client, db_session):
    children = _default_children()
    children[-1]["order_id"] = "dry-run-should-not-have-order"
    _seed_run(db_session, child_runs=children)

    body = client.get("/kis/scheduler/dry-run-review").json()

    assert body["summary"]["no_submit_invariant_ok"] is False
    assert "child_order_id_present" in _violation_reasons(body)


def test_review_detects_buy_before_sell_ordering_violation(client, db_session):
    children = _default_children()
    buy = children.pop()
    sell = children.pop()
    children.extend([buy, sell])
    _seed_run(db_session, child_runs=children)

    body = client.get("/kis/scheduler/dry-run-review").json()

    assert body["summary"]["sell_before_buy_ordering_ok"] is False
    assert "buy_before_sell_ordering_violation" in _violation_reasons(body)


def test_review_respects_limit_and_days_filters(client, db_session):
    _seed_run(db_session, slot_label="old", created_days_ago=60)
    _seed_run(db_session, slot_label="newer", created_days_ago=2)
    _seed_run(db_session, slot_label="newest", created_days_ago=1)

    body = client.get("/kis/scheduler/dry-run-review?days=30&limit=1").json()

    assert body["summary"]["total_runs"] == 1
    assert body["recent_runs"][0]["slot_label"] == "newest"
    assert body["diagnostics"]["source_row_count"] == 2


def test_review_respects_slot_label_and_module_filters(client, db_session):
    _seed_run(db_session, slot_label="morning", child_runs=_default_children())
    _seed_run(
        db_session,
        slot_label="closing",
        child_runs=[
            _scheduler_readiness_child(),
            _portfolio_child(),
            _limited_auto_sell_child(),
        ],
    )

    body = client.get(
        "/kis/scheduler/dry-run-review?slot_label=morning&module=limited_auto_buy"
    ).json()

    assert body["summary"]["total_runs"] == 1
    assert body["recent_runs"][0]["slot_label"] == "morning"
    assert [child["module"] for child in body["recent_runs"][0]["child_runs"]] == [
        "limited_auto_buy"
    ]
    assert body["module_summary"]["limited_auto_buy"]["run_count"] == 1
    assert body["module_summary"]["limited_auto_sell"]["run_count"] == 0


def test_include_raw_false_hides_raw_payload(client, db_session):
    children = _default_children()
    children[-1]["raw_payload"] = {"provider": "kis", "debug": "hidden"}
    _seed_run(db_session, child_runs=children)

    body = client.get("/kis/scheduler/dry-run-review?include_raw=false").json()

    run = body["recent_runs"][0]
    assert "raw_payload" not in run
    assert all("raw_payload" not in child for child in run["child_runs"])


def test_include_raw_true_includes_raw_payload(client, db_session):
    children = _default_children()
    children[-1]["raw_payload"] = {"provider": "kis", "debug": "visible"}
    _seed_run(db_session, child_runs=children)

    body = client.get("/kis/scheduler/dry-run-review?include_raw=true").json()

    run = body["recent_runs"][0]
    assert run["raw_payload"]["provider"] == "kis"
    assert _child(run, "limited_auto_buy")["raw_payload"]["debug"] == "visible"


def test_review_does_not_create_order_log(client, db_session):
    _seed_run(db_session)
    before = db_session.query(OrderLog).count()

    response = client.get("/kis/scheduler/dry-run-review")

    assert response.status_code == 200
    assert db_session.query(OrderLog).count() == before
    assert response.json()["summary"]["order_log_created_count"] == 0


def test_review_does_not_call_broker_or_manual_submit(
    monkeypatch,
    client,
    db_session,
):
    _seed_run(db_session)
    monkeypatch.setattr(
        "app.routes.kis._client",
        lambda db: pytest.fail("review endpoint must not create a broker client"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("manual path must not run"),
    )

    body = client.get("/kis/scheduler/dry-run-review").json()

    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False


def test_review_detects_scheduler_dry_run_order_log_violation(client, db_session):
    _seed_run(db_session)
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            internal_status="SIMULATED",
            request_payload=json.dumps(
                {"mode": "kis_scheduler_dry_run_orchestration"}
            ),
            response_payload=json.dumps(
                {"trigger_source": "scheduler_dry_run_orchestration"}
            ),
            created_at=(datetime.now(UTC) - timedelta(days=1)).replace(
                tzinfo=None
            ),
        )
    )
    db_session.commit()

    body = client.get("/kis/scheduler/dry-run-review").json()

    assert body["summary"]["order_log_created_count"] == 1
    assert body["summary"]["no_submit_invariant_ok"] is False
    assert "scheduler_dry_run_order_log_created" in _violation_reasons(body)


def _seed_run(
    db_session,
    *,
    slot_label: str = "manual_dry_run",
    result: str = "completed",
    child_runs: list[dict] | None = None,
    block_reasons: list[str] | None = None,
    response_overrides: dict | None = None,
    summary_overrides: dict | None = None,
    created_days_ago: int = 1,
) -> TradeRunLog:
    children = child_runs or _default_children()
    reasons = block_reasons or ["scheduler_real_orders_disabled"]
    summary = _summary(children, result=result)
    summary.update(summary_overrides or {})
    payload = {
        "provider": "kis",
        "market": "KR",
        "mode": "kis_scheduler_dry_run_orchestration",
        "trigger_source": "scheduler_dry_run_orchestration",
        "slot_label": slot_label,
        "result": result,
        "readiness_only": True,
        "dry_run": True,
        "scheduler_real_orders_enabled": False,
        "real_order_submit_allowed": False,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "child_runs": children,
        "summary": summary,
        "block_reasons": reasons,
        "safety": {
            "scheduler_dry_run_orchestration": True,
            "readiness_only": True,
            "no_broker_submit": True,
            "no_manual_submit": True,
            "no_order_log_created": True,
            "scheduler_real_orders_enabled": False,
            "kis_scheduler_allow_real_orders": False,
        },
        "diagnostics": {},
    }
    payload.update(response_overrides or {})
    created_at = (datetime.now(UTC) - timedelta(days=created_days_ago)).replace(
        tzinfo=None
    )
    row = TradeRunLog(
        run_key=f"scheduler-dry-run-review-{slot_label}-{created_days_ago}",
        trigger_source="scheduler_dry_run_orchestration",
        symbol="WATCHLIST",
        mode="kis_scheduler_dry_run_orchestration",
        stage="done",
        result=result,
        reason=summary["primary_block_reason"],
        request_payload=json.dumps(
            {
                "mode": "kis_scheduler_dry_run_orchestration",
                "trigger_source": "scheduler_dry_run_orchestration",
                "slot_label": slot_label,
            }
        ),
        response_payload=json.dumps(payload),
        created_at=created_at,
    )
    db_session.add(row)
    db_session.commit()
    return row


def _summary(children: list[dict], *, result: str) -> dict:
    sell = _find_child(children, "limited_auto_sell")
    buy = _find_child(children, "limited_auto_buy")
    primary = "scheduler_real_orders_disabled"
    return {
        "modules_requested": [
            "scheduler_readiness",
            "portfolio_management",
            "limited_auto_sell",
            "limited_auto_buy",
        ],
        "modules_completed": [
            child["module"]
            for child in children
            if child.get("result") not in {"blocked", "error"}
        ],
        "modules_blocked": [
            child["module"]
            for child in children
            if child.get("result") in {"blocked", "error"}
            or child.get("primary_block_reason")
        ],
        "sell_candidates_reviewed": _summary_int(sell, "candidates_reviewed"),
        "buy_candidates_reviewed": _summary_int(buy, "candidates_reviewed"),
        "sell_ready_count": _summary_int(sell, "ready_count"),
        "buy_ready_count": _summary_int(buy, "ready_count"),
        "submitted_order_count": 0,
        "broker_submit_count": 0,
        "manual_submit_count": 0,
        "real_order_submit_allowed": False,
        "primary_block_reason": primary,
        "top_block_reasons": [primary],
        "next_recommended_operator_action": "review_buy_candidate"
        if _summary_int(buy, "ready_count") > 0
        else "review_scheduler_readiness_blocks",
    }


def _default_children() -> list[dict]:
    return [
        _scheduler_readiness_child(),
        _portfolio_child(),
        _limited_auto_sell_child(),
        _limited_auto_buy_child(),
    ]


def _sell_ready_buy_skipped_children() -> list[dict]:
    return [
        _scheduler_readiness_child(),
        _portfolio_child(),
        _limited_auto_sell_child(
            result="preview_only",
            action="sell_ready",
            symbol="005930",
            primary_block_reason="stop_loss_candidate_ready_read_only",
            block_reasons=["preflight_read_only_no_submit"],
            ready_count=1,
            candidates_reviewed=1,
        ),
        _limited_auto_buy_child(
            result="skipped",
            action="hold",
            symbol=None,
            status="after_sell_review",
            primary_block_reason="sell_review_required_before_buy",
            block_reasons=["sell_review_required_before_buy"],
            ready_count=0,
            candidates_reviewed=0,
        ),
    ]


def _scheduler_readiness_child() -> dict:
    return _child_payload(
        "scheduler_readiness",
        result="completed",
        action="hold",
        status="DISABLED",
        primary_block_reason="scheduler_real_orders_disabled",
        block_reasons=["scheduler_real_orders_disabled"],
    )


def _portfolio_child() -> dict:
    return _child_payload(
        "portfolio_management",
        result="completed",
        action="review_positions",
        status="read_only",
    )


def _limited_auto_sell_child(
    *,
    result: str = "blocked",
    action: str = "hold",
    symbol: str | None = "005930",
    status: str = "ok",
    primary_block_reason: str | None = "no_held_position",
    block_reasons: list[str] | None = None,
    ready_count: int = 0,
    candidates_reviewed: int = 1,
) -> dict:
    return _child_payload(
        "limited_auto_sell",
        result=result,
        action=action,
        symbol=symbol,
        status=status,
        primary_block_reason=primary_block_reason,
        block_reasons=block_reasons or ["no_held_position"],
        ready_count=ready_count,
        candidates_reviewed=candidates_reviewed,
        mode="kis_limited_auto_stop_loss_preflight",
        source="kis_limited_auto_stop_loss",
        trigger_source="kis_limited_auto_sell",
    )


def _limited_auto_buy_child(
    *,
    result: str = "ready",
    action: str = "buy_ready",
    symbol: str | None = "035420",
    status: str = "ok",
    primary_block_reason: str | None = "dry_run_enabled",
    block_reasons: list[str] | None = None,
    ready_count: int = 1,
    candidates_reviewed: int = 1,
) -> dict:
    return _child_payload(
        "limited_auto_buy",
        result=result,
        action=action,
        symbol=symbol,
        status=status,
        primary_block_reason=primary_block_reason,
        block_reasons=block_reasons or ["dry_run_enabled"],
        ready_count=ready_count,
        candidates_reviewed=candidates_reviewed,
        mode="kis_limited_auto_buy_preflight",
        source="kis_limited_auto_buy",
        trigger_source="limited_auto_buy_preflight",
    )


def _child_payload(
    module: str,
    *,
    result: str,
    action: str,
    status: str,
    symbol: str | None = None,
    primary_block_reason: str | None = None,
    block_reasons: list[str] | None = None,
    ready_count: int = 0,
    candidates_reviewed: int = 0,
    mode: str | None = None,
    source: str | None = None,
    trigger_source: str = "scheduler_dry_run_orchestration",
) -> dict:
    return {
        "module": module,
        "result": result,
        "action": action,
        "symbol": symbol,
        "status": status,
        "primary_block_reason": primary_block_reason,
        "block_reasons": block_reasons or [],
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "order_id": None,
        "source": source or module,
        "mode": mode or module,
        "trigger_source": trigger_source,
        "summary": {
            "candidates_reviewed": candidates_reviewed,
            "ready_count": ready_count,
        },
    }


def _find_child(children: list[dict], module: str) -> dict:
    for child in children:
        if child.get("module") == module:
            return child
    return {}


def _summary_int(child: dict, key: str) -> int:
    summary = child.get("summary") if isinstance(child.get("summary"), dict) else {}
    try:
        return int(summary.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _child(run: dict, module: str) -> dict:
    for child in run["child_runs"]:
        if child["module"] == module:
            return child
    pytest.fail(f"missing child module {module}")


def _violation_reasons(body: dict) -> list[str]:
    return [item["reason"] for item in body["safety_violations"]]
