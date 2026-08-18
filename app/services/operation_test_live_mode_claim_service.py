from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.db.models import (
    OperationTestLiveModeClaim,
    RuntimeSetting,
)


TEST3_OWNER = "test3"
TEST4_OWNER = "test4"
UNCLAIMED_OWNER = ""
OPERATION_TEST3_ACTIVATION_KEYS = (
    "operation_test3_enabled",
    "operation_test3_scheduler_enabled",
    "operation_test3_allow_real_orders",
    "operation_test3_position_management_enabled",
)
OPERATION_TEST4_ACTIVATION_KEYS = (
    "operation_test4_enabled",
    "operation_test4_scheduler_enabled",
    "operation_test4_allow_real_entry",
    "operation_test4_allow_real_exit",
    "operation_test4_entry_enabled",
    "operation_test4_position_management_enabled",
)
OPERATION_TEST_MODE_SETTING_KEYS = frozenset(
    OPERATION_TEST3_ACTIVATION_KEYS + OPERATION_TEST4_ACTIVATION_KEYS
)
_FAIL_CLOSED_RUNTIME_VALUES = {
    "dry_run": True,
    "kill_switch": True,
    "operation_test3_enabled": False,
    "operation_test3_scheduler_enabled": False,
    "operation_test3_allow_real_orders": False,
    "operation_test3_position_management_enabled": False,
    "operation_test3_stop_loss_enabled": False,
    "operation_test3_take_profit_enabled": False,
    "operation_test4_enabled": False,
    "operation_test4_scheduler_enabled": False,
    "operation_test4_allow_real_entry": False,
    "operation_test4_allow_real_exit": False,
    "operation_test4_entry_enabled": False,
    "operation_test4_position_management_enabled": False,
    "operation_test4_stop_loss_enabled": False,
    "operation_test4_take_profit_enabled": False,
}


class OperationTestLiveModeConflict(RuntimeError):
    """A requested Test3/Test4 mode would violate the durable mode claim."""

    def __init__(self, active_owner: str | None) -> None:
        self.active_owner = active_owner
        super().__init__(
            "Operation Test3 and Operation Test4 cannot be active together"
        )


class _ClaimRetry(RuntimeError):
    pass


class OperationTestLiveModeClaimService:
    """Cross-worker Test3/Test4 mutual exclusion coupled to runtime mutations."""

    SCOPE_KEY = "operation_test3_test4_live"
    _MAX_LOCK_ATTEMPTS = 3

    def update_runtime_settings(
        self,
        db: Session,
        *,
        runtime_settings: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply Test3/Test4 runtime changes and claim ownership in one commit.

        The claim generation is updated with a compare-and-swap before the
        runtime row is changed. That makes SQLite writers serialize as well as
        row-locking databases, while a concurrent stale request rolls back and
        retries with fresh state rather than releasing a newer mode claim.
        """

        for attempt in range(self._MAX_LOCK_ATTEMPTS):
            transient_runtime_row: RuntimeSetting | None = None
            try:
                claim = self._lock_claim_for_runtime_update(db)
                runtime_rows = list(
                    db.execute(
                        select(RuntimeSetting)
                        .order_by(RuntimeSetting.id.asc())
                        .with_for_update()
                    ).scalars()
                )
                if not runtime_rows:
                    transient_runtime_row = runtime_settings.get_or_create(
                        db,
                        commit=False,
                    )
                    runtime_rows = [transient_runtime_row]
                if len(runtime_rows) != 1:
                    self._force_safe_runtime_rows(runtime_rows)
                    claim.owner = UNCLAIMED_OWNER
                    db.flush()
                    db.commit()
                    raise OperationTestLiveModeConflict(
                        "runtime_settings_ambiguous"
                    )

                settings = runtime_settings.update_settings(
                    db,
                    payload,
                    commit=False,
                )
                desired_owner = self._desired_owner(settings)
                active_owner = self._owner(claim.owner)
                if desired_owner is not None and active_owner not in {
                    None,
                    desired_owner,
                }:
                    raise OperationTestLiveModeConflict(active_owner)

                claim.owner = desired_owner or UNCLAIMED_OWNER
                db.flush()
                db.commit()
                return settings
            except _ClaimRetry:
                self._rollback_mode_transaction(db, transient_runtime_row)
                if attempt + 1 == self._MAX_LOCK_ATTEMPTS:
                    raise OperationTestLiveModeConflict("transition_in_progress")
            except IntegrityError:
                self._rollback_mode_transaction(db, transient_runtime_row)
                if attempt + 1 == self._MAX_LOCK_ATTEMPTS:
                    raise OperationTestLiveModeConflict("transition_in_progress")
            except OperationalError:
                self._rollback_mode_transaction(db, transient_runtime_row)
                if attempt + 1 == self._MAX_LOCK_ATTEMPTS:
                    raise OperationTestLiveModeConflict("transition_in_progress")
            except OperationTestLiveModeConflict:
                self._rollback_mode_transaction(db, transient_runtime_row)
                raise
            except Exception:
                self._rollback_mode_transaction(db, transient_runtime_row)
                raise

        raise OperationTestLiveModeConflict("transition_in_progress")

    def acquire(self, db: Session, *, owner: str) -> bool:
        """Compatibility helper for explicit fail-closed test/operator claims."""

        try:
            claim = self._lock_claim_for_runtime_update(db)
            active_owner = self._owner(claim.owner)
            if active_owner not in {None, owner}:
                db.rollback()
                return False
            claim.owner = owner
            db.flush()
            db.commit()
            return True
        except (IntegrityError, OperationalError, _ClaimRetry):
            db.rollback()
            return False
        except Exception:
            db.rollback()
            raise

    def release(
        self,
        db: Session,
        *,
        owner: str,
        expected_generation: int | None = None,
    ) -> bool:
        """Compatibility-only conditional release; runtime paths use one commit."""

        try:
            claim = self._lock_claim_for_runtime_update(db)
            previous_generation = int(claim.generation or 0) - 1
            if self._owner(claim.owner) != owner or (
                expected_generation is not None
                and previous_generation != expected_generation
            ):
                db.rollback()
                return False
            claim.owner = UNCLAIMED_OWNER
            db.flush()
            db.commit()
            return True
        except (IntegrityError, OperationalError, _ClaimRetry):
            db.rollback()
            return False
        except Exception:
            db.rollback()
            raise

    def _lock_claim_for_runtime_update(
        self,
        db: Session,
    ) -> OperationTestLiveModeClaim:
        claim = db.execute(
            select(OperationTestLiveModeClaim)
            .where(OperationTestLiveModeClaim.scope_key == self.SCOPE_KEY)
            .with_for_update()
        ).scalar_one_or_none()
        if claim is None:
            claim = OperationTestLiveModeClaim(
                scope_key=self.SCOPE_KEY,
                owner=UNCLAIMED_OWNER,
                generation=0,
            )
            db.add(claim)
            db.flush()

        expected_generation = int(claim.generation or 0)
        result = db.execute(
            update(OperationTestLiveModeClaim)
            .where(OperationTestLiveModeClaim.scope_key == self.SCOPE_KEY)
            .where(OperationTestLiveModeClaim.generation == expected_generation)
            .values(generation=expected_generation + 1)
        )
        if int(result.rowcount or 0) != 1:
            raise _ClaimRetry()
        db.flush()
        db.expire(claim)
        return db.execute(
            select(OperationTestLiveModeClaim)
            .where(OperationTestLiveModeClaim.scope_key == self.SCOPE_KEY)
            .with_for_update()
        ).scalar_one()

    @staticmethod
    def _rollback_mode_transaction(
        db: Session,
        transient_runtime_row: RuntimeSetting | None,
    ) -> None:
        db.rollback()
        if transient_runtime_row is not None and transient_runtime_row in db:
            db.expunge(transient_runtime_row)

    @staticmethod
    def _force_safe_runtime_rows(rows: list[RuntimeSetting]) -> None:
        for row in rows:
            for key, value in _FAIL_CLOSED_RUNTIME_VALUES.items():
                setattr(row, key, value)

    @staticmethod
    def _owner(value: Any) -> str | None:
        normalized = str(value or "").strip().lower()
        return normalized if normalized in {TEST3_OWNER, TEST4_OWNER} else None

    @staticmethod
    def _desired_owner(settings: dict[str, Any]) -> str | None:
        test3_active = any(
            settings.get(key) is True for key in OPERATION_TEST3_ACTIVATION_KEYS
        )
        test4_active = any(
            settings.get(key) is True for key in OPERATION_TEST4_ACTIVATION_KEYS
        )
        if test3_active and test4_active:
            raise OperationTestLiveModeConflict("both_runtime_modes_active")
        if test3_active:
            return TEST3_OWNER
        if test4_active:
            return TEST4_OWNER
        return None