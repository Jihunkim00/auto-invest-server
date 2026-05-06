from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import requests

from app.brokers.base import BrokerNotEnabledError, KisApiError
from app.brokers.kis_auth_manager import KisAuthManager
from app.config import get_settings
from app.services.kis_payload_sanitizer import (
    mask_kis_account_value,
    sanitize_kis_payload,
    sanitize_kis_text,
)

# Official sample references:
# - examples_llm/domestic_stock/inquire_price/inquire_price.py
# - examples_llm/domestic_stock/inquire_daily_itemchartprice/inquire_daily_itemchartprice.py
# - examples_llm/domestic_stock/inquire_balance/inquire_balance.py
# - examples_llm/domestic_stock/inquire_psbl_rvsecncl/inquire_psbl_rvsecncl.py
KIS_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
KIS_PRICE_TR_ID = "FHKST01010100"
KIS_DAILY_BARS_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
KIS_DAILY_BARS_TR_ID = "FHKST03010100"
KIS_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
KIS_BALANCE_TR_ID_REAL = "TTTC8434R"
KIS_BALANCE_TR_ID_DEMO = "VTTC8434R"
KIS_OPEN_ORDERS_PATH = "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
KIS_OPEN_ORDERS_TR_ID = "TTTC0084R"
KIS_DAILY_ORDER_EXECUTIONS_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
KIS_DAILY_ORDER_EXECUTIONS_TR_ID_REAL = "TTTC8001R"
KIS_DAILY_ORDER_EXECUTIONS_TR_ID_DEMO = "VTTC8001R"
KIS_CASH_ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
KIS_CASH_BUY_TR_ID_REAL = "TTTC0802U"
KIS_CASH_SELL_TR_ID_REAL = "TTTC0801U"
KIS_CASH_BUY_TR_ID_DEMO = "VTTC0802U"
KIS_CASH_SELL_TR_ID_DEMO = "VTTC0801U"
KIS_MARKET_ORDER_DIVISION = "01"
KIS_TOKEN_REFRESH_GUARD_DEFAULT = timedelta(hours=23)


class KisClient:
    """Safe KIS Open API client for auth, reads, and explicit cash orders.

    Order submission is exposed only through a dedicated method; callers must
    enforce the manual safety gates before invoking it.
    """

    def __init__(self, settings=None, auth_manager: KisAuthManager | None = None):
        self.settings = settings or get_settings()
        self.auth_manager = auth_manager or KisAuthManager(self.settings)

    def is_configured(self) -> bool:
        return self.auth_manager.is_configured()

    def get_access_token(self, force_refresh: bool = False):
        return self.auth_manager.get_valid_access_token(force_refresh=force_refresh)

    def get_approval_key(self, force_refresh: bool = False):
        return self.auth_manager.get_valid_approval_key(force_refresh=force_refresh)

    def build_headers(
        self,
        tr_id: str | None = None,
        *,
        include_auth: bool = True,
        access_token: str | None = None,
    ) -> dict[str, str]:
        self.auth_manager.require_configured()

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "charset": "UTF-8",
            "appkey": self.settings.kis_app_key,
            "appsecret": self.settings.kis_app_secret,
            "custtype": "P",
        }
        if include_auth:
            if access_token is None:
                token = self.get_access_token()
                access_token = token.token
            headers["authorization"] = f"Bearer {access_token}"
        if tr_id:
            headers["tr_id"] = tr_id
        return headers

    def request_get(
        self,
        path: str,
        *,
        tr_id: str,
        params: dict | None = None,
    ) -> dict:
        return self._request("GET", path, tr_id=tr_id, params=params)

    def request_post(
        self,
        path: str,
        *,
        tr_id: str,
        payload: dict | None = None,
    ) -> dict:
        return self._request("POST", path, tr_id=tr_id, payload=payload)

    def issue_access_token(self):
        return self.get_access_token(force_refresh=True)

    def issue_approval_key(self):
        return self.get_approval_key(force_refresh=True)

    def get_domestic_stock_price(self, symbol: str) -> dict:
        normalized_symbol = symbol.strip()
        response = self.request_get(
            KIS_PRICE_PATH,
            tr_id=KIS_PRICE_TR_ID,
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": normalized_symbol,
            },
        )
        output = _as_dict(response.get("output"))
        return {
            "provider": "kis",
            "environment": self.settings.kis_env,
            "symbol": normalized_symbol,
            "name": output.get("hts_kor_isnm") or output.get("prdt_name"),
            "current_price": to_float(output.get("stck_prpr")),
            "change": to_float(output.get("prdy_vrss")),
            "change_rate": normalize_percent(output.get("prdy_ctrt")),
            "timestamp": self._timestamp_from_output(output),
            "raw_status": "ok",
            "raw": _safe_raw(response),
        }

    def get_domestic_daily_bars(self, symbol: str, limit: int = 120) -> list[dict]:
        """Return normalized read-only KIS daily OHLCV bars, oldest first."""
        normalized_symbol = symbol.strip()
        safe_limit = max(1, min(int(limit or 120), 240))
        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=max(safe_limit * 3, 90))

        response = self.request_get(
            KIS_DAILY_BARS_PATH,
            tr_id=KIS_DAILY_BARS_TR_ID,
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": normalized_symbol,
                "FID_INPUT_DATE_1": start_date.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": end_date.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": "0",
            },
        )
        return normalize_domestic_daily_bars(
            normalized_symbol,
            _as_list(response.get("output2")),
            limit=safe_limit,
        )

    def get_account_balance(self) -> dict:
        response = self._request_balance()
        summary = _first_dict(response.get("output2"))

        cash = first_float(summary, ["dnca_tot_amt", "nass_amt", "cash"])
        stock_evaluation_amount = first_float(summary, ["scts_evlu_amt", "tot_evlu_amt"])
        total_asset_value = first_float(
            summary, ["tot_evlu_amt", "nass_amt", "tot_asst_amt"]
        )
        purchase_amount = first_float(summary, ["pchs_amt_smtl_amt", "pchs_amt"])
        unrealized_pl = first_float(summary, ["evlu_pfls_smtl_amt", "evlu_pfls_amt"])
        unrealized_plpc = normalize_percent(
            first_present(summary, ["asst_icdc_erng_rt", "evlu_pfls_rt"])
        )

        return {
            "provider": "kis",
            "environment": self.settings.kis_env,
            "currency": "KRW",
            "cash": cash,
            "total_asset_value": total_asset_value,
            "stock_evaluation_amount": stock_evaluation_amount,
            "purchase_amount": purchase_amount,
            "unrealized_pl": unrealized_pl,
            "unrealized_plpc": unrealized_plpc,
            "raw_status": "ok",
        }

    def list_positions(self) -> list[dict]:
        response = self._request_balance()
        rows = _as_list(response.get("output1"))
        positions = []

        for row in rows:
            item = _as_dict(row)
            qty = first_float(item, ["hldg_qty", "qty"])
            if qty <= 0:
                continue

            avg_entry_price = first_float(item, ["pchs_avg_pric", "avg_prvs"])
            cost_basis = first_float(item, ["pchs_amt", "pchs_amt_smtl_amt"])
            if cost_basis <= 0 and avg_entry_price > 0:
                cost_basis = qty * avg_entry_price
            current_price = first_float(item, ["prpr", "stck_prpr"])
            market_value = first_float(item, ["evlu_amt", "scts_evlu_amt"])
            if market_value <= 0 and current_price > 0:
                market_value = qty * current_price
            unrealized_pl = first_float(item, ["evlu_pfls_amt", "evlu_pfls"])
            unrealized_plpc = normalize_percent(
                first_present(item, ["evlu_pfls_rt", "evlu_pfls_erng_rt"])
            )
            if unrealized_plpc == 0 and cost_basis > 0 and unrealized_pl != 0:
                unrealized_plpc = unrealized_pl / cost_basis

            positions.append(
                {
                    "symbol": item.get("pdno") or item.get("symbol") or "",
                    "name": item.get("prdt_name") or item.get("name"),
                    "qty": qty,
                    "avg_entry_price": avg_entry_price,
                    "cost_basis": cost_basis,
                    "current_price": current_price,
                    "market_value": market_value,
                    "unrealized_pl": unrealized_pl,
                    "unrealized_plpc": unrealized_plpc,
                }
            )

        return positions

    def list_open_orders(self) -> list[dict]:
        response = self.request_get(
            KIS_OPEN_ORDERS_PATH,
            tr_id=KIS_OPEN_ORDERS_TR_ID,
            params={
                "CANO": self.settings.kis_account_no,
                "ACNT_PRDT_CD": self.settings.kis_account_product_code,
                "INQR_DVSN_1": "1",
                "INQR_DVSN_2": "0",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )
        rows = _as_list(response.get("output"))
        orders = []

        for row in rows:
            item = _as_dict(row)
            qty = first_float(item, ["ord_qty"])
            unfilled_qty = first_float(item, ["psbl_qty", "rmn_qty"])
            price = first_float(item, ["ord_unpr"])
            side = _normalize_side(
                item.get("sll_buy_dvsn_cd") or item.get("sll_buy_dvsn_name")
            )
            orders.append(
                {
                    "order_id": item.get("odno") or item.get("order_id") or "",
                    "symbol": item.get("pdno") or "",
                    "name": item.get("prdt_name"),
                    "side": side,
                    "qty": qty,
                    "unfilled_qty": unfilled_qty,
                    "price": price,
                    "estimated_amount": unfilled_qty * price if price > 0 else None,
                    "status": "pending",
                    "submitted_at": _format_order_time(item.get("ord_tmd")),
                }
            )

        return orders

    def inquire_daily_order_executions(
        self,
        *,
        order_no: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        today = datetime.now(UTC).date()
        safe_end = end_date or today
        safe_start = start_date or safe_end
        response = self.request_get(
            KIS_DAILY_ORDER_EXECUTIONS_PATH,
            tr_id=self._daily_order_executions_tr_id(),
            params={
                "CANO": self.settings.kis_account_no,
                "ACNT_PRDT_CD": self.settings.kis_account_product_code,
                "INQR_STRT_DT": safe_start.strftime("%Y%m%d"),
                "INQR_END_DT": safe_end.strftime("%Y%m%d"),
                "SLL_BUY_DVSN_CD": "00",
                "INQR_DVSN": "00",
                "PDNO": "",
                "CCLD_DVSN": "00",
                "ORD_GNO_BRNO": "",
                "ODNO": str(order_no or "").strip(),
                "INQR_DVSN_3": "00",
                "INQR_DVSN_1": "",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )
        rows = _as_list(response.get("output1") or response.get("output"))
        return {
            "provider": "kis",
            "environment": self.settings.kis_env,
            "order_no": str(order_no or "").strip() or None,
            "start_date": safe_start.isoformat(),
            "end_date": safe_end.isoformat(),
            "count": len(rows),
            "orders": rows,
            "raw_status": "ok",
            "raw": _safe_raw(response),
        }

    def submit_order(self, *args, **kwargs):
        raise BrokerNotEnabledError(
            "KIS order submission is disabled. This connector is read-only here."
        )

    def submit_domestic_cash_order(
        self,
        *,
        symbol: str,
        side: str,
        qty: int,
        order_type: str = "market",
    ) -> dict:
        if not bool(getattr(self.settings, "kis_enabled", False)):
            raise BrokerNotEnabledError(
                "KIS domestic cash order submission requires KIS_ENABLED=true."
            )
        if not bool(getattr(self.settings, "kis_real_order_enabled", False)):
            raise BrokerNotEnabledError(
                "KIS domestic cash order submission requires "
                "KIS_REAL_ORDER_ENABLED=true."
            )
        payload = self.build_domestic_order_payload(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
        )
        return self._request_order(
            KIS_CASH_ORDER_PATH,
            tr_id=self.domestic_cash_order_tr_id(side),
            payload=payload,
        )

    def domestic_cash_order_tr_id(self, side: str) -> str:
        normalized_side = str(side or "").strip().lower()
        if normalized_side not in ("buy", "sell"):
            raise ValueError("KIS domestic cash order side must be buy or sell.")

        env = str(self.settings.kis_env or "").lower()
        is_demo = env in ("paper", "vps", "demo", "mock")
        if normalized_side == "buy":
            return KIS_CASH_BUY_TR_ID_DEMO if is_demo else KIS_CASH_BUY_TR_ID_REAL
        return KIS_CASH_SELL_TR_ID_DEMO if is_demo else KIS_CASH_SELL_TR_ID_REAL

    def build_domestic_order_payload(
        self,
        *,
        symbol: str,
        side: str,
        qty: int,
        order_type: str = "market",
        price: float | None = None,
    ) -> dict[str, str]:
        """Build a KIS domestic cash order payload without submitting it."""
        self.auth_manager.require_configured()

        normalized_order_type = str(order_type or "market").strip().lower()
        if normalized_order_type != "market":
            raise ValueError("Only market KIS domestic order previews are supported.")

        return {
            "CANO": str(self.settings.kis_account_no),
            "ACNT_PRDT_CD": str(self.settings.kis_account_product_code),
            "PDNO": str(symbol).strip(),
            "ORD_DVSN": KIS_MARKET_ORDER_DIVISION,
            "ORD_QTY": str(int(qty)),
            "ORD_UNPR": "0",
        }

    def _request_balance(self) -> dict:
        return self.request_get(
            KIS_BALANCE_PATH,
            tr_id=self._balance_tr_id(),
            params={
                "CANO": self.settings.kis_account_no,
                "ACNT_PRDT_CD": self.settings.kis_account_product_code,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        tr_id: str,
        params: dict | None = None,
        payload: dict | None = None,
    ) -> dict:
        return self._request_with_token_retry(
            method=method,
            path=path,
            tr_id=tr_id,
            params=params,
            payload=payload,
            request_kind="read_only",
        )

    def _request_order(
        self,
        path: str,
        *,
        tr_id: str,
        payload: dict | None = None,
    ) -> dict:
        return self._request_with_token_retry(
            method="POST",
            path=path,
            tr_id=tr_id,
            payload=payload,
            request_kind="order",
        )

    def _request_with_token_retry(
        self,
        method: str,
        path: str,
        *,
        tr_id: str,
        params: dict | None = None,
        payload: dict | None = None,
        request_kind: str = "read_only",
    ) -> dict:
        url = f"{str(self.settings.kis_base_url).rstrip('/')}{path}"
        context = self._request_diagnostics(
            method=method,
            path=path,
            tr_id=tr_id,
            params=params,
            payload=payload,
            request_kind=request_kind,
        )

        def send_request(access_token: str | None = None) -> tuple[dict, int]:
            headers = self.build_headers(
                tr_id=tr_id,
                include_auth=True,
                access_token=access_token,
            )
            try:
                if method == "GET":
                    response = requests.get(
                        url,
                        params=params or {},
                        headers=headers,
                        timeout=10,
                    )
                elif method == "POST":
                    response = requests.post(
                        url,
                        data=json.dumps(payload or {}),
                        headers=headers,
                        timeout=10,
                    )
                else:
                    raise ValueError(f"Unsupported KIS request method: {method}")
            except requests.RequestException as exc:
                details = {**context, "error_type": type(exc).__name__}
                raise KisApiError(
                    _format_kis_api_error(
                        "KIS read-only request failed" if request_kind == "read_only" else "KIS order request failed",
                        details,
                    ),
                    details=details,
                ) from exc

            try:
                data = response.json()
            except ValueError as exc:
                if response.status_code < 400:
                    details = {**context, "error_type": "invalid_json"}
                    raise KisApiError(
                        _format_kis_api_error(
                            "KIS read-only response was not valid JSON" if request_kind == "read_only" else "KIS order response was not valid JSON",
                            details,
                        ),
                        details=details,
                    ) from exc
                else:
                    # For HTTP errors, if can't parse JSON, raise with response_text
                    details = {
                        **context,
                        "http_status": response.status_code,
                        "response_text": response.text,
                        "error_type": "invalid_json_on_error",
                    }
                    raise KisApiError(
                        _format_kis_api_error(
                            "KIS read-only HTTP failure" if request_kind == "read_only" else "KIS order HTTP failure",
                            details,
                        ),
                        details=details,
                    )

            if not isinstance(data, dict):
                if response.status_code < 400:
                    details = {**context, "error_type": "unexpected_shape"}
                    raise KisApiError(
                        _format_kis_api_error(
                            "KIS read-only response had an unexpected shape" if request_kind == "read_only" else "KIS order response had an unexpected shape",
                            details,
                        ),
                        details=details,
                    )
                else:
                    # For HTTP errors, unexpected shape
                    details = {
                        **context,
                        "http_status": response.status_code,
                        "response_text": json.dumps(data),
                        "error_type": "unexpected_shape_on_error",
                    }
                    raise KisApiError(
                        _format_kis_api_error(
                            "KIS read-only HTTP failure" if request_kind == "read_only" else "KIS order HTTP failure",
                            details,
                        ),
                        details=details,
                    )

            return data, response.status_code

        response_data, status = send_request()
        if status >= 400:
            if self._is_token_expired_response(response_data):
                allowed, diagnostics = self._token_refresh_guard_diagnostics()
                if not allowed:
                    details = self._sanitize_diagnostics(
                        {
                            **context,
                            "http_status": status,
                            "rt_cd": response_data.get("rt_cd"),
                            "msg_cd": response_data.get("msg_cd"),
                            "msg1": response_data.get("msg1"),
                            **diagnostics,
                        }
                    )
                    raise KisApiError(
                        _format_kis_api_error(
                            "KIS token expired, but refresh is blocked by daily token issuance guard.",
                            details,
                        ),
                        details=details,
                    )

                refreshed_token = self.get_access_token(force_refresh=True)
                response_data, status = send_request(access_token=refreshed_token.token)
                if status >= 400 or self._is_token_expired_response(response_data):
                    details = self._sanitize_diagnostics(
                        {
                            **context,
                            "http_status": status,
                            "rt_cd": response_data.get("rt_cd"),
                            "msg_cd": response_data.get("msg_cd"),
                            "msg1": response_data.get("msg1"),
                            **diagnostics,
                        }
                    )
                    raise KisApiError(
                        _format_kis_api_error(
                            "KIS token refresh failed.",
                            details,
                        ),
                        details=details,
                    )
            else:
                details = {
                    **context,
                    "http_status": status,
                    "response_text": json.dumps(response_data),
                }
                raise KisApiError(
                    _format_kis_api_error(
                        "KIS read-only HTTP failure" if request_kind == "read_only" else "KIS order HTTP failure",
                        details,
                    ),
                    details=details,
                )

        if self._is_token_expired_response(response_data):
            allowed, diagnostics = self._token_refresh_guard_diagnostics()
            if not allowed:
                details = self._sanitize_diagnostics(
                    {
                        **context,
                        "rt_cd": response_data.get("rt_cd"),
                        "msg_cd": response_data.get("msg_cd"),
                        "msg1": response_data.get("msg1"),
                        **diagnostics,
                    }
                )
                raise KisApiError(
                    _format_kis_api_error(
                        "KIS token expired, but refresh is blocked by daily token issuance guard.",
                        details,
                    ),
                    details=details,
                )

            refreshed_token = self.get_access_token(force_refresh=True)
            response_data, status = send_request(access_token=refreshed_token.token)
            if status >= 400 or self._is_token_expired_response(response_data):
                details = self._sanitize_diagnostics(
                    {
                        **context,
                        "http_status": status,
                        "rt_cd": response_data.get("rt_cd"),
                        "msg_cd": response_data.get("msg_cd"),
                        "msg1": response_data.get("msg1"),
                        **diagnostics,
                    }
                )
                raise KisApiError(
                    _format_kis_api_error(
                        "KIS token refresh failed.",
                        details,
                    ),
                    details=details,
                )

        rt_cd = str(response_data.get("rt_cd", "0"))
        if rt_cd not in ("0", ""):
            details = {
                **context,
                "rt_cd": response_data.get("rt_cd"),
                "msg_cd": response_data.get("msg_cd"),
                "msg1": response_data.get("msg1"),
            }
            details = self._sanitize_diagnostics(details)
            raise KisApiError(
                _format_kis_api_error(
                    "KIS read-only API failed" if request_kind == "read_only" else "KIS order API failed",
                    details,
                ),
                details=details,
            )

        return response_data


    def _token_refresh_guard_diagnostics(self) -> tuple[bool, dict]:
        last_issued_at = self.auth_manager.get_latest_access_token_issue_time()
        min_interval = KIS_TOKEN_REFRESH_GUARD_DEFAULT
        now = datetime.now(UTC)

        if last_issued_at is None:
            return False, {
                "last_token_issued_at": None,
                "next_refresh_allowed_at": None,
                "refresh_guard_min_interval_seconds": int(min_interval.total_seconds()),
                "refresh_guard_reason": "missing_issue_timestamp",
            }

        next_allowed = last_issued_at + min_interval
        allowed = now >= next_allowed
        return allowed, {
            "last_token_issued_at": last_issued_at.isoformat(),
            "next_refresh_allowed_at": next_allowed.isoformat(),
            "refresh_guard_min_interval_seconds": int(min_interval.total_seconds()),
            "refresh_guard_reason": "allowed" if allowed else "too_recent",
        }
    def _is_token_expired_response(self, data: dict) -> bool:
        if not isinstance(data, dict):
            return False
        msg_cd = str(data.get("msg_cd") or "").strip()
        msg1 = str(data.get("msg1") or "").strip().lower()
        if msg_cd == "EGW00123":
            return True

        token_expired_signatures = [
            "기간이 만료된 token",
            "만료된 token",
            "token expired",
            "expired token",
            "토큰이 만료",
        ]
        return any(signature in msg1 for signature in token_expired_signatures)

    def _request_diagnostics(
        self,
        *,
        method: str,
        path: str,
        tr_id: str,
        params: dict | None = None,
        payload: dict | None = None,
        request_kind: str = "read_only",
    ) -> dict:
        env = str(self.settings.kis_env or "").strip() or "unknown"
        return self._sanitize_diagnostics(
            {
                "provider": "kis",
                "environment": env,
                "is_virtual": env.lower() in ("paper", "vps", "demo", "mock"),
                "request_kind": request_kind,
                "method": method,
                "path": path,
                "tr_id": tr_id,
                "params": params or {},
                "payload": payload or {},
            }
        )

    def _sanitize_diagnostics(self, value):
        return sanitize_kis_payload(
            value,
            known_secrets=_known_sensitive_values(self.settings),
        )

    def _balance_tr_id(self) -> str:
        env = str(self.settings.kis_env or "").lower()
        if env in ("paper", "vps", "demo", "mock"):
            return KIS_BALANCE_TR_ID_DEMO
        return KIS_BALANCE_TR_ID_REAL

    def _daily_order_executions_tr_id(self) -> str:
        env = str(self.settings.kis_env or "").lower()
        if env in ("paper", "vps", "demo", "mock"):
            return KIS_DAILY_ORDER_EXECUTIONS_TR_ID_DEMO
        return KIS_DAILY_ORDER_EXECUTIONS_TR_ID_REAL

    def _timestamp_from_output(self, output: dict) -> str | None:
        raw_time = output.get("stck_cntg_hour") or output.get("aspr_acpt_hour")
        if not raw_time:
            return datetime.now(UTC).isoformat()
        value = str(raw_time).zfill(6)
        return f"{value[0:2]}:{value[2:4]}:{value[4:6]}"


def to_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        text = str(value).strip().replace(",", "")
        if not text:
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def to_int(value, default: int = 0) -> int:
    return int(to_float(value, float(default)))


def normalize_percent(value) -> float:
    numeric = to_float(value)
    if abs(numeric) > 1:
        return numeric / 100
    return numeric


def normalize_domestic_daily_bars(
    symbol: str,
    rows: list,
    *,
    limit: int = 120,
) -> list[dict]:
    by_timestamp: dict[str, dict] = {}
    for row in rows or []:
        item = _as_dict(row)
        timestamp = _normalize_kis_date(
            first_present(item, ["stck_bsop_date", "bsop_date", "date", "timestamp"])
        )
        if not timestamp:
            continue

        open_price = first_float(item, ["stck_oprc", "oprc", "open"])
        high = first_float(item, ["stck_hgpr", "hgpr", "high"])
        low = first_float(item, ["stck_lwpr", "lwpr", "low"])
        close = first_float(item, ["stck_clpr", "clpr", "close"])
        volume = first_float(item, ["acml_vol", "cntg_vol", "volume"])

        if open_price <= 0 or high <= 0 or low <= 0 or close <= 0:
            continue

        by_timestamp[timestamp] = {
            "symbol": str(symbol).strip(),
            "timestamp": timestamp,
            "open": float(open_price),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(max(volume, 0.0)),
        }

    sorted_bars = [by_timestamp[key] for key in sorted(by_timestamp)]
    safe_limit = max(1, int(limit or 120))
    return sorted_bars[-safe_limit:]


def _normalize_kis_date(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
    return text


def first_present(item: dict, keys: list[str]):
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def first_float(item: dict, keys: list[str], default: float = 0.0) -> float:
    value = first_present(item, keys)
    return to_float(value, default)


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _first_dict(value) -> dict:
    rows = _as_list(value)
    return _as_dict(rows[0]) if rows else {}


def _safe_raw(response: dict) -> dict:
    return {
        "rt_cd": response.get("rt_cd"),
        "msg_cd": response.get("msg_cd"),
        "has_output": bool(response.get("output")),
    }


def _format_kis_api_error(prefix: str, details: dict) -> str:
    parts = []
    for key in ("msg_cd", "msg1", "rt_cd", "http_status", "tr_id", "path"):
        value = details.get(key)
        if value is not None and str(value).strip():
            parts.append(f"{key}={value}")
    return f"{prefix}: {', '.join(parts)}" if parts else prefix


def _mask_account_value(value) -> str | None:
    return mask_kis_account_value(value)


def _redact_sensitive_text(value: str, settings) -> str:
    return sanitize_kis_text(
        value,
        known_secrets=_known_sensitive_values(settings),
    )


def _known_sensitive_values(settings) -> list:
    return [
        getattr(settings, "kis_app_key", None),
        getattr(settings, "kis_app_secret", None),
        getattr(settings, "kis_access_token", None),
        getattr(settings, "kis_approval_key", None),
        getattr(settings, "kis_account_no", None),
    ]


def _normalize_side(value) -> str:
    text = str(value or "").strip().lower()
    if text in ("02", "buy", "매수") or "매수" in text:
        return "buy"
    if text in ("01", "sell", "매도") or "매도" in text:
        return "sell"
    return text or "unknown"


def _format_order_time(value) -> str | None:
    if not value:
        return None
    text = str(value).strip().zfill(6)
    if len(text) < 6:
        return str(value)
    return f"{text[0:2]}:{text[2:4]}:{text[4:6]}"
