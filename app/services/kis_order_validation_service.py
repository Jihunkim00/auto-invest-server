from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.brokers.factory import mask_account_no
from app.brokers.kis_client import KisClient, to_float
from app.services.market_profile_service import MarketProfileService
from app.services.market_session_service import MarketSessionService


class KisOrderValidationError(ValueError):
    """Raised when a KIS dry-run order request is structurally unsafe."""


class KisOrderValidationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    market: str = Field(default="KR", examples=["KR"])
    symbol: str = Field(examples=["005930"])
    side: str = Field(examples=["buy"])
    qty: int = Field(gt=0, examples=[1])
    order_type: str = Field(default="market", examples=["market"])
    dry_run: bool = Field(default=True)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("market")
    @classmethod
    def validate_market(cls, value: str) -> str:
        normalized = str(value or "").strip().upper()
        if normalized != "KR":
            raise ValueError("KIS order validation only supports market=KR.")
        return normalized

    @field_validator("side")
    @classmethod
    def validate_side(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in ("buy", "sell"):
            raise ValueError("KIS order side must be buy or sell.")
        return normalized

    @field_validator("order_type")
    @classmethod
    def normalize_order_type(cls, value: str) -> str:
        return str(value or "market").strip().lower()


@dataclass(frozen=True)
class KisOrderPreview:
    account_no_masked: str | None
    product_code: str
    symbol: str
    side: str
    qty: int
    order_type: str
    kis_tr_id_preview: str
    payload_preview: dict[str, str | None]


@dataclass(frozen=True)
class KisOrderValidationResult:
    provider: str
    market: str
    environment: str
    dry_run: bool
    validated_for_submission: bool
    can_submit_later: bool
    symbol: str
    side: str
    qty: int
    order_type: str
    current_price: float | None
    estimated_amount: float | None
    available_cash: float | None
    held_qty: float | None
    warnings: list[str]
    block_reasons: list[str]
    market_session: dict
    order_preview: KisOrderPreview

    def to_dict(self) -> dict:
        return asdict(self)


class KisOrderValidationService:
    def __init__(
        self,
        client: KisClient,
        *,
        profile_service: MarketProfileService | None = None,
        session_service: MarketSessionService | None = None,
    ):
        self.client = client
        self.profile_service = profile_service or MarketProfileService()
        self.session_service = session_service or MarketSessionService()

    def validate(
        self,
        request: KisOrderValidationRequest,
        *,
        now: datetime | None = None,
    ) -> KisOrderValidationResult:
        if request.dry_run is not True:
            raise KisOrderValidationError(
                "KIS order validation is dry-run only; dry_run must be true."
            )
        if request.order_type != "market":
            raise KisOrderValidationError(
                "Only market KIS dry-run order validation is supported."
            )

        symbol = self.profile_service.normalize_symbol(request.symbol, request.market)
        self.client.auth_manager.require_configured()

        warnings: list[str] = []
        block_reasons: list[str] = []
        available_cash: float | None = None
        held_qty: float | None = None

        market_session = self.session_service.get_session_status(request.market, now=now)
        if not market_session["is_market_open"]:
            warnings.append("market_closed")
            block_reasons.append("market_closed")
            closure_reason = market_session.get("closure_reason")
            if closure_reason:
                warnings.append(f"market_closed_{closure_reason}")
        if request.side == "buy" and not market_session["is_entry_allowed_now"]:
            warnings.append("after_no_new_entry_time")
            block_reasons.append("after_no_new_entry_time")
        if market_session["is_near_close"]:
            warnings.append("near_close")

        price_info = self.client.get_domestic_stock_price(symbol)
        current_price = _optional_float(price_info.get("current_price"))
        if current_price is None or current_price <= 0:
            current_price = None
            warnings.append("current_price_unavailable")
            block_reasons.append("current_price_unavailable")

        estimated_amount = (
            request.qty * current_price if current_price is not None else None
        )

        if request.side == "buy":
            balance = self.client.get_account_balance()
            available_cash = _optional_float(balance.get("cash"))
            if available_cash is None:
                warnings.append("available_cash_unavailable")
                block_reasons.append("available_cash_unavailable")
            elif estimated_amount is not None and available_cash < estimated_amount:
                block_reasons.append("insufficient_cash")

        if request.side == "sell":
            positions = self.client.list_positions()
            match = _find_position(positions, symbol)
            if match is None:
                held_qty = 0.0
                block_reasons.append("no_position_for_symbol")
            else:
                held_qty = to_float(match.get("qty"))
                if held_qty < request.qty:
                    block_reasons.append("insufficient_holdings")

        preview = self._build_preview(
            symbol=symbol,
            side=request.side,
            qty=request.qty,
            order_type=request.order_type,
        )
        validated = len(block_reasons) == 0

        return KisOrderValidationResult(
            provider="kis",
            market=request.market,
            environment=self.client.settings.kis_env,
            dry_run=True,
            validated_for_submission=validated,
            can_submit_later=validated,
            symbol=symbol,
            side=request.side,
            qty=request.qty,
            order_type=request.order_type,
            current_price=current_price,
            estimated_amount=estimated_amount,
            available_cash=available_cash,
            held_qty=held_qty,
            warnings=_dedupe(warnings),
            block_reasons=_dedupe(block_reasons),
            market_session=_public_market_session(market_session),
            order_preview=preview,
        )

    def _build_preview(
        self,
        *,
        symbol: str,
        side: str,
        qty: int,
        order_type: str,
    ) -> KisOrderPreview:
        payload = self.client.build_domestic_order_payload(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
        )
        payload_preview = dict(payload)
        payload_preview["CANO"] = mask_account_no(payload.get("CANO"))
        return KisOrderPreview(
            account_no_masked=mask_account_no(self.client.settings.kis_account_no),
            product_code=str(self.client.settings.kis_account_product_code),
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            kis_tr_id_preview=self.client.domestic_cash_order_tr_id(side),
            payload_preview=payload_preview,
        )


def _optional_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return to_float(value)


def _find_position(positions: list[dict], symbol: str) -> dict | None:
    for position in positions:
        if str(position.get("symbol") or "").strip() == symbol:
            return position
    return None


def _dedupe(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _public_market_session(market_session: dict) -> dict:
    keys = [
        "market",
        "timezone",
        "is_market_open",
        "is_entry_allowed_now",
        "is_near_close",
        "closure_reason",
        "closure_name",
        "regular_open",
        "regular_close",
        "effective_close",
        "no_new_entry_after",
    ]
    return {key: market_session.get(key) for key in keys}
