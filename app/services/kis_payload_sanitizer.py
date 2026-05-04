from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

REDACTED = "***REDACTED***"
SECRET_REDACTED = "***"

TRADING_CRITICAL_KEYS = {
    "ord_dt",
    "odno",
    "orgn_odno",
    "ord_dvsn_name",
    "sll_buy_dvsn_cd",
    "sll_buy_dvsn_cd_name",
    "pdno",
    "prdt_name",
    "ord_qty",
    "tot_ccld_qty",
    "avg_prvs",
    "tot_ccld_amt",
    "rmn_qty",
    "rjct_qty",
    "cncl_yn",
    "excg_id_dvsn_cd",
}

DATE_AND_CONTEXT_KEYS = {
    "inqr_strt_dt",
    "inqr_end_dt",
    "start_date",
    "end_date",
    "ord_dt",
    "stck_bsop_date",
}

PERSONAL_FIELD_KEYS = {
    "ctac_tlno",
    "inqr_ip_addr",
    "ip_addr",
    "client_ip",
    "remote_ip",
}

ACCOUNT_FIELD_KEYS = {
    "cano",
    "account",
    "account_no",
    "account_number",
    "kis_account_no",
}

ACCOUNT_PRODUCT_KEYS = {"acnt_prdt_cd"}
SECRET_KEY_TOKENS = ("token", "secret", "key", "auth", "password")

PHONE_RE = re.compile(
    r"\b(?:01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}|0\d{1,2}[-\s.]\d{3,4}[-\s.]\d{4})\b"
)
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
BEARER_RE = re.compile(r"Bearer\s+[^\s,]+", re.IGNORECASE)
SECRET_VALUE_RE = re.compile(r"secret-[A-Za-z0-9_.-]+", re.IGNORECASE)
ASSIGNMENT_SECRET_RE = re.compile(
    r"\b(appsecret|appkey|access_token|approval_key|authorization|password)\s*[:=]\s*[^,\s]+",
    re.IGNORECASE,
)
ACCOUNT_CONTEXT_RE = re.compile(
    r"\b(account(?:\s+(?:no|number))?\s*[:=]?\s*)(\d{6,16})\b",
    re.IGNORECASE,
)


def sanitize_kis_payload(
    value: Any,
    *,
    key: str | None = None,
    known_secrets: Iterable[Any] | None = None,
) -> Any:
    normalized_key = _normalize_key(key)
    if _is_personal_key(normalized_key):
        return REDACTED if value is not None else None
    if _is_secret_key(normalized_key):
        return SECRET_REDACTED if value is not None else None
    if _is_account_key(normalized_key):
        return mask_kis_account_value(value)
    if normalized_key in ACCOUNT_PRODUCT_KEYS:
        return REDACTED if value is not None else None

    if isinstance(value, dict):
        return {
            item_key: sanitize_kis_payload(
                item,
                key=str(item_key),
                known_secrets=known_secrets,
            )
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [
            sanitize_kis_payload(item, key=key, known_secrets=known_secrets)
            for item in value
        ]

    if isinstance(value, str):
        return sanitize_kis_text(value, key=key, known_secrets=known_secrets)
    return value


def sanitize_kis_text(
    value: str,
    *,
    key: str | None = None,
    known_secrets: Iterable[Any] | None = None,
) -> str:
    normalized_key = _normalize_key(key)
    if _is_personal_key(normalized_key):
        return REDACTED
    if _is_secret_key(normalized_key):
        return SECRET_REDACTED
    if _is_account_key(normalized_key):
        return mask_kis_account_value(value) or ""
    if normalized_key in ACCOUNT_PRODUCT_KEYS:
        return REDACTED

    text = str(value)
    for secret in _clean_known_secrets(known_secrets):
        text = text.replace(secret, SECRET_REDACTED)
    text = BEARER_RE.sub("Bearer ***", text)
    text = SECRET_VALUE_RE.sub(SECRET_REDACTED, text)
    text = ASSIGNMENT_SECRET_RE.sub(
        lambda match: f"{match.group(1)}={SECRET_REDACTED}",
        text,
    )

    if normalized_key not in TRADING_CRITICAL_KEYS:
        text = PHONE_RE.sub(REDACTED, text)
        text = IPV4_RE.sub(REDACTED, text)
        text = ACCOUNT_CONTEXT_RE.sub(
            lambda match: f"{match.group(1)}{mask_kis_account_value(match.group(2))}",
            text,
        )
    return text


def mask_kis_account_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return ""
    if len(text) <= 4:
        return "*" * len(text)
    return f"{text[:2]}{'*' * (len(text) - 4)}{text[-2:]}"


def _normalize_key(key: str | None) -> str:
    return str(key or "").strip().lower()


def _is_personal_key(key: str) -> bool:
    return (
        key in PERSONAL_FIELD_KEYS
        or key.endswith("_ip")
        or "ip_addr" in key
        or "phone" in key
        or "tel" in key
        or "tlno" in key
        or "mobile" in key
    )


def _is_secret_key(key: str) -> bool:
    return any(token in key for token in SECRET_KEY_TOKENS)


def _is_account_key(key: str) -> bool:
    return key in ACCOUNT_FIELD_KEYS or "account" in key


def _clean_known_secrets(known_secrets: Iterable[Any] | None) -> list[str]:
    values = []
    for item in known_secrets or []:
        if item is None:
            continue
        text = str(item)
        if len(text.strip()) >= 4:
            values.append(text)
    return values
