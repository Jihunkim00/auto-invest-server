from __future__ import annotations

from app.services.agent_operations_service import AgentOperationsService
from app.tests.test_agent_operations_service import _create_plan


def test_reviewed_item_is_hidden_from_open_queue_and_visible_by_status(db_session):
    plan = _create_plan(
        db_session,
        {"command_type": "SHOW_POSITIONS", "domain": "position", "intent": "show_positions"},
    )
    key = f"plan_{plan['id']}"
    service = AgentOperationsService()

    service.mark_reviewed(db_session, queue_key=key, request={"reviewer_note": "done"})

    assert all(item["queue_key"] != key for item in service.review_queue(db_session)["items"])
    reviewed = service.review_queue(db_session, status="reviewed")["items"]
    assert reviewed[0]["queue_key"] == key
    assert reviewed[0]["review_status"] == "reviewed"


def test_dismissed_item_is_hidden_from_open_queue_and_visible_by_status(db_session):
    plan = _create_plan(
        db_session,
        {"command_type": "SHOW_POSITIONS", "domain": "position", "intent": "show_positions"},
    )
    key = f"plan_{plan['id']}"
    service = AgentOperationsService()

    service.dismiss(db_session, queue_key=key, request={"reviewer_note": "not relevant"})

    assert all(item["queue_key"] != key for item in service.review_queue(db_session)["items"])
    dismissed = service.review_queue(db_session, status="dismissed")["items"]
    assert dismissed[0]["queue_key"] == key
    assert dismissed[0]["review_status"] == "dismissed"
