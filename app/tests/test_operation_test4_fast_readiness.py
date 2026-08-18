from __future__ import annotations

from time import perf_counter

from app.tests.test_operation_test4_entry import NOW, arm_for_entry, make_service


def test_readiness_does_not_call_candidate_or_possible_order_providers(db_session, tmp_path):
    calls = {"candidate": 0, "possible": 0}

    def candidate(**kwargs):
        calls["candidate"] += 1
        raise AssertionError("heavy candidate analysis must be deferred")

    def possible(**kwargs):
        calls["possible"] += 1
        raise AssertionError("possible-order is candidate-specific")

    service, _, _ = make_service(
        tmp_path,
        candidate=candidate,
        possible_order=possible,
    )
    arm_for_entry(db_session, service)

    started = perf_counter()
    result = service.readiness(db_session, now=NOW)
    elapsed = perf_counter() - started

    assert result["status"] == "ready_for_preflight"
    assert result["candidate_required"] is True
    assert result["heavy_analysis"]["performed"] is False
    assert calls == {"candidate": 0, "possible": 0}
    assert elapsed < 5