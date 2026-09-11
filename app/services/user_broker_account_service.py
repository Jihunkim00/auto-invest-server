from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

import requests
from sqlalchemy.orm import Session

from app.db.models import User, UserBrokerCredential
from app.services.broker_credential_crypto_service import (
    BrokerCredentialCryptoService,
    BrokerCredentialEncryptionNotConfigured,
    BrokerCredentialPayloadError,
)


KIS_BASE_URLS = {
    'paper': 'https://openapivts.koreainvestment.com:29443',
    'live': 'https://openapi.koreainvestment.com:9443',
}
KIS_TOKEN_PATH = '/oauth2/tokenP'
KIS_BALANCE_PATH = '/uapi/domestic-stock/v1/trading/inquire-balance'
KIS_BALANCE_TR_IDS = {'paper': 'VTTC8434R', 'live': 'TTTC8434R'}
KIS_OPEN_ORDERS_PATH = '/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl'
KIS_OPEN_ORDERS_TR_ID = 'TTTC0084R'
ALPACA_BASE_URLS = {
    'paper': 'https://paper-api.alpaca.markets',
    'live': 'https://api.alpaca.markets',
}
TOKEN_REFRESH_MARGIN = timedelta(seconds=30)


class UserBrokerAuthenticationError(RuntimeError):
    '''A user broker rejected authentication or the user token.'''


class UserBrokerUnavailableError(RuntimeError):
    '''A user broker read failed for a non-authentication reason.'''


class UserBrokerEncryptionUnavailableError(RuntimeError):
    '''The user credential encryption key is unavailable.'''


class UserBrokerCredentialsUnavailableError(RuntimeError):
    '''The encrypted user credentials cannot be decrypted.'''


@dataclass(frozen=True)
class _CachedKisToken:
    access_token: str
    expires_at: datetime


class UserKisTokenManager:
    '''In-memory KIS tokens keyed by user, environment, and credential identity.'''

    def __init__(self):
        self._tokens: dict[tuple[int, str, str, str], _CachedKisToken] = {}
        self._locks: dict[tuple[int, str, str, str], threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def get_token(
        self,
        *,
        user_id: int,
        environment: str,
        credential_identity: str,
        credentials: Mapping[str, Any],
        http_client,
        timeout_seconds: float,
        force_refresh: bool = False,
    ) -> str:
        key = (int(user_id), 'kis', environment, credential_identity)
        lock = self._lock_for(key)
        with lock:
            cached = None if force_refresh else self._tokens.get(key)
            if cached is not None and cached.expires_at > _now() + TOKEN_REFRESH_MARGIN:
                return cached.access_token
            token = _issue_kis_token(
                credentials=credentials,
                environment=environment,
                http_client=http_client,
                timeout_seconds=timeout_seconds,
            )
            self._tokens[key] = token
            return token.access_token

    def invalidate(
        self,
        *,
        user_id: int,
        environment: str | None = None,
        credential_identity: str | None = None,
    ) -> None:
        user_id = int(user_id)
        for key in list(self._tokens):
            if key[0] != user_id:
                continue
            if environment is not None and key[2] != environment:
                continue
            if credential_identity is not None and key[3] != credential_identity:
                continue
            self._tokens.pop(key, None)

    def _lock_for(self, key: tuple[int, str, str, str]) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock


_USER_KIS_TOKEN_MANAGER = UserKisTokenManager()


def get_user_kis_token_manager() -> UserKisTokenManager:
    return _USER_KIS_TOKEN_MANAGER


def invalidate_user_kis_tokens(user_id: int) -> None:
    '''Invalidate all cached user KIS tokens after credential changes.'''

    _USER_KIS_TOKEN_MANAGER.invalidate(user_id=user_id)


class UserKisReadOnlyClient:
    '''KIS account reader using one users decrypted credentials.'''

    def __init__(
        self,
        *,
        user_id: int,
        credentials: Mapping[str, Any],
        credential_identity: str,
        http_client=None,
        token_manager: UserKisTokenManager | None = None,
        timeout_seconds: float = 10.0,
    ):
        self.user_id = int(user_id)
        self.credentials = dict(credentials)
        self.environment = str(credentials.get('environment') or '').strip().lower()
        self.credential_identity = credential_identity
        self.http_client = http_client or requests
        self.token_manager = token_manager or get_user_kis_token_manager()
        self.timeout_seconds = timeout_seconds

    def get_snapshot(self) -> dict[str, Any]:
        balance_response = self._get(
            KIS_BALANCE_PATH,
            tr_id=KIS_BALANCE_TR_IDS[self.environment],
            params=self._balance_params(),
        )
        orders_response = self._get(
            KIS_OPEN_ORDERS_PATH,
            tr_id=KIS_OPEN_ORDERS_TR_ID,
            params=self._open_orders_params(),
        )
        return _normalize_kis_snapshot(balance_response, orders_response)

    def _get(self, path: str, *, tr_id: str, params: dict[str, str]) -> dict[str, Any]:
        token = self._token()
        response = self._send_get(path, tr_id=tr_id, params=params, token=token)
        if _kis_auth_failure(response):
            self.token_manager.invalidate(
                user_id=self.user_id,
                environment=self.environment,
                credential_identity=self.credential_identity,
            )
            token = self._token(force_refresh=True)
            response = self._send_get(path, tr_id=tr_id, params=params, token=token)
            if _kis_auth_failure(response):
                raise UserBrokerAuthenticationError('user KIS authentication failed')
        return _require_kis_read_response(response)

    def _token(self, *, force_refresh: bool = False) -> str:
        return self.token_manager.get_token(
            user_id=self.user_id,
            environment=self.environment,
            credential_identity=self.credential_identity,
            credentials=self.credentials,
            http_client=self.http_client,
            timeout_seconds=self.timeout_seconds,
            force_refresh=force_refresh,
        )

    def _send_get(
        self,
        path: str,
        *,
        tr_id: str,
        params: dict[str, str],
        token: str,
    ):
        url = f'{KIS_BASE_URLS[self.environment]}{path}'
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'charset': 'UTF-8',
            'appkey': str(self.credentials.get('app_key') or ''),
            'appsecret': str(self.credentials.get('app_secret') or ''),
            'custtype': 'P',
            'authorization': f'Bearer {token}',
            'tr_id': tr_id,
        }
        try:
            return self.http_client.get(
                url, params=params, headers=headers, timeout=self.timeout_seconds
            )
        except Exception as exc:
            raise UserBrokerUnavailableError('user KIS account request failed') from exc

    def _balance_params(self) -> dict[str, str]:
        return {
            'CANO': str(self.credentials.get('account_no') or ''),
            'ACNT_PRDT_CD': str(self.credentials.get('account_product_code') or ''),
            'AFHR_FLPR_YN': 'N',
            'OFL_YN': '',
            'INQR_DVSN': '02',
            'UNPR_DVSN': '01',
            'FUND_STTL_ICLD_YN': 'N',
            'FNCG_AMT_AUTO_RDPT_YN': 'N',
            'PRCS_DVSN': '00',
            'CTX_AREA_FK100': '',
            'CTX_AREA_NK100': '',
        }

    def _open_orders_params(self) -> dict[str, str]:
        return {
            'CANO': str(self.credentials.get('account_no') or ''),
            'ACNT_PRDT_CD': str(self.credentials.get('account_product_code') or ''),
            'INQR_DVSN_1': '1',
            'INQR_DVSN_2': '0',
            'CTX_AREA_FK100': '',
            'CTX_AREA_NK100': '',
        }


class UserAlpacaReadOnlyClient:
    '''Alpaca account reader using only one users decrypted credentials.'''

    def __init__(self, *, credentials: Mapping[str, Any], http_client=None, timeout_seconds: float = 10.0):
        self.credentials = dict(credentials)
        self.environment = str(credentials.get('environment') or '').strip().lower()
        self.http_client = http_client or requests
        self.timeout_seconds = timeout_seconds

    def get_snapshot(self) -> dict[str, Any]:
        account = self._get('/v2/account')
        positions = self._get('/v2/positions')
        orders = self._get(
            '/v2/orders',
            params={'status': 'open', 'limit': '100', 'nested': 'true'},
        )
        return _normalize_alpaca_snapshot(account, positions, orders)

    def _get(self, path: str, *, params: dict[str, str] | None = None):
        url = f'{ALPACA_BASE_URLS[self.environment]}{path}'
        try:
            response = self.http_client.get(
                url,
                params=params or {},
                headers={
                    'APCA-API-KEY-ID': str(self.credentials.get('api_key') or ''),
                    'APCA-API-SECRET-KEY': str(self.credentials.get('secret_key') or ''),
                },
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            raise UserBrokerUnavailableError('user Alpaca account request failed') from exc

        status = _status_code(response)
        if status in {401, 403}:
            raise UserBrokerAuthenticationError('user Alpaca authentication failed')
        if status >= 400:
            raise UserBrokerUnavailableError('user Alpaca account request failed')
        try:
            payload = response.json()
        except Exception as exc:
            raise UserBrokerUnavailableError('user Alpaca response was invalid') from exc
        if not isinstance(payload, (dict, list)):
            raise UserBrokerUnavailableError('user Alpaca response had an unexpected shape')
        return payload


class UserBrokerAccountService:
    '''Resolve one authenticated users encrypted credentials and read a snapshot.'''

    SUPPORTED_PROVIDERS = {'kis', 'alpaca'}

    def __init__(
        self,
        *,
        crypto=None,
        http_client=None,
        token_manager: UserKisTokenManager | None = None,
        timeout_seconds: float = 10.0,
    ):
        self.crypto = crypto or BrokerCredentialCryptoService()
        self.http_client = http_client or requests
        self.token_manager = token_manager or get_user_kis_token_manager()
        self.timeout_seconds = timeout_seconds

    def get_broker_snapshot(
        self,
        db: Session,
        user: User,
        provider: str,
    ) -> dict[str, Any]:
        normalized_provider = self._provider(provider)
        row = (
            db.query(UserBrokerCredential)
            .filter(
                UserBrokerCredential.user_id == user.id,
                UserBrokerCredential.provider == normalized_provider,
            )
            .first()
        )
        if row is None:
            raise LookupError('broker_credentials_not_configured')

        try:
            self.crypto.ensure_configured()
        except BrokerCredentialEncryptionNotConfigured as exc:
            raise UserBrokerEncryptionUnavailableError from exc
        try:
            credentials = self.crypto.decrypt(
                row.encrypted_payload,
                encryption_version=row.encryption_version,
            )
        except BrokerCredentialPayloadError as exc:
            raise UserBrokerCredentialsUnavailableError from exc
        environment = str(credentials.get('environment') or row.environment or '').strip().lower()
        if environment not in {'paper', 'live'}:
            raise UserBrokerUnavailableError('user broker environment is invalid')

        if normalized_provider == 'kis':
            client = UserKisReadOnlyClient(
                user_id=user.id,
                credentials={**credentials, 'environment': environment},
                credential_identity=_credential_identity(row),
                http_client=self.http_client,
                token_manager=self.token_manager,
                timeout_seconds=self.timeout_seconds,
            )
        else:
            client = UserAlpacaReadOnlyClient(
                credentials={**credentials, 'environment': environment},
                http_client=self.http_client,
                timeout_seconds=self.timeout_seconds,
            )

        snapshot = client.get_snapshot()
        snapshot.update({
            'provider': normalized_provider,
            'environment': environment,
            'connected': True,
            'connection_status': 'connected',
            'fetched_at': _now().isoformat(),
        })
        return snapshot

    @classmethod
    def _provider(cls, provider: str) -> str:
        normalized = str(provider or '').strip().lower()
        if normalized not in cls.SUPPORTED_PROVIDERS:
            raise ValueError('unsupported_broker_provider')
        return normalized


def _issue_kis_token(
    *,
    credentials: Mapping[str, Any],
    environment: str,
    http_client,
    timeout_seconds: float,
) -> _CachedKisToken:
    url = f'{KIS_BASE_URLS[environment]}{KIS_TOKEN_PATH}'
    try:
        response = http_client.post(
            url,
            data=json.dumps({
                'grant_type': 'client_credentials',
                'appkey': str(credentials.get('app_key') or ''),
                'appsecret': str(credentials.get('app_secret') or ''),
            }),
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'charset': 'UTF-8',
            },
            timeout=timeout_seconds,
        )
    except Exception as exc:
        raise UserBrokerUnavailableError('user KIS token request failed') from exc

    if _status_code(response) >= 400:
        raise UserBrokerAuthenticationError('user KIS authentication failed')
    try:
        payload = response.json()
    except Exception as exc:
        raise UserBrokerAuthenticationError('user KIS authentication failed') from exc
    if not isinstance(payload, dict) or not payload.get('access_token'):
        raise UserBrokerAuthenticationError('user KIS authentication failed')

    issued_at = _now()
    return _CachedKisToken(
       str(payload['access_token']),
       _parse_expiration(payload, issued_at),
   )


def _normalize_kis_snapshot(
    balance_response: Mapping[str, Any],
    orders_response: Mapping[str, Any],
) -> dict[str, Any]:
    summary = _first_dict(balance_response.get('output2'))
    positions = [_normalize_kis_position(row) for row in _as_list(balance_response.get('output1'))]
    positions = [item for item in positions if item is not None]
    orders = [_normalize_kis_order(row) for row in _as_list(orders_response.get('output'))]
    orders = [item for item in orders if item is not None]

    cost_basis = _first_number(summary, ('pchs_amt_smtl_amt', 'pchs_amt'))
    if cost_basis is None:
        cost_basis = sum(item['cost_basis'] or 0 for item in positions)
    unrealized_pl = _first_number(summary, ('evlu_pfls_smtl_amt', 'evlu_pfls_amt'))
    if unrealized_pl is None:
        unrealized_pl = sum(item['unrealized_pl'] or 0 for item in positions)
    total_asset_value = _first_number(summary, ('tot_evlu_amt', 'nass_amt', 'tot_asst_amt'))
    stock_value = _first_number(summary, ('scts_evlu_amt',))
    cash = _first_number(summary, ('dnca_tot_amt', 'cash'))
    buying_power = _first_number(summary, ('ord_psbl_cash', 'ord_psbl_amt', 'ord_psbl_cash_amt'))

    return {
        'account': {
            'currency': 'KRW',
            'cash': cash,
            'buying_power': buying_power,
            'equity': total_asset_value,
            'portfolio_value': total_asset_value,
            'stock_evaluation_amount': stock_value,
            'withdrawable_cash': _first_number(summary, ('wdrw_psbl_tot_amt',)),
            'd1_cash': _first_number(summary, ('nxdy_excc_amt',)),
            'd2_cash': _first_number(summary, ('d2_cash', 'd2_excc_amt')),
            'unrealized_pl': unrealized_pl,
            'unrealized_pl_pct': _percentage(unrealized_pl, cost_basis),
        },
        'positions': positions,
        'open_orders': orders,
    }


def _normalize_kis_position(row: Any) -> dict[str, Any] | None:
    item = _as_dict(row)
    quantity = _first_number(item, ('hldg_qty', 'qty')) or 0
    if quantity <= 0:
        return None
    avg_price = _first_number(item, ('pchs_avg_pric', 'avg_prvs'))
    cost_basis = _first_number(item, ('pchs_amt', 'pchs_amt_smtl_amt'))
    if cost_basis is None and avg_price is not None:
        cost_basis = quantity * avg_price
    current_price = _first_number(item, ('prpr', 'stck_prpr'))
    market_value = _first_number(item, ('evlu_amt', 'scts_evlu_amt'))
    if market_value is None and current_price is not None:
        market_value = quantity * current_price
    unrealized_pl = _first_number(item, ('evlu_pfls_amt', 'evlu_pfls'))
    symbol = _first_text(item, ('pdno', 'symbol')) or ''
    return {
        'symbol': symbol,
        'name': _first_text(item, ('prdt_name', 'name')),
        'quantity': quantity,
        'available_quantity': _first_number(item, ('ord_psbl_qty', 'hldg_qty', 'qty')),
        'avg_price': avg_price,
        'current_price': current_price,
        'market_value': market_value,
        'cost_basis': cost_basis,
        'unrealized_pl': unrealized_pl,
        'unrealized_pl_pct': _percentage(unrealized_pl, cost_basis),
    }


def _normalize_alpaca_order(row: Any) -> dict[str, Any] | None:
    item = _as_dict(row)
    quantity = _number(item.get('qty'))
    filled = _number(item.get('filled_qty'))
    remaining = None
    if quantity is not None and filled is not None:
        remaining = max(quantity - filled, 0)
    return {
        'broker_order_id': _first_text(item, ('id', 'order_id')) or '',
        'symbol': _first_text(item, ('symbol',)) or '',
        'side': _first_text(item, ('side',)) or '',
        'quantity': quantity,
        'filled_quantity': filled,
        'remaining_quantity': remaining,
        'order_type': _first_text(item, ('type', 'order_type')),
        'status': _first_text(item, ('status',)) or '',
        'submitted_at': _first_text(item, ('submitted_at',)),
    }


def _require_kis_read_response(response) -> dict[str, Any]:
    status = _status_code(response)
    if status in {401, 403}:
        raise UserBrokerAuthenticationError('user KIS authentication failed')
    if status >= 400:
        raise UserBrokerUnavailableError('user KIS account request failed')
    try:
        payload = response.json()
    except Exception as exc:
        raise UserBrokerUnavailableError('user KIS response was invalid') from exc
    if not isinstance(payload, dict):
        raise UserBrokerUnavailableError('user KIS response had an unexpected shape')
    if str(payload.get('rt_cd', '0') or '0') not in {'', '0'}:
        if _kis_auth_failure(payload):
            raise UserBrokerAuthenticationError('user KIS authentication failed')
        raise UserBrokerUnavailableError('user KIS account request failed')
    return payload


def _kis_auth_failure(value: Any) -> bool:
    status = _status_code(value)
    if status in {401, 403}:
        return True
    if not hasattr(value, 'get'):
        try:
            value = value.json()
        except Exception:
            return False
    if not isinstance(value, Mapping):
        return False
    msg_cd = str(value.get('msg_cd') or '').strip()
    message = str(value.get('msg1') or '').strip().lower()
    return msg_cd == 'EGW00123' or 'token expired' in message or 'expired token' in message


def _parse_expiration(payload: Mapping[str, Any], issued_at: datetime) -> datetime:
    raw = payload.get('access_token_token_expired') or payload.get('expires_at')
    if raw:
        text = str(raw).strip()
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y%m%d%H%M%S'):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=UTC)
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(text.replace('Z', '+00:00')).astimezone(UTC)
        except ValueError:
            pass
    try:
        return issued_at + timedelta(seconds=int(payload.get('expires_in')))
    except (TypeError, ValueError):
        return issued_at + timedelta(hours=23)


def _credential_identity(row: UserBrokerCredential) -> str:
    updated_at = getattr(row, 'updated_at', None) or getattr(row, 'created_at', None)
    identity_value = updated_at.isoformat() if updated_at is not None else 'unknown'
    return f'{row.id}:{identity_value}'


def _first_dict(value: Any) -> dict[str, Any]:
    rows = _as_list(value)
    return _as_dict(rows[0]) if rows else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_text(item: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _first_number(item: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _number(item.get(key))
        if value is not None:
            return value
    return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).strip().replace(',', '')
        return None if not text else float(text)
    except (TypeError, ValueError):
        return None


def _percentage(value: float | None, cost_basis: float | None) -> float | None:
    if value is None or cost_basis is None or cost_basis == 0:
        return None
    return (value / cost_basis) * 100.0


def _normalize_side(value: str | None) -> str:
    text = str(value or '').strip().lower()
    if text in {'02', 'buy'}:
        return 'buy'
    if text in {'01', 'sell'}:
        return 'sell'
    return text or 'unknown'


def _status_code(value: Any) -> int:
    try:
        return int(getattr(value, 'status_code', 0) or 0)
    except (TypeError, ValueError):
        return 0


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_kis_order(row: Any) -> dict[str, Any] | None:
    item = _as_dict(row)
    quantity = _first_number(item, ('ord_qty',))
    remaining = _first_number(item, ('psbl_qty', 'rmn_qty'))
    filled = None
    if quantity is not None and remaining is not None:
        filled = max(quantity - remaining, 0)
    return {
        'broker_order_id': _first_text(item, ('odno', 'order_id')) or '',
        'symbol': _first_text(item, ('pdno', 'symbol')) or '',
        'name': _first_text(item, ('prdt_name', 'name')),
        'side': _normalize_side(_first_text(item, ('sll_buy_dvsn_cd', 'sll_buy_dvsn_name'))),
        'quantity': quantity,
        'filled_quantity': filled,
        'remaining_quantity': remaining,
        'order_price': _first_number(item, ('ord_unpr', 'order_price')),
        'status': _first_text(item, ('status',)) or 'pending',
        'submitted_at': _first_text(item, ('ord_tmd', 'submitted_at')),
    }


def _normalize_alpaca_snapshot(
    account_raw: Any,
    positions_raw: Any,
    orders_raw: Any,
) -> dict[str, Any]:
    account_item = _as_dict(account_raw)
    positions = [_normalize_alpaca_position(row) for row in _as_list(positions_raw)]
    positions = [item for item in positions if item is not None]
    orders = [_normalize_alpaca_order(row) for row in _as_list(orders_raw)]
    orders = [item for item in orders if item is not None]
    cost_basis = sum(item['cost_basis'] or 0 for item in positions)
    unrealized_pl = sum(item['unrealized_pl'] or 0 for item in positions)
    return {
        'account': {
            'currency': _first_text(account_item, ('currency',)) or 'USD',
            'cash': _number(account_item.get('cash')),
            'buying_power': _number(account_item.get('buying_power')),
            'equity': _number(account_item.get('equity')),
            'portfolio_value': _number(account_item.get('portfolio_value')),
            'unrealized_pl': unrealized_pl,
            'unrealized_pl_pct': _percentage(unrealized_pl, cost_basis),
        },
        'positions': positions,
        'open_orders': orders,
    }


def _normalize_alpaca_position(row: Any) -> dict[str, Any] | None:
    item = _as_dict(row)
    quantity = _number(item.get('qty'))
    if quantity is None or quantity == 0:
        return None
    avg_price = _number(item.get('avg_entry_price'))
    cost_basis = _number(item.get('cost_basis'))
    if cost_basis is None and avg_price is not None:
        cost_basis = abs(quantity) * avg_price
    unrealized_pl = _number(item.get('unrealized_pl'))
    return {
        'symbol': _first_text(item, ('symbol',)) or '',
        'name': _first_text(item, ('name',)),
        'quantity': quantity,
        'available_quantity': quantity,
        'avg_price': avg_price,
        'current_price': _number(item.get('current_price')),
        'market_value': _number(item.get('market_value')),
        'cost_basis': cost_basis,
        'unrealized_pl': unrealized_pl,
        'unrealized_pl_pct': _percentage(unrealized_pl, cost_basis),
    }
