from __future__ import annotations

import json

from app.db.models import AgentPlan
from app.services.agent_operations_service import AgentOperationsService
from app.tests.test_agent_operations_service import _create_plan


def test_operations_queue_does_not_return_secret_text_or_unsafe_metadata(db_session):
    plan = _create_plan(
        db_session,
        {"command_type": "SHOW_POSITIONS", "domain": "position", "intent": "show_positions"},
    )
    row = db_session.get(AgentPlan, plan["id"])
    row.plan_title = "OPENAI_API_KEY=sk-secret authorization: Bearer abc.def"
    row.user_visible_summary = "appkey=secret appsecret=secret account 123456789"
    row.safety_json = json.dumps(
        {"OPENAI_API_KEY": "sk-secret", "raw_account_number": "123456789"},
        ensure_ascii=False,
    )
    db_session.commit()

    payload = AgentOperationsService().review_queue(db_session)
    rendered = json.dumps(payload, default=str)

    assert "sk-secret" not in rendered
    assert "abc.def" not in rendered
    assert "123456789" not in rendered
    assert "raw_account_number" not in rendered
    assert "OPENAI_API_KEY" not in payload["items"][0]["metadata"]
