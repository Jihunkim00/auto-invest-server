from __future__ import annotations

import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import requests

from app.brokers.kis_auth_manager import KisAuthManager
from app.services.kis_corporate_event_service import dividend_events
from app.services.kis_stop_loss_aware_feature_service import KST, MINUTE, number, timestamp

_activity_lock = threading.Lock()
_last_production_request = float("-inf")
_last_shadow_request = float("-inf")
_production_inflight = 0


@contextmanager
def production_kis_request():
    global _last_production_request, _production_inflight
    with _activity_lock:
        _last_production_request = time.perf_counter()
        _production_inflight += 1
    try:
        yield
    finally:
        with _activity_lock:
            _production_inflight -= 1


def load_sector_mapping(directory, decision):
    """Read the dated, operator-supplied official KIS stock master files."""
    if not directory:
        return {}
    mapping = {}
    for name, width, broad_code in (("kospi_code.mst", 227, "0001"), ("kosdaq_code.mst", 221, "1001")):
        path = Path(directory) / decision.date().isoformat() / name
        try:
            # The date directory records the master date; mtime additionally
            # prevents a current export from being imported into old replays.
            if (path.stat().st_mtime > decision.timestamp() or path.stat().st_size > 10_000_000):
                continue
            with path.open(encoding="cp949") as source:
                for row in source:
                    line = row.rstrip("\r\n")
                    if len(line) < width + 21:
                        continue
                    symbol, sector = line[:9].strip(), line[-width + 3:-width + 7]
                    if re.fullmatch(r"[0-9]{6}", symbol) and re.fullmatch(r"[0-9]{4}", sector) and sector != "0000":
                        mapping[symbol] = (sector, broad_code)
        except (OSError, UnicodeError):
            continue
    return mapping


class KisShadowMarketData:
    """A best-effort, fixed-endpoint market-data reader using existing tokens."""

    def __init__(self, settings, session_factory, capacity):
        self.settings = settings
        self.session_factory = session_factory
        self.capacity = capacity

    def _get(self, path, tr_id, params, deadline):
        global _last_shadow_request
        if not (self.settings.kis_enabled and self.settings.kis_base_url):
            return None, 0
        if not self.capacity.acquire(blocking=False):
            return None, 0
        try:
            with self.session_factory() as db:
                token = KisAuthManager(self.settings, db).get_cached_access_token()
            if not token:
                return None, 0
            with _activity_lock:
                now = time.perf_counter()
                spacing = max(2.0, 2 * self.settings.kis_read_only_min_interval_seconds)
                if (_production_inflight or deadline <= now
                        or now - max(_last_production_request, _last_shadow_request) < spacing):
                    return None, 0
                _last_shadow_request = now
            response = requests.get(
                str(self.settings.kis_base_url).rstrip("/") + path,
                params=params, headers={
                    "authorization": f"Bearer {token}", "appkey": self.settings.kis_app_key,
                    "appsecret": self.settings.kis_app_secret, "tr_id": tr_id, "custtype": "P",
                },
                timeout=min(3.0, max(0.1, (deadline - time.perf_counter()) / 2)),
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or data.get("rt_cd") != "0" or response.headers.get("tr_cont") == "M":
                return None, 1
            return data, 1
        except (ValueError, requests.RequestException):
            return None, 1
        finally:
            self.capacity.release()

    def dividend(self, symbol, start, end, deadline):
        payload, count = self._get("/uapi/domestic-stock/v1/ksdinfo/dividend", "HHKDB669102C0", {
            "CTS": "", "GB1": "0", "F_DT": start.strftime("%Y%m%d"), "T_DT": end.strftime("%Y%m%d"),
            "SHT_CD": symbol, "HIGH_GB": "",
        }, deadline)
        seen = datetime.now(KST)
        return (seen, dividend_events(payload, symbol, seen) if payload else None), count

    def sector(self, code, decision, deadline):
        if not re.fullmatch(r"[0-9]{4}", code):
            return None, 0
        payload, count = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-time-indexchartprice", "FHKUP03500200",
            {"FID_COND_MRKT_DIV_CODE": "U", "FID_ETC_CLS_CODE": "1", "FID_INPUT_ISCD": code,
             "FID_INPUT_HOUR_1": "60", "FID_PW_DATA_INCU_YN": "N"}, deadline,
        )
        rows = {}
        for row in (payload or {}).get("output2", []):
            day, clock = str(row.get("stck_bsop_date")), str(row.get("stck_cntg_hour")).zfill(6)
            at = timestamp(f"{day[:4]}-{day[4:6]}-{day[6:]}T{clock[:2]}:{clock[2:4]}:{clock[4:]}")
            price = number(row.get("bstp_nmix_prpr"))
            if at and at.date() == decision.date() and not at.second and at + MINUTE <= decision and price and price > 0:
                rows[at] = price
        return (datetime.now(KST), rows) if rows else None, count

    def execution_strength(self, symbol, decision, deadline):
        if datetime.now(KST).date() != decision.date():
            return None, 0
        payload, count = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemconclusion", "FHPST01060000",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol,
             "FID_INPUT_HOUR_1": decision.strftime("%H%M%S")}, deadline,
        )
        ticks = []
        for row in (payload or {}).get("output2", []):
            clock = str(row.get("stck_cntg_hour") or "").zfill(6)
            at = timestamp(f"{decision.date()}T{clock[:2]}:{clock[2:4]}:{clock[4:]}")
            strength = number(row.get("tday_rltv"))
            if at and decision - timedelta(minutes=5) <= at <= decision and strength is not None:
                ticks.append((at, strength, number(row.get("bidp")), number(row.get("askp"))))
        if not ticks:
            return None, count
        ticks.sort(key=lambda tick: tick[0])
        at, latest, bid, ask = ticks[-1]
        return {"value": latest, "change": latest - ticks[0][1] if len(ticks) > 1 else None,
                "bid": bid, "ask": ask, "as_of": at.isoformat(),
                "retrieved_at": datetime.now(KST).isoformat()}, count
