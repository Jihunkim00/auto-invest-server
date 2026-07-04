from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.db.models import (
    OrderLog,
    SignalLog,
    StrategyAutoBuyPromotion,
    StrategyLiveAutoBuyAttempt,
    StrategyLiveAutoExitAttempt,
    TradeRunLog,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload


PositionSnapshotLoader = Callable[[Session, str, str], list[dict[str, Any]]]

FILLED_STATUSES = {"FILLED", "PARTIALLY_FILLED", "PARTIAL_FILLED"}
SUBMITTED_STATUSES = {"REQUESTED", "SUBMITTED", "ACCEPTED", "PENDING_SYNC"}
PROVIDER = "kis"
MARKET = "KR"


class PositionLifecycleAuditService:
    """Read-only lifecycle reconstruction from local audit tables."""

    def __init__(
        self,
        *,
        position_loader: PositionSnapshotLoader | None = None,
    ) -> None:
        self.position_loader = position_loader

    def list(
        self,
        db: Session,
        *,
        symbol: str | None = None,
        provider: str = PROVIDER,
        market: str = MARKET,
        status: str = "all",
        limit: int = 50,
        include_events: bool = True,
    ) -> dict[str, Any]:
        normalized_provider = _provider(provider)
        normalized_market = _market(market)
        normalized_symbol = _normalize_symbol(symbol)
        normalized_status = _status(status)
        safe_limit = max(1, min(int(limit or 50), 200))

        orders = self._orders(
            db,
            provider=normalized_provider,
            market=normalized_market,
            symbol=normalized_symbol,
        )
        links = self._links(
            db,
            provider=normalized_provider,
            market=normalized_market,
            symbol=normalized_symbol,
            orders=orders,
        )
        positions, position_flags = self._positions(
            db,
            provider=normalized_provider,
            market=normalized_market,
        )
        if normalized_symbol:
            positions = [
                item
                for item in positions
                if _normalize_symbol(item.get("symbol") or item.get("pdno"))
                == normalized_symbol
            ]

        items = self._items(
            orders=orders,
            links=links,
            positions=positions,
            provider=normalized_provider,
            market=normalized_market,
            include_events=include_events,
        )
        if normalized_status != "all":
            items = [
                item
                for item in items
                if str(item.get("lifecycle_status") or "").lower()
                == normalized_status
            ]
        items.sort(key=_item_sort_time, reverse=True)
        items = items[:safe_limit]

        return sanitize_kis_payload(
            {
                "provider": normalized_provider,
                "market": normalized_market,
                "generated_at": datetime.now(UTC).isoformat(),
                "items": items,
                "totals": _totals(items),
                "safety": _safety(),
                "audit_flags": _dedupe(["read_only_lifecycle", *position_flags]),
            }
        )

    def detail(
        self,
        db: Session,
        *,
        symbol: str,
        provider: str = PROVIDER,
        market: str = MARKET,
        status: str = "all",
        include_events: bool = True,
    ) -> dict[str, Any]:
        return self.list(
            db,
            symbol=symbol,
            provider=provider,
            market=market,
            status=status,
            limit=50,
            include_events=include_events,
        )

    def _orders(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
        symbol: str | None,
    ) -> list[OrderLog]:
        query = db.query(OrderLog).filter(OrderLog.broker == provider)
        if symbol:
            query = query.filter(OrderLog.symbol == symbol)
        rows = query.order_by(OrderLog.created_at.asc(), OrderLog.id.asc()).all()
        return [row for row in rows if _order_market(row) == market]

    def _links(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
        symbol: str | None,
        orders: list[OrderLog],
    ) -> dict[str, Any]:
        order_ids = [int(row.id) for row in orders if row.id is not None]
        buy_attempt_query = (
            db.query(StrategyLiveAutoBuyAttempt)
            .filter(StrategyLiveAutoBuyAttempt.provider == provider)
            .filter(StrategyLiveAutoBuyAttempt.market == market)
        )
        sell_attempt_query = (
            db.query(StrategyLiveAutoExitAttempt)
            .filter(StrategyLiveAutoExitAttempt.provider == provider)
            .filter(StrategyLiveAutoExitAttempt.market == market)
        )
        promotion_query = (
            db.query(StrategyAutoBuyPromotion)
            .filter(StrategyAutoBuyPromotion.provider == provider)
            .filter(StrategyAutoBuyPromotion.market == market)
        )
        if symbol:
            buy_attempt_query = buy_attempt_query.filter(
                StrategyLiveAutoBuyAttempt.symbol == symbol
            )
            sell_attempt_query = sell_attempt_query.filter(
                StrategyLiveAutoExitAttempt.symbol == symbol
            )
            promotion_query = promotion_query.filter(
                StrategyAutoBuyPromotion.symbol == symbol
            )

        buy_attempts = buy_attempt_query.order_by(
            StrategyLiveAutoBuyAttempt.created_at.asc(),
            StrategyLiveAutoBuyAttempt.id.asc(),
        ).all()
        sell_attempts = sell_attempt_query.order_by(
            StrategyLiveAutoExitAttempt.created_at.asc(),
            StrategyLiveAutoExitAttempt.id.asc(),
        ).all()
        promotions = promotion_query.order_by(
            StrategyAutoBuyPromotion.created_at.asc(),
            StrategyAutoBuyPromotion.id.asc(),
        ).all()

        signals: list[SignalLog] = []
        runs: list[TradeRunLog] = []
        if order_ids:
            signals = (
                db.query(SignalLog)
                .filter(SignalLog.related_order_id.in_(order_ids))
                .all()
            )
            runs = db.query(TradeRunLog).filter(TradeRunLog.order_id.in_(order_ids)).all()

        return {
            "buy_attempt_by_order": _attempt_by_order(buy_attempts),
            "sell_attempt_by_order": _attempt_by_order(sell_attempts),
            "buy_attempt_by_id": {
                int(row.id): row for row in buy_attempts if row.id is not None
            },
            "sell_attempts_by_symbol": _attempts_by_symbol(sell_attempts),
            "promotions": promotions,
            "promotion_by_order": _promotion_by_order(promotions),
            "promotion_by_attempt": _promotion_by_attempt(promotions),
            "promotions_by_symbol": _promotions_by_symbol(promotions),
            "signal_by_order": {
                int(row.related_order_id): row
                for row in signals
                if row.related_order_id is not None
            },
            "run_by_order": {
                int(row.order_id): row for row in runs if row.order_id is not None
            },
        }

    def _positions(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if self.position_loader is None:
            return [], ["cached_position_snapshot_missing"]
        try:
            rows = self.position_loader(db, provider, market)
        except Exception as exc:
            return [], [f"cached_position_snapshot_unavailable:{exc.__class__.__name__}"]
        positions = [
            _normalize_position(item)
            for item in rows
            if isinstance(item, dict) and _position_qty(item) > 0
        ]
        return positions, []

    def _items(
        self,
        *,
        orders: list[OrderLog],
        links: dict[str, Any],
        positions: list[dict[str, Any]],
        provider: str,
        market: str,
        include_events: bool,
    ) -> list[dict[str, Any]]:
        lots: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        items: list[dict[str, Any]] = []
        position_map = {
            str(item.get("symbol") or "").upper(): item
            for item in positions
            if str(item.get("symbol") or "").strip()
        }
        open_lot_qty: dict[str, float] = defaultdict(float)
        closed_index = 0

        for order in orders:
            if not _is_filled(order):
                continue
            quantity = _filled_quantity(order)
            if quantity <= 0:
                continue
            side = str(order.side or "").strip().lower()
            if side == "buy":
                lot = self._entry_lot(
                    order,
                    links=links,
                    provider=provider,
                    market=market,
                    quantity=quantity,
                    include_events=include_events,
                )
                lots[order.symbol].append(lot)
                open_lot_qty[order.symbol] += quantity
                continue
            if side != "sell":
                continue

            remaining = quantity
            while remaining > 1e-9 and lots[order.symbol]:
                lot = lots[order.symbol][0]
                matched = min(remaining, float(lot["remaining"]))
                closed_index += 1
                items.append(
                    self._closed_item(
                        entry_lot=lot,
                        exit_order=order,
                        links=links,
                        provider=provider,
                        market=market,
                        quantity=matched,
                        item_index=closed_index,
                        include_events=include_events,
                    )
                )
                remaining -= matched
                lot["remaining"] = float(lot["remaining"]) - matched
                open_lot_qty[order.symbol] -= matched
                if float(lot["remaining"]) <= 1e-9:
                    lots[order.symbol].popleft()
            if remaining > 1e-9:
                closed_index += 1
                items.append(
                    self._unmatched_sell_item(
                        order,
                        links=links,
                        provider=provider,
                        market=market,
                        quantity=remaining,
                        item_index=closed_index,
                        include_events=include_events,
                    )
                )

        for symbol, symbol_lots in lots.items():
            position = position_map.get(symbol.upper(), {})
            for lot in symbol_lots:
                if float(lot["remaining"]) <= 1e-9:
                    continue
                items.append(
                    self._open_item(
                        entry_lot=lot,
                        links=links,
                        provider=provider,
                        market=market,
                        position=position,
                        include_events=include_events,
                    )
                )

        for symbol, position in position_map.items():
            residual_qty = _position_qty(position) - open_lot_qty.get(symbol, 0.0)
            if residual_qty <= 1e-9:
                continue
            items.append(
                self._position_snapshot_item(
                    position,
                    links=links,
                    provider=provider,
                    market=market,
                    quantity=residual_qty,
                    include_events=include_events,
                )
            )
        return items

    def _entry_lot(
        self,
        order: OrderLog,
        *,
        links: dict[str, Any],
        provider: str,
        market: str,
        quantity: float,
        include_events: bool,
    ) -> dict[str, Any]:
        attempt = links["buy_attempt_by_order"].get(order.id)
        promotion = _promotion_for_entry(order, attempt, links)
        signal = links["signal_by_order"].get(order.id)
        price = _fill_price(order)
        return {
            "order": order,
            "attempt": attempt,
            "promotion": promotion,
            "signal": signal,
            "quantity": quantity,
            "remaining": quantity,
            "price": price,
            "events": (
                self._entry_events(
                    order,
                    attempt=attempt,
                    promotion=promotion,
                    provider=provider,
                    market=market,
                )
                if include_events
                else []
            ),
        }

    def _closed_item(
        self,
        *,
        entry_lot: dict[str, Any],
        exit_order: OrderLog,
        links: dict[str, Any],
        provider: str,
        market: str,
        quantity: float,
        item_index: int,
        include_events: bool,
    ) -> dict[str, Any]:
        entry_order: OrderLog = entry_lot["order"]
        entry_attempt = entry_lot.get("attempt")
        exit_attempt = links["sell_attempt_by_order"].get(exit_order.id)
        promotion = entry_lot.get("promotion")
        signal = entry_lot.get("signal") or links["signal_by_order"].get(entry_order.id)
        entry_price = _float_or_none(entry_lot.get("price"))
        exit_price = _fill_price(exit_order)
        cost_basis = _notional(quantity, entry_price)
        exit_notional = _notional(quantity, exit_price)
        realized = (
            _round_money(exit_notional - cost_basis)
            if exit_notional is not None and cost_basis is not None
            else None
        )
        audit_flags = _dedupe(
            [
                "read_only_lifecycle",
                "average_entry_price_missing" if entry_price is None else "",
                "average_exit_price_missing" if exit_price is None else "",
                "calculation_incomplete"
                if realized is None or cost_basis is None or cost_basis <= 0
                else "",
            ]
        )
        events = []
        if include_events:
            events = [
                *entry_lot.get("events", []),
                *self._exit_events(exit_order, attempt=exit_attempt),
                _event(
                    _order_event_time(exit_order),
                    "position_closed",
                    "Position closed",
                    _order_status(exit_order),
                    "position_lifecycle",
                    f"order:{exit_order.id}",
                    f"{exit_order.symbol} position closed for {quantity:g} share(s).",
                    safety_flags=["read_only_lifecycle"],
                ),
            ]
        return _item(
            lifecycle_id=(
                f"{provider}:{market}:{entry_order.symbol}:"
                f"buy-{entry_order.id}:sell-{exit_order.id}:{item_index}"
            ),
            symbol=entry_order.symbol,
            name=_best_name(entry_attempt, promotion, None),
            provider=provider,
            market=market,
            lifecycle_status="closed",
            entry_source=_entry_source(entry_order, entry_attempt, promotion),
            entry_order_id=entry_order.id,
            entry_broker_order_id=entry_order.broker_order_id,
            entry_kis_odno=entry_order.kis_odno,
            entry_submitted_at=_iso(entry_order.submitted_at),
            entry_filled_at=_iso(entry_order.filled_at or _order_event_time(entry_order)),
            entry_quantity=_round_quantity(quantity),
            entry_average_price=_round_optional_money(entry_price),
            entry_notional=_round_optional_money(cost_basis),
            related_promotion_id=promotion.id if promotion is not None else None,
            related_signal_id=signal.id if signal is not None else None,
            current_quantity=0,
            current_price=None,
            current_value=None,
            cost_basis=_round_optional_money(cost_basis),
            unrealized_pl=None,
            unrealized_pl_pct=None,
            exit_order_id=exit_order.id,
            exit_broker_order_id=exit_order.broker_order_id,
            exit_kis_odno=exit_order.kis_odno,
            exit_submitted_at=_iso(exit_order.submitted_at),
            exit_filled_at=_iso(exit_order.filled_at or _order_event_time(exit_order)),
            exit_quantity=_round_quantity(quantity),
            exit_average_price=_round_optional_money(exit_price),
            exit_notional=_round_optional_money(exit_notional),
            realized_pl=realized,
            realized_pl_pct=(
                _round_ratio(realized / cost_basis)
                if realized is not None and cost_basis and cost_basis > 0
                else None
            ),
            fees=None,
            holding_period_minutes=_holding_minutes(
                _order_event_time(entry_order),
                _order_event_time(exit_order),
            ),
            latest_status=_order_status(exit_order),
            latest_broker_status=_broker_status(exit_order),
            risk_flags=_dedupe(
                _flags_from_order(entry_order)
                + _flags_from_order(exit_order)
                + _flags_from_attempt(entry_attempt)
                + _flags_from_attempt(exit_attempt)
                + _flags_from_promotion(promotion)
            ),
            gating_notes=_dedupe(
                _notes_from_order(entry_order)
                + _notes_from_order(exit_order)
                + _notes_from_attempt(entry_attempt)
                + _notes_from_attempt(exit_attempt)
                + _notes_from_promotion(promotion)
            ),
            audit_flags=audit_flags,
            next_safe_action=(
                "review_missing_lifecycle_data"
                if "calculation_incomplete" in audit_flags
                else "review_audit_trail"
            ),
            events=_sorted_events(events),
        )

    def _open_item(
        self,
        *,
        entry_lot: dict[str, Any],
        links: dict[str, Any],
        provider: str,
        market: str,
        position: dict[str, Any],
        include_events: bool,
    ) -> dict[str, Any]:
        entry_order: OrderLog = entry_lot["order"]
        entry_attempt = entry_lot.get("attempt")
        promotion = entry_lot.get("promotion")
        signal = entry_lot.get("signal")
        quantity = float(entry_lot["remaining"])
        entry_price = _float_or_none(entry_lot.get("price"))
        snapshot_price = _position_current_price(position)
        current_value = _notional(quantity, snapshot_price)
        if current_value is None:
            current_value = _allocated_current_value(position, quantity=quantity)
        cost_basis = _notional(quantity, entry_price)
        if cost_basis is None:
            cost_basis = _position_cost_basis(position, quantity=quantity)
        unrealized = (
            _round_money(current_value - cost_basis)
            if current_value is not None and cost_basis is not None
            else _allocated_unrealized(position, quantity=quantity)
        )
        audit_flags = _dedupe(
            [
                "read_only_lifecycle",
                "current_position_snapshot_missing" if not position else "",
                "cost_basis_missing" if cost_basis is None or cost_basis <= 0 else "",
                "current_value_missing" if current_value is None else "",
                "calculation_incomplete"
                if unrealized is None or cost_basis is None or cost_basis <= 0
                else "",
            ]
        )
        standalone_sell_events = []
        if include_events:
            standalone_sell_events = self._standalone_sell_attempt_events(
                symbol=entry_order.symbol,
                links=links,
            )
        events = []
        if include_events:
            events = [
                *entry_lot.get("events", []),
                _event(
                    _order_event_time(entry_order),
                    "position_opened",
                    "Position opened",
                    _order_status(entry_order),
                    "position_lifecycle",
                    f"order:{entry_order.id}",
                    f"{entry_order.symbol} position opened for {quantity:g} share(s).",
                    safety_flags=["read_only_lifecycle"],
                ),
                *standalone_sell_events,
            ]
        return _item(
            lifecycle_id=f"{provider}:{market}:{entry_order.symbol}:buy-{entry_order.id}:open",
            symbol=entry_order.symbol,
            name=_best_name(entry_attempt, promotion, position),
            provider=provider,
            market=market,
            lifecycle_status="open",
            entry_source=_entry_source(entry_order, entry_attempt, promotion),
            entry_order_id=entry_order.id,
            entry_broker_order_id=entry_order.broker_order_id,
            entry_kis_odno=entry_order.kis_odno,
            entry_submitted_at=_iso(entry_order.submitted_at),
            entry_filled_at=_iso(entry_order.filled_at or _order_event_time(entry_order)),
            entry_quantity=_round_quantity(quantity),
            entry_average_price=_round_optional_money(entry_price),
            entry_notional=_round_optional_money(cost_basis),
            related_promotion_id=promotion.id if promotion is not None else None,
            related_signal_id=signal.id if signal is not None else None,
            current_quantity=_round_quantity(quantity),
            current_price=_round_optional_money(snapshot_price),
            current_value=_round_optional_money(current_value),
            cost_basis=_round_optional_money(cost_basis),
            unrealized_pl=_round_optional_money(unrealized),
            unrealized_pl_pct=(
                _round_ratio(unrealized / cost_basis)
                if unrealized is not None and cost_basis and cost_basis > 0
                else None
            ),
            latest_status=_order_status(entry_order),
            latest_broker_status=_broker_status(entry_order),
            risk_flags=_dedupe(
                _flags_from_order(entry_order)
                + _flags_from_attempt(entry_attempt)
                + _flags_from_promotion(promotion)
            ),
            gating_notes=_dedupe(
                _notes_from_order(entry_order)
                + _notes_from_attempt(entry_attempt)
                + _notes_from_promotion(promotion)
            ),
            audit_flags=audit_flags,
            next_safe_action=(
                "review_missing_lifecycle_data"
                if "calculation_incomplete" in audit_flags
                else "monitor_or_run_sell_preflight"
            ),
            events=_sorted_events(events),
        )

    def _position_snapshot_item(
        self,
        position: dict[str, Any],
        *,
        links: dict[str, Any],
        provider: str,
        market: str,
        quantity: float,
        include_events: bool,
    ) -> dict[str, Any]:
        symbol = str(position.get("symbol") or "").upper()
        avg_price = _position_average_price(position)
        cost_basis = _position_cost_basis(position, quantity=quantity)
        current_price = _position_current_price(position)
        current_value = _notional(quantity, current_price)
        if current_value is None:
            current_value = _allocated_current_value(position, quantity=quantity)
        unrealized = _allocated_unrealized(position, quantity=quantity)
        if unrealized is None and current_value is not None and cost_basis is not None:
            unrealized = current_value - cost_basis
        audit_flags = _dedupe(
            [
                "read_only_lifecycle",
                "entry_order_missing",
                "cost_basis_missing" if cost_basis is None or cost_basis <= 0 else "",
                "calculation_incomplete"
                if unrealized is None or cost_basis is None or cost_basis <= 0
                else "",
            ]
        )
        events = (
            [
                _event(
                    None,
                    "position_opened",
                    "Position observed",
                    "open",
                    "cached_position_snapshot",
                    f"symbol:{symbol}",
                    "Position exists in cached broker snapshot; local entry order is missing.",
                    safety_flags=["read_only_lifecycle", "entry_order_missing"],
                ),
                *self._standalone_sell_attempt_events(symbol=symbol, links=links),
            ]
            if include_events
            else []
        )
        return _item(
            lifecycle_id=f"{provider}:{market}:{symbol}:position-snapshot",
            symbol=symbol,
            name=_best_name(None, None, position),
            provider=provider,
            market=market,
            lifecycle_status="open",
            entry_source="unknown",
            entry_quantity=_round_quantity(quantity),
            entry_average_price=_round_optional_money(avg_price),
            entry_notional=_round_optional_money(cost_basis),
            current_quantity=_round_quantity(quantity),
            current_price=_round_optional_money(current_price),
            current_value=_round_optional_money(current_value),
            cost_basis=_round_optional_money(cost_basis),
            unrealized_pl=_round_optional_money(unrealized),
            unrealized_pl_pct=(
                _round_ratio(unrealized / cost_basis)
                if unrealized is not None and cost_basis and cost_basis > 0
                else None
            ),
            latest_status="open_position_snapshot",
            latest_broker_status=None,
            risk_flags=[],
            gating_notes=[
                "Local entry order was not found; lifecycle is based on cached position snapshot."
            ],
            audit_flags=audit_flags,
            next_safe_action=(
                "review_missing_lifecycle_data"
                if "calculation_incomplete" in audit_flags
                else "monitor_or_run_sell_preflight"
            ),
            events=_sorted_events(events),
        )

    def _unmatched_sell_item(
        self,
        order: OrderLog,
        *,
        links: dict[str, Any],
        provider: str,
        market: str,
        quantity: float,
        item_index: int,
        include_events: bool,
    ) -> dict[str, Any]:
        exit_attempt = links["sell_attempt_by_order"].get(order.id)
        exit_price = _fill_price(order)
        exit_notional = _notional(quantity, exit_price)
        events = self._exit_events(order, attempt=exit_attempt) if include_events else []
        return _item(
            lifecycle_id=f"{provider}:{market}:{order.symbol}:sell-{order.id}:unmatched:{item_index}",
            symbol=order.symbol,
            name=_best_name(exit_attempt, None, None),
            provider=provider,
            market=market,
            lifecycle_status="unknown",
            entry_source="unknown",
            current_quantity=0,
            exit_order_id=order.id,
            exit_broker_order_id=order.broker_order_id,
            exit_kis_odno=order.kis_odno,
            exit_submitted_at=_iso(order.submitted_at),
            exit_filled_at=_iso(order.filled_at or _order_event_time(order)),
            exit_quantity=_round_quantity(quantity),
            exit_average_price=_round_optional_money(exit_price),
            exit_notional=_round_optional_money(exit_notional),
            latest_status=_order_status(order),
            latest_broker_status=_broker_status(order),
            risk_flags=_dedupe(
                _flags_from_order(order) + _flags_from_attempt(exit_attempt)
            ),
            gating_notes=_dedupe(
                _notes_from_order(order) + _notes_from_attempt(exit_attempt)
            ),
            audit_flags=[
                "read_only_lifecycle",
                "entry_order_missing",
                "calculation_incomplete",
            ],
            next_safe_action="review_missing_lifecycle_data",
            events=_sorted_events(events),
        )

    def _entry_events(
        self,
        order: OrderLog,
        *,
        attempt: StrategyLiveAutoBuyAttempt | None,
        promotion: StrategyAutoBuyPromotion | None,
        provider: str,
        market: str,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if promotion is not None:
            events.append(
                _event(
                    _aware(promotion.created_at),
                    "promotion_created",
                    "Promotion created",
                    promotion.status,
                    "strategy_auto_buy_promotion",
                    f"promotion:{promotion.id}",
                    promotion.promotion_reason,
                    safety_flags=["promotion_is_not_order", "read_only_lifecycle"],
                    real_order_submitted=False,
                    broker_submit_called=False,
                    manual_submit_called=False,
                )
            )
            reviewed_at = promotion.acknowledged_at or promotion.converted_at
            if reviewed_at is not None:
                events.append(
                    _event(
                        _aware(reviewed_at),
                        "promotion_reviewed",
                        "Promotion reviewed",
                        promotion.status,
                        "strategy_auto_buy_promotion",
                        f"promotion:{promotion.id}",
                        promotion.conversion_status or promotion.status,
                        safety_flags=["promotion_is_not_order", "read_only_lifecycle"],
                    )
                )
        if attempt is not None:
            events.append(
                _event(
                    _aware(attempt.created_at),
                    "buy_preflight",
                    "Guarded buy preflight",
                    attempt.status,
                    attempt.trigger_source,
                    f"attempt:{attempt.id}",
                    attempt.block_reason,
                    safety_flags=_attempt_safety_flags(attempt),
                    real_order_submitted=False,
                    broker_submit_called=False,
                    manual_submit_called=False,
                )
            )
        events.append(
            _event(
                _order_event_time(order),
                "guarded_buy_submitted",
                "Guarded buy submitted",
                _order_status(order),
                _order_source(order) or (attempt.trigger_source if attempt else "order_log"),
                f"order:{order.id}",
                "Existing buy order record linked to lifecycle.",
                safety_flags=_order_safety_flags(order),
                real_order_submitted=_real_order_submitted(order),
                broker_submit_called=_broker_submit_called(order),
                manual_submit_called=_manual_submit_called(order),
            )
        )
        if _is_filled(order):
            events.append(
                _event(
                    _aware(order.filled_at) or _order_event_time(order),
                    "buy_filled",
                    "Buy filled",
                    _order_status(order),
                    "order_log",
                    f"order:{order.id}",
                    "Buy fill recorded in local order log.",
                    safety_flags=["read_only_lifecycle"],
                    real_order_submitted=_real_order_submitted(order),
                    broker_submit_called=_broker_submit_called(order),
                    manual_submit_called=_manual_submit_called(order),
                )
            )
        if order.last_synced_at is not None:
            events.append(_sync_event(order))
        return events

    def _exit_events(
        self,
        order: OrderLog,
        *,
        attempt: StrategyLiveAutoExitAttempt | None,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if attempt is not None:
            events.append(
                _event(
                    _aware(attempt.created_at),
                    "sell_preflight",
                    "Sell preflight",
                    attempt.status,
                    attempt.trigger_source,
                    f"attempt:{attempt.id}",
                    attempt.block_reason or attempt.exit_reason,
                    safety_flags=_attempt_safety_flags(attempt),
                    real_order_submitted=False,
                    broker_submit_called=False,
                    manual_submit_called=False,
                )
            )
        events.append(
            _event(
                _order_event_time(order),
                "guarded_sell_submitted",
                "Guarded sell submitted",
                _order_status(order),
                _order_source(order) or (attempt.trigger_source if attempt else "order_log"),
                f"order:{order.id}",
                "Existing sell order record linked to lifecycle.",
                safety_flags=_order_safety_flags(order),
                real_order_submitted=_real_order_submitted(order),
                broker_submit_called=_broker_submit_called(order),
                manual_submit_called=_manual_submit_called(order),
            )
        )
        if _is_filled(order):
            events.append(
                _event(
                    _aware(order.filled_at) or _order_event_time(order),
                    "sell_filled",
                    "Sell filled",
                    _order_status(order),
                    "order_log",
                    f"order:{order.id}",
                    "Sell fill recorded in local order log.",
                    safety_flags=["read_only_lifecycle"],
                    real_order_submitted=_real_order_submitted(order),
                    broker_submit_called=_broker_submit_called(order),
                    manual_submit_called=_manual_submit_called(order),
                )
            )
        if order.last_synced_at is not None:
            events.append(_sync_event(order))
        return events

    def _standalone_sell_attempt_events(
        self,
        *,
        symbol: str,
        links: dict[str, Any],
    ) -> list[dict[str, Any]]:
        events = []
        for attempt in links["sell_attempts_by_symbol"].get(symbol.upper(), []):
            if attempt.related_order_id:
                continue
            event_type = "blocked" if str(attempt.status).lower() == "blocked" else "sell_preflight"
            events.append(
                _event(
                    _aware(attempt.created_at),
                    event_type,
                    "Sell review recorded",
                    attempt.status,
                    attempt.trigger_source,
                    f"attempt:{attempt.id}",
                    attempt.block_reason or attempt.exit_reason,
                    safety_flags=_attempt_safety_flags(attempt),
                    real_order_submitted=False,
                    broker_submit_called=False,
                    manual_submit_called=False,
                )
            )
        return events


def _provider(value: str | None) -> str:
    return str(value or PROVIDER).strip().lower() or PROVIDER


def _market(value: str | None) -> str:
    return str(value or MARKET).strip().upper() or MARKET


def _status(value: str | None) -> str:
    status = str(value or "all").strip().lower()
    return status if status in {"open", "closed", "all"} else "all"


def _normalize_symbol(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if text.isdigit() and len(text) < 6:
        return text.zfill(6)
    return text


def _order_market(order: OrderLog) -> str:
    return _market(order.market or ("KR" if order.broker == "kis" else "US"))


def _attempt_by_order(rows: list[Any]) -> dict[int, Any]:
    result: dict[int, Any] = {}
    for row in rows:
        if row.related_order_id is None:
            continue
        result[int(row.related_order_id)] = row
    return result


def _attempts_by_symbol(rows: list[Any]) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        symbol = _normalize_symbol(row.symbol)
        if symbol:
            result[symbol].append(row)
    return result


def _promotion_by_order(rows: list[StrategyAutoBuyPromotion]) -> dict[int, StrategyAutoBuyPromotion]:
    result: dict[int, StrategyAutoBuyPromotion] = {}
    for row in rows:
        for value in (row.converted_order_id, row.related_live_order_id):
            if value is not None:
                result[int(value)] = row
    return result


def _promotion_by_attempt(rows: list[StrategyAutoBuyPromotion]) -> dict[int, StrategyAutoBuyPromotion]:
    result: dict[int, StrategyAutoBuyPromotion] = {}
    for row in rows:
        for value in (row.converted_live_attempt_id, row.promoted_to_live_attempt_id):
            if value is not None:
                result[int(value)] = row
    return result


def _promotions_by_symbol(rows: list[StrategyAutoBuyPromotion]) -> dict[str, list[StrategyAutoBuyPromotion]]:
    result: dict[str, list[StrategyAutoBuyPromotion]] = defaultdict(list)
    for row in rows:
        symbol = _normalize_symbol(row.symbol)
        if symbol:
            result[symbol].append(row)
    return result


def _promotion_for_entry(
    order: OrderLog,
    attempt: StrategyLiveAutoBuyAttempt | None,
    links: dict[str, Any],
) -> StrategyAutoBuyPromotion | None:
    direct = links["promotion_by_order"].get(order.id)
    if direct is not None:
        return direct
    if attempt is not None:
        direct = links["promotion_by_attempt"].get(attempt.id)
        if direct is not None:
            return direct
    payloads = [_parse_json(order.request_payload), _parse_json(order.response_payload)]
    if attempt is not None:
        payloads += [_parse_json(attempt.request_payload), _parse_json(attempt.response_payload)]
    promotion_id = _first_int_from_payloads(payloads, {"promotion_id", "source_promotion_id", "auto_buy_promotion_id"})
    if promotion_id is not None:
        for row in links["promotions"]:
            if int(row.id) == promotion_id:
                return row
    return None


def _entry_source(
    order: OrderLog,
    attempt: StrategyLiveAutoBuyAttempt | None,
    promotion: StrategyAutoBuyPromotion | None,
) -> str:
    if promotion is not None:
        return "promotion_conversion"
    payloads = [_parse_json(order.request_payload), _parse_json(order.response_payload)]
    if any(_payload_bool(payload, "simulated") or _payload_bool(payload, "dry_run") for payload in payloads):
        return "dry_run_simulation"
    trigger = str(attempt.trigger_source if attempt is not None else "").lower()
    source = str(_order_source(order) or "").lower()
    if "guarded_live_auto_buy" in trigger or "guarded_live_auto_buy" in source:
        return "manual_live_buy"
    if _real_order_submitted(order):
        return "manual_live_buy"
    return "unknown"


def _normalize_position(item: dict[str, Any]) -> dict[str, Any]:
    symbol = _normalize_symbol(item.get("symbol") or item.get("pdno") or item.get("code"))
    return {
        **item,
        "symbol": symbol or "",
        "qty": _float(item.get("qty") or item.get("quantity") or item.get("hldg_qty")),
        "avg_entry_price": _float_or_none(
            item.get("avg_entry_price") or item.get("average_price") or item.get("pchs_avg_pric")
        ),
        "cost_basis": _float_or_none(
            item.get("cost_basis") or item.get("pchs_amt") or item.get("pchs_amt_smtl_amt")
        ),
        "current_price": _float_or_none(
            item.get("current_price") or item.get("prpr") or item.get("stck_prpr")
        ),
        "current_value": _float_or_none(
            item.get("current_value") or item.get("market_value") or item.get("evlu_amt")
        ),
        "unrealized_pl": _float_or_none(
            item.get("unrealized_pl") or item.get("evlu_pfls_amt")
        ),
    }


def _position_qty(item: dict[str, Any]) -> float:
    return _float(item.get("qty") or item.get("quantity") or item.get("hldg_qty"))


def _position_average_price(position: dict[str, Any]) -> float | None:
    return _float_or_none(position.get("avg_entry_price") or position.get("average_price"))


def _position_cost_basis(position: dict[str, Any], *, quantity: float) -> float | None:
    direct = _float_or_none(position.get("cost_basis"))
    total_qty = _position_qty(position)
    if direct is not None and direct > 0:
        if total_qty > 0 and quantity < total_qty:
            return direct * (quantity / total_qty)
        return direct
    avg = _position_average_price(position)
    if avg is not None and avg > 0 and quantity > 0:
        return avg * quantity
    return None


def _position_current_price(position: dict[str, Any]) -> float | None:
    return _float_or_none(position.get("current_price"))


def _allocated_current_value(position: dict[str, Any], *, quantity: float) -> float | None:
    value = _float_or_none(position.get("current_value") or position.get("market_value"))
    total_qty = _position_qty(position)
    if value is None or total_qty <= 0:
        return value
    return value * (quantity / total_qty)


def _allocated_unrealized(position: dict[str, Any], *, quantity: float) -> float | None:
    value = _float_or_none(position.get("unrealized_pl"))
    total_qty = _position_qty(position)
    if value is None or total_qty <= 0:
        return value
    return value * (quantity / total_qty)


def _is_filled(order: OrderLog) -> bool:
    return str(order.internal_status or "").upper() in FILLED_STATUSES or _float(order.filled_qty) > 0


def _filled_quantity(order: OrderLog) -> float:
    return max(_float(order.filled_qty or order.requested_qty or order.qty), 0.0)


def _fill_price(order: OrderLog) -> float | None:
    direct = _float_or_none(order.avg_fill_price or order.filled_avg_price)
    if direct is not None and direct > 0:
        return direct
    for payload in (
        _parse_json(order.last_sync_payload),
        _parse_json(order.response_payload),
        _parse_json(order.request_payload),
    ):
        found = _find_number(
            payload,
            {"avg_fill_price", "average_fill_price", "filled_avg_price", "avg_prvs"},
        )
        if found is not None and found > 0:
            return found
    if order.notional and _filled_quantity(order) > 0:
        return _float(order.notional) / _filled_quantity(order)
    return None


def _notional(quantity: float | None, price: float | None) -> float | None:
    if quantity is None or price is None or quantity <= 0 or price <= 0:
        return None
    return quantity * price


def _order_event_time(order: OrderLog) -> datetime:
    return _aware(order.filled_at or order.submitted_at or order.created_at) or datetime.now(UTC)


def _order_status(order: OrderLog) -> str:
    return str(order.internal_status or order.broker_status or order.broker_order_status or "unknown")


def _broker_status(order: OrderLog) -> str | None:
    return _text(order.broker_status or order.broker_order_status)


def _order_source(order: OrderLog) -> str | None:
    for payload in (_parse_json(order.response_payload), _parse_json(order.request_payload)):
        for key in ("source", "source_type", "source_context", "trigger_source", "mode"):
            text = _text(payload.get(key) if isinstance(payload, dict) else None)
            if text:
                return text
    return None


def _flags_from_order(order: OrderLog | None) -> list[str]:
    if order is None:
        return []
    flags: list[str] = []
    for payload in (_parse_json(order.request_payload), _parse_json(order.response_payload)):
        flags += _string_list(payload.get("risk_flags") if isinstance(payload, dict) else None)
        flags += _string_list(payload.get("block_reasons") if isinstance(payload, dict) else None)
    return _dedupe(flags)


def _notes_from_order(order: OrderLog | None) -> list[str]:
    if order is None:
        return []
    notes: list[str] = []
    for payload in (_parse_json(order.request_payload), _parse_json(order.response_payload)):
        notes += _string_list(payload.get("gating_notes") if isinstance(payload, dict) else None)
        notes += _string_list(payload.get("failed_checks") if isinstance(payload, dict) else None)
    return _dedupe(notes)


def _flags_from_attempt(attempt: Any | None) -> list[str]:
    if attempt is None:
        return []
    return _dedupe(_string_list(attempt.risk_flags) + ([attempt.block_reason] if attempt.block_reason else []))


def _notes_from_attempt(attempt: Any | None) -> list[str]:
    if attempt is None:
        return []
    return _dedupe(_string_list(attempt.gating_notes))


def _flags_from_promotion(promotion: StrategyAutoBuyPromotion | None) -> list[str]:
    if promotion is None:
        return []
    return _dedupe(_string_list(promotion.risk_flags) + ([promotion.block_reason] if promotion.block_reason else []))


def _notes_from_promotion(promotion: StrategyAutoBuyPromotion | None) -> list[str]:
    if promotion is None:
        return []
    return _dedupe(_string_list(promotion.gating_notes))


def _order_safety_flags(order: OrderLog) -> list[str]:
    flags = ["read_only_lifecycle"]
    if _real_order_submitted(order):
        flags.append("historical_real_order_submitted")
    else:
        flags.append("no_live_order_submitted")
    if _broker_submit_called(order):
        flags.append("historical_broker_submit_called")
    if _manual_submit_called(order):
        flags.append("historical_manual_submit_called")
    return flags


def _attempt_safety_flags(attempt: Any | None) -> list[str]:
    if attempt is None:
        return ["read_only_lifecycle"]
    payloads = [_parse_json(attempt.safety_flags), _parse_json(attempt.response_payload)]
    flags = ["read_only_lifecycle"]
    for payload in payloads:
        safety = payload.get("safety") if isinstance(payload, dict) else payload
        if not isinstance(safety, dict):
            continue
        for key in (
            "manual_only",
            "final_confirmation_required",
            "real_order_submitted",
            "broker_submit_called",
            "manual_submit_called",
        ):
            if safety.get(key) is True:
                flags.append(key)
    return _dedupe(flags)


def _real_order_submitted(order: OrderLog) -> bool:
    value = _payload_bool_from_order(order, "real_order_submitted")
    if value is not None:
        return value
    return bool(order.broker_order_id or order.kis_odno) and str(order.internal_status or "").upper() != "DRY_RUN_SIMULATED"


def _broker_submit_called(order: OrderLog) -> bool:
    value = _payload_bool_from_order(order, "broker_submit_called")
    return bool(value) if value is not None else _real_order_submitted(order)


def _manual_submit_called(order: OrderLog) -> bool:
    value = _payload_bool_from_order(order, "manual_submit_called")
    return bool(value) if value is not None else False


def _payload_bool_from_order(order: OrderLog, key: str) -> bool | None:
    for payload in (_parse_json(order.response_payload), _parse_json(order.request_payload)):
        value = _payload_bool(payload, key)
        if value is not None:
            return value
        audit = payload.get("audit_metadata") if isinstance(payload, dict) else None
        value = _payload_bool(audit, key)
        if value is not None:
            return value
    return None


def _payload_bool(payload: Any, key: str) -> bool | None:
    if not isinstance(payload, dict) or key not in payload:
        return None
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _sync_event(order: OrderLog) -> dict[str, Any]:
    return _event(
        _aware(order.last_synced_at),
        "sync_update",
        "Order sync updated",
        _order_status(order),
        "order_sync",
        f"order:{order.id}",
        "Existing order sync fields were already present in local order log.",
        safety_flags=["read_only_lifecycle"],
        real_order_submitted=_real_order_submitted(order),
        broker_submit_called=_broker_submit_called(order),
        manual_submit_called=_manual_submit_called(order),
    )


def _event(
    timestamp: datetime | None,
    event_type: str,
    title: str,
    status: str | None,
    source: str | None,
    related_id: str | None,
    summary: str | None,
    *,
    safety_flags: list[str] | None = None,
    real_order_submitted: bool = False,
    broker_submit_called: bool = False,
    manual_submit_called: bool = False,
) -> dict[str, Any]:
    return {
        "timestamp": _iso(timestamp),
        "event_type": event_type,
        "title": title,
        "status": status,
        "source": source,
        "related_id": related_id,
        "summary": summary,
        "safety_flags": _dedupe(safety_flags or []),
        "real_order_submitted": bool(real_order_submitted),
        "broker_submit_called": bool(broker_submit_called),
        "manual_submit_called": bool(manual_submit_called),
    }


def _sorted_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(events, key=_event_sort_time)


def _event_sort_time(event: dict[str, Any]) -> datetime:
    timestamp = event.get("timestamp")
    if not timestamp:
        return datetime.min.replace(tzinfo=UTC)
    try:
        return _aware(datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))) or datetime.min.replace(tzinfo=UTC)
    except Exception:
        return datetime.min.replace(tzinfo=UTC)


def _item_sort_time(item: dict[str, Any]) -> datetime:
    for key in ("exit_filled_at", "exit_submitted_at", "entry_filled_at", "entry_submitted_at"):
        value = item.get(key)
        if not value:
            continue
        try:
            return _aware(datetime.fromisoformat(str(value).replace("Z", "+00:00"))) or datetime.min.replace(tzinfo=UTC)
        except Exception:
            continue
    return datetime.min.replace(tzinfo=UTC)


def _item(**kwargs: Any) -> dict[str, Any]:
    defaults = {
        "name": None,
        "entry_order_id": None,
        "entry_broker_order_id": None,
        "entry_kis_odno": None,
        "entry_submitted_at": None,
        "entry_filled_at": None,
        "entry_quantity": None,
        "entry_average_price": None,
        "entry_notional": None,
        "related_promotion_id": None,
        "related_signal_id": None,
        "current_quantity": None,
        "current_price": None,
        "current_value": None,
        "cost_basis": None,
        "unrealized_pl": None,
        "unrealized_pl_pct": None,
        "exit_order_id": None,
        "exit_broker_order_id": None,
        "exit_kis_odno": None,
        "exit_submitted_at": None,
        "exit_filled_at": None,
        "exit_quantity": None,
        "exit_average_price": None,
        "exit_notional": None,
        "realized_pl": None,
        "realized_pl_pct": None,
        "fees": None,
        "holding_period_minutes": None,
        "latest_status": None,
        "latest_broker_status": None,
        "risk_flags": [],
        "gating_notes": [],
        "audit_flags": [],
        "events": [],
    }
    return {**defaults, **kwargs}


def _totals(items: list[dict[str, Any]]) -> dict[str, Any]:
    open_items = [item for item in items if item.get("lifecycle_status") == "open"]
    closed_items = [item for item in items if item.get("lifecycle_status") == "closed"]
    incomplete = sum(
        1 for item in items if "calculation_incomplete" in (item.get("audit_flags") or [])
    )
    realized = sum(_float(item.get("realized_pl")) for item in closed_items if item.get("realized_pl") is not None)
    realized_basis = sum(_float(item.get("cost_basis")) for item in closed_items if item.get("realized_pl") is not None)
    return {
        "open_position_count": len(open_items),
        "closed_lifecycle_count": len(closed_items),
        "total_current_value": _round_money(
            sum(_float(item.get("current_value")) for item in open_items)
        ),
        "total_unrealized_pl": _round_money(
            sum(_float(item.get("unrealized_pl")) for item in open_items)
        ),
        "total_realized_pl": _round_money(realized),
        "total_realized_pl_pct": (
            _round_ratio(realized / realized_basis)
            if realized_basis > 0 and incomplete == 0
            else None
        ),
        "incomplete_calculation_count": incomplete,
    }


def _safety() -> dict[str, Any]:
    return {
        "read_only": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "broker_api_called": False,
        "submit_service_called": False,
        "sync_called": False,
        "order_state_mutated": False,
        "scheduler_changed": False,
        "setting_changed": False,
        "dry_run_changed": False,
        "kill_switch_changed": False,
        "kis_real_order_changed": False,
    }


def _best_name(
    attempt: Any | None,
    promotion: StrategyAutoBuyPromotion | None,
    position: dict[str, Any] | None,
) -> str | None:
    for value in (
        getattr(attempt, "symbol_name", None),
        promotion.symbol_name if promotion is not None else None,
        (position or {}).get("name"),
        (position or {}).get("prdt_name"),
        (position or {}).get("company_name"),
    ):
        text = _text(value)
        if text:
            return text
    return None


def _holding_minutes(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    return max(0, int((_aware(end) - _aware(start)).total_seconds() // 60))  # type: ignore[operator]


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
    if isinstance(value, list):
        for item in value:
            nested = _find_number(item, keys)
            if nested is not None:
                return nested
    return None


def _first_int_from_payloads(payloads: list[Any], keys: set[str]) -> int | None:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key in keys:
            value = _int_or_none(payload.get(key))
            if value is not None:
                return value
        trace = payload.get("promotion_trace")
        if isinstance(trace, dict):
            value = _int_or_none(trace.get("promotion_id"))
            if value is not None:
                return value
    return None


def _string_list(value: Any) -> list[str]:
    parsed = _parse_json(value)
    if isinstance(parsed, list):
        return [str(item)[:240] for item in parsed if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()[:240]]
    return []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _float(value: Any) -> float:
    return _float_or_none(value) or 0.0


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    aware = _aware(value)
    return aware.isoformat() if aware is not None else None


def _round_money(value: float) -> float:
    return round(float(value), 2)


def _round_optional_money(value: float | None) -> float | None:
    return None if value is None else _round_money(value)


def _round_ratio(value: float) -> float:
    return round(float(value), 6)


def _round_quantity(value: float) -> float:
    return round(float(value), 8)
