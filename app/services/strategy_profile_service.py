from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import StrategyProfile, StrategyProfileAudit
from app.schemas.strategy import StrategyProfilePayload


PROFILE_ORDER = {"safe": 0, "balanced": 1, "aggressive": 2}

DEFAULT_STRATEGY_PROFILES: dict[str, dict[str, Any]] = {
    "safe": {
        "profile_name": "safe",
        "display_name": "안정형",
        "description": "월 1~2% 목표, 낮은 주문 비중, 엄격한 매수 기준을 쓰는 보수적인 전략 프로필입니다.",
        "monthly_target_return_pct": 0.015,
        "monthly_target_min_pct": 0.01,
        "monthly_target_max_pct": 0.02,
        "monthly_max_loss_pct": -0.02,
        "daily_max_loss_pct": -0.005,
        "max_order_notional_pct": 0.02,
        "max_order_notional_krw": 30000,
        "max_trades_per_day": 1,
        "max_positions": 2,
        "buy_score_threshold": 75,
        "sell_score_threshold": 65,
        "stop_loss_pct": -0.012,
        "take_profit_pct": 0.02,
        "max_holding_days": 5,
        "stop_after_monthly_target": True,
        "reduce_size_after_loss": True,
        "consecutive_loss_reduce_threshold": 1,
    },
    "balanced": {
        "profile_name": "balanced",
        "display_name": "보통형",
        "description": "월 3~5% 목표, 중간 주문 비중과 중간 손실 한도를 쓰는 기본 전략 프로필입니다.",
        "monthly_target_return_pct": 0.04,
        "monthly_target_min_pct": 0.03,
        "monthly_target_max_pct": 0.05,
        "monthly_max_loss_pct": -0.04,
        "daily_max_loss_pct": -0.01,
        "max_order_notional_pct": 0.04,
        "max_order_notional_krw": 50000,
        "max_trades_per_day": 2,
        "max_positions": 3,
        "buy_score_threshold": 68,
        "sell_score_threshold": 60,
        "stop_loss_pct": -0.02,
        "take_profit_pct": 0.04,
        "max_holding_days": 7,
        "stop_after_monthly_target": False,
        "reduce_size_after_loss": True,
        "consecutive_loss_reduce_threshold": 2,
    },
    "aggressive": {
        "profile_name": "aggressive",
        "display_name": "고수익형",
        "description": "월 5% 이상을 목표로 하지만 월간/일간 손실 한도를 우선하는 공격적인 전략 프로필입니다.",
        "monthly_target_return_pct": 0.06,
        "monthly_target_min_pct": 0.05,
        "monthly_target_max_pct": 0.08,
        "monthly_max_loss_pct": -0.06,
        "daily_max_loss_pct": -0.015,
        "max_order_notional_pct": 0.06,
        "max_order_notional_krw": 80000,
        "max_trades_per_day": 2,
        "max_positions": 5,
        "buy_score_threshold": 62,
        "sell_score_threshold": 55,
        "stop_loss_pct": -0.03,
        "take_profit_pct": 0.06,
        "max_holding_days": 10,
        "stop_after_monthly_target": False,
        "reduce_size_after_loss": True,
        "consecutive_loss_reduce_threshold": 3,
    },
}


class StrategyProfileAckRequired(Exception):
    pass


class StrategyProfileNotFound(Exception):
    pass


class StrategyProfileService:
    def ensure_seeded(self, db: Session) -> None:
        existing = {
            row.profile_name: row
            for row in db.query(StrategyProfile).all()
        }
        now = datetime.now(UTC)
        changed = False
        for profile_name, payload in DEFAULT_STRATEGY_PROFILES.items():
            row = existing.get(profile_name)
            if row is None:
                row = StrategyProfile(
                    **payload,
                    is_active=False,
                    is_builtin=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
                changed = True
                continue
            for key, value in payload.items():
                if getattr(row, key) != value:
                    setattr(row, key, value)
                    changed = True
            if not row.is_builtin:
                row.is_builtin = True
                changed = True
            row.updated_at = now

        if changed:
            db.commit()

        active_count = db.query(StrategyProfile).filter(StrategyProfile.is_active == True).count()  # noqa: E712
        if active_count == 0:
            safe = self._profile_or_raise(db, "safe")
            safe.is_active = True
            safe.updated_at = now
            db.commit()
        elif active_count > 1:
            rows = (
                db.query(StrategyProfile)
                .filter(StrategyProfile.is_active == True)  # noqa: E712
                .order_by(StrategyProfile.id.asc())
                .all()
            )
            for row in rows[1:]:
                row.is_active = False
                row.updated_at = now
            db.commit()

    def list_profiles(self, db: Session) -> dict[str, Any]:
        self.ensure_seeded(db)
        profiles = sorted(
            db.query(StrategyProfile).all(),
            key=lambda row: PROFILE_ORDER.get(row.profile_name, 99),
        )
        active = self.active_profile(db)
        return {
            "profiles": [self.serialize_profile(row) for row in profiles],
            "active_profile": self.serialize_profile(active),
        }

    def active_profile(self, db: Session) -> StrategyProfile:
        self.ensure_seeded(db)
        row = (
            db.query(StrategyProfile)
            .filter(StrategyProfile.is_active == True)  # noqa: E712
            .order_by(StrategyProfile.id.asc())
            .first()
        )
        if row is None:
            row = self._profile_or_raise(db, "safe")
            row.is_active = True
            db.commit()
            db.refresh(row)
        return row

    def get_profile(self, db: Session, profile_name: str) -> StrategyProfile:
        self.ensure_seeded(db)
        return self._profile_or_raise(db, profile_name)

    def apply_preset(
        self,
        db: Session,
        *,
        profile_name: str,
        confirm_operator_ack: bool,
        source: str = "settings_ui",
    ) -> dict[str, Any]:
        self.ensure_seeded(db)
        if confirm_operator_ack is not True:
            raise StrategyProfileAckRequired("confirm_operator_ack_required")
        requested = self._profile_or_raise(db, profile_name)
        previous = self.active_profile(db)
        before_snapshot = self.serialize_profile(previous)
        if previous.profile_name == requested.profile_name:
            audit = self._audit(
                db,
                action="apply_preset_noop",
                previous_profile=previous.profile_name,
                new_profile=requested.profile_name,
                before_snapshot=before_snapshot,
                after_snapshot=self.serialize_profile(requested),
                confirm_operator_ack=True,
                source=source,
            )
            return {
                "status": "ok",
                "active_profile": self.serialize_profile(requested),
                "previous_profile": self.serialize_profile(previous),
                "audit_id": audit.id,
                "safety": _profile_safety(setting_changed=False),
            }

        now = datetime.now(UTC)
        for row in db.query(StrategyProfile).all():
            row.is_active = row.profile_name == requested.profile_name
            row.updated_at = now
        db.commit()
        db.refresh(requested)
        after_snapshot = self.serialize_profile(requested)
        audit = self._audit(
            db,
            action="apply_preset",
            previous_profile=previous.profile_name,
            new_profile=requested.profile_name,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            confirm_operator_ack=True,
            source=source,
        )
        return {
            "status": "ok",
            "active_profile": after_snapshot,
            "previous_profile": before_snapshot,
            "audit_id": audit.id,
            "safety": _profile_safety(setting_changed=True),
        }

    def monthly_progress(self, db: Session) -> dict[str, Any]:
        active = self.active_profile(db)
        profile = self.serialize_profile(active)
        target = float(active.monthly_target_return_pct or 0)
        current = 0.0
        progress_ratio = 0.0 if target <= 0 else current / target
        return {
            "active_profile": profile,
            "current_month_return_pct": current,
            "target_return_pct": target,
            "target_min_pct": float(active.monthly_target_min_pct),
            "target_max_pct": float(active.monthly_target_max_pct),
            "progress_ratio": progress_ratio,
            "skeleton": True,
            "note": "PR70 skeleton: realized P&L 연결은 PR71에서 진행합니다.",
        }

    def risk_budget(self, db: Session) -> dict[str, Any]:
        active = self.active_profile(db)
        return {
            "active_profile": self.serialize_profile(active),
            "monthly_max_loss_pct": float(active.monthly_max_loss_pct),
            "daily_max_loss_pct": float(active.daily_max_loss_pct),
            "max_order_notional_pct": float(active.max_order_notional_pct),
            "max_order_notional_krw": float(active.max_order_notional_krw),
            "max_trades_per_day": int(active.max_trades_per_day),
            "max_positions": int(active.max_positions),
            "buy_score_threshold": float(active.buy_score_threshold),
            "sell_score_threshold": float(active.sell_score_threshold),
            "stop_loss_pct": float(active.stop_loss_pct),
            "take_profit_pct": float(active.take_profit_pct),
            "safety": _profile_safety(setting_changed=False, read_only=True),
        }

    def serialize_profile(self, row: StrategyProfile) -> dict[str, Any]:
        return StrategyProfilePayload.model_validate(row).model_dump(mode="json")

    def _profile_or_raise(self, db: Session, profile_name: str) -> StrategyProfile:
        normalized = str(profile_name or "").strip().lower()
        row = (
            db.query(StrategyProfile)
            .filter(StrategyProfile.profile_name == normalized)
            .first()
        )
        if row is None:
            raise StrategyProfileNotFound(normalized)
        return row

    def _audit(
        self,
        db: Session,
        *,
        action: str,
        previous_profile: str | None,
        new_profile: str | None,
        before_snapshot: dict[str, Any],
        after_snapshot: dict[str, Any],
        confirm_operator_ack: bool,
        source: str,
    ) -> StrategyProfileAudit:
        row = StrategyProfileAudit(
            action=action,
            previous_profile=previous_profile,
            new_profile=new_profile,
            before_snapshot=_json(before_snapshot),
            after_snapshot=_json(after_snapshot),
            confirm_operator_ack=confirm_operator_ack,
            source=_source(source),
            safety_flags=_json(_profile_safety(setting_changed=previous_profile != new_profile)),
            created_at=datetime.now(UTC),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


def _profile_safety(*, setting_changed: bool, read_only: bool = False) -> dict[str, Any]:
    return {
        "read_only": read_only,
        "safe_execution_only": True,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "validation_called": False,
        "setting_changed": setting_changed,
        "scheduler_changed": False,
        "confirm_live_auto_checked": False,
        "broker_api_called": False,
        "mutation": setting_changed,
    }


def _source(value: str) -> str:
    raw = str(value or "").strip()
    return raw if raw in {"settings_ui", "agent_chat"} else "unknown"


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)

