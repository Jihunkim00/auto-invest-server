from __future__ import annotations

from typing import Any

from app.core.automation_mode import automation_mode_authority


LEGACY_EXECUTION_FLAGS = (
    'dry_run',
    'kill_switch',
    'runtime_authorized',
    'live_order_possible',
    'kis_real_order_enabled',
    'strategy_live_auto_buy_enabled',
    'strategy_live_auto_buy_scheduler_enabled',
    'auto_buy_live_phase1_enabled',
)


class AutomationExecutionAuthorityService:
    '''Single source of truth for user-controlled automation execution authority.'''

    def __init__(self, runtime_settings: Any | None = None) -> None:
        self.runtime_settings = runtime_settings

    def snapshot(self, db) -> dict[str, Any]:
        runtime_settings = self.runtime_settings
        if runtime_settings is None:
            try:
                from app.services.runtime_setting_service import RuntimeSettingService

                runtime_settings = RuntimeSettingService()
            except Exception:
                runtime_settings = None

        if runtime_settings is None:
            return self._off_snapshot(reason='automation_mode_unavailable')

        try:
            settings = runtime_settings.get_settings_read_only(db)
            authority = automation_mode_authority(settings.get('automation_mode'))
            legacy_flags = {
                key: settings.get(key)
                for key in LEGACY_EXECUTION_FLAGS
            }
            return {
                **authority,
                'legacy_flags': legacy_flags,
                'legacy_flags_ignored': list(LEGACY_EXECUTION_FLAGS),
                'authority_snapshot_source': 'AutomationExecutionAuthorityService',
            }
        except Exception:
            return self._off_snapshot(reason='automation_mode_unavailable')

    def is_scheduler_allowed(self, db) -> bool:
        return bool(self.snapshot(db).get('scheduler_allowed'))

    def is_simulation_allowed(self, db) -> bool:
        return bool(self.snapshot(db).get('simulation_allowed'))

    def is_broker_submit_allowed(self, db) -> bool:
        snapshot = self.snapshot(db)
        return snapshot.get('automation_mode') == 'live'

    @staticmethod
    def _off_snapshot(*, reason: str) -> dict[str, Any]:
        authority = automation_mode_authority('off')
        return {
            **authority,
            'legacy_flags': {},
            'legacy_flags_ignored': list(LEGACY_EXECUTION_FLAGS),
            'authority_snapshot_source': 'AutomationExecutionAuthorityService',
            'authority_block_reason': reason,
        }
