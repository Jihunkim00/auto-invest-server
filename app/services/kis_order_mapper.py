from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.enums import InternalOrderStatus


@dataclass(frozen=True)
class KisMappedOrderStatus:
    order_no: str | None
    original_order_no: str | None
    requested_qty: float
    filled_qty: float
    remaining_qty: float
    avg_fill_price: float | None
    broker_order_status: str
    internal_status: str
    raw_payload: dict[str, Any]


def find_kis_order_row(rows: list[dict[str, Any]], order_no: str) -> dict[str, Any] | None:
    target = _normalize_order_no(order_no)
    if not target:
        return None

    target_unpadded = target.lstrip("0") or target
    for row in rows:
        item = _as_dict(row)
        candidate = _normalize_order_no(
            first_present(
                item,
                [
                    "ODNO",
                    "odno",
                    "ord_no",
                    "ORD_NO",
                    "order_no",
                    "order_id",
                    "broker_order_id",
                ],
            )
        )
        if not candidate:
            continue
        if candidate == target or (candidate.lstrip("0") or candidate) == target_unpadded:
            return item
    return None


def map_kis_order_row(
    row: dict[str, Any],
    *,
    requested_qty_fallback: float | None = None,
) -> KisMappedOrderStatus:
    item = _as_dict(row)
    requested_qty = first_float(
        item,
        [
            "ord_qty",
            "ORD_QTY",
            "order_qty",
            "qty",
            "requested_qty",
        ],
        default=float(requested_qty_fallback or 0),
    )
    filled_qty = first_float(
        item,
        [
            "tot_ccld_qty",
            "TOT_CCLD_QTY",
            "ccld_qty",
            "filled_qty",
            "exec_qty",
        ],
    )
    remaining_qty = first_float(
        item,
        [
            "rmn_qty",
            "RMN_QTY",
            "unccld_qty",
            "unfilled_qty",
            "psbl_qty",
            "remaining_qty",
        ],
        default=max(requested_qty - filled_qty, 0),
    )
    avg_fill_price = first_float_or_none(
        item,
        [
            "avg_prvs",
            "AVG_PRVS",
            "avg_ccld_prc",
            "ccld_avg_pric",
            "filled_avg_price",
            "avg_fill_price",
        ],
    )
    if filled_qty <= 0:
        avg_fill_price = None

    broker_order_status = _derive_broker_order_status(
        item,
        requested_qty=requested_qty,
        filled_qty=filled_qty,
        remaining_qty=remaining_qty,
    )
    internal_status = _derive_internal_status(
        item,
        requested_qty=requested_qty,
        filled_qty=filled_qty,
        remaining_qty=remaining_qty,
    )

    return KisMappedOrderStatus(
        order_no=_normalize_order_no(
            first_present(item, ["ODNO", "odno", "ord_no", "ORD_NO", "order_no"])
        ),
        original_order_no=_normalize_order_no(
            first_present(item, ["ORGN_ODNO", "orgn_odno", "orgn_ord_no"])
        ),
        requested_qty=float(requested_qty),
        filled_qty=float(filled_qty),
        remaining_qty=float(max(remaining_qty, 0)),
        avg_fill_price=avg_fill_price,
        broker_order_status=broker_order_status,
        internal_status=internal_status,
        raw_payload=item,
    )


def stale_kis_order_status(order_no: str, raw_payload: dict[str, Any]) -> KisMappedOrderStatus:
    return KisMappedOrderStatus(
        order_no=_normalize_order_no(order_no),
        original_order_no=None,
        requested_qty=0,
        filled_qty=0,
        remaining_qty=0,
        avg_fill_price=None,
        broker_order_status="not_found_in_inquiry",
        internal_status=InternalOrderStatus.UNKNOWN_STALE.value,
        raw_payload=raw_payload,
    )


def first_present(item: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def first_float(item: dict[str, Any], keys: list[str], default: float = 0.0) -> float:
    value = first_present(item, keys)
    parsed = _to_float(value)
    return default if parsed is None else parsed


def first_float_or_none(item: dict[str, Any], keys: list[str]) -> float | None:
    value = first_present(item, keys)
    parsed = _to_float(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _derive_internal_status(
    item: dict[str, Any],
    *,
    requested_qty: float,
    filled_qty: float,
    remaining_qty: float,
) -> str:
    status_text = _status_text(item)
    if _is_rejected(item, status_text):
        return InternalOrderStatus.REJECTED.value
    if filled_qty >= requested_qty > 0:
        return InternalOrderStatus.FILLED.value
    if _is_cancelled(item, status_text):
        return InternalOrderStatus.CANCELED.value
    if 0 < filled_qty < requested_qty:
        return InternalOrderStatus.PARTIALLY_FILLED.value
    if requested_qty > 0 and remaining_qty <= 0 and filled_qty <= 0 and "cancel" in status_text:
        return InternalOrderStatus.CANCELED.value
    return InternalOrderStatus.ACCEPTED.value


def _derive_broker_order_status(
    item: dict[str, Any],
    *,
    requested_qty: float,
    filled_qty: float,
    remaining_qty: float,
) -> str:
    explicit = first_present(
        item,
        [
            "ordr_stat_name",
            "ord_stts_name",
            "ord_status",
            "status",
            "ccld_cndt_name",
            "ccld_dvsn_name",
        ],
    )
    if explicit:
        return str(explicit).strip()
    internal = _derive_internal_status(
        item,
        requested_qty=requested_qty,
        filled_qty=filled_qty,
        remaining_qty=remaining_qty,
    )
    return internal.lower()


def _is_cancelled(item: dict[str, Any], status_text: str) -> bool:
    cancel_flag = str(first_present(item, ["cncl_yn", "cancel_yn"]) or "").strip().upper()
    cancel_qty = first_float(item, ["cncl_cfrm_qty", "cancel_qty"])
    return (
        cancel_flag == "Y"
        or cancel_qty > 0
        or "cancel" in status_text
        or "\ucde8\uc18c" in status_text
    )


def _is_rejected(item: dict[str, Any], status_text: str) -> bool:
    reject_qty = first_float(item, ["rjct_qty", "reject_qty"])
    reject_reason = first_present(item, ["rjct_rson", "rjct_rson_name", "reject_reason"])
    return (
        reject_qty > 0
        or reject_reason is not None
        or "reject" in status_text
        or "\uac70\ubd80" in status_text
    )


def _status_text(item: dict[str, Any]) -> str:
    values = [
        first_present(
            item,
            [
                "ordr_stat_name",
                "ord_stts_name",
                "ord_status",
                "status",
                "ccld_cndt_name",
                "ccld_dvsn_name",
                "rjct_rson_name",
            ],
        )
    ]
    return " ".join(str(value).strip().lower() for value in values if value is not None)


def _normalize_order_no(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
