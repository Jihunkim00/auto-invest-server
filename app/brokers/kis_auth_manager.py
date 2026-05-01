from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Callable

import requests
from sqlalchemy.orm import Session

from app.brokers.base import KisAuthError, KisConfigurationError
from app.config import get_settings
from app.db.database import SessionLocal
from app.db.models import BrokerAuthToken


@dataclass(frozen=True)
class KisTokenResult:
    token_type: str
    token: str = field(repr=False)
    expires_at: datetime | None
    issued_at: datetime
    source: str
    environment: str


class KisAuthManager:
    def __init__(self, settings=None, db: Session | None = None):
        self.settings = settings or get_settings()
        self.db = db

    def is_configured(self) -> bool:
        return all(
            [
                self.settings.kis_app_key,
                self.settings.kis_app_secret,
                self.settings.kis_account_no,
                self.settings.kis_account_product_code,
                self.settings.kis_base_url,
            ]
        )

    def require_configured(self) -> None:
        missing = []
        for field_name, env_name in [
            ("kis_app_key", "KIS_APP_KEY"),
            ("kis_app_secret", "KIS_APP_SECRET"),
            ("kis_account_no", "KIS_ACCOUNT_NO"),
            ("kis_account_product_code", "KIS_ACCOUNT_PRODUCT_CODE"),
            ("kis_base_url", "KIS_BASE_URL"),
        ]:
            if not getattr(self.settings, field_name, None):
                missing.append(env_name)

        if missing:
            raise KisConfigurationError(
                "KIS configuration is incomplete; missing "
                + ", ".join(missing)
                + "."
            )

    def get_cached_access_token(self) -> str | None:
        row = self._get_cached_token("access_token")
        return row.token_value if row else None

    def get_cached_approval_key(self) -> str | None:
        row = self._get_cached_token("approval_key")
        return row.token_value if row else None

    def issue_access_token(self, force_refresh: bool = False) -> KisTokenResult:
        if not force_refresh:
            cached = self._cached_result("access_token")
            if cached is not None:
                return cached

        self.require_configured()
        issued_at = self._now()
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.settings.kis_app_key,
            "appsecret": self.settings.kis_app_secret,
        }
        response_data = self._post_auth_json("/oauth2/tokenP", payload, "access_token")
        token = response_data.get("access_token")
        if not token:
            raise KisAuthError("KIS access token response did not include a token.")

        expires_at = self._parse_access_token_expiration(response_data, issued_at)
        return self._store_token(
            token_type="access_token",
            token=token,
            expires_at=expires_at,
            issued_at=issued_at,
        )

    def issue_approval_key(self, force_refresh: bool = False) -> KisTokenResult:
        if not force_refresh:
            cached = self._cached_result("approval_key")
            if cached is not None:
                return cached

        self.require_configured()
        issued_at = self._now()
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.settings.kis_app_key,
            "secretkey": self.settings.kis_app_secret,
        }
        access_token = self.get_cached_access_token()
        if access_token:
            payload["token"] = access_token

        response_data = self._post_auth_json("/oauth2/Approval", payload, "approval_key")
        token = response_data.get("approval_key")
        if not token:
            raise KisAuthError("KIS approval key response did not include a key.")

        return self._store_token(
            token_type="approval_key",
            token=token,
            expires_at=None,
            issued_at=issued_at,
        )

    def get_valid_access_token(self, force_refresh: bool = False) -> KisTokenResult:
        return self.issue_access_token(force_refresh=force_refresh)

    def get_valid_approval_key(self, force_refresh: bool = False) -> KisTokenResult:
        return self.issue_approval_key(force_refresh=force_refresh)

    def clear_cached_tokens(self) -> None:
        self._with_session(
            lambda db: db.query(BrokerAuthToken)
            .filter(BrokerAuthToken.provider == "kis")
            .delete(synchronize_session=False),
            commit=True,
        )

    def get_auth_status(self) -> dict:
        access = self._get_cached_token("access_token")
        approval = self._get_cached_token("approval_key")
        return {
            "kis_enabled": bool(self.settings.kis_enabled),
            "kis_configured": self.is_configured(),
            "kis_env": self.settings.kis_env,
            "has_access_token": access is not None,
            "access_token_expires_at": self._iso_or_none(
                access.expires_at if access else None
            ),
            "has_approval_key": approval is not None,
            "approval_key_expires_at": self._iso_or_none(
                approval.expires_at if approval else None
            ),
        }

    def _post_auth_json(self, path: str, payload: dict, token_type: str) -> dict:
        url = f"{str(self.settings.kis_base_url).rstrip('/')}{path}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
        }

        try:
            response = requests.post(
                url,
                data=json.dumps(payload),
                headers=headers,
                timeout=10,
            )
        except requests.RequestException as exc:
            raise KisAuthError(f"KIS {token_type} request failed: {type(exc).__name__}.") from exc

        if response.status_code >= 400:
            raise KisAuthError(
                f"KIS {token_type} request failed with HTTP {response.status_code}."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise KisAuthError(f"KIS {token_type} response was not valid JSON.") from exc

        if not isinstance(data, dict):
            raise KisAuthError(f"KIS {token_type} response had an unexpected shape.")
        return data

    def _cached_result(self, token_type: str) -> KisTokenResult | None:
        row = self._get_cached_token(token_type)
        if row is None:
            return None
        return KisTokenResult(
            token_type=row.token_type,
            token=row.token_value,
            expires_at=self._as_utc(row.expires_at),
            issued_at=self._as_utc(row.issued_at) or self._now(),
            source="cache",
            environment=row.environment,
        )

    def _get_cached_token(self, token_type: str) -> BrokerAuthToken | None:
        def query(db: Session):
            rows = (
                db.query(BrokerAuthToken)
                .filter(
                    BrokerAuthToken.provider == "kis",
                    BrokerAuthToken.token_type == token_type,
                    BrokerAuthToken.environment == self.settings.kis_env,
                )
                .order_by(BrokerAuthToken.updated_at.desc(), BrokerAuthToken.id.desc())
                .all()
            )
            for row in rows:
                if row.token_value and self._is_unexpired(row.expires_at):
                    return row
            return None

        return self._with_session(query)

    def _store_token(
        self,
        *,
        token_type: str,
        token: str,
        expires_at: datetime | None,
        issued_at: datetime,
    ) -> KisTokenResult:
        def save(db: Session):
            row = (
                db.query(BrokerAuthToken)
                .filter(
                    BrokerAuthToken.provider == "kis",
                    BrokerAuthToken.token_type == token_type,
                    BrokerAuthToken.environment == self.settings.kis_env,
                )
                .order_by(BrokerAuthToken.updated_at.desc(), BrokerAuthToken.id.desc())
                .first()
            )
            if row is None:
                row = BrokerAuthToken(
                    provider="kis",
                    token_type=token_type,
                    environment=self.settings.kis_env,
                )
                db.add(row)

            row.token_value = token
            row.expires_at = expires_at
            row.issued_at = issued_at
            row.updated_at = issued_at
            db.commit()
            db.refresh(row)
            return row

        row = self._with_session(save)
        return KisTokenResult(
            token_type=row.token_type,
            token=row.token_value,
            expires_at=self._as_utc(row.expires_at),
            issued_at=self._as_utc(row.issued_at) or issued_at,
            source="issued",
            environment=row.environment,
        )

    def _with_session(self, fn: Callable[[Session], object], *, commit: bool = False):
        if self.db is not None:
            result = fn(self.db)
            if commit:
                self.db.commit()
            return result

        db = SessionLocal()
        try:
            result = fn(db)
            if commit:
                db.commit()
            return result
        finally:
            db.close()

    def _parse_access_token_expiration(
        self, response_data: dict, issued_at: datetime
    ) -> datetime | None:
        raw_expires_at = response_data.get("access_token_token_expired") or response_data.get(
            "expires_at"
        )
        parsed = self._parse_datetime(raw_expires_at)
        if parsed is not None:
            return parsed

        expires_in = response_data.get("expires_in")
        try:
            if expires_in is not None:
                return issued_at + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            pass

        return issued_at + timedelta(hours=23)

    def _parse_datetime(self, raw_value) -> datetime | None:
        if raw_value is None:
            return None
        if isinstance(raw_value, datetime):
            return self._as_utc(raw_value)

        value = str(raw_value).strip()
        if not value:
            return None

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=UTC)
            except ValueError:
                pass

        try:
            return self._as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None

    def _is_unexpired(self, expires_at: datetime | None) -> bool:
        normalized = self._as_utc(expires_at)
        if normalized is None:
            return True
        return normalized > self._now()

    def _as_utc(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _iso_or_none(self, value: datetime | None) -> str | None:
        normalized = self._as_utc(value)
        return normalized.isoformat() if normalized else None

    def _now(self) -> datetime:
        return datetime.now(UTC)
