from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Mapping

import requests


KIS_BASE_URLS = {
    "paper": "https://openapivts.koreainvestment.com:29443",
    "live": "https://openapi.koreainvestment.com:9443",
}
KIS_TOKEN_PATH = "/oauth2/tokenP"
KIS_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
KIS_BALANCE_TR_IDS = {
    "paper": "VTTC8434R",
    "live": "TTTC8434R",
}
ALPACA_BASE_URLS = {
    "paper": "https://paper-api.alpaca.markets",
    "live": "https://api.alpaca.markets",
}
ALPACA_ACCOUNT_PATH = "/v2/account"


class UserBrokerValidationService:
    """Read-only validation for credentials supplied by a regular user.

    KIS tokens remain in memory for one validation call only. This service
    intentionally does not use the admin KisAuthManager token cache and does
    not expose any order submission operation.
    """

    def __init__(self, *, http_client=None, timeout_seconds: float = 10.0):
        self.http_client = http_client or requests
        self.timeout_seconds = timeout_seconds

    def validate(self, provider: str, credentials: Mapping[str, Any]) -> dict[str, Any]:
        normalized_provider = str(provider or "").strip().lower()
        if normalized_provider == "kis":
            return self._validate_kis(credentials)
        if normalized_provider == "alpaca":
            return self._validate_alpaca(credentials)
        raise ValueError("Unsupported broker provider.")

    def _validate_kis(self, credentials: Mapping[str, Any]) -> dict[str, Any]:
        environment = str(credentials.get("environment") or "").strip().lower()
        app_key = str(credentials.get("app_key") or "").strip()
        app_secret = str(credentials.get("app_secret") or "").strip()
        account_no = str(credentials.get("account_no") or "").strip()
        product_code = str(credentials.get("account_product_code") or "").strip()

        if (
            environment not in KIS_BASE_URLS
            or not app_key
            or not app_secret
            or not account_no
            or not product_code
        ):
            return self._failed("kis", "invalid_credentials")

        base_url = KIS_BASE_URLS[environment]
        token_url = f"{base_url}{KIS_TOKEN_PATH}"
        token_payload = {
            "grant_type": "client_credentials",
            "appkey": app_key,
            "appsecret": app_secret,
        }
        token_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "charset": "UTF-8",
        }

        try:
            token_response = self.http_client.post(
                token_url,
                data=json.dumps(token_payload),
                headers=token_headers,
                timeout=self.timeout_seconds,
            )
        except Exception:
            return self._failed("kis", "network_error")

        token_data = self._response_json(token_response)
        if (
            self._status_code(token_response) >= 400
            or not isinstance(token_data, dict)
            or not token_data.get("access_token")
        ):
            return self._failed("kis", "authentication_failed")

        balance_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "charset": "UTF-8",
            "appkey": app_key,
            "appsecret": app_secret,
            "custtype": "P",
            "authorization": f"Bearer {token_data['access_token']}",
            "tr_id": KIS_BALANCE_TR_IDS[environment],
        }
        balance_params = {
            "CANO": account_no,
            "ACNT_PRDT_CD": product_code,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        try:
            balance_response = self.http_client.get(
                f"{base_url}{KIS_BALANCE_PATH}",
                params=balance_params,
                headers=balance_headers,
                timeout=self.timeout_seconds,
            )
        except Exception:
            return self._failed("kis", "network_error")

        balance_data = self._response_json(balance_response)
        if (
            self._status_code(balance_response) >= 400
            or not isinstance(balance_data, dict)
            or str(balance_data.get("rt_cd", "0")) not in {"", "0"}
        ):
            return self._failed("kis", "account_query_failed")

        return self._success("kis")

    def _validate_alpaca(self, credentials: Mapping[str, Any]) -> dict[str, Any]:
        environment = str(credentials.get("environment") or "").strip().lower()
        api_key = str(credentials.get("api_key") or "").strip()
        secret_key = str(credentials.get("secret_key") or "").strip()
        if environment not in ALPACA_BASE_URLS or not api_key or not secret_key:
            return self._failed("alpaca", "invalid_credentials")

        try:
            response = self.http_client.get(
                f"{ALPACA_BASE_URLS[environment]}{ALPACA_ACCOUNT_PATH}",
                headers={
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": secret_key,
                },
                timeout=self.timeout_seconds,
            )
        except Exception:
            return self._failed("alpaca", "network_error")

        response_data = self._response_json(response)
        if self._status_code(response) in {401, 403}:
            return self._failed("alpaca", "authentication_failed")
        if self._status_code(response) >= 400 or not isinstance(response_data, dict):
            return self._failed("alpaca", "account_query_failed")

        return self._success("alpaca")

    @staticmethod
    def _status_code(response) -> int:
        try:
            return int(getattr(response, "status_code", 0) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _response_json(response):
        try:
            return response.json()
        except (AttributeError, TypeError, ValueError):
            return None

    @staticmethod
    def _success(provider: str) -> dict[str, Any]:
        return {
            "provider": provider,
            "valid": True,
            "status": "success",
            "message": None,
            "validated_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _failed(provider: str, message: str) -> dict[str, Any]:
        return {
            "provider": provider,
            "valid": False,
            "status": "failed",
            "message": message,
            "validated_at": datetime.now(UTC).isoformat(),
        }

