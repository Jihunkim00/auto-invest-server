from __future__ import annotations

import json
from datetime import UTC, datetime

import requests

from app.brokers.base import BrokerNotEnabledError, KisApiError
from app.brokers.kis_auth_manager import KisAuthManager
from app.config import get_settings

# Official sample references:
# - examples_llm/domestic_stock/inquire_price/inquire_price.py
# - examples_llm/domestic_stock/inquire_balance/inquire_balance.py
# - examples_llm/domestic_stock/inquire_psbl_rvsecncl/inquire_psbl_rvsecncl.py
KIS_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
KIS_PRICE_TR_ID = "FHKST01010100"
KIS_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
KIS_BALANCE_TR_ID_REAL = "TTTC8434R"
KIS_BALANCE_TR_ID_DEMO = "VTTC8434R"
KIS_OPEN_ORDERS_PATH = "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
KIS_OPEN_ORDERS_TR_ID = "TTTC0084R"
KIS_CASH_ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
KIS_CASH_BUY_TR_ID_REAL = "TTTC0802U"
KIS_CASH_SELL_TR_ID_REAL = "TTTC0801U"
KIS_CASH_BUY_TR_ID_DEMO = "VTTC0802U"
KIS_CASH_SELL_TR_ID_DEMO = "VTTC0801U"
KIS_MARKET_ORDER_DIVISION = "01"


class KisClient:
    """Safe KIS Open API client for auth and read-only data.

    This class can query read-only market/account endpoints, but still does not
    submit, modify, or cancel orders.
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
            token = self.get_access_token()
            headers["authorization"] = f"Bearer {token.token}"
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

    def submit_order(self, *args, **kwargs):
        raise BrokerNotEnabledError(
            "KIS order submission is disabled. This connector is read-only here."
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
        url = f"{str(self.settings.kis_base_url).rstrip('/')}{path}"
        headers = self.build_headers(tr_id=tr_id, include_auth=True)

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
            raise KisApiError(f"KIS read-only request failed: {type(exc).__name__}.") from exc

        if response.status_code >= 400:
            raise KisApiError(
                f"KIS read-only request failed with HTTP {response.status_code}."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise KisApiError("KIS read-only response was not valid JSON.") from exc

        if not isinstance(data, dict):
            raise KisApiError("KIS read-only response had an unexpected shape.")

        rt_cd = str(data.get("rt_cd", "0"))
        if rt_cd not in ("0", ""):
            code = data.get("msg_cd") or rt_cd
            raise KisApiError(f"KIS read-only API returned error code {code}.")

        return data

    def _balance_tr_id(self) -> str:
        env = str(self.settings.kis_env or "").lower()
        if env in ("paper", "vps", "demo", "mock"):
            return KIS_BALANCE_TR_ID_DEMO
        return KIS_BALANCE_TR_ID_REAL

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
