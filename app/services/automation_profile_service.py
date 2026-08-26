from __future__ import annotations

import copy
import hashlib
import json
import re
import secrets
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import StrategyProfile
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.automation_profile_safety import TEST4_HARD_SAFETY, effective_profile_settings
from app.services.strategy_profile_sizing_service import StrategyProfileSizingService


KST = ZoneInfo('Asia/Seoul')
ALLOWED_PROVIDERS = {'kis', 'alpaca'}
ALLOWED_MARKETS = {'KR', 'US'}
ALLOWED_STATUSES = {'scheduled', 'active', 'paused', 'ended', 'disabled', 'archived'}
RESERVED_PROFILE_KEYS = {'safe', 'balanced', 'aggressive'}


DEFAULT_PROFILE_SETTINGS: dict[str, Any] = {
    'capital': {
        'sizing_mode': 'equity_pct',
        'target_position_pct': 10.0,
        'max_position_pct': 12.0,
        'max_total_exposure_pct': 30.0,
        'max_order_notional_krw': 500000.0,
        'fixed_budget': 0.0,
        'cash_only': True,
    },
    'universe': {
        'universe_mode': 'auto',
        'watchlist_size': 50,
        'min_price_krw': 5000.0,
        'max_price_krw': 500000.0,
        'include_kospi': True,
        'include_kosdaq': True,
        'exclude_preferred': True,
        'exclude_etf': True,
        'exclude_etn': True,
        'exclude_spac': True,
        'min_volume_ratio': None,
        'top_quant_candidates': 10,
        'top_ai_candidates': 5,
        'manual_symbols': [],
        'favorites': [],
        'strategy_universe': [],
    },
    'entry': {
        'analysis_times': ['09:10', '11:30', '13:30'],
        'no_new_entry_after': '14:00',
        'max_new_entries_per_day': 1,
        'max_entries_per_scan': 1,
        'min_final_score': 65.0,
        'gate_level': 2,
    },
    'monitoring': {'interval_seconds': 60},
    'exit': {
        'stop_loss_enabled': True,
        'stop_loss_pct': 2.0,
        'take_profit_enabled': True,
        'take_profit_pct': 3.0,
    },
    'operation': {
        'start_date': '2026-08-17',
        'end_date': '2026-09-18',
        'weekdays_only': True,
        'auto_start': False,
        'end_policy': 'manage_until_exit',
        'timezone': 'Asia/Seoul',
    },
    'max_open_positions': 1,
}


class AutomationProfileNotFound(Exception):
    pass


class AutomationProfileValidationError(ValueError):
    def __init__(self, errors: list[dict[str, str]]):
        self.errors = errors
        super().__init__('automation_profile_validation_failed')


class AutomationProfileConflict(ValueError):
    pass


class AutomationProfileService:
    def __init__(self, *, runtime_settings: RuntimeSettingService | None = None) -> None:
        self.runtime_settings = runtime_settings or RuntimeSettingService()

    def selected_profile(self, db: Session) -> StrategyProfile | None:
        runtime = self.runtime_settings.get_settings_read_only(db)
        active_key = str(runtime.get("active_automation_profile_key") or "").strip().lower()
        if not active_key:
            return None
        return (
            db.query(StrategyProfile)
            .filter(StrategyProfile.profile_key == active_key)
            .filter(StrategyProfile.profile_key.isnot(None))
            .first()
        )

    def get_active_profile(self, db: Session) -> dict[str, Any] | None:
        runtime = self.runtime_settings.get_settings_read_only(db)
        active_key = str(runtime.get('active_automation_profile_key') or '').strip().lower()
        if not active_key:
            return None
        try:
            row = self.get(db, active_key)
        except AutomationProfileNotFound:
            return None
        profile = self.serialize(row)
        if profile.get('status') != 'active' or profile.get('enabled') is not True:
            return None
        return profile

    def list_profiles(self, db: Session) -> dict[str, Any]:
        rows = (
            db.query(StrategyProfile)
            .filter(StrategyProfile.profile_key.isnot(None))
            .order_by(StrategyProfile.id.asc())
            .all()
        )
        selected_row = self.selected_profile(db)
        selected = self.serialize(selected_row) if selected_row is not None else None
        selected_status = self._status(selected_row) if selected_row is not None else None
        active = selected if selected_status == "active" else None
        return {
            "profiles": [self.serialize(row) for row in rows],
            "selected_profile": selected,
            "selected_profile_status": selected_status,
            "automation_selected": selected is not None,
            "active_profile": active,
        }

    def selected_profile_schedule(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        row = self.selected_profile(db)
        if row is None:
            return None
        settings = self._settings(row)
        timezone_name = str(settings["operation"].get("timezone") or "Asia/Seoul")
        timezone = _profile_timezone(settings, row.market or "KR")
        local_now = _aware_in_timezone(now, timezone)
        status = self._status(row, now=local_now)
        cutoff = _parse_time(settings["entry"]["no_new_entry_after"])
        analysis_times = sorted({
            value.strftime("%H:%M")
            for value in (_parse_time(value) for value in settings["entry"]["analysis_times"])
            if value < cutoff
        })
        start = date.fromisoformat(settings["operation"]["start_date"])
        end = date.fromisoformat(settings["operation"]["end_date"])
        next_run = None
        if status in {"scheduled", "active"} and analysis_times:
            cursor = max(local_now.date(), start)
            while cursor <= end:
                if not settings["operation"].get("weekdays_only") or cursor.weekday() < 5:
                    for value in analysis_times:
                        hour, minute = (int(part) for part in value.split(":", 1))
                        candidate = datetime.combine(cursor, time(hour, minute), tzinfo=timezone)
                        if candidate > local_now:
                            next_run = candidate
                            break
                if next_run is not None:
                    break
                cursor += timedelta(days=1)
        return {
            "selected": True,
            "profile": self.serialize(row),
            "profile_key": row.profile_key,
            "status": status,
            "timezone": timezone_name,
            "analysis_times": analysis_times,
            "next_run_at": next_run,
        }

    def create(self, db: Session, request: AutomationProfileWriteRequest) -> dict[str, Any]:
        values = self._normalize_request(request, require_identity=True)
        self.validate_settings(values['settings'])
        generated_key = not values['profile_key']
        key = values['profile_key'] or self._new_profile_key(db, values['provider'])
        if generated_key:
            values['settings'].setdefault('_system', {})['generated_profile_key'] = True
        if db.query(StrategyProfile).filter(StrategyProfile.profile_key == key).first() is not None:
            raise AutomationProfileConflict('profile_key_already_exists')
        legacy_name = key[:40]
        if db.query(StrategyProfile).filter(StrategyProfile.profile_name == legacy_name).first() is not None:
            legacy_name = f'pr108_{hashlib.sha1(key.encode()).hexdigest()[:32]}'
        row = StrategyProfile(
            profile_name=legacy_name,
            display_name=values['name'],
            description='PR108 automation configuration profile',
            monthly_target_return_pct=0.0,
            monthly_target_min_pct=0.0,
            monthly_target_max_pct=0.0,
            monthly_max_loss_pct=0.0,
            daily_max_loss_pct=0.0,
            max_order_notional_pct=float(values['settings']['capital']['target_position_pct']) / 100.0,
            max_order_notional_krw=float(values['settings']['capital']['max_order_notional_krw']),
            max_trades_per_day=int(values['settings']['entry']['max_new_entries_per_day']),
            max_positions=int(values['settings']['max_open_positions']),
            buy_score_threshold=float(values['settings']['entry']['min_final_score']),
            sell_score_threshold=0.0,
            stop_loss_pct=-float(values['settings']['exit']['stop_loss_pct']) / 100.0,
            take_profit_pct=float(values['settings']['exit']['take_profit_pct']) / 100.0,
            max_holding_days=0,
            stop_after_monthly_target=False,
            reduce_size_after_loss=True,
            consecutive_loss_reduce_threshold=1,
            is_active=False,
            is_builtin=False,
            profile_key=key,
            custom_name=values['name'],
            provider=values['provider'],
            market=values['market'],
            enabled=bool(values['enabled']),
            custom_status=values['status'],
            settings_json=_json(values['settings']),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return self.serialize(row)

    def get(self, db: Session, profile_id: str) -> StrategyProfile:
        value = str(profile_id or '').strip()
        row = None
        if value.isdigit():
            row = db.get(StrategyProfile, int(value))
        if row is None:
            row = db.query(StrategyProfile).filter(StrategyProfile.profile_key == value).first()
        if row is None or row.profile_key is None:
            raise AutomationProfileNotFound(value)
        return row

    def update(self, db: Session, profile_id: str, request: AutomationProfileWriteRequest) -> dict[str, Any]:
        row = self.get(db, profile_id)
        current = self.serialize(row)
        values = self._normalize_request(request, current=current, require_identity=False)
        self.validate_settings(values['settings'])
        requested_key = values['profile_key']
        if requested_key != row.profile_key:
            if self._status(row) == 'active' or self._is_generated_profile_key(row):
                raise AutomationProfileConflict('profile_key_is_immutable')
            conflict = db.query(StrategyProfile).filter(StrategyProfile.profile_key == requested_key).first()
            if conflict is not None and conflict.id != row.id:
                raise AutomationProfileConflict('profile_key_already_exists')
            row.profile_key = requested_key
            legacy_name = requested_key[:40]
            legacy_conflict = (
                db.query(StrategyProfile)
                .filter(StrategyProfile.profile_name == legacy_name, StrategyProfile.id != row.id)
                .first()
            )
            row.profile_name = (
                f'pr108_{hashlib.sha1(requested_key.encode()).hexdigest()[:32]}'
                if legacy_conflict is not None
                else legacy_name
            )
        row.display_name = values['name']
        row.custom_name = values['name']
        row.provider = values['provider']
        row.market = values['market']
        row.enabled = bool(values['enabled'])
        row.custom_status = values['status']
        row.max_positions = int(values['settings']['max_open_positions'])
        row.max_trades_per_day = int(values['settings']['entry']['max_new_entries_per_day'])
        row.max_order_notional_pct = float(values['settings']['capital']['target_position_pct']) / 100.0
        row.max_order_notional_krw = float(values['settings']['capital']['max_order_notional_krw'])
        row.buy_score_threshold = float(values['settings']['entry']['min_final_score'])
        row.stop_loss_pct = -float(values['settings']['exit']['stop_loss_pct']) / 100.0
        row.take_profit_pct = float(values['settings']['exit']['take_profit_pct']) / 100.0
        row.settings_json = _json(values['settings'])
        row.is_active = False
        row.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        runtime = self.runtime_settings.get_settings_read_only(db)
        if (runtime.get("active_automation_profile_key") == row.profile_key and self._status(row) in {"paused", "archived", "disabled"}):
            self.runtime_settings.update_settings(
                db, {"active_automation_profile_key": None, "automation_profile_scheduler_enabled": False}
            )
        return self.serialize(row)

    def archive(self, db: Session, profile_id: str) -> dict[str, Any]:
        row = self.get(db, profile_id)
        row.enabled = False
        row.is_active = False
        row.custom_status = 'archived'
        row.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        runtime = self.runtime_settings.get_settings_read_only(db)
        if runtime.get('active_automation_profile_key') == row.profile_key:
            self.runtime_settings.update_settings(db, {'active_automation_profile_key': None, 'automation_profile_scheduler_enabled': False})
        return self.serialize(row)

    def activate(self, db: Session, profile_id: str) -> dict[str, Any]:
        row = self.get(db, profile_id)
        settings = self._settings(row)
        self.validate_settings(settings)
        for other in db.query(StrategyProfile).filter(StrategyProfile.profile_key.isnot(None)).all():
            if other.id != row.id and other.custom_status == 'active':
                other.custom_status = 'paused'
        row.enabled = True
        row.custom_status = 'active'
        # Keep the legacy ``is_active`` column false for PR108 rows. Legacy
        # StrategyProfileService uses that column for built-in presets; a
        # custom activation must not replace the legacy active profile.
        row.is_active = False
        row.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        # Select policy at runtime; safety and authorization remain separate.
        self.runtime_settings.update_settings(
            db, {'active_automation_profile_key': row.profile_key, 'automation_profile_scheduler_enabled': True},
        )
        return {
            'status': 'active',
            'profile': self.serialize(row),
            'readiness': self.readiness(db, str(row.id)),
            'safety': _profile_safety(setting_changed=True),
        }

    def pause(self, db: Session, profile_id: str) -> dict[str, Any]:
        row = self.get(db, profile_id)
        row.enabled = False
        row.is_active = False
        row.custom_status = 'paused'
        row.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        runtime = self.runtime_settings.get_settings_read_only(db)
        if runtime.get('active_automation_profile_key') == row.profile_key:
            self.runtime_settings.update_settings(db, {'active_automation_profile_key': None, 'automation_profile_scheduler_enabled': False})
        return {'status': 'paused', 'profile': self.serialize(row), 'safety': _profile_safety(setting_changed=True)}

    def validate_profile(self, db: Session, profile_id: str) -> dict[str, Any]:
        row = self.get(db, profile_id)
        try:
            self.validate_settings(self._settings(row))
            errors: list[dict[str, str]] = []
        except AutomationProfileValidationError as exc:
            errors = exc.errors
        return {
            'valid': not errors,
            'errors': errors,
            'profile': self.serialize(row),
            'safety': _profile_safety(setting_changed=False, read_only=True),
        }

    def readiness(self, db: Session, profile_id: str) -> dict[str, Any]:
        row = self.get(db, profile_id)
        settings = self._settings(row)
        effective = effective_profile_settings(settings, provider=row.provider or 'kis', market=row.market or 'KR')
        period_status = self._period_status(row, effective)
        now = datetime.now(_profile_timezone(effective, row.market or 'KR'))
        cutoff = _parse_time(effective['entry']['no_new_entry_after'])
        entry_allowed = period_status == 'active' and now.time() < cutoff
        runtime = self.runtime_settings.get_settings_read_only(db)
        max_positions = int(effective.get('max_open_positions') or 1)
        configured_max_positions = int(settings.get('max_open_positions') or 1)
        return {
            'profile': self.serialize(row),
            'effective_settings': effective,
            'safety_hard_floors': TEST4_HARD_SAFETY,
            'status': period_status,
            'period': settings['operation'],
            'entry_allowed_now': entry_allowed,
            'new_entries_allowed': entry_allowed and bool(row.enabled),
            'multi_position_execution_supported': False,
            'requires_pr109_portfolio_engine': configured_max_positions > 1,
            'operation_mode': runtime.get('operation_mode_requested', 'paper'),
            'runtime_safety': {
                'dry_run': bool(runtime.get('dry_run', True)),
                'kill_switch': bool(runtime.get('kill_switch', True)),
                'live_flags_unchanged': True,
            },
            'safety': _profile_safety(setting_changed=False, read_only=True),
        }

    def sizing(self, db: Session, profile_id: str, request: dict[str, Any]) -> dict[str, Any]:
        row = self.get(db, profile_id)
        result = StrategyProfileSizingService.calculate(self._settings(row), **request)
        return {'profile': self.serialize(row), 'sizing': result, 'safety': _profile_safety(setting_changed=False, read_only=True)}

    def watchlist(self, db: Session, profile_id: str) -> dict[str, Any]:
        row = self.get(db, profile_id)
        settings = self._settings(row)
        return {
            'profile_id': row.id,
            'profile_key': row.profile_key,
            'universe': settings['universe'],
            'safety': _profile_safety(setting_changed=False, read_only=True),
        }

    def update_watchlist(self, db: Session, profile_id: str, universe: dict[str, Any]) -> dict[str, Any]:
        row = self.get(db, profile_id)
        current = self._settings(row)
        current['universe'] = _deep_merge(current['universe'], universe)
        candidate = self._normalize_settings(current)
        self.validate_settings(candidate)
        row.settings_json = _json(candidate)
        row.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        return {'profile': self.serialize(row), 'universe': candidate['universe'], 'safety': _profile_safety(setting_changed=True)}

    def serialize(self, row: StrategyProfile) -> dict[str, Any]:
        settings = self._settings(row)
        effective = effective_profile_settings(settings, provider=row.provider or 'kis', market=row.market or 'KR')
        return {
            'id': row.id,
            'profile_key': row.profile_key,
            'name': row.custom_name or row.display_name,
            'display_name': row.custom_name or row.display_name,
            'provider': row.provider or 'kis',
            'market': row.market or 'KR',
            'enabled': bool(row.enabled),
            'status': self._status(row),
            'settings': settings,
            'effective_settings': effective,
            'safety_hard_floors': TEST4_HARD_SAFETY,
            'profile_key_generated': self._is_generated_profile_key(row),
            'capital': settings['capital'],
            'universe': settings['universe'],
            'entry': settings['entry'],
            'monitoring': settings['monitoring'],
            'exit': settings['exit'],
            'operation': settings['operation'],
            'max_open_positions': int(settings['max_open_positions']),
            'multi_position_execution_supported': False,
            'requires_pr109_portfolio_engine': int(settings['max_open_positions']) > 1,
            'created_at': row.created_at.isoformat() if row.created_at else None,
            'updated_at': row.updated_at.isoformat() if row.updated_at else None,
        }

    def _is_generated_profile_key(self, row: StrategyProfile) -> bool:
        settings = self._settings(row)
        system = settings.get('_system') if isinstance(settings.get('_system'), dict) else {}
        return bool(system.get('generated_profile_key'))

    def _new_profile_key(self, db: Session, provider: str) -> str:
        prefix = f'aut_{str(provider).strip().lower()}'
        for _ in range(10):
            candidate = f'{prefix}_{secrets.token_hex(4)}'
            if db.query(StrategyProfile).filter(StrategyProfile.profile_key == candidate).first() is None:
                return candidate
        raise AutomationProfileConflict('profile_key_generation_failed')

    def validate_settings(self, settings: dict[str, Any]) -> None:
        errors: list[dict[str, str]] = []
        capital = settings['capital']
        universe = settings['universe']
        entry = settings['entry']
        monitoring = settings['monitoring']
        exit_settings = settings['exit']
        operation = settings['operation']
        if capital['sizing_mode'] not in {'equity_pct', 'fixed_budget'}:
            errors.append({'field': 'capital.sizing_mode', 'message': 'must be equity_pct or fixed_budget'})
        if (
            capital['sizing_mode'] == 'equity_pct'
            and not 0 < float(capital['target_position_pct']) <= 100
        ):
            errors.append({'field': 'capital.target_position_pct', 'message': 'must be between 0 and 100'})
        if (
            capital['sizing_mode'] == 'equity_pct'
            and float(capital['max_position_pct']) < float(capital['target_position_pct'])
        ):
            errors.append({'field': 'capital.max_position_pct', 'message': 'must be >= target_position_pct'})
        if (
            capital['sizing_mode'] == 'equity_pct'
            and float(capital['max_total_exposure_pct']) < float(capital['max_position_pct'])
        ):
            errors.append({'field': 'capital.max_total_exposure_pct', 'message': 'must be >= max_position_pct'})
        if float(capital['max_order_notional_krw']) <= 0:
            errors.append({'field': 'capital.max_order_notional_krw', 'message': 'must be positive'})
        if (
            capital['sizing_mode'] == 'fixed_budget'
            and float(capital.get('fixed_budget') or 0) <= 0
        ):
            errors.append({'field': 'capital.fixed_budget', 'message': 'must be positive in fixed_budget mode'})
        watchlist_size = int(universe['watchlist_size'])
        if not 1 <= watchlist_size <= 100:
            errors.append({'field': 'universe.watchlist_size', 'message': 'must be between 1 and 100'})
        if universe['universe_mode'] not in {'auto', 'manual', 'hybrid'}:
            errors.append({'field': 'universe.universe_mode', 'message': 'must be auto, manual, or hybrid'})
        if float(universe['min_price_krw']) >= float(universe['max_price_krw']):
            errors.append({'field': 'universe.price_filter', 'message': 'min price must be below max price'})
        times = list(entry['analysis_times'])
        if not times:
            errors.append({'field': 'entry.analysis_times', 'message': 'at least one analysis time is required'})
        parsed_times = []
        for value in times:
            try:
                parsed_times.append(_parse_time(value))
            except ValueError:
                errors.append({'field': 'entry.analysis_times', 'message': f'invalid HH:mm: {value}'})
        if len(set(times)) != len(times):
            errors.append({'field': 'entry.analysis_times', 'message': 'duplicate analysis times are not allowed'})
        if parsed_times and (min(parsed_times) < time(9, 0) or max(parsed_times) > time(15, 30)):
            errors.append({'field': 'entry.analysis_times', 'message': 'must be within 09:00-15:30 Asia/Seoul'})
        try:
            cutoff = _parse_time(entry['no_new_entry_after'])
            if cutoff > time(15, 30):
                errors.append({'field': 'entry.no_new_entry_after', 'message': 'must not be after 15:30'})
            if parsed_times and any(value >= cutoff for value in parsed_times):
                errors.append({'field': 'entry.analysis_times', 'message': 'BUY analysis times must be before no_new_entry_after'})
        except ValueError:
            errors.append({'field': 'entry.no_new_entry_after', 'message': 'invalid HH:mm'})
        if not 1 <= int(entry['max_new_entries_per_day']) <= 3:
            errors.append({'field': 'entry.max_new_entries_per_day', 'message': 'must be between 1 and 3'})
        if int(entry['max_entries_per_scan']) != 1:
            errors.append({'field': 'entry.max_entries_per_scan', 'message': 'must be 1 in PR108 reference mode'})
        if int(settings['max_open_positions']) not in {1, 2, 3}:
            errors.append({'field': 'max_open_positions', 'message': 'must be between 1 and 3'})
        if int(monitoring['interval_seconds']) < 30:
            errors.append({'field': 'monitoring.interval_seconds', 'message': 'must be at least 30 seconds'})
        if not 0 < float(exit_settings['stop_loss_pct']) <= 50:
            errors.append({'field': 'exit.stop_loss_pct', 'message': 'must be > 0 and <= 50'})
        if not 1 <= float(exit_settings['take_profit_pct']) <= 15:
            errors.append({'field': 'exit.take_profit_pct', 'message': 'must be between 1 and 15 percent'})
        try:
            start = date.fromisoformat(operation['start_date'])
            end = date.fromisoformat(operation['end_date'])
            if start > end:
                errors.append({'field': 'operation.period', 'message': 'start_date must be <= end_date'})
        except (TypeError, ValueError):
            errors.append({'field': 'operation.period', 'message': 'dates must be ISO YYYY-MM-DD'})
        if operation['end_policy'] not in {'manage_until_exit', 'close_all'}:
            errors.append({'field': 'operation.end_policy', 'message': 'unsupported end policy'})
        timezone_name = str(operation.get('timezone') or '').strip()
        try:
            ZoneInfo(timezone_name)
        except Exception:
            errors.append({'field': 'operation.timezone', 'message': 'must be a valid IANA timezone'})
        if errors:
            raise AutomationProfileValidationError(errors)

    def _normalize_request(self, request: AutomationProfileWriteRequest, *, current: dict[str, Any] | None = None, require_identity: bool) -> dict[str, Any]:
        payload = request.model_dump(exclude_unset=True)
        base = current or {
            'profile_key': None,
            'name': None,
            'provider': 'kis',
            'market': 'KR',
            'enabled': False,
            'status': 'disabled',
            'settings': copy.deepcopy(DEFAULT_PROFILE_SETTINGS),
        }
        key = str(payload.get('profile_key') or base.get('profile_key') or '').strip().lower()
        name = str(payload.get('name') or base.get('name') or '').strip()
        provider = str(payload.get('provider') or base.get('provider') or 'kis').strip().lower()
        market = str(payload.get('market') or base.get('market') or 'KR').strip().upper()
        if require_identity and not name:
            raise AutomationProfileValidationError([{'field': 'name', 'message': 'name is required'}])
        if key in RESERVED_PROFILE_KEYS:
            raise AutomationProfileValidationError([{'field': 'profile_key', 'message': 'legacy profile key is reserved'}])
        if provider not in ALLOWED_PROVIDERS or market not in ALLOWED_MARKETS:
            raise AutomationProfileValidationError([{'field': 'provider/market', 'message': 'unsupported provider or market'}])
        settings = copy.deepcopy(base.get('settings') or DEFAULT_PROFILE_SETTINGS)
        for section in ('capital', 'universe', 'entry', 'monitoring', 'exit', 'operation'):
            if section in payload and isinstance(payload[section], dict):
                settings[section] = _deep_merge(settings.get(section, {}), payload[section])
        if isinstance(payload.get('settings'), dict):
            settings = _deep_merge(settings, payload['settings'])
        if 'max_open_positions' in payload:
            settings['max_open_positions'] = payload['max_open_positions']
        settings = self._normalize_settings(settings)
        if current is None and 'timezone' not in (payload.get('operation') or {}):
            settings['operation']['timezone'] = 'America/New_York' if market == 'US' else 'Asia/Seoul'
        enabled = bool(payload.get('enabled', base.get('enabled', False)))
        status = str(payload.get('status') or base.get('status') or ('scheduled' if enabled else 'disabled')).lower()
        if status not in ALLOWED_STATUSES:
            raise AutomationProfileValidationError([{'field': 'status', 'message': 'unsupported profile status'}])
        return {'profile_key': key, 'name': name, 'provider': provider, 'market': market, 'enabled': enabled, 'status': status, 'settings': settings}

    def _normalize_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = _deep_merge(copy.deepcopy(DEFAULT_PROFILE_SETTINGS), settings)
        merged['entry']['analysis_times'] = [
            str(value).strip() for value in merged['entry']['analysis_times']
        ]
        merged['universe']['manual_symbols'] = _symbols(merged['universe'].get('manual_symbols'))
        merged['universe']['favorites'] = _symbols(merged['universe'].get('favorites'))
        merged['max_open_positions'] = int(merged.get('max_open_positions') or 1)
        return merged

    def _settings(self, row: StrategyProfile) -> dict[str, Any]:
        try:
            raw = json.loads(row.settings_json or '{}')
        except (TypeError, ValueError):
            raw = {}
        return self._normalize_settings(raw if isinstance(raw, dict) else {})

    def _status(self, row: StrategyProfile | None, *, now: datetime | None = None) -> str:
        if row is None:
            return "disabled"
        if row.custom_status in {"paused", "archived", "disabled"}:
            return str(row.custom_status)
        return self._period_status(row, self._settings(row), now=now) if row.enabled else "disabled"

    def _period_status(
        self,
        row: StrategyProfile,
        settings: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> str:
        current = _aware_in_timezone(now, _profile_timezone(settings, row.market or "KR"))
        current_date = current.date()
        start = date.fromisoformat(settings["operation"]["start_date"])
        end = date.fromisoformat(settings["operation"]["end_date"])
        if current_date < start:
            return "scheduled"
        if current_date > end:
            return "ended"
        return "active" if row.enabled else "disabled"

def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _symbols(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    result = []
    for item in value:
        symbol = str(item or '').strip().upper()
        if symbol and symbol not in result:
            result.append(symbol)
    return result


def _parse_time(value: Any) -> time:
    text = str(value or '').strip()
    if not re.fullmatch(r'\d{2}:\d{2}', text):
        raise ValueError('invalid_time')
    hour, minute = (int(part) for part in text.split(':'))
    return time(hour, minute)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _aware_in_timezone(value: datetime | None, timezone: ZoneInfo) -> datetime:
    if value is None:
        return datetime.now(timezone)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)

def _profile_timezone(settings: dict[str, Any], market: str) -> ZoneInfo:
    operation = settings.get('operation') if isinstance(settings.get('operation'), dict) else {}
    requested = str(operation.get('timezone') or '').strip()
    if requested:
        try:
            return ZoneInfo(requested)
        except Exception:
            pass
    return ZoneInfo('America/New_York' if str(market).upper() == 'US' else 'Asia/Seoul')


def _profile_safety(*, setting_changed: bool, read_only: bool = False) -> dict[str, Any]:
    return {
        'read_only': read_only,
        'safe_execution_only': True,
        'real_order_submitted': False,
        'broker_submit_called': False,
        'manual_submit_called': False,
        'validation_called': False,
        'setting_changed': setting_changed,
        'scheduler_changed': False,
        'dry_run_changed': False,
        'kill_switch_changed': False,
        'kis_real_order_enabled_changed': False,
    }
