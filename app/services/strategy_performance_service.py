from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db.models import (
    AgentChatOrderAction,
    OrderLog,
    SignalLog,
    StrategyPerformanceSnapshot,
    TradeRunLog,
)
from app.services.strategy_profile_service import StrategyProfileService


PositionLoader = Callable[[Session, str, str], list[dict[str, Any]]]
_KST = ZoneInfo("Asia/Seoul")
_FILLED_STATUSES = {"FILLED", "PARTIALLY_FILLED", "PARTIAL_FILLED"}
_REJECTED_STATUSES = {"REJECTED", "REJECTED_BY_SAFETY_GATE", "FAILED"}
_REDACTED_KEYS = {
    "account",
    "account_no",
    "cano",
    "appkey",
    "app_key",
    "appsecret",
    "app_secret",
    "approval_key",
    "token",
    "access_token",
    "secret",
}


class StrategyPerformanceService:
    def __init__(
        self,
        *,
        position_loader: PositionLoader | None = None,
        strategy_profiles: StrategyProfileService | None = None,
        fee_rate: float = 0.00015,
    ) -> None:
        self.position_loader = position_loader
        self.strategy_profiles = strategy_profiles or StrategyProfileService()
        self.fee_rate = max(0.0, float(fee_rate))

    def daily(
        self,
        db: Session,
        *,
        provider: str = "kis",
        market: str = "KR",
        date_value: date | str | None = None,
    ) -> dict[str, Any]:
        target_date = _parse_date(date_value)
        start, end = _day_window(target_date)
        summary = self._period_summary(
            db,
            provider=provider,
            market=market,
            start=start,
            end=end,
        )
        return {
            "date": target_date,
            "provider": _provider(provider),
            "market": _market(market),
            "active_profile": summary["active_profile"],
            "realized_pnl": summary["realized_pnl"],
            "unrealized_pnl": summary["unrealized_pnl"],
            "gross_pnl": summary["gross_pnl"],
            "estimated_fees": summary["estimated_fees"],
            "net_pnl_estimated": summary["net_pnl_estimated"],
            "pnl_pct": summary["pnl_pct"],
            "orders_count": summary["orders_count"],
            "filled_orders_count": summary["filled_orders_count"],
            "rejected_orders_count": summary["rejected_orders_count"],
            "winning_trades_count": summary["winning_trades_count"],
            "losing_trades_count": summary["losing_trades_count"],
            "win_rate": summary["win_rate"],
            "data_quality": summary["data_quality"],
            "safety": _safety(),
        }

    def monthly(
        self,
        db: Session,
        *,
        provider: str = "kis",
        market: str = "KR",
        month: str | None = None,
        profile_name: str | None = None,
    ) -> dict[str, Any]:
        month_key, start, end = _month_window(month)
        summary = self._period_summary(
            db,
            provider=provider,
            market=market,
            start=start,
            end=end,
            profile_name=profile_name,
        )
        profile = summary["active_profile"]
        current = summary["pnl_pct"]
        target = float(profile.get("monthly_target_return_pct") or 0)
        max_loss = float(profile.get("monthly_max_loss_pct") or 0)
        target_progress = (current / target * 100) if target > 0 else 0.0
        loss_budget_used = (
            abs(min(current, 0.0)) / abs(max_loss) * 100
            if max_loss < 0
            else 0.0
        )
        target_hit = current >= target if target > 0 else False
        loss_limit_hit = current <= max_loss if max_loss < 0 else False
        stop_after_target = bool(profile.get("stop_after_monthly_target"))
        allowed = not loss_limit_hit and (not target_hit or not stop_after_target)
        block_reason = None
        if loss_limit_hit:
            block_reason = "monthly_loss_limit_hit"
        elif target_hit and stop_after_target:
            block_reason = "monthly_target_hit"
        return {
            "month": month_key,
            "provider": _provider(provider),
            "market": _market(market),
            "active_profile": profile,
            "monthly_target_return_pct": target,
            "monthly_target_min_pct": float(profile.get("monthly_target_min_pct") or 0),
            "monthly_target_max_pct": float(profile.get("monthly_target_max_pct") or 0),
            "current_month_return_pct": current,
            "target_progress_pct": _round_ratio(target_progress),
            "monthly_max_loss_pct": max_loss,
            "loss_budget_used_pct": _round_ratio(loss_budget_used),
            "target_hit": target_hit,
            "loss_limit_hit": loss_limit_hit,
            "realized_pnl": summary["realized_pnl"],
            "unrealized_pnl": summary["unrealized_pnl"],
            "gross_pnl": summary["gross_pnl"],
            "net_pnl_estimated": summary["net_pnl_estimated"],
            "estimated_fees": summary["estimated_fees"],
            "orders_count": summary["orders_count"],
            "filled_orders_count": summary["filled_orders_count"],
            "rejected_orders_count": summary["rejected_orders_count"],
            "winning_trades_count": summary["winning_trades_count"],
            "losing_trades_count": summary["losing_trades_count"],
            "win_rate": summary["win_rate"],
            "average_win": summary["average_win"],
            "average_loss": summary["average_loss"],
            "profit_factor": summary["profit_factor"],
            "max_drawdown_pct": summary["max_drawdown_pct"],
            "new_entries_allowed_by_target": allowed,
            "new_entries_block_reason": block_reason,
            "data_quality": summary["data_quality"],
            "safety": _safety(),
        }

    def trades(
        self,
        db: Session,
        *,
        provider: str = "kis",
        market: str = "KR",
        symbol: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        positions, position_notes = self._load_positions(db, provider, market)
        orders = self._orders(db, provider=provider, market=market)
        items, quality = self._match_orders(
            db,
            orders=orders,
            provider=provider,
            market=market,
            positions=positions,
        )
        quality["notes"] = _dedupe([*quality["notes"], *position_notes])
        if symbol:
            normalized = str(symbol).strip().upper()
            items = [item for item in items if item["symbol"].upper() == normalized]
        if status:
            normalized_status = str(status).strip().lower()
            items = [
                item for item in items
                if str(item.get("status") or "").lower() == normalized_status
            ]
        items.sort(
            key=lambda item: item.get("closed_at") or item.get("created_at") or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        safe_limit = max(1, min(int(limit or 50), 200))
        return {
            "provider": _provider(provider),
            "market": _market(market),
            "count": min(len(items), safe_limit),
            "items": items[:safe_limit],
            "data_quality": quality,
            "safety": _safety(),
        }

    def snapshot(
        self,
        db: Session,
        *,
        provider: str = "kis",
        market: str = "KR",
        period_type: str = "monthly",
        period_key: str | None = None,
    ) -> dict[str, Any]:
        normalized_type = str(period_type or "monthly").strip().lower()
        if normalized_type == "daily":
            payload = self.daily(
                db,
                provider=provider,
                market=market,
                date_value=period_key,
            )
            key = str(payload["date"])
            target_progress = None
            loss_budget = None
            profit_factor = None
            max_drawdown = 0.0
        elif normalized_type == "monthly":
            payload = self.monthly(
                db,
                provider=provider,
                market=market,
                month=period_key,
            )
            key = payload["month"]
            target_progress = payload["target_progress_pct"]
            loss_budget = payload["loss_budget_used_pct"]
            profit_factor = payload["profit_factor"]
            max_drawdown = payload["max_drawdown_pct"]
        else:
            raise ValueError("period_type_must_be_daily_or_monthly")

        profile = payload["active_profile"]
        row = StrategyPerformanceSnapshot(
            provider=payload["provider"],
            market=payload["market"],
            profile_name=str(profile.get("profile_name") or "unknown"),
            period_type=normalized_type,
            period_key=key,
            realized_pnl=payload["realized_pnl"],
            unrealized_pnl=payload["unrealized_pnl"],
            gross_pnl=payload["gross_pnl"],
            estimated_fees=payload["estimated_fees"],
            net_pnl_estimated=payload["net_pnl_estimated"],
            pnl_pct=payload.get("pnl_pct", payload.get("current_month_return_pct", 0)),
            target_progress_pct=target_progress,
            loss_budget_used_pct=loss_budget,
            orders_count=payload["orders_count"],
            filled_orders_count=payload["filled_orders_count"],
            rejected_orders_count=payload["rejected_orders_count"],
            win_rate=payload["win_rate"],
            profit_factor=profit_factor,
            max_drawdown_pct=max_drawdown,
            data_quality=_json(payload.get("data_quality") or {}),
            source_payload=_json(_sanitize_payload(payload)),
            safety_flags=_json(_safety()),
            created_at=datetime.now(UTC),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "status": "saved",
            "snapshot_id": row.id,
            "period_type": normalized_type,
            "period_key": key,
            "safety": _safety(mutation=True),
        }

    def _period_summary(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
        start: datetime,
        end: datetime,
        profile_name: str | None = None,
    ) -> dict[str, Any]:
        active = (
            self.strategy_profiles.get_profile(db, profile_name)
            if profile_name
            else self.strategy_profiles.active_profile(db)
        )
        profile = self.strategy_profiles.serialize_profile(active)
        positions, position_notes = self._load_positions(db, provider, market)
        all_orders = self._orders(db, provider=provider, market=market, before=end)
        items, quality = self._match_orders(
            db,
            orders=all_orders,
            provider=provider,
            market=market,
            positions=positions,
        )
        period_orders = [
            order for order in all_orders
            if start <= _order_event_time(order) < end
        ]
        closed = [
            item for item in items
            if item.get("closed_at") is not None
            and start <= _ensure_aware(item["closed_at"]) < end
            and item.get("realized_pnl") is not None
        ]
        realized_values = [float(item["realized_pnl"]) for item in closed]
        realized = sum(realized_values)
        position_values = self._position_totals(positions)
        unrealized = position_values["unrealized_pnl"]
        basis = sum(
            max(float(item.get("entry_price") or 0) * float(item.get("quantity") or 0), 0)
            for item in closed
        ) + position_values["cost_basis"]
        fees = self._estimated_order_fees(period_orders)
        gross = realized + unrealized
        net = gross - fees
        pnl_pct = net / basis if basis > 0 else 0.0
        wins = [value for value in realized_values if value > 0]
        losses = [value for value in realized_values if value < 0]
        total_closed = len(wins) + len(losses)
        quality["missing_cost_basis"] = bool(position_values["missing_cost_basis"])
        quality["notes"] = _dedupe(
            [
                *quality["notes"],
                *position_notes,
                "fee_estimated",
                "fifo_matching_best_effort",
                "unrealized_is_current_position_snapshot",
            ]
        )
        if position_values["missing_cost_basis"]:
            quality["notes"].append("insufficient_cost_basis")
        return {
            "active_profile": profile,
            "realized_pnl": _round_money(realized),
            "unrealized_pnl": _round_money(unrealized),
            "gross_pnl": _round_money(gross),
            "estimated_fees": _round_money(fees),
            "net_pnl_estimated": _round_money(net),
            "pnl_pct": _round_ratio(pnl_pct),
            "orders_count": len(period_orders),
            "filled_orders_count": sum(1 for row in period_orders if _is_filled(row)),
            "rejected_orders_count": sum(
                1 for row in period_orders
                if str(row.internal_status or "").upper() in _REJECTED_STATUSES
            ),
            "winning_trades_count": len(wins),
            "losing_trades_count": len(losses),
            "win_rate": _round_ratio((len(wins) / total_closed) if total_closed else 0),
            "average_win": _round_money(sum(wins) / len(wins)) if wins else 0.0,
            "average_loss": _round_money(sum(losses) / len(losses)) if losses else 0.0,
            "profit_factor": (
                _round_ratio(sum(wins) / abs(sum(losses)))
                if losses
                else None
            ),
            "max_drawdown_pct": self._max_drawdown_pct(closed),
            "data_quality": quality,
        }

    def _orders(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
        before: datetime | None = None,
    ) -> list[OrderLog]:
        query = db.query(OrderLog).filter(OrderLog.broker == _provider(provider))
        rows = query.order_by(OrderLog.created_at.asc(), OrderLog.id.asc()).all()
        normalized_market = _market(market)
        result = []
        for row in rows:
            row_market = str(row.market or ("KR" if row.broker == "kis" else "US")).upper()
            if row_market != normalized_market:
                continue
            if before is not None and _order_event_time(row) >= before:
                continue
            result.append(row)
        return result

    def _load_positions(
        self,
        db: Session,
        provider: str,
        market: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if self.position_loader is None:
            return [], ["positions_not_loaded"]
        try:
            rows = self.position_loader(db, _provider(provider), _market(market))
            return [
                _sanitize_payload(item)
                for item in rows
                if isinstance(item, dict)
            ], []
        except Exception as exc:
            return [], [f"positions_unavailable:{exc.__class__.__name__}"]

    def _match_orders(
        self,
        db: Session,
        *,
        orders: list[OrderLog],
        provider: str,
        market: str,
        positions: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        lots: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        items: list[dict[str, Any]] = []
        missing_price = 0
        unmatched = 0
        partial = 0
        links = self._order_links(db, orders)

        for order in orders:
            if not _is_filled(order):
                continue
            quantity = _filled_quantity(order)
            price = _fill_price(order)
            if quantity <= 0:
                continue
            if price is None or price <= 0:
                missing_price += 1
                items.append(
                    self._trade_item(
                        order=order,
                        provider=provider,
                        market=market,
                        quantity=quantity,
                        status="average_price_missing",
                        links=links,
                    )
                )
                continue
            side = str(order.side or "").lower()
            if side == "buy":
                lots[order.symbol].append(
                    {
                        "order": order,
                        "remaining": quantity,
                        "price": price,
                        "opened_at": _order_event_time(order),
                    }
                )
                continue
            if side != "sell":
                continue

            remaining = quantity
            matched_any = False
            while remaining > 0 and lots[order.symbol]:
                lot = lots[order.symbol][0]
                matched_qty = min(remaining, lot["remaining"])
                entry = lot["order"]
                realized = (price - lot["price"]) * matched_qty
                entry_fee = lot["price"] * matched_qty * self.fee_rate
                exit_fee = price * matched_qty * self.fee_rate
                item = self._trade_item(
                    order=order,
                    provider=provider,
                    market=market,
                    quantity=matched_qty,
                    status="closed",
                    links=links,
                    entry_order=entry,
                    entry_price=lot["price"],
                    exit_price=price,
                    realized_pnl=realized,
                    net_pnl=realized - entry_fee - exit_fee,
                    created_at=lot["opened_at"],
                    closed_at=_order_event_time(order),
                )
                items.append(item)
                matched_any = True
                remaining -= matched_qty
                lot["remaining"] -= matched_qty
                if lot["remaining"] <= 1e-9:
                    lots[order.symbol].popleft()
            if remaining > 1e-9:
                unmatched += 1
                items.append(
                    self._trade_item(
                        order=order,
                        provider=provider,
                        market=market,
                        quantity=remaining,
                        status="unmatched_sell",
                        links=links,
                        exit_price=price,
                    )
                )
            if matched_any and remaining > 1e-9:
                partial += 1

        position_map = {
            str(item.get("symbol") or "").upper(): item
            for item in positions
            if str(item.get("symbol") or "").strip()
        }
        local_open_symbols: set[str] = set()
        for symbol, symbol_lots in lots.items():
            position = position_map.get(symbol.upper(), {})
            total_lot_cost = sum(
                lot["price"] * lot["remaining"]
                for lot in symbol_lots
            )
            position_unrealized = _float_or_none(position.get("unrealized_pl"))
            current_price = _float_or_none(position.get("current_price"))
            for lot in symbol_lots:
                quantity = lot["remaining"]
                lot_cost = lot["price"] * quantity
                unrealized = None
                if position_unrealized is not None and total_lot_cost > 0:
                    unrealized = position_unrealized * (lot_cost / total_lot_cost)
                elif current_price is not None:
                    unrealized = (current_price - lot["price"]) * quantity
                items.append(
                    self._trade_item(
                        order=lot["order"],
                        provider=provider,
                        market=market,
                        quantity=quantity,
                        status="open",
                        links=links,
                        entry_order=lot["order"],
                        entry_price=lot["price"],
                        current_price=current_price,
                        unrealized_pnl=unrealized,
                        net_pnl=(
                            unrealized - lot_cost * self.fee_rate
                            if unrealized is not None
                            else None
                        ),
                        created_at=lot["opened_at"],
                    )
                )
                local_open_symbols.add(symbol.upper())

        for symbol, position in position_map.items():
            if symbol in local_open_symbols:
                continue
            quantity = _float(position.get("qty") or position.get("quantity"))
            if quantity <= 0:
                continue
            cost_basis = _float_or_none(position.get("cost_basis"))
            current_price = _float_or_none(position.get("current_price"))
            unrealized = _float_or_none(position.get("unrealized_pl"))
            entry_price = (
                cost_basis / quantity
                if cost_basis is not None and cost_basis > 0
                else _float_or_none(position.get("avg_entry_price"))
            )
            if unrealized is None and cost_basis is not None:
                market_value = _float_or_none(
                    position.get("market_value") or position.get("current_value")
                )
                if market_value is not None:
                    unrealized = market_value - cost_basis
            items.append(
                {
                    "order_id": None,
                    "entry_order_id": None,
                    "exit_order_id": None,
                    "symbol": symbol,
                    "symbol_name": position.get("name"),
                    "provider": _provider(provider),
                    "market": _market(market),
                    "side": "buy",
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "exit_price": None,
                    "current_price": current_price,
                    "realized_pnl": None,
                    "unrealized_pnl": _round_optional_money(unrealized),
                    "net_pnl_estimated": _round_optional_money(unrealized),
                    "pnl_pct": (
                        _round_ratio(unrealized / cost_basis)
                        if unrealized is not None and cost_basis and cost_basis > 0
                        else None
                    ),
                    "holding_minutes": None,
                    "decision_source": "position_snapshot",
                    "signal_id": None,
                    "run_id": None,
                    "agent_chat_action_id": None,
                    "risk_flags": [],
                    "gating_notes": [],
                    "created_at": None,
                    "closed_at": None,
                    "status": "open_position",
                    "data_quality": {
                        "is_estimated": True,
                        "missing_cost_basis": not bool(cost_basis and cost_basis > 0),
                    },
                }
            )

        quality = {
            "is_estimated": True,
            "has_complete_fills": missing_price == 0 and unmatched == 0,
            "missing_cost_basis": False,
            "unmatched_orders_count": unmatched,
            "missing_fill_price_count": missing_price,
            "partially_matched_count": partial,
            "notes": [],
        }
        if missing_price:
            quality["notes"].append("average_price_missing")
        if unmatched:
            quality["notes"].append("unmatched_sell")
        if partial:
            quality["notes"].append("partially_matched")
        return items, quality

    def _trade_item(
        self,
        *,
        order: OrderLog,
        provider: str,
        market: str,
        quantity: float,
        status: str,
        links: dict[int, dict[str, Any]],
        entry_order: OrderLog | None = None,
        entry_price: float | None = None,
        exit_price: float | None = None,
        current_price: float | None = None,
        realized_pnl: float | None = None,
        unrealized_pnl: float | None = None,
        net_pnl: float | None = None,
        created_at: datetime | None = None,
        closed_at: datetime | None = None,
    ) -> dict[str, Any]:
        linked = links.get(order.id, {})
        basis = (entry_price or 0) * quantity
        pnl_value = realized_pnl if realized_pnl is not None else unrealized_pnl
        return {
            "order_id": order.id,
            "entry_order_id": entry_order.id if entry_order is not None else None,
            "exit_order_id": order.id if str(order.side or "").lower() == "sell" else None,
            "symbol": order.symbol,
            "symbol_name": linked.get("symbol_name"),
            "provider": _provider(provider),
            "market": _market(market),
            "side": str(order.side or "").lower(),
            "quantity": _round_quantity(quantity),
            "entry_price": _round_optional_money(entry_price),
            "exit_price": _round_optional_money(exit_price),
            "current_price": _round_optional_money(current_price),
            "realized_pnl": _round_optional_money(realized_pnl),
            "unrealized_pnl": _round_optional_money(unrealized_pnl),
            "net_pnl_estimated": _round_optional_money(net_pnl),
            "pnl_pct": (
                _round_ratio(pnl_value / basis)
                if pnl_value is not None and basis > 0
                else None
            ),
            "holding_minutes": _holding_minutes(created_at, closed_at),
            "decision_source": linked.get("decision_source"),
            "signal_id": linked.get("signal_id"),
            "run_id": linked.get("run_id"),
            "agent_chat_action_id": linked.get("agent_chat_action_id"),
            "risk_flags": linked.get("risk_flags") or [],
            "gating_notes": linked.get("gating_notes") or [],
            "created_at": created_at or _order_event_time(entry_order or order),
            "closed_at": closed_at,
            "status": status,
            "data_quality": {
                "is_estimated": True,
                "fill_price_available": bool(entry_price or exit_price),
            },
        }

    def _order_links(
        self,
        db: Session,
        orders: list[OrderLog],
    ) -> dict[int, dict[str, Any]]:
        order_ids = [row.id for row in orders if row.id is not None]
        links: dict[int, dict[str, Any]] = {order_id: {} for order_id in order_ids}
        if not order_ids:
            return links
        for signal in db.query(SignalLog).filter(SignalLog.related_order_id.in_(order_ids)).all():
            target = links.setdefault(signal.related_order_id, {})
            target["signal_id"] = signal.id
            target["decision_source"] = signal.trigger_source or "signal"
            target["risk_flags"] = _string_list(signal.risk_flags)
            target["gating_notes"] = _string_list(signal.gating_notes)
        for run in db.query(TradeRunLog).filter(TradeRunLog.order_id.in_(order_ids)).all():
            target = links.setdefault(run.order_id, {})
            target["run_id"] = run.id
            target["decision_source"] = target.get("decision_source") or run.trigger_source
        for action in (
            db.query(AgentChatOrderAction)
            .filter(AgentChatOrderAction.related_order_id.in_(order_ids))
            .all()
        ):
            target = links.setdefault(action.related_order_id, {})
            target["agent_chat_action_id"] = action.id
            target["symbol_name"] = action.symbol_name
            target["decision_source"] = target.get("decision_source") or "agent_chat"
        return links

    def _position_totals(self, positions: list[dict[str, Any]]) -> dict[str, Any]:
        unrealized = 0.0
        cost_basis = 0.0
        missing = False
        for position in positions:
            basis = _float_or_none(position.get("cost_basis"))
            if basis is None or basis <= 0:
                qty = _float(position.get("qty") or position.get("quantity"))
                avg = _float_or_none(position.get("avg_entry_price"))
                if qty > 0 and avg is not None and avg > 0:
                    basis = qty * avg
                else:
                    missing = True
            if basis is not None and basis > 0:
                cost_basis += basis
            value = _float_or_none(position.get("unrealized_pl"))
            if value is None and basis is not None:
                current_value = _float_or_none(
                    position.get("market_value") or position.get("current_value")
                )
                if current_value is not None:
                    value = current_value - basis
            if value is not None:
                unrealized += value
        return {
            "unrealized_pnl": unrealized,
            "cost_basis": cost_basis,
            "missing_cost_basis": missing,
        }

    def _estimated_order_fees(self, orders: list[OrderLog]) -> float:
        total = 0.0
        for order in orders:
            if not _is_filled(order):
                continue
            price = _fill_price(order)
            quantity = _filled_quantity(order)
            if price is not None and price > 0 and quantity > 0:
                total += price * quantity * self.fee_rate
        return total

    def _max_drawdown_pct(self, closed: list[dict[str, Any]]) -> float:
        ordered = sorted(closed, key=lambda item: item.get("closed_at") or datetime.min.replace(tzinfo=UTC))
        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0
        total_basis = 0.0
        for item in ordered:
            pnl = float(item.get("realized_pnl") or 0)
            cumulative += pnl
            total_basis += float(item.get("entry_price") or 0) * float(item.get("quantity") or 0)
            peak = max(peak, cumulative)
            max_drawdown = min(max_drawdown, cumulative - peak)
        return _round_ratio(max_drawdown / total_basis) if total_basis > 0 else 0.0


def _parse_date(value: date | str | None) -> date:
    if isinstance(value, date):
        return value
    if value:
        return date.fromisoformat(str(value))
    return datetime.now(_KST).date()


def _day_window(value: date) -> tuple[datetime, datetime]:
    start = datetime.combine(value, time.min, tzinfo=_KST).astimezone(UTC)
    return start, start + timedelta(days=1)


def _month_window(value: str | None) -> tuple[str, datetime, datetime]:
    now = datetime.now(_KST)
    raw = str(value or f"{now.year:04d}-{now.month:02d}")
    year, month = (int(part) for part in raw.split("-", 1))
    start_local = datetime(year, month, 1, tzinfo=_KST)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=_KST)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=_KST)
    return raw, start_local.astimezone(UTC), end_local.astimezone(UTC)


def _provider(value: str) -> str:
    return str(value or "kis").strip().lower() or "kis"


def _market(value: str) -> str:
    return str(value or "KR").strip().upper() or "KR"


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _order_event_time(order: OrderLog) -> datetime:
    value = order.filled_at or order.submitted_at or order.created_at or datetime.now(UTC)
    return _ensure_aware(value)


def _is_filled(order: OrderLog) -> bool:
    return (
        str(order.internal_status or "").upper() in _FILLED_STATUSES
        or float(order.filled_qty or 0) > 0
    )


def _filled_quantity(order: OrderLog) -> float:
    return max(float(order.filled_qty or order.requested_qty or order.qty or 0), 0.0)


def _fill_price(order: OrderLog) -> float | None:
    direct = _float_or_none(order.avg_fill_price or order.filled_avg_price)
    if direct is not None and direct > 0:
        return direct
    for payload in (order.last_sync_payload, order.response_payload):
        parsed = _parse_json(payload)
        found = _find_number(
            parsed,
            {"avg_fill_price", "average_fill_price", "filled_avg_price", "avg_prvs"},
        )
        if found is not None and found > 0:
            return found
    return None


def _parse_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {}
    try:
        return json.loads(str(value))
    except Exception:
        return {}


def _find_number(value: Any, keys: set[str]) -> float | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in keys:
                number = _float_or_none(item)
                if number is not None:
                    return number
            nested = _find_number(item, keys)
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for item in value:
            nested = _find_number(item, keys)
            if nested is not None:
                return nested
    return None


def _float(value: Any) -> float:
    return _float_or_none(value) or 0.0


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _string_list(value: Any) -> list[str]:
    parsed = _parse_json(value)
    if isinstance(parsed, list):
        return [str(item)[:240] for item in parsed if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()[:240]]
    return []


def _dedupe(values: list[str]) -> list[str]:
    result = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _holding_minutes(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    return max(0, int((_ensure_aware(end) - _ensure_aware(start)).total_seconds() // 60))


def _round_money(value: float) -> float:
    return round(float(value), 2)


def _round_optional_money(value: float | None) -> float | None:
    return None if value is None else _round_money(value)


def _round_ratio(value: float) -> float:
    return round(float(value), 6)


def _round_quantity(value: float) -> float:
    return round(float(value), 8)


def _safety(*, mutation: bool = False) -> dict[str, Any]:
    return {
        "read_only": not mutation,
        "safe_execution_only": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "validation_called": False,
        "setting_changed": False,
        "scheduler_changed": False,
        "broker_api_called": False,
        "mutation": mutation,
        "snapshot_write_only": mutation,
    }


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key)[:100]: (
                "[REDACTED]"
                if str(key).lower() in _REDACTED_KEYS
                else _sanitize_payload(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value[:200]]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return value[:1000]
    return value


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
