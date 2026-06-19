from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AgentChatMessage
from app.schemas.agent_chat_orchestrator import AgentChatIntent
from app.schemas.agent_chat_tool import AgentChatToolResult


class AgentChatContextService:
    def load_context(
        self,
        db: Session,
        *,
        conversation_key: str,
        limit: int = 30,
    ) -> dict[str, Any]:
        if not conversation_key:
            return {}
        rows = (
            db.query(AgentChatMessage)
            .filter(AgentChatMessage.conversation_key == conversation_key)
            .order_by(AgentChatMessage.id.desc())
            .limit(limit)
            .all()
        )
        for row in rows:
            metadata = self._parse_json_object(row.metadata_json)
            snapshot = metadata.get("context_snapshot")
            if isinstance(snapshot, dict) and snapshot:
                return self._clean_snapshot(snapshot)
            inferred = self._snapshot_from_metadata(metadata)
            if inferred:
                return inferred
        return {}

    def build_snapshot(
        self,
        *,
        intent: AgentChatIntent,
        tool_results: list[AgentChatToolResult],
        previous: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous = previous or {}
        snapshot: dict[str, Any] = dict(previous)
        if intent.symbol:
            snapshot["last_symbol"] = intent.symbol
        if intent.symbol_name:
            snapshot["last_symbol_name"] = intent.symbol_name
        if intent.market:
            snapshot["last_market"] = intent.market
        if intent.provider:
            snapshot["last_provider"] = intent.provider
        snapshot["last_intent"] = intent.category.value

        if intent.selected_tools:
            snapshot["last_tool_name"] = intent.selected_tools[0].tool_name

        for result in tool_results:
            if result.status != "success":
                continue
            if result.result_type == "price":
                price = result.data.get("price") if isinstance(result.data.get("price"), dict) else {}
                snapshot["last_tool_name"] = result.tool_name
                if price.get("symbol"):
                    snapshot["last_symbol"] = price["symbol"]
                if price.get("name"):
                    snapshot["last_symbol_name"] = price["name"]
                if price.get("market"):
                    snapshot["last_market"] = price["market"]
                if price.get("provider"):
                    snapshot["last_provider"] = price["provider"]
                value = price.get("price", price.get("current_price"))
                if value is not None:
                    snapshot["last_price"] = value
            if result.result_type == "positions":
                positions = result.data.get("positions") if isinstance(result.data.get("positions"), list) else []
                first = positions[0] if positions and isinstance(positions[0], dict) else {}
                snapshot["last_tool_name"] = result.tool_name
                symbol = str(first.get("symbol") or "").strip().upper()
                name = str(first.get("name") or "").strip()
                if symbol:
                    snapshot["first_position_symbol"] = symbol
                    snapshot["last_symbol"] = symbol
                if name:
                    snapshot["first_position_name"] = name
                    snapshot["last_symbol_name"] = name
                market = str(result.data.get("market") or "").strip().upper()
                provider = str(result.data.get("provider") or "").strip().lower()
                if market:
                    snapshot["last_market"] = market
                if provider:
                    snapshot["last_provider"] = provider
            if result.result_type == "analysis":
                analysis = result.data.get("analysis")
                if isinstance(analysis, dict) and analysis.get("action"):
                    snapshot["last_analysis_action"] = analysis["action"]

        return self._clean_snapshot(snapshot)

    def _snapshot_from_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        for source_key, target_key in (
            ("symbol", "last_symbol"),
            ("symbol_name", "last_symbol_name"),
            ("market", "last_market"),
            ("provider", "last_provider"),
            ("intent_category", "last_intent"),
        ):
            value = metadata.get(source_key)
            if value not in (None, "", "null"):
                snapshot[target_key] = value
        tools = metadata.get("selected_tools")
        if isinstance(tools, list) and tools:
            first = tools[0]
            if isinstance(first, dict) and first.get("tool_name"):
                snapshot["last_tool_name"] = first["tool_name"]
        return self._clean_snapshot(snapshot)

    def _clean_snapshot(self, value: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in (
            "last_symbol",
            "last_symbol_name",
            "last_market",
            "last_provider",
            "last_intent",
            "last_tool_name",
            "last_price",
            "last_analysis_action",
            "first_position_symbol",
            "first_position_name",
        ):
            raw = value.get(key)
            if raw is None or raw == "" or raw == "null":
                continue
            result[key] = raw
        return result

    def _parse_json_object(self, raw_value: str | None) -> dict[str, Any]:
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
        return {}
